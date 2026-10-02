"""Real-file prepare/dispatch fences; no Gmail invocation or raw content storage."""

import sqlite3
from contextlib import suppress
from dataclasses import replace
from datetime import timedelta

import pytest
from test_db_repositories import (
    T,
    admit,
    attempt,
    claim,
    job,
    publish,
    ready_test_metadata,
    view,
)
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
    ClaimPhase,
    ErrorCode,
    InsertState,
    OutcomeCertainty,
    Revision,
    Timestamp,
)
from facet.db.codecs import StorageFailure, ThreadStopReason
from facet.db.connection import _attach_writer
from facet.db.models import JobClaimRow, RevisionGuard
from facet.db.repositories import intents, jobs, policy
from facet.db.repositories.base import _insert


def setup(state):
    _, connection, session, info = state
    publish(session)
    tracked, _ = admit(session)
    value = job(100)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, value)
    ready_test_metadata(connection, session)
    acquired, receipt = claim(session, info, value)
    prepared = attempt(value, acquired, 200, InsertState.PREPARED)
    return value, tracked, acquired, receipt, prepared


def prepare(session, row, *, revision=1):
    with session.transaction() as uow:
        return intents.prepare_attempt(uow, P, row, RevisionGuard(Revision(revision)))


def dispatch(session, row, *, revision=0):
    with session.transaction() as uow:
        return intents.mark_dispatch(
            uow, P, row.attempt_id, row.claim_id, NOW, RevisionGuard(Revision(revision))
        )


def test_intent_precedes_dispatch_and_claim_phase_changes_in_the_same_transaction(
    state,
):
    _, connection, session, _ = state
    value, _, acquired, _, prepared = setup(state)
    receipt = prepare(session, prepared)
    assert receipt.disposition == "created" and receipt.revision == Revision(0)
    changes = connection.total_changes
    replay = prepare(session, prepared)
    assert replay.disposition == "replayed" and connection.total_changes == changes
    with view(state) as reader:
        assert reader.get_attempt(P, prepared.attempt_id) == prepared
    dispatched = dispatch(session, prepared)
    assert dispatched.revision == Revision(1)
    with view(state) as reader:
        actual = reader.get_attempt(P, prepared.attempt_id)
        assert actual.state is InsertState.DISPATCH_STARTED
        assert actual.certainty is OutcomeCertainty.UNKNOWN
        assert actual.dispatch_started_at == NOW and actual.result_at is None
        assert actual.claim_id == acquired.claim_id
        assert actual.target_message_id is None
    assert connection.execute(
        "SELECT phase,job_revision FROM job_claims WHERE job_id=?",
        (value.job_id.value,),
    ).fetchone() == (ClaimPhase.DISPATCHING.value, 1)
    changes = connection.total_changes
    replay = dispatch(session, prepared, revision=dispatched.revision.value)
    assert replay.disposition == "replayed" and replay.revision == dispatched.revision
    assert connection.total_changes == changes


@pytest.mark.parametrize(
    "bad",
    ["job_guard", "claim", "message", "thread", "binding", "time", "revision", "state"],
)
def test_invalid_prepare_has_no_intent_or_partial_audit(state, bad):
    _, connection, session, _ = state
    _, _, _, _, prepared = setup(state)
    audit_count = connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()
    changes = {
        "claim": {"claim_id": lid(999)},
        "message": {"source_message_id": T},
        "thread": {"source_thread_id": prepared.source_message_id},
        "binding": {"binding_revision": Revision(1)},
        "time": {"prepared_at": Timestamp(NOW.value - timedelta(seconds=1))},
        "revision": {"revision": Revision(1)},
        "state": {
            "state": InsertState.DEFINITE_NOT_INSERTED,
            "certainty": OutcomeCertainty.DEFINITELY_NOT_INSERTED,
            "result_at": NOW,
        },
    }
    row = prepared if bad == "job_guard" else replace(prepared, **changes[bad])
    with pytest.raises(StorageFailure):
        prepare(session, row, revision=0 if bad == "job_guard" else 1)
    assert connection.execute("SELECT COUNT(*) FROM insert_attempts").fetchone() == (0,)
    assert (
        connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()
        == audit_count
    )


@pytest.mark.parametrize(
    "bad", ["pause", "restore", "binding", "phase", "owner", "claim", "time", "stale"]
)
def test_dispatch_rechecks_actor_entry_guards_and_leaves_prepared_on_refusal(
    state, bad
):
    _, connection, session, _ = state
    value, _, acquired, _, prepared = setup(state)
    prepare(session, prepared)
    if bad in {"pause", "restore", "binding", "phase", "owner"}:
        with session.transaction() as uow:
            if bad == "pause":
                uow._execute(
                    "UPDATE projections SET daemon_paused=1 WHERE projection_id=?",
                    (P.value,),
                )
            elif bad == "restore":
                uow._execute(
                    "UPDATE projections SET restore_state='revalidation_required' "
                    "WHERE projection_id=?",
                    (P.value,),
                )
            elif bad == "binding":
                uow._execute(
                    "UPDATE projections SET binding_state='verification_pending' "
                    "WHERE projection_id=?",
                    (P.value,),
                )
            elif bad == "phase":
                uow._execute(
                    "UPDATE job_claims SET phase='verifying' "
                    "WHERE projection_id=? AND job_id=?",
                    (P.value, value.job_id.value),
                )
            else:
                # Closed old-owner claim fixture, not a production restart/
                # claim replacement entry. The immutable owner column cannot
                # be updated even by test SQL; no triggers are weakened.
                uow._execute(
                    "DELETE FROM job_claims WHERE projection_id=? AND job_id=?",
                    (P.value, value.job_id.value),
                )
                _insert(
                    uow,
                    P,
                    "job_claims",
                    JobClaimRow(
                        P, value.job_id, replace(acquired, owner_run_id=lid(999))
                    ),
                )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        intents.mark_dispatch(
            uow,
            P,
            prepared.attempt_id,
            lid(999) if bad == "claim" else prepared.claim_id,
            Timestamp(NOW.value - timedelta(seconds=1)) if bad == "time" else NOW,
            RevisionGuard(Revision(1 if bad == "stale" else 0)),
        )
    with view(state) as reader:
        assert reader.get_attempt(P, prepared.attempt_id) == prepared


@pytest.mark.parametrize("after_dispatch", [False, True])
def test_stop_keeps_dispatched_facts_but_never_authorizes_marker_replay(
    state, after_dispatch
):
    _, _, session, _ = state
    _, tracked, _, _, prepared = setup(state)
    prepare(session, prepared)
    if after_dispatch:
        dispatch(session, prepared)
    with session.transaction() as uow:
        policy.stop_thread(
            uow, P, T, tracked.generation, NOW, ThreadStopReason.MANUAL_STOP
        )
    with view(state) as reader:
        actual = reader.get_attempt(P, prepared.attempt_id)
        assert actual.state is (
            InsertState.DISPATCH_STARTED
            if after_dispatch
            else InsertState.CANCELLED_BEFORE_DISPATCH
        )
        assert actual.target_message_id is None
    with pytest.raises(StorageFailure):
        dispatch(session, prepared, revision=actual.revision.value)
    with view(state) as reader:
        assert reader.get_attempt(P, prepared.attempt_id) == actual


def test_unresolved_thread_blocks_new_message_prepare_even_with_another_actual_claim(
    state,
):
    _, _, session, info = state
    _, _, _, _, prepared = setup(state)
    prepare(session, prepared)
    dispatch(session, prepared)
    from facet.contracts import ProviderId
    from facet.contracts.records import JobSubjectProjectMessage

    other = job(
        101,
        subject=JobSubjectProjectMessage(
            "project_message",
            ProviderId("other-source-message"),
            T,
            prepared.generation,
        ),
    )
    with session.transaction() as uow:
        jobs.enqueue(uow, P, other)
    acquired, _ = claim(session, info, other)
    new_attempt = attempt(other, acquired, 201, InsertState.PREPARED)
    with pytest.raises(StorageFailure, match=ErrorCode.INSERT_RESULT_UNKNOWN.value):
        prepare(session, new_attempt)
    with view(state) as reader:
        assert reader.get_attempt(P, new_attempt.attempt_id) is None
        assert (
            reader.get_attempt(P, prepared.attempt_id).state
            is InsertState.DISPATCH_STARTED
        )


def test_dispatch_failure_rolls_back_preceding_prepare_marker_and_claim_phase(state):
    _, connection, session, _ = state
    value, _, _, _, prepared = setup(state)

    def fail_phase(action, table, column, database, trigger):
        return (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_UPDATE and table == "job_claims"
            else sqlite3.SQLITE_OK
        )

    audits = connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()
    connection.set_authorizer(fail_phase)
    try:
        with pytest.raises(StorageFailure), session.transaction() as uow:
            receipt = intents.prepare_attempt(
                uow, P, prepared, RevisionGuard(Revision(1))
            )
            with suppress(StorageFailure):
                intents.mark_dispatch(
                    uow,
                    P,
                    prepared.attempt_id,
                    prepared.claim_id,
                    NOW,
                    RevisionGuard(receipt.revision),
                )
    finally:
        connection.set_authorizer(None)
    with view(state) as reader:
        assert reader.get_attempt(P, prepared.attempt_id) is None
    assert connection.execute(
        "SELECT phase FROM job_claims WHERE job_id=?", (value.job_id.value,)
    ).fetchone() == (ClaimPhase.PREPARING.value,)
    assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone() == audits


def test_committed_unknown_dispatch_marker_survives_close_and_reopen_without_resending(
    state,
):
    path, _, session, info = state
    _, _, _, _, prepared = setup(state)
    prepare(session, prepared)
    dispatch(session, prepared)
    session.close()
    # Same supplied test lineage, not the M1-03 fresh owner-run restart protocol.
    reopened = _attach_writer(sqlite3.connect(path, autocommit=True), info)
    try:
        with view((path, reopened._connection, reopened, info)) as reader:
            actual = reader.get_attempt(P, prepared.attempt_id)
        assert actual.state is InsertState.DISPATCH_STARTED
        assert actual.certainty is OutcomeCertainty.UNKNOWN
        with pytest.raises(StorageFailure):
            prepare(reopened, replace(prepared, attempt_id=lid(201)))
        changes = reopened._connection.total_changes
        replay = dispatch(reopened, prepared, revision=actual.revision.value)
        assert replay.disposition == "replayed"
        assert reopened._connection.total_changes == changes
    finally:
        reopened.close()
