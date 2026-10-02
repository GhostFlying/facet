"""MV-01..12: real first-map SQL groups using synthetic direct/fidelity facts.

These tests use actual claim/prepare/dispatch/result producers. Typed synthetic
fidelity observations are not Gmail readback evidence or runtime authorization.
"""

import sqlite3
from contextlib import suppress
from dataclasses import replace
from datetime import timedelta

import pytest
from fakes.privacy import (
    Profile,
    assert_private_boundary,
    inspect_files,
    inspect_sqlite,
    markers,
)
from test_db_intents import dispatch, prepare
from test_db_repositories import attempt as attempt_fixture
from test_db_repositories import claim, job, thread_rows, view
from test_db_repositories import state as state
from test_db_results import (
    get_attempt,
    known,
    pending,
    ready,
    record,
    recovery,
    selected_epoch,
)
from test_db_schema import NOW, P, lid

from facet.contracts import (
    Claim,
    ClaimPhase,
    Count,
    EpochState,
    ErrorCode,
    Generation,
    InsertState,
    PolicyVersion,
    Priority,
    ProjectionId,
    ProviderId,
    Revision,
    Sha256Hex,
    Timestamp,
    Visibility,
)
from facet.contracts.records import ThreadGenerationGuardTracked
from facet.db.codecs import MAX_INTEGER, StorageFailure, ThreadStopReason
from facet.db.connection import _attach_writer
from facet.db.models import (
    JobClaimRow,
    MappingHistoryRow,
    MessageMappingRow,
    RevisionGuard,
    TargetOwnershipRow,
    ThreadTargetRow,
)
from facet.db.repositories import epochs, jobs, mappings, policy, reads
from facet.db.repositories.base import _insert


def inserted(state, *, pair=True, visibility=Visibility.UNKNOWN):
    original, tracked, acquired, old = ready(state)
    row = replace(
        known(old),
        semantic_digest=Sha256Hex("b" * 64) if pair else None,
        semantic_version=PolicyVersion("synthetic-mime-v1") if pair else None,
        visibility=visibility,
    )
    record(state, row)
    return original, tracked, acquired, row


def attention(state, old):
    row = replace(
        old,
        state=InsertState.NEEDS_ATTENTION,
        error_code=ErrorCode.FIDELITY_MISMATCH,
        revision=Revision(old.revision.value + 1),
    )
    record(state, row)
    return row


def group(attempt, *, at=NOW, visibility=Visibility.NORMAL, target=None, anchor=True):
    mapping = MessageMappingRow(
        P,
        attempt.source_message_id,
        attempt.source_thread_id,
        Revision(1),
        attempt.attempt_id,
        attempt.target_message_id,
        attempt.target_thread_id,
        at,
        visibility,
        None,
        None,
    )
    history = MappingHistoryRow(
        P,
        attempt.source_message_id,
        Revision(1),
        attempt.source_thread_id,
        attempt.attempt_id,
        attempt.target_message_id,
        attempt.target_thread_id,
        at,
        None,
    )
    ownership = TargetOwnershipRow(
        P, attempt.target_message_id, attempt.source_message_id, attempt.attempt_id, at
    )
    thread_target = target or ThreadTargetRow(
        P,
        attempt.source_thread_id,
        attempt.target_thread_id,
        anchor,
        attempt.attempt_id,
        at,
    )
    return mapping, history, ownership, thread_target


def verify(state, attempt, values=None, *, guard=None):
    with state[2].transaction() as uow:
        return mappings.verify_mapping(
            uow,
            P,
            attempt.attempt_id,
            *(values or group(attempt)),
            RevisionGuard(guard or attempt.revision),
        )


def observed_group(state, attempt):
    with view(state) as reader:
        actual = reader.get_mapping(P, attempt.source_message_id)
        target = reader.get_thread_target(
            P, attempt.source_thread_id, attempt.target_thread_id
        )
    # Immutable history/ownership facts come from the original actual group,
    # not arbitrary SQL or a synthesized claim/receipt used as permission.
    values = list(group(attempt, at=actual.verified_at, target=target))
    values[0] = actual
    return tuple(values)


def assert_no_group(state, attempt):
    with view(state) as reader:
        assert reader.get_mapping(P, attempt.source_message_id) is None
        assert reader.get_attempt(P, attempt.attempt_id) == attempt
    for table in ("mapping_history", "target_ownership", "thread_targets"):
        assert state[1].execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)


@pytest.mark.parametrize(
    "visibility", [Visibility.NORMAL, Visibility.SPAM, Visibility.TRASH]
)
def test_actual_known_result_verifies_complete_group_and_visibility_distinctly(
    state, visibility
):
    original, _, acquired, attempt = inserted(state)
    values = group(attempt, visibility=visibility)
    receipt = verify(state, attempt, values)
    assert receipt.object_id == attempt.attempt_id and receipt.revision == Revision(3)
    assert receipt.disposition == "updated"
    with view(state) as reader:
        actual = reader.get_attempt(P, attempt.attempt_id)
        assert actual == replace(
            attempt,
            state=InsertState.VERIFIED,
            verified_at=NOW,
            visibility=visibility,
            revision=Revision(3),
        )
        mapped = reader.get_mapping(P, attempt.source_message_id)
        assert mapped == values[0]
        assert (
            reader.get_thread_target(
                P, attempt.source_thread_id, attempt.target_thread_id
            )
            == values[3]
        )
        assert reader.get_thread_anchor(P, attempt.source_thread_id) == values[3]
        completed = reader.get_job(P, original.job_id)
        assert completed.state.value == "completed" and completed.revision == Revision(
            2
        )
        assert reader.counts(P, None).confirmed_mappings.value == 1
    assert actual.claim_id == acquired.claim_id
    assert state[1].execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)
    for table in (
        "message_mappings",
        "mapping_history",
        "target_ownership",
        "thread_targets",
    ):
        assert state[1].execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (1,)


def test_actual_inserted_attention_completes_original_and_recovery_without_reclaim(
    state,
):
    original, _, _, attempt = inserted(state)
    attempt = attention(state, attempt)
    old_recovery = recovery(state, attempt)
    assert state[1].execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)
    receipt = verify(state, attempt)
    assert receipt.revision == Revision(4)
    with view(state) as reader:
        assert reader.get_job(P, original.job_id).state.value == "completed"
        actual_recovery = reader.get_job(P, old_recovery.job_id)
        assert actual_recovery.state.value == "completed"
        assert actual_recovery.origin_epoch_id == old_recovery.origin_epoch_id
        assert actual_recovery.subject == old_recovery.subject
        assert actual_recovery.created_at == old_recovery.created_at
        assert actual_recovery.revision.value == old_recovery.revision.value + 1
        assert reader.get_attempt(P, attempt.attempt_id).error_code is None
    assert state[1].execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)
    assert state[1].execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (2,)


@pytest.mark.parametrize("branch", ["normal", "attention"])
@pytest.mark.parametrize("other_state", ["queued", "needs_attention"])
def test_actual_mapping_preserves_epoch_membership_and_unique_success_counts(
    state, branch, other_state
):
    original, _, _, attempt = inserted(state)
    connection, session = state[1:3]
    for n in (700, 701):
        with session.transaction() as uow:
            epochs.start_epoch(uow, P, selected_epoch(n), ())
            receipt = jobs.enqueue(
                uow,
                P,
                replace(original, job_id=lid(n + 100), origin_epoch_id=lid(n)),
            )
            assert receipt.object_id == original.job_id
    if branch == "attention":
        attempt = attention(state, attempt)
        work = recovery(state, attempt)
        assert work.origin_epoch_id == original.origin_epoch_id
    unrelated = replace(job(900), origin_epoch_id=lid(701))
    with session.transaction() as uow:
        jobs.enqueue(uow, P, unrelated)
        if other_state == "needs_attention":
            jobs.defer_job(
                uow,
                P,
                unrelated.job_id,
                "needs_attention",
                ErrorCode.CONSISTENCY_FAILURE,
                None,
                RevisionGuard(Revision(0)),
            )
    members = connection.execute(
        "SELECT epoch_id,job_id FROM epoch_jobs ORDER BY epoch_id,job_id"
    ).fetchall()
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_epoch(
            uow,
            P,
            lid(700),
            EpochState.COMPLETED,
            True,
            Count(1),
            RevisionGuard(Revision(0)),
        )
    verify(state, attempt)
    assert (
        connection.execute(
            "SELECT epoch_id,job_id FROM epoch_jobs ORDER BY epoch_id,job_id"
        ).fetchall()
        == members
    )
    with view(state) as reader:
        for n in (700, 701):
            snapshot = reader.counts(P, lid(n))
            # Original and recovery can both be completed work, but only one
            # source message is a confirmed success, never two attempts/jobs.
            assert snapshot.confirmed_mappings == Count(1)
            completed = next(
                x for x in snapshot.by_job_state if x.state.value == "completed"
            )
            assert completed.count == Count(2 if branch == "attention" else 1)
            assert reader.get_epoch(P, lid(n)).state is EpochState.PREPARED
        assert reader.get_job(P, original.job_id).origin_epoch_id is None
        assert reader.get_job(P, unrelated.job_id).state.value == other_state
    with session.transaction() as uow:
        epochs.advance_epoch(
            uow,
            P,
            lid(700),
            EpochState.COMPLETED,
            True,
            Count(1),
            RevisionGuard(Revision(0)),
        )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_epoch(
            uow,
            P,
            lid(701),
            EpochState.COMPLETED,
            True,
            Count(1),
            RevisionGuard(Revision(0)),
        )
    with view(state) as reader:
        assert reader.get_epoch(P, lid(700)).state is EpochState.COMPLETED
        assert reader.get_epoch(P, lid(701)).state is EpochState.PREPARED


@pytest.mark.parametrize("branch", ["normal", "attention"])
def test_missing_stored_semantic_pair_cannot_be_filled_by_arbitrary_mapping(
    state, branch
):
    _, _, _, attempt = inserted(state, pair=False)
    if branch == "attention":
        attempt = attention(state, attempt)
    with pytest.raises(StorageFailure):
        verify(state, attempt)
    assert_no_group(state, attempt)


def test_unknown_attention_cannot_be_adopted_as_known_mapping(state):
    _, _, _, old = ready(state)
    attempt = replace(
        pending(old),
        state=InsertState.NEEDS_ATTENTION,
        error_code=ErrorCode.ATTRIBUTION_UNKNOWN,
    )
    record(state, attempt)
    # Supplying plausible target rows cannot manufacture direct-response facts.
    fake = replace(
        known(old),
        semantic_digest=Sha256Hex("b" * 64),
        semantic_version=PolicyVersion("synthetic-v1"),
    )
    with pytest.raises(StorageFailure):
        verify(state, attempt, group(fake))
    assert_no_group(state, attempt)


@pytest.mark.parametrize("change", ["stop", "retrack", "pause", "restore"])
def test_old_dispatched_effect_can_be_verified_without_new_admission(state, change):
    original, tracked, _, attempt = inserted(state)
    with state[2].transaction() as uow:
        if change in {"stop", "retrack"}:
            policy.stop_thread(
                uow,
                P,
                tracked.source_thread_id,
                tracked.generation,
                NOW,
                ThreadStopReason.MANUAL_STOP,
            )
        if change == "retrack":
            new, admission = thread_rows(generation=3, admission_revision=2)
            policy.admit_thread(
                uow,
                P,
                new,
                admission,
                (),
                ThreadGenerationGuardTracked(
                    "tracked",
                    reads.get_thread(uow, P, tracked.source_thread_id).generation,
                ),
            )
        if change == "pause":
            uow._execute(
                "UPDATE projections SET daemon_paused=1 WHERE projection_id=?",
                (P.value,),
            )
        if change == "restore":
            uow._execute(
                "UPDATE projections SET restore_state='revalidation_required' "
                "WHERE projection_id=?",
                (P.value,),
            )
    with view(state) as reader:
        before_thread = reader.get_thread(P, tracked.source_thread_id)
        before_projection = reader.get_projection(P)
    verify(state, attempt)
    with view(state) as reader:
        assert reader.get_thread(P, tracked.source_thread_id) == before_thread
        assert reader.get_projection(P) == before_projection
        assert reader.get_job(P, original.job_id).state.value == "completed"
    assert state[1].execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (1,)


@pytest.mark.parametrize(
    "bad", ["claim", "owner", "phase", "job_revision", "generation"]
)
def test_normal_branch_requires_exact_current_verifying_acquisition(state, bad):
    _, _, acquired, attempt = inserted(state)
    with pytest.raises(StorageFailure), state[2].transaction() as uow:
        current = replace(acquired, phase=ClaimPhase.VERIFYING)
        changes = {
            "claim": {"claim_id": lid(999)},
            "owner": {"owner_run_id": lid(999)},
            "phase": {"phase": ClaimPhase.PREPARING},
            "job_revision": {"job_revision": Revision(0)},
            "generation": {"thread_generation": Generation(2)},
        }
        uow._execute(
            "DELETE FROM job_claims WHERE projection_id=? AND job_id=?",
            (P.value, attempt.job_id.value),
        )
        _insert(
            uow,
            P,
            "job_claims",
            JobClaimRow(P, attempt.job_id, replace(current, **changes[bad])),
        )
        mappings.verify_mapping(
            uow, P, attempt.attempt_id, *group(attempt), RevisionGuard(attempt.revision)
        )
    assert_no_group(state, attempt)


@pytest.mark.parametrize(
    "bad", ["queued_recovery", "missing_recovery", "wrong_error", "wrong_priority"]
)
def test_attention_branch_cannot_resume_or_manufacture_recovery_work(state, bad):
    _, _, _, attempt = inserted(state)
    attempt = attention(state, attempt)
    current = recovery(state, attempt)
    with state[2].transaction() as uow:
        if bad == "missing_recovery":
            uow._execute(
                "DELETE FROM sync_jobs WHERE projection_id=? AND job_id=?",
                (P.value, current.job_id.value),
            )
        elif bad == "queued_recovery":
            uow._execute(
                "UPDATE sync_jobs SET state='queued',last_error_code=NULL "
                "WHERE projection_id=? AND job_id=?",
                (P.value, current.job_id.value),
            )
        elif bad == "wrong_error":
            uow._execute(
                "UPDATE sync_jobs SET last_error_code='network_unavailable' "
                "WHERE projection_id=? AND job_id=?",
                (P.value, current.job_id.value),
            )
        else:
            uow._execute(
                "DELETE FROM sync_jobs WHERE projection_id=? AND job_id=?",
                (P.value, current.job_id.value),
            )
            _insert(
                uow,
                P,
                "sync_jobs",
                replace(current, priority=Priority.REALTIME),
            )
    with pytest.raises(StorageFailure):
        verify(state, attempt)
    assert_no_group(state, attempt)


@pytest.mark.parametrize(
    "bad",
    [
        "revision",
        "source",
        "history_time",
        "superseded",
        "ownership",
        "first_owner",
        "anchor",
        "audit",
        "visibility",
    ],
)
def test_four_row_identity_time_and_first_map_inputs_refuse_atomically(state, bad):
    _, _, _, attempt = inserted(state)
    values = list(group(attempt))
    if bad == "revision":
        values[0] = replace(values[0], mapping_revision=Revision(2))
    elif bad == "source":
        values[0] = replace(values[0], source_message_id=ProviderId("other-source"))
    elif bad == "history_time":
        values[1] = replace(
            values[1], verified_at=Timestamp(NOW.value + timedelta(seconds=1))
        )
    elif bad == "superseded":
        values[1] = replace(values[1], superseded_at=NOW)
    elif bad == "ownership":
        values[2] = replace(values[2], first_attempt_id=lid(999))
    elif bad == "first_owner":
        values[3] = replace(values[3], first_attempt_id=lid(999))
    elif bad == "anchor":
        values[3] = replace(values[3], anchor=False)
    elif bad == "audit":
        values[0] = replace(values[0], last_audit_at=NOW, target_present=True)
    else:
        values[0] = replace(values[0], visibility=Visibility.UNKNOWN)
    with pytest.raises(StorageFailure):
        verify(state, attempt, tuple(values))
    assert_no_group(state, attempt)


def next_message(
    state, n, *, target_thread="synthetic-target-thread", target_message=None
):
    original = job(n)
    with state[2].transaction() as uow:
        jobs.enqueue(uow, P, original)
    acquired, _ = claim(state[2], state[3], original)
    prepared = attempt_fixture(original, acquired, n + 1000, InsertState.PREPARED)
    prepare(state[2], prepared)
    dispatch(state[2], prepared)
    row = replace(
        known(get_attempt(state, prepared.attempt_id)),
        target_message_id=ProviderId(target_message or f"target-{n}"),
        target_thread_id=ProviderId(target_thread),
        semantic_digest=Sha256Hex("b" * 64),
        semantic_version=PolicyVersion("synthetic-mime-v1"),
    )
    record(state, row)
    return row


def test_shared_thread_target_retains_first_facts_and_fallback_does_not_switch_anchor(
    state,
):
    _, _, _, first = inserted(state)
    verify(state, first)
    with view(state) as reader:
        anchor = reader.get_thread_anchor(P, first.source_thread_id)
    second = next_message(state, 101)
    values = group(second, target=anchor)
    verify(state, second, values)
    third = next_message(state, 102, target_thread="synthetic-fallback-thread")
    verify(state, third, group(third, anchor=False))
    with view(state) as reader:
        assert reader.get_thread_anchor(P, first.source_thread_id) == anchor
        assert (
            reader.get_thread_target(
                P, second.source_thread_id, second.target_thread_id
            )
            == anchor
        )
        fallback = reader.get_thread_target(
            P, third.source_thread_id, third.target_thread_id
        )
        assert not fallback.anchor and fallback.first_attempt_id == third.attempt_id
        assert reader.counts(P, None).confirmed_mappings.value == 3
    assert state[1].execute("SELECT COUNT(*) FROM thread_targets").fetchone() == (2,)


@pytest.mark.parametrize(
    "bad", ["first_owner", "anchor", "created_at", "foreign_target"]
)
def test_reused_thread_target_and_target_ownership_cannot_be_reassigned(state, bad):
    _, _, _, first = inserted(state)
    verify(state, first)
    with view(state) as reader:
        old_target = reader.get_thread_anchor(P, first.source_thread_id)
    second = next_message(
        state,
        101,
        target_message=first.target_message_id.value
        if bad == "foreign_target"
        else None,
    )
    changes = {
        "first_owner": {"first_attempt_id": second.attempt_id},
        "anchor": {"anchor": False},
        "created_at": {"created_at": Timestamp(NOW.value + timedelta(seconds=1))},
        "foreign_target": {},
    }
    with pytest.raises(StorageFailure):
        verify(state, second, group(second, target=replace(old_target, **changes[bad])))
    with view(state) as reader:
        assert reader.get_attempt(P, second.attempt_id) == second
        assert reader.get_mapping(P, second.source_message_id) is None
        assert reader.counts(P, None).confirmed_mappings.value == 1


def test_lost_ack_reopen_current_read_replay_and_post_audit_facts_are_zero_write(state):
    _, _, _, attempt = inserted(state)
    verify(state, attempt)
    with pytest.raises(StorageFailure):
        verify(state, attempt)
    path, _, session, info = state
    session.close()
    connection = sqlite3.connect(path, autocommit=True)
    reopened = _attach_writer(connection, info)
    try:
        actual_state = path, connection, reopened, info
        actual = get_attempt(actual_state)
        current = observed_group(actual_state, actual)
        before = connection.total_changes
        assert verify(actual_state, actual, current).disposition == "replayed"
        assert connection.total_changes == before
        with reopened.transaction() as uow:
            mappings.record_target_audit(
                uow,
                P,
                actual.source_message_id,
                False,
                Visibility.TRASH,
                NOW,
                RevisionGuard(Revision(1)),
            )
        with pytest.raises(StorageFailure):
            verify(actual_state, actual, current)
        audited = observed_group(actual_state, actual)
        before = connection.total_changes
        assert verify(actual_state, actual, audited).disposition == "replayed"
        assert connection.total_changes == before
        assert get_attempt(actual_state).visibility is Visibility.NORMAL
    finally:
        reopened.close()


@pytest.mark.parametrize("bad", ["missing_history", "job", "recovery"])
def test_damaged_verified_group_is_not_replayed_or_repaired(state, bad):
    _, _, _, attempt = inserted(state)
    if bad == "recovery":
        attempt = attention(state, attempt)
    verify(state, attempt)
    actual = get_attempt(state)
    values = observed_group(state, actual)
    recovered = recovery(state, actual) if bad == "recovery" else None
    with state[2].transaction() as uow:
        if bad == "missing_history":
            # Damage the deferred cyclic relation in a test-only transaction
            # without disabling schema guards is not possible; instead supply a
            # conflicting immutable historical identity and require refusal.
            values = (
                values[0],
                replace(values[1], target_thread_id=ProviderId("wrong-history")),
                *values[2:],
            )
        elif bad == "job":
            uow._execute(
                "UPDATE sync_jobs SET state='needs_attention',"
                "last_error_code='consistency_failure' "
                "WHERE projection_id=? AND job_id=?",
                (P.value, actual.job_id.value),
            )
        else:
            uow._execute(
                "UPDATE sync_jobs SET state='needs_attention',"
                "last_error_code='consistency_failure' "
                "WHERE projection_id=? AND job_id=?",
                (P.value, recovered.job_id.value),
            )
    with pytest.raises(StorageFailure):
        verify(state, actual, values)


@pytest.mark.parametrize(
    "table",
    [
        "mapping_history",
        "message_mappings",
        "target_ownership",
        "thread_targets",
        "insert_attempts",
        "sync_jobs",
        "job_claims",
        "audit_events",
    ],
)
def test_each_group_write_fault_caught_inside_uow_rolls_back_and_reopens(state, table):
    _, _, _, attempt = inserted(state)
    operation = (
        "UPDATE"
        if table in {"insert_attempts", "sync_jobs"}
        else "DELETE"
        if table == "job_claims"
        else "INSERT"
    )
    state[1].execute(
        f"CREATE TEMP TRIGGER mapping_fault AFTER {operation} ON {table} "
        "BEGIN SELECT RAISE(ABORT,'SYNTHETIC_PRIVATE_PROVIDER_ERROR'); END"
    )
    with (
        pytest.raises(StorageFailure),
        state[2].transaction() as uow,
        suppress(StorageFailure),
    ):
        mappings.verify_mapping(
            uow, P, attempt.attempt_id, *group(attempt), RevisionGuard(attempt.revision)
        )
    path, _, session, info = state
    session.close()
    reopened = _attach_writer(sqlite3.connect(path, autocommit=True), info)
    try:
        actual_state = path, reopened._connection, reopened, info
        assert_no_group(actual_state, attempt)
        with view(actual_state) as reader:
            assert reader.get_job(P, attempt.job_id).state.value == "claimed"
        assert reopened._connection.execute(
            "SELECT phase FROM job_claims"
        ).fetchone() == ("verifying",)
        assert reopened._connection.execute("PRAGMA integrity_check").fetchone() == (
            "ok",
        )
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "bad", ["clock", "attempt_overflow", "job_overflow", "known_visibility"]
)
def test_time_revision_overflow_and_conflicting_known_visibility_refuse(state, bad):
    _, _, _, attempt = inserted(
        state,
        visibility=Visibility.SPAM if bad == "known_visibility" else Visibility.UNKNOWN,
    )
    values = group(attempt)
    if bad == "clock":
        values = group(attempt, at=Timestamp(NOW.value - timedelta(microseconds=1)))
    elif bad in {"attempt_overflow", "job_overflow"}:
        with state[2].transaction() as uow:
            if bad == "attempt_overflow":
                uow._execute(
                    "UPDATE insert_attempts SET revision=? "
                    "WHERE projection_id=? AND attempt_id=?",
                    (MAX_INTEGER, P.value, attempt.attempt_id.value),
                )
            else:
                uow._execute(
                    "UPDATE sync_jobs SET revision=? "
                    "WHERE projection_id=? AND job_id=?",
                    (MAX_INTEGER, P.value, attempt.job_id.value),
                )
                uow._execute(
                    "DELETE FROM job_claims WHERE projection_id=? AND job_id=?",
                    (P.value, attempt.job_id.value),
                )
                _insert(
                    uow,
                    P,
                    "job_claims",
                    JobClaimRow(
                        P,
                        attempt.job_id,
                        Claim(
                            attempt.claim_id,
                            state[3].owner_run_id,
                            NOW,
                            Generation(1),
                            Revision(MAX_INTEGER),
                            ClaimPhase.VERIFYING,
                        ),
                    ),
                )
        attempt = get_attempt(state)
    with pytest.raises(StorageFailure):
        verify(state, attempt, values)
    assert_no_group(state, attempt)


def test_named_thread_reads_reject_writer_context_wrongtypes_and_foreign_thread(state):
    _, _, _, attempt = inserted(state)
    verify(state, attempt)
    with view(state) as reader:
        assert (
            reader.get_thread_anchor(
                ProjectionId("missing-projection"), attempt.source_thread_id
            )
            is None
        )
        assert reader.call(
            "guard_thread_reads",
            P,
            source=attempt.source_thread_id.value,
            target=attempt.target_thread_id.value,
        ) == {"actual_child_assertions": True}
    with state[2].transaction() as uow:
        with pytest.raises(StorageFailure):
            reads.get_thread_anchor(uow, P, attempt.source_thread_id)
        assert not uow._failed


def test_mapping_private_boundaries_and_later_failure_rollback_prior_group(
    state, capsys, caplog
):
    _, _, _, attempt = inserted(state)
    sentinels = markers()

    class Foreign:
        def __repr__(self):
            raise AssertionError("private repr must not execute")

    with pytest.raises(StorageFailure) as caught, state[2].transaction() as uow:
        mappings.verify_mapping(
            uow, P, attempt.attempt_id, *group(attempt), RevisionGuard(attempt.revision)
        )
        with suppress(StorageFailure):
            mappings.verify_mapping(
                uow,
                P,
                attempt.attempt_id,
                Foreign(),
                *group(attempt)[1:],
                RevisionGuard(Revision(3)),
            )
    assert str(caught.value) == "consistency_failure"
    assert_no_group(state, attempt)
    verify(state, attempt)
    inspect_sqlite(state[1], sentinels)
    inspect_files(state[0].parent, list(state[0].parent.iterdir()), sentinels)
    capture = capsys.readouterr()
    assert_private_boundary(
        capture.out + capture.err + caplog.text + str(caught.value),
        sentinels,
        Profile.PUBLIC,
    )
