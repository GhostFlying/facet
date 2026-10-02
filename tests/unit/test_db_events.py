"""Actual file-backed event membership, resolution jobs and classification."""

from contextlib import suppress
from dataclasses import replace
from datetime import timedelta

import pytest
from test_db_history import page, poll, start
from test_db_repositories import T, admit, job, publish, thread_rows, view
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
    Count,
    ErrorCode,
    Generation,
    JobState,
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
    ThreadGenerationGuardTracked,
)
from facet.db.codecs import (
    AuditKind,
    AuditObjectKind,
    EventProcessing,
    StorageFailure,
    ThreadStopReason,
)
from facet.db.keys import event_key
from facet.db.models import RevisionGuard, SourceEventRow
from facet.db.repositories import events, history, policy, reads
from facet.db.repositories import jobs as queue
from facet.db.repositories.audit import _audit


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
        receipt = history.begin_history_page(
            uow, P, response, RevisionGuard(value.revision)
        )
    return replace(value, revision=receipt.revision), response


def ingest(session, value, response, rows, jobs=None, *, revision=None):
    if jobs is None:
        jobs = tuple(resolution(row) for row in rows)
    with session.transaction() as uow:
        return events.ingest_history_chunk(
            uow,
            P,
            value.poll_id,
            response.ordinal,
            rows,
            jobs,
            RevisionGuard(value.revision if revision is None else revision),
        )


def test_split_large_history_page_preserves_all_distinct_events_and_resolution_jobs(
    state,
):
    _, connection, session, _ = state
    value, response = setup(session, count=601)
    selected = tuple(event(n) for n in range(1, 602))
    first = ingest(session, value, response, selected[:500])
    assert first.revision == Revision(2) and first.disposition == "updated"
    with pytest.raises(StorageFailure), session.transaction() as uow:
        history.finish_history_page(
            uow,
            P,
            value.poll_id,
            Count(1),
            response.metadata_digest,
            RevisionGuard(first.revision),
        )
    second = ingest(session, value, response, selected[500:], revision=first.revision)
    assert second.revision == Revision(3)
    # Replaying an entire chunk preserves the first allocated IDs/work.
    changes = connection.total_changes
    replay = ingest(session, value, response, selected[:500], revision=second.revision)
    assert replay.disposition == "replayed" and replay.revision == second.revision
    assert connection.total_changes == changes
    with session.transaction() as uow:
        finished = history.finish_history_page(
            uow,
            P,
            value.poll_id,
            Count(1),
            response.metadata_digest,
            RevisionGuard(replay.revision),
        )
        history.finish_history_poll(
            uow,
            P,
            value.poll_id,
            response.response_history_id,
            RevisionGuard(finished.revision),
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
    assert connection.execute("SELECT revision FROM history_polls").fetchone() == (
        value.revision.value,
    )


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
    ingested = ingest(session, first, response, (original,))
    with session.transaction() as uow:
        finished = history.finish_history_page(
            uow,
            P,
            first.poll_id,
            Count(1),
            response.metadata_digest,
            RevisionGuard(ingested.revision),
        )
        history.finish_history_poll(
            uow,
            P,
            first.poll_id,
            response.response_history_id,
            RevisionGuard(finished.revision),
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
        begun = history.begin_history_page(
            uow, P, later_page, RevisionGuard(second.revision)
        )
    second = replace(second, revision=begun.revision)
    ingested = ingest(
        session, second, later_page, (later,), (resolution(later, 19999),)
    )
    assert ingested.revision == Revision(2)
    with session.transaction() as uow:
        history.finish_history_page(
            uow,
            P,
            second.poll_id,
            Count(1),
            later_page.metadata_digest,
            RevisionGuard(ingested.revision),
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
    ingested = ingest(session, value, response, (original,))
    conflicting = replace(
        original,
        event_id=lid(99),
        event=replace(
            original.event, source_thread_id=ProviderId("conflicting-thread")
        ),
    )
    ingested = ingest(
        session, value, response, (conflicting,), revision=ingested.revision
    )
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
            revision=ingested.revision,
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


def selected_project(original, n=100, *, generation=1, thread=T):
    return job(
        n,
        subject=JobSubjectProjectMessage(
            "project_message",
            original.event.key.source_message_id,
            thread,
            Generation(generation),
        ),
    )


def retrack(session):
    tracked, admission = thread_rows(generation=3, admission_revision=2)
    with session.transaction() as uow:
        policy.admit_thread(
            uow,
            P,
            tracked,
            admission,
            (),
            ThreadGenerationGuardTracked("tracked", Generation(2)),
        )


@pytest.mark.parametrize(
    "case", ["stop", "stop_retrack", "failed", "cancelled", "wrong_thread"]
)
def test_preexisting_effect_cannot_bypass_new_consumption_authority(state, case):
    _, connection, session, _ = state
    publish(session)
    tracked, _ = admit(session)
    value, response = setup(session)
    original = event(thread=T)
    ingest(session, value, response, (original,))
    selected = selected_project(original)
    with session.transaction() as uow:
        queue.enqueue(uow, P, selected)
        if case in {"stop", "stop_retrack"}:
            policy.stop_thread(
                uow, P, T, tracked.generation, NOW, ThreadStopReason.MANUAL_STOP
            )
        elif case in {"failed", "cancelled"}:
            # Durable synthetic prior scheduler consequence, not an exposed
            # arbitrary status setter or actual cancellation CLI implementation.
            uow._execute(
                "UPDATE sync_jobs SET state=? WHERE projection_id=? AND job_id=?",
                (case, P.value, selected.job_id.value),
            )
    if case == "stop_retrack":
        retrack(session)
    provided = (
        selected_project(original, thread=ProviderId("wrong-thread"))
        if case == "wrong_thread"
        else selected
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        events.classify_event(
            uow,
            P,
            original.event_id,
            EventProcessing.CONSUMED,
            None,
            (provided,),
            RevisionGuard(Revision(0)),
        )
    with view(state) as reader:
        saved = reads.get_event(reader, P, original.event_id)
        assert (
            saved.processing is EventProcessing.PENDING
            and saved.revision == Revision(0)
        )
        actual = reads.get_job(reader, P, selected.job_id)
        if case in {"stop", "stop_retrack", "cancelled"}:
            assert actual.state is JobState.CANCELLED
        elif case == "failed":
            assert actual.state is JobState.FAILED
        else:
            assert actual.state is JobState.QUEUED
        if case == "stop_retrack":
            assert reads.get_thread(reader, P, T).generation == Generation(3)
    assert connection.execute(
        "SELECT COUNT(*) FROM sync_jobs WHERE kind='project_message'"
    ).fetchone() == (1,)


def test_existing_current_effect_and_consumed_post_stop_replay_do_not_enqueue(state):
    _, connection, session, _ = state
    publish(session)
    tracked, _ = admit(session)
    value, response = setup(session)
    original = event(thread=T)
    ingest(session, value, response, (original,))
    selected = selected_project(original)
    with session.transaction() as uow:
        queue.enqueue(uow, P, selected)
        events.classify_event(
            uow,
            P,
            original.event_id,
            EventProcessing.CONSUMED,
            None,
            (selected,),
            RevisionGuard(Revision(0)),
        )
        policy.stop_thread(
            uow, P, T, tracked.generation, NOW, ThreadStopReason.MANUAL_STOP
        )
    before = connection.total_changes
    with session.transaction() as uow:
        receipt = events.classify_event(
            uow,
            P,
            original.event_id,
            EventProcessing.CONSUMED,
            None,
            (selected,),
            RevisionGuard(Revision(1)),
        )
        assert receipt.disposition == "replayed" and receipt.revision == Revision(1)
    assert connection.total_changes == before
    with view(state) as reader:
        assert (
            reads.get_event(reader, P, original.event_id).processing
            is EventProcessing.CONSUMED
        )
        assert reads.get_job(reader, P, selected.job_id).state is JobState.CANCELLED
        assert not reads.get_thread(reader, P, T).active
    # Replaying a genuinely recorded event may not allocate a new generation's
    # work, even after explicit retracking. It is receipt lookup, not scheduling.
    retrack(session)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        events.classify_event(
            uow,
            P,
            original.event_id,
            EventProcessing.CONSUMED,
            None,
            (selected_project(original, 101, generation=3),),
            RevisionGuard(Revision(1)),
        )
    assert connection.execute(
        "SELECT COUNT(*) FROM sync_jobs WHERE kind='project_message'"
    ).fetchone() == (1,)


def test_caught_new_consumption_failure_rolls_back_prior_job_and_audit(state):
    _, connection, session, _ = state
    publish(session)
    tracked, _ = admit(session)
    other = ProviderId("separately-tracked-thread")
    admit(session, thread=other)
    value, response = setup(session)
    original = event(thread=T)
    ingest(session, value, response, (original,))
    selected = selected_project(original)
    with session.transaction() as uow:
        queue.enqueue(uow, P, selected)
        policy.stop_thread(
            uow, P, T, tracked.generation, NOW, ThreadStopReason.MANUAL_STOP
        )
    before_audit = connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()
    first = job(202, thread=other)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        queue.enqueue(uow, P, first)
        _audit(
            uow,
            P,
            AuditKind.JOB_STATE_CHANGED,
            AuditObjectKind.JOB,
            NOW,
            local_id=first.job_id,
            after_state=JobState.QUEUED,
        )
        with suppress(StorageFailure):
            events.classify_event(
                uow,
                P,
                original.event_id,
                EventProcessing.CONSUMED,
                None,
                (selected,),
                RevisionGuard(Revision(0)),
            )
    # The independently reopened view observes no partial transaction success.
    with view(state) as reader:
        assert reads.get_job(reader, P, first.job_id) is None
        assert (
            reads.get_event(reader, P, original.event_id).processing
            is EventProcessing.PENDING
        )
    assert (
        connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()
        == before_audit
    )


def test_chunk_stale_guard_never_replays_or_accepts_new_membership(state):
    _, connection, session, _ = state
    value, response = setup(session, count=2)
    first = event()
    receipt = ingest(session, value, response, (first,))
    assert receipt.revision == Revision(2)
    for rows in [(first,), (event(2),)]:
        with pytest.raises(StorageFailure):
            ingest(session, value, response, rows)
    assert connection.execute("SELECT revision FROM history_polls").fetchone() == (2,)
    assert connection.execute("SELECT COUNT(*) FROM source_events").fetchone() == (1,)
    second = ingest(session, value, response, (event(2),), revision=receipt.revision)
    assert second.revision == Revision(3)


def test_empty_chunk_is_zero_write_replay_and_caught_failure_undoes_accepted_chunk(
    state,
):
    _, connection, session, _ = state
    value, response = setup(session)
    changes = connection.total_changes
    empty = ingest(session, value, response, ())
    assert empty.disposition == "replayed" and empty.revision == value.revision
    assert connection.total_changes == changes
    first = event()
    with pytest.raises(StorageFailure), session.transaction() as uow:
        receipt = events.ingest_history_chunk(
            uow,
            P,
            value.poll_id,
            response.ordinal,
            (first,),
            (resolution(first),),
            RevisionGuard(value.revision),
        )
        assert receipt.revision == Revision(2)
        with suppress(StorageFailure):
            events.ingest_history_chunk(
                uow,
                P,
                value.poll_id,
                response.ordinal,
                (event(2),),
                (),
                RevisionGuard(receipt.revision),
            )
    assert connection.execute("SELECT revision FROM history_polls").fetchone() == (1,)
    for table in ["source_events", "sync_jobs", "history_page_events"]:
        assert connection.execute("SELECT COUNT(*) FROM " + table).fetchone() == (0,)
