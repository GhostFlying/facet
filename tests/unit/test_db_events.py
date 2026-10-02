"""Actual file-backed event membership, resolution jobs and classification."""

from dataclasses import replace
from datetime import timedelta

import pytest
from test_db_history import page, poll, start
from test_db_repositories import T, admit, job, publish, view
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
    Count,
    ErrorCode,
    Generation,
    LabelChange,
    ProviderId,
    Revision,
    Sha256Hex,
    SourceEvent,
    Timestamp,
)
from facet.contracts.records import (
    JobSubjectProjectMessage,
    JobSubjectResolveEvent,
    SourceEventKeyLabelChanged,
    SourceEventKeyMessageAdded,
    SourceEventKeyMessageDeleted,
)
from facet.db.codecs import EventProcessing, StorageFailure
from facet.db.keys import event_key
from facet.db.models import RevisionGuard, SourceEventRow
from facet.db.repositories import events, history, reads


def event(n=1, *, thread=None, tag="message_added", change=LabelChange.ADDED):
    args = (tag, P, ProviderId(f"history-{n}"), ProviderId(f"msg-{n}"))
    if tag == "label_changed":
        key = SourceEventKeyLabelChanged(*args, ProviderId("synthetic-label"), change)
    elif tag == "message_deleted":
        key = SourceEventKeyMessageDeleted(*args)
    else:
        key = SourceEventKeyMessageAdded(*args)
    return SourceEventRow(
        P,
        lid(n),
        event_key(P, key),
        SourceEvent(key, NOW, thread),
        EventProcessing.PENDING,
        Revision(0),
        None,
    )


def resolution(row, n=None):
    return job(
        10000 + int(row.event_id.value[-6:], 16) if n is None else n,
        subject=JobSubjectResolveEvent("resolve_event", row.event.key),
    )


def setup(session, *, count=1):
    value = start(session)
    response = page(value, count=count)
    with session.transaction() as uow:
        history.begin_history_page(uow, P, response, RevisionGuard(Revision(0)))
    return value, response


def ingest(session, value, response, rows, jobs=None):
    if jobs is None:
        jobs = tuple(resolution(row) for row in rows)
    with session.transaction() as uow:
        events.ingest_history_chunk(
            uow,
            P,
            value.poll_id,
            response.ordinal,
            rows,
            jobs,
            RevisionGuard(Revision(0)),
        )


def test_split_large_history_page_preserves_all_distinct_events_and_resolution_jobs(
    state,
):
    _, connection, session, _ = state
    value, response = setup(session, count=601)
    selected = tuple(event(n) for n in range(1, 602))
    ingest(session, value, response, selected[:500])
    with pytest.raises(StorageFailure), session.transaction() as uow:
        history.finish_history_page(
            uow,
            P,
            value.poll_id,
            Count(1),
            response.metadata_digest,
            RevisionGuard(Revision(0)),
        )
    ingest(session, value, response, selected[500:])
    # Replaying an entire chunk preserves the first allocated IDs/work.
    ingest(session, value, response, selected[:500])
    with session.transaction() as uow:
        history.finish_history_page(
            uow,
            P,
            value.poll_id,
            Count(1),
            response.metadata_digest,
            RevisionGuard(Revision(0)),
        )
        history.finish_history_poll(
            uow,
            P,
            value.poll_id,
            response.response_history_id,
            RevisionGuard(Revision(1)),
        )
    assert connection.execute("SELECT COUNT(*) FROM source_events").fetchone() == (601,)
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (601,)
    assert connection.execute(
        "SELECT COUNT(*) FROM history_page_events"
    ).fetchone() == (601,)
    assert connection.execute("SELECT cursor FROM history_checkpoints").fetchone() == (
        response.response_history_id.value,
    )


@pytest.mark.parametrize(
    "bad",
    [
        "missing_job",
        "wrong_event_job",
        "wrong_kind",
        "wrong_epoch",
        "oversize",
        "overcount",
    ],
)
def test_chunk_refusal_rolls_back_event_membership_and_jobs(state, bad):
    _, connection, session, _ = state
    value, response = setup(session, count=0 if bad == "overcount" else 1)
    row = event()
    rows, work = (row,), (resolution(row),)
    if bad == "missing_job":
        work = ()
    elif bad == "wrong_event_job":
        work = (resolution(event(2)),)
    elif bad == "wrong_kind":
        work = (job(100),)
    elif bad == "wrong_epoch":
        work = (replace(resolution(row), origin_epoch_id=lid(999)),)
    elif bad == "oversize":
        rows = (row,) * 501
    with pytest.raises(StorageFailure):
        ingest(session, value, response, rows, work)
    for table in ["source_events", "sync_jobs", "history_page_events"]:
        assert connection.execute("SELECT COUNT(*) FROM " + table).fetchone() == (0,)
    assert connection.execute("SELECT complete FROM history_pages").fetchone() == (0,)


def test_added_deleted_and_label_add_remove_are_distinct_activation_keys(state):
    _, connection, session, _ = state
    value, response = setup(session, count=4)
    added, deleted = event(1), event(2, tag="message_deleted")
    deleted = replace(
        deleted,
        event=replace(
            deleted.event,
            key=replace(
                deleted.event.key,
                history_record_id=added.event.key.history_record_id,
                source_message_id=added.event.key.source_message_id,
            ),
        ),
        event_key=event_key(
            P,
            SourceEventKeyMessageDeleted(
                "message_deleted",
                P,
                added.event.key.history_record_id,
                added.event.key.source_message_id,
            ),
        ),
    )
    labeled = event(3, tag="label_changed")
    removed_key = replace(labeled.event.key, change=LabelChange.REMOVED)
    removed = replace(
        labeled,
        event_id=lid(4),
        event_key=event_key(P, removed_key),
        event=replace(labeled.event, key=removed_key),
    )
    ingest(session, value, response, (added, deleted, labeled, removed))
    assert connection.execute("SELECT COUNT(*) FROM source_events").fetchone() == (4,)
    assert connection.execute(
        "SELECT COUNT(DISTINCT event_key) FROM source_events"
    ).fetchone() == (4,)


def test_cross_poll_reobservation_and_late_thread_enrichment_preserve_page_snapshot(
    state,
):
    _, connection, session, _ = state
    first, response = setup(session)
    original = event()
    ingest(session, first, response, (original,))
    with session.transaction() as uow:
        history.finish_history_page(
            uow,
            P,
            first.poll_id,
            Count(1),
            response.metadata_digest,
            RevisionGuard(Revision(0)),
        )
        history.finish_history_poll(
            uow,
            P,
            first.poll_id,
            response.response_history_id,
            RevisionGuard(Revision(1)),
        )
    second = replace(
        poll(1100, cursor=response.response_history_id, checkpoint_revision=1),
        started_at=Timestamp(NOW.value + timedelta(minutes=10)),
    )
    later_page = replace(
        page(second),
        received_at=Timestamp(NOW.value + timedelta(minutes=11)),
        metadata_digest=Sha256Hex("f" * 64),
        expected_event_count=Count(1),
    )
    later = replace(
        original,
        event_id=lid(99),
        event=replace(
            original.event, observed_at=second.started_at, source_thread_id=T
        ),
    )
    with session.transaction() as uow:
        history.begin_history_poll(uow, P, second, RevisionGuard(Revision(1)))
        history.begin_history_page(uow, P, later_page, RevisionGuard(Revision(0)))
    ingest(session, second, later_page, (later,), (resolution(later, 19999),))
    with session.transaction() as uow:
        history.finish_history_page(
            uow,
            P,
            second.poll_id,
            Count(1),
            later_page.metadata_digest,
            RevisionGuard(Revision(0)),
        )
    with view(state) as reader:
        saved = reads.get_event(reader, P, original.event_id)
        assert saved.event.observed_at == original.event.observed_at
        assert saved.event.source_thread_id == T and saved.revision == Revision(1)
        assert reads.get_event(reader, P, later.event_id) is None
    assert connection.execute(
        "SELECT metadata_digest FROM history_pages ORDER BY received_at"
    ).fetchall() == [
        (response.metadata_digest.value,),
        (later_page.metadata_digest.value,),
    ]
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (1,)


def test_enrich_same_value_replay_and_conflict_durable_attention_no_context_replacement(
    state,
):
    _, _, session, _ = state
    value, response = setup(session)
    original = event()
    ingest(session, value, response, (original,))
    with session.transaction() as uow:
        events.enrich_event(uow, P, original.event_id, T, RevisionGuard(Revision(0)))
        receipt = events.enrich_event(
            uow, P, original.event_id, T, RevisionGuard(Revision(1))
        )
        assert receipt.disposition == "replayed"
        events.enrich_event(
            uow,
            P,
            original.event_id,
            ProviderId("conflicting-thread"),
            RevisionGuard(Revision(1)),
        )
    with view(state) as reader:
        saved = reads.get_event(reader, P, original.event_id)
        assert saved.event.key == original.event.key and saved.event.observed_at == NOW
        assert (
            saved.event.source_thread_id == T
            and saved.processing is EventProcessing.NEEDS_ATTENTION
        )
        assert (
            saved.error_code is ErrorCode.CONSISTENCY_FAILURE
            and saved.revision == Revision(2)
        )


def test_conflicting_ingest_retains_attention_and_only_resolution_work(
    state,
):
    _, _, session, _ = state
    value, response = setup(session)
    original = event(thread=T)
    ingest(session, value, response, (original,))
    conflicting = replace(
        original,
        event_id=lid(99),
        event=replace(
            original.event, source_thread_id=ProviderId("conflicting-thread")
        ),
    )
    ingest(session, value, response, (conflicting,))
    with view(state) as reader:
        saved = reads.get_event(reader, P, original.event_id)
        assert (
            saved.event.source_thread_id == T
            and saved.processing is EventProcessing.NEEDS_ATTENTION
        )
    with pytest.raises(StorageFailure):
        ingest(
            session,
            value,
            response,
            (conflicting,),
            (job(200, thread=ProviderId("conflicting-thread")),),
        )


def test_event_consumption_requires_its_exact_durable_effect_not_unrelated_jobs(state):
    _, connection, session, _ = state
    publish(session)
    admit(session)
    value, response = setup(session)
    original = event(thread=T)
    ingest(session, value, response, (original,))
    with (
        pytest.raises(StorageFailure, match="owner_unavailable"),
        session.transaction() as uow,
    ):
        events.classify_event(
            uow,
            P,
            original.event_id,
            EventProcessing.CONSUMED,
            None,
            (),
            RevisionGuard(Revision(0)),
        )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        events.classify_event(
            uow,
            P,
            original.event_id,
            EventProcessing.CONSUMED,
            None,
            (job(101),),
            RevisionGuard(Revision(0)),
        )
    selected = job(
        100,
        subject=JobSubjectProjectMessage(
            "project_message", original.event.key.source_message_id, T, Generation(1)
        ),
    )
    with session.transaction() as uow:
        events.classify_event(
            uow,
            P,
            original.event_id,
            EventProcessing.CONSUMED,
            None,
            (selected,),
            RevisionGuard(Revision(0)),
        )
    with view(state) as reader:
        assert (
            reads.get_event(reader, P, original.event_id).processing
            is EventProcessing.CONSUMED
        )
        assert reads.get_job(reader, P, selected.job_id) is not None
    assert connection.execute(
        "SELECT COUNT(*) FROM sync_jobs WHERE kind='project_message'"
    ).fetchone() == (1,)


@pytest.mark.parametrize("bad", ["wrong_thread", "stopped", "stale", "unknown_no_work"])
def test_classification_never_loses_work_or_bypasses_generation_and_context(state, bad):
    _, connection, session, _ = state
    publish(session)
    tracked, _ = admit(session)
    value, response = setup(session)
    original = event(thread=T)
    ingest(session, value, response, (original,))
    selected = job(
        100,
        subject=JobSubjectProjectMessage(
            "project_message",
            original.event.key.source_message_id,
            ProviderId("wrong-thread") if bad == "wrong_thread" else T,
            Generation(1),
        ),
    )
    if bad == "stopped":
        from facet.db.codecs import ThreadStopReason
        from facet.db.repositories import policy

        with session.transaction() as uow:
            policy.stop_thread(
                uow, P, T, tracked.generation, NOW, ThreadStopReason.MANUAL_STOP
            )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        events.classify_event(
            uow,
            P,
            original.event_id,
            EventProcessing.CONSUMED,
            None,
            () if bad == "unknown_no_work" else (selected,),
            RevisionGuard(Revision(1 if bad == "stale" else 0)),
        )
    assert connection.execute("SELECT processing FROM source_events").fetchone() == (
        "pending",
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM sync_jobs WHERE kind='project_message'"
    ).fetchone() == (0,)


@pytest.mark.parametrize(
    "processing,error",
    [
        (EventProcessing.RESOLVED, None),
        (EventProcessing.NEEDS_ATTENTION, ErrorCode.CONSISTENCY_FAILURE),
        (EventProcessing.SOURCE_MISSING, ErrorCode.SOURCE_MISSING),
    ],
)
def test_explicit_resolved_attention_source_missing_states_are_durable(
    state, processing, error
):
    _, _, session, _ = state
    value, response = setup(session)
    original = event(thread=T)
    ingest(session, value, response, (original,))
    with session.transaction() as uow:
        events.classify_event(
            uow, P, original.event_id, processing, error, (), RevisionGuard(Revision(0))
        )
    with view(state) as reader:
        saved = reads.get_event(reader, P, original.event_id)
        assert saved.processing is processing and saved.error_code is error
