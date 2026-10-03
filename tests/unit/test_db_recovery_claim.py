"""Recovery claims use closed phases and never authorize another insert."""

from dataclasses import replace

import pytest
from test_db_intents import dispatch, prepare, setup
from test_db_repositories import job, view
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import Claim, ClaimPhase, ErrorCode, Priority, Revision
from facet.contracts.records import JobSubjectRecoverInsert
from facet.db.codecs import StorageFailure, ThreadStopReason, timestamp_to_sql
from facet.db.models import RevisionGuard
from facet.db.repositories import intents, jobs, policy


def recovery_work(state):
    _, _, session, _ = state
    original, tracked, _, _, prepared = setup(state)
    prepare(session, prepared)
    dispatch(session, prepared)
    recovering = job(
        300,
        subject=JobSubjectRecoverInsert("recover_insert", prepared.attempt_id),
        priority=Priority.RECOVERY,
    )
    with session.transaction() as uow:
        # Closed already-recorded unknown-result fixture. The result producer is
        # a separate pending slice; this does not claim invocation proof.
        uow._execute(
            "UPDATE insert_attempts SET state='pending_recovery',result_at=?,"
            "revision=2 WHERE projection_id=? AND attempt_id=?",
            (timestamp_to_sql(NOW), P.value, prepared.attempt_id.value),
        )
        uow._execute(
            "DELETE FROM job_claims WHERE projection_id=? AND job_id=?",
            (P.value, original.job_id.value),
        )
        uow._execute(
            "UPDATE sync_jobs SET state='blocked',revision=2 "
            "WHERE projection_id=? AND job_id=?",
            (P.value, original.job_id.value),
        )
        jobs.enqueue(uow, P, recovering)
    return prepared, recovering, tracked


@pytest.mark.parametrize("stopped", [False, True])
def test_actual_recovery_claim_prepares_old_attempt_checks_without_insert_permission(
    state, stopped
):
    _, connection, session, info = state
    prepared, recovering, tracked = recovery_work(state)
    if stopped:
        with session.transaction() as uow:
            policy.stop_thread(
                uow,
                P,
                tracked.source_thread_id,
                tracked.generation,
                NOW,
                ThreadStopReason.MANUAL_STOP,
            )
            uow._execute(
                "UPDATE projections SET daemon_paused=1 WHERE projection_id=?",
                (P.value,),
            )
    acquired = Claim(
        lid(500),
        info.owner_run_id,
        NOW,
        prepared.generation,
        Revision(1),
        ClaimPhase.PREPARING,
    )
    with session.transaction() as uow:
        receipt = jobs.claim(
            uow, P, recovering.job_id, acquired, RevisionGuard(Revision(0)), NOW
        )
    assert receipt.revision == Revision(1)
    assert connection.execute(
        "SELECT phase FROM job_claims WHERE job_id=?", (recovering.job_id.value,)
    ).fetchone() == ("preparing",)
    with view(state) as reader:
        before = reader.get_attempt(P, prepared.attempt_id)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        intents.mark_dispatch(
            uow,
            P,
            prepared.attempt_id,
            acquired.claim_id,
            NOW,
            RevisionGuard(before.revision),
        )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        intents.prepare_attempt(
            uow,
            P,
            replace(
                prepared,
                attempt_id=lid(201),
                job_id=recovering.job_id,
                claim_id=acquired.claim_id,
            ),
            RevisionGuard(receipt.revision),
        )
    with session.transaction() as uow:
        jobs.defer_job(
            uow,
            P,
            recovering.job_id,
            "retry_wait",
            ErrorCode.NETWORK_UNAVAILABLE,
            NOW,
            RevisionGuard(receipt.revision),
        )
    with view(state) as reader:
        assert reader.get_attempt(P, prepared.attempt_id) == before
        assert reader.get_job(P, recovering.job_id).state.value == "retry_wait"
    assert connection.execute("SELECT COUNT(*) FROM insert_attempts").fetchone() == (1,)


@pytest.mark.parametrize("phase", [ClaimPhase.DISPATCHING, ClaimPhase.VERIFYING])
def test_recovery_claim_refuses_nonpreparing_acquisition(state, phase):
    _, connection, session, info = state
    prepared, recovering, _ = recovery_work(state)
    invalid = Claim(
        lid(500), info.owner_run_id, NOW, prepared.generation, Revision(1), phase
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.claim(uow, P, recovering.job_id, invalid, RevisionGuard(Revision(0)), NOW)
    assert connection.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)
    with view(state) as reader:
        assert reader.get_job(P, recovering.job_id).state.value == "queued"
