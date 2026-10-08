"""False event attention closes only against an exact persisted business effect."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_db_events import event, resolution
from test_db_mappings import inserted, verify
from test_db_repositories import ready_test_metadata
from test_db_repositories import state as state
from test_db_results import pending, ready, record
from test_db_schema import NOW, P
from test_projection_action_consumer import _repairable_alias

from facet.contracts import Claim, ClaimPhase, ErrorCode, ProviderId, Revision
from facet.db.codecs import EventProcessing, StorageFailure, ThreadStopReason
from facet.db.keys import event_key
from facet.db.models import RevisionGuard
from facet.db.repositories import events, jobs, policy, reads
from facet.db.repositories.base import _insert
from facet.sync import ForegroundSync


def _notification(state, *, attention=True, mapped=False):
    _, _, session, info = state
    if mapped:
        original, tracked, _, attempt = inserted(state)
        verify(state, attempt)
    else:
        original, tracked, _, attempt = ready(state)
        record(state, pending(attempt))
    template = event(700, thread=tracked.source_thread_id)
    key = replace(template.event.key, source_message_id=attempt.source_message_id)
    row = replace(
        template, event_key=event_key(P, key), event=replace(template.event, key=key)
    )
    resolver = resolution(row)
    with session.transaction() as uow:
        _insert(uow, P, "source_events", row)
        jobs.enqueue(uow, P, resolver)
    if attention:
        with session.transaction() as uow:
            from test_db_schema import lid

            acquired = Claim(
                lid(9999),
                info.owner_run_id,
                NOW,
                None,
                Revision(resolver.revision.value + 1),
                ClaimPhase.PREPARING,
            )
            receipt = jobs.claim(
                uow, P, resolver.job_id, acquired, RevisionGuard(resolver.revision), NOW
            )
            events.classify_event(
                uow,
                P,
                row.event_id,
                EventProcessing.NEEDS_ATTENTION,
                ErrorCode.REQUEST_CONFLICT,
                (),
                RevisionGuard(row.revision),
            )
            jobs.defer_job(
                uow,
                P,
                resolver.job_id,
                "needs_attention",
                ErrorCode.REQUEST_CONFLICT,
                None,
                RevisionGuard(receipt.revision),
            )
    with session.transaction() as uow:
        return (
            original,
            tracked,
            reads.get_event(uow, P, row.event_id),
            reads.get_job(uow, P, resolver.job_id),
        )


@pytest.mark.parametrize("attention", [False, True])
def test_unknown_blocked_effect_consumes_only_the_duplicate_notification(
    state, attention
):
    _, connection, session, _ = state
    original, _, row, resolver = _notification(state, attention=attention)
    before = connection.execute("SELECT * FROM insert_attempts").fetchall()
    with session.transaction() as uow:
        events.consume_message_added_existing_effect(
            uow,
            P,
            row.event_id,
            RevisionGuard(row.revision),
            RevisionGuard(resolver.revision),
            NOW,
        )
    with session.transaction() as uow:
        assert reads.get_event(uow, P, row.event_id).processing.value == "consumed"
        assert reads.get_job(uow, P, resolver.job_id).state.value == "completed"
        assert reads.get_job(uow, P, original.job_id).state.value == "blocked"
    assert connection.execute("SELECT * FROM insert_attempts").fetchall() == before
    assert connection.execute("SELECT COUNT(*) FROM message_mappings").fetchone() == (
        0,
    )


@pytest.mark.parametrize(
    "fault", ["stop", "wrong_message", "wrong_reason", "stale_guard"]
)
def test_unsupported_event_attention_is_not_overridden(state, fault):
    _, connection, session, _ = state
    _, tracked, row, resolver = _notification(state)
    with session.transaction() as uow:
        if fault == "stop":
            policy.stop_thread(
                uow,
                P,
                tracked.source_thread_id,
                tracked.generation,
                NOW,
                ThreadStopReason.MANUAL_STOP,
            )
        elif fault == "wrong_message":
            # Contradictory thread cannot silently replace immutable event facts.
            events.enrich_event(
                uow,
                P,
                row.event_id,
                ProviderId("wrong-thread"),
                RevisionGuard(row.revision),
            )
        elif fault == "wrong_reason":
            events.classify_event(
                uow,
                P,
                row.event_id,
                EventProcessing.NEEDS_ATTENTION,
                ErrorCode.CONSISTENCY_FAILURE,
                (),
                RevisionGuard(row.revision),
            )
        current = reads.get_event(uow, P, row.event_id)
    before = connection.execute("SELECT * FROM source_events").fetchall()
    with pytest.raises(StorageFailure), session.transaction() as uow:
        events.consume_message_added_existing_effect(
            uow,
            P,
            row.event_id,
            RevisionGuard(
                resolver.revision if fault == "stale_guard" else current.revision
            ),
            RevisionGuard(resolver.revision),
            NOW,
        )
    assert connection.execute("SELECT * FROM source_events").fetchall() == before


def _runner(session):
    def forbidden(*args, **kwargs):
        raise AssertionError("convergence must not call Gmail or admission")

    return ForegroundSync(
        SimpleNamespace(session=session, projection_id=P),
        SimpleNamespace(profile=forbidden, history=forbidden),
        SimpleNamespace(insert=forbidden),
        SimpleNamespace(evaluate=forbidden),
    )


def test_normal_sync_converges_old_proven_action_alias_without_business_replay(state):
    _, connection, session, _ = state
    ready_test_metadata(connection, session)
    _, row, _, _ = _repairable_alias(state)
    before = {
        table: connection.execute("SELECT * FROM " + table).fetchall()
        for table in ("rules", "tracked_threads", "insert_attempts", "action_commands")
    }
    assert _runner(session)._converge_completed_events(100) == 1
    assert _runner(session)._converge_completed_events(100) == 0
    with session.transaction() as uow:
        assert reads.get_event(uow, P, row.event_id).processing.value == "consumed"
    for table, rows in before.items():
        assert connection.execute("SELECT * FROM " + table).fetchall() == rows


def test_normal_sync_converges_old_message_effect_without_resend(state):
    _, connection, session, _ = state
    _notification(state)
    before = connection.execute("SELECT * FROM insert_attempts").fetchall()
    assert _runner(session)._converge_completed_events(100) == 1
    assert connection.execute("SELECT * FROM insert_attempts").fetchall() == before


def test_confirmed_mapping_closes_only_the_resolver_and_replays_idempotently(state):
    _, connection, session, _ = state
    _, _, row, resolver = _notification(state, mapped=True)
    before = {
        table: connection.execute("SELECT * FROM " + table).fetchall()
        for table in ("message_mappings", "insert_attempts", "tracked_threads")
    }
    with session.transaction() as uow:
        events.consume_message_added_existing_effect(
            uow,
            P,
            row.event_id,
            RevisionGuard(row.revision),
            RevisionGuard(resolver.revision),
            NOW,
        )
    with session.transaction() as uow:
        current = reads.get_event(uow, P, row.event_id)
        job = reads.get_job(uow, P, resolver.job_id)
        receipt = events.consume_message_added_existing_effect(
            uow,
            P,
            row.event_id,
            RevisionGuard(current.revision),
            RevisionGuard(job.revision),
            NOW,
        )
        assert receipt.disposition == "replayed"
    for table, rows in before.items():
        assert connection.execute("SELECT * FROM " + table).fetchall() == rows


def test_convergence_group_rolls_back_after_late_failure(state, monkeypatch):
    _, connection, session, _ = state
    _, _, row, resolver = _notification(state)
    before = connection.execute("SELECT * FROM source_events").fetchall()

    def failure(*args, **kwargs):
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)

    monkeypatch.setattr(events, "_audit", failure)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        events.consume_message_added_existing_effect(
            uow,
            P,
            row.event_id,
            RevisionGuard(row.revision),
            RevisionGuard(resolver.revision),
            NOW,
        )
    assert connection.execute("SELECT * FROM source_events").fetchall() == before
    with session.transaction() as uow:
        assert reads.get_job(uow, P, resolver.job_id).state.value == "needs_attention"
