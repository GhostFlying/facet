"""IR-01..10: actual SQL result consequences, not Gmail invocation evidence."""

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
from test_db_epochs import epoch
from test_db_intents import dispatch, prepare, setup
from test_db_repositories import job, view
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
    Claim,
    ClaimPhase,
    Count,
    ErrorCode,
    InsertState,
    OutcomeCertainty,
    PolicyVersion,
    Priority,
    ProviderId,
    Revision,
    Sha256Hex,
    Timestamp,
    Visibility,
)
from facet.contracts.records import JobSubjectRecoverInsert
from facet.db.codecs import (
    MAX_INTEGER,
    AttributionKind,
    PageLimit,
    StorageFailure,
    ThreadStopReason,
)
from facet.db.connection import _attach_writer
from facet.db.models import JobClaimRow, RevisionGuard
from facet.db.repositories import epochs, intents, jobs, policy
from facet.db.repositories.serialization import _encode_row


def get_attempt(state, attempt_id=None):
    with view(state) as reader:
        return reader.get_attempt(P, attempt_id or lid(200))


def ready(state, *, dispatched=True):
    _, _, session, _ = state
    original, tracked, acquired, _, prepared = setup(state)
    prepare(session, prepared)
    if dispatched:
        dispatch(session, prepared)
    return original, tracked, acquired, get_attempt(state)


def known(old):
    return replace(
        old,
        state=InsertState.KNOWN_INSERTED,
        certainty=OutcomeCertainty.INSERTED,
        target_message_id=ProviderId("synthetic-target-msg"),
        target_thread_id=ProviderId("synthetic-target-thread"),
        attribution=AttributionKind.DIRECT_RESPONSE,
        result_at=NOW,
        revision=Revision(old.revision.value + 1),
    )


def pending(old):
    return replace(
        old,
        state=InsertState.PENDING_RECOVERY,
        result_at=NOW,
        error_code=ErrorCode.INSERT_RESULT_UNKNOWN,
        revision=Revision(old.revision.value + 1),
    )


def record(state, row, *, guard=None, observed=NOW):
    with state[2].transaction() as uow:
        return intents.record_attempt_result(
            uow,
            P,
            row,
            observed,
            RevisionGuard(guard or Revision(row.revision.value - 1)),
        )


def selected_epoch(n):
    value = epoch(n)
    return replace(
        value, decision=replace(value.decision, ruleset_revision=Revision(1))
    )


def recovery(state, row):
    with view(state) as reader:
        page = reader.list_jobs(
            P,
            PageLimit(500),
            None,
        )
        return next(j for j in page.items if j.kind.value == "recover_insert")


def test_known_result_keeps_verifying_claim_and_lost_ack_replay_is_zero_write(state):
    path, connection, session, info = state
    original, _, acquired, old = ready(state)
    row = known(old)
    result = record(state, row)
    assert result.object_id == row.attempt_id and result.revision == Revision(2)
    assert connection.execute(
        "SELECT claim_id,job_revision,phase FROM job_claims WHERE job_id=?",
        (original.job_id.value,),
    ).fetchone() == (acquired.claim_id.value, 1, "verifying")
    session.close()
    reopened = sqlite3.connect(path, autocommit=True)
    new_session = _attach_writer(reopened, info)
    reopened_state = path, reopened, new_session, info
    try:
        actual = get_attempt(reopened_state)
        assert actual == row
        before = reopened.total_changes
        replay = record(reopened_state, actual, guard=actual.revision)
        assert replay.disposition == "replayed" and reopened.total_changes == before
        with view(reopened_state) as reader:
            assert reader.get_job(P, original.job_id).state.value == "claimed"
            assert reader.counts(P, None).confirmed_mappings.value == 0
    finally:
        new_session.close()


@pytest.mark.parametrize("state_kind", ["known", "pending", "attention"])
def test_poststop_dispatched_results_are_retained_without_new_admission(
    state, state_kind
):
    _, connection, session, _ = state
    original, tracked, _, old = ready(state)
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
            "UPDATE projections SET daemon_paused=1 WHERE projection_id=?", (P.value,)
        )
    row = known(old) if state_kind == "known" else pending(old)
    if state_kind == "attention":
        row = replace(
            row,
            state=InsertState.NEEDS_ATTENTION,
            error_code=ErrorCode.ATTRIBUTION_UNKNOWN,
        )
    record(state, row)
    with view(state) as reader:
        assert reader.get_attempt(P, row.attempt_id) == row
        thread = reader.get_thread(P, tracked.source_thread_id)
        assert not thread.active and thread.generation.value == 2
        assert reader.counts(P, None).confirmed_mappings.value == 0
        assert (
            reader.get_job(P, original.job_id).state.value
            == {
                "known": "claimed",
                "pending": "blocked",
                "attention": "needs_attention",
            }[state_kind]
        )
    assert connection.execute("SELECT COUNT(*) FROM insert_attempts").fetchone() == (1,)


@pytest.mark.parametrize("bad", ["stale", "same_revision", "skip", "fake_increment"])
def test_result_revision_guard_is_actual_attempt_and_rejects_fake_mutation(state, bad):
    _, _, _, old = ready(state)
    row, guard = known(old), old.revision
    if bad == "stale":
        guard = Revision(0)
    elif bad == "same_revision":
        row = replace(row, revision=old.revision)
    elif bad == "skip":
        row = replace(row, revision=Revision(3))
    else:
        row = replace(old, revision=Revision(2))
    with pytest.raises(StorageFailure):
        record(state, row, guard=guard)
    assert get_attempt(state) == old


@pytest.mark.parametrize(
    "bad",
    [
        "claim",
        "job",
        "source",
        "thread",
        "binding",
        "raw",
        "dispatch",
        "result_time",
        "observed_time",
        "certainty",
        "visibility",
        "counter",
        "deadline",
        "error",
    ],
)
def test_result_preserves_identity_axes_times_and_closed_schedule(state, bad):
    _, _, _, old = ready(state)
    changes = {
        "claim": {"claim_id": lid(999)},
        "job": {"job_id": lid(999)},
        "source": {"source_message_id": ProviderId("other-source")},
        "thread": {"source_thread_id": ProviderId("other-thread")},
        "binding": {"binding_revision": Revision(1)},
        "raw": {"raw_digest": Sha256Hex("b" * 64)},
        "dispatch": {
            "dispatch_started_at": Timestamp(NOW.value + timedelta(seconds=1))
        },
        "result_time": {"result_at": Timestamp(NOW.value - timedelta(seconds=1))},
        "certainty": {"certainty": OutcomeCertainty.UNKNOWN},
        "counter": {"recovery_checks": Count(1)},
        "deadline": {"next_recovery_at": NOW},
        "error": {"error_code": ErrorCode.NETWORK_UNAVAILABLE},
    }
    row = known(old)
    if bad == "visibility":
        row = replace(pending(old), visibility=Visibility.NORMAL)
    elif bad != "observed_time":
        row = replace(row, **changes[bad])
    observed = (
        Timestamp(NOW.value - timedelta(seconds=1)) if bad == "observed_time" else NOW
    )
    with pytest.raises(StorageFailure):
        record(state, row, observed=observed)
    assert get_attempt(state) == old


def test_actual_nullable_fidelity_enrichment_does_not_change_known_provider_facts(
    state,
):
    _, _, _, old = ready(state)
    connection = state[1]
    initial = known(old)
    record(state, initial)
    enriched = replace(
        initial,
        revision=Revision(3),
        semantic_digest=Sha256Hex("b" * 64),
        semantic_version=PolicyVersion("synthetic-mime-v1"),
        visibility=Visibility.SPAM,
    )
    receipt = record(state, enriched)
    assert receipt.revision == Revision(3) and get_attempt(state) == enriched
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (1,)
    for changed in (
        replace(
            enriched, revision=Revision(4), target_message_id=ProviderId("different")
        ),
        replace(
            enriched, revision=Revision(4), semantic_digest=None, semantic_version=None
        ),
        replace(enriched, revision=Revision(4), semantic_digest=Sha256Hex("c" * 64)),
        replace(enriched, revision=Revision(4), visibility=Visibility.NORMAL),
        replace(enriched, revision=Revision(4), error_code=ErrorCode.FIDELITY_MISMATCH),
    ):
        with pytest.raises(StorageFailure):
            record(state, changed)
        assert get_attempt(state) == enriched


def test_unknown_result_blocks_original_and_preserves_one_old_attempt_recovery(state):
    _, connection, session, _ = state
    original, _, _, old = ready(state)
    row = pending(old)
    record(state, row)
    work = recovery(state, row)
    assert work.state.value == "queued" and work.priority is Priority.RECOVERY
    with view(state) as reader:
        blocked = reader.get_job(P, original.job_id)
        assert blocked.state.value == "blocked"
        assert blocked.last_error_code is ErrorCode.INSERT_RESULT_UNKNOWN
    assert connection.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)
    before = connection.total_changes
    assert record(state, row, guard=row.revision).disposition == "replayed"
    assert connection.total_changes == before
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.defer_job(
            uow,
            P,
            original.job_id,
            "retry_wait",
            ErrorCode.NETWORK_UNAVAILABLE,
            NOW,
            RevisionGuard(blocked.revision),
        )
    with pytest.raises(StorageFailure):
        record(state, replace(known(row), revision=Revision(3)))
    assert get_attempt(state) == row


def test_orphaned_dispatch_marker_materializes_recovery_without_remote_retry(state):
    _, connection, session, _ = state
    original, _, _, old = ready(state)
    with session.transaction() as uow:
        jobs.defer_job(
            uow,
            P,
            original.job_id,
            "needs_attention",
            ErrorCode.INVALID_INPUT,
            None,
            RevisionGuard(Revision(1)),
        )
    with session.transaction() as uow:
        result = intents.reconcile_orphaned_attempt(
            uow, P, old.attempt_id, Timestamp(NOW.value)
        )
    assert result.disposition == "updated"
    assert get_attempt(state).state is InsertState.PENDING_RECOVERY
    work = recovery(state, pending(get_attempt(state)))
    assert work.state.value == "queued"
    with view(state) as reader:
        blocked = reader.get_job(P, original.job_id)
        assert blocked.state.value == "blocked"
        assert blocked.last_error_code is ErrorCode.INSERT_RESULT_UNKNOWN
    assert connection.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)


def test_pending_attention_after_actual_recovery_defer_and_reclaim_is_not_success(
    state,
):
    _, connection, session, info = state
    original, _, _, old = ready(state)
    row = pending(old)
    record(state, row)
    work = recovery(state, row)
    first = Claim(
        lid(400),
        info.owner_run_id,
        NOW,
        old.generation,
        Revision(1),
        ClaimPhase.PREPARING,
    )
    with session.transaction() as uow:
        jobs.claim(uow, P, work.job_id, first, RevisionGuard(Revision(0)), NOW)
    with session.transaction() as uow:
        jobs.defer_job(
            uow,
            P,
            work.job_id,
            "retry_wait",
            ErrorCode.NETWORK_UNAVAILABLE,
            NOW,
            RevisionGuard(Revision(1)),
        )
    second = replace(first, claim_id=lid(401), job_revision=Revision(3))
    with session.transaction() as uow:
        jobs.claim(uow, P, work.job_id, second, RevisionGuard(Revision(2)), NOW)
    attentive = replace(
        row,
        state=InsertState.NEEDS_ATTENTION,
        error_code=ErrorCode.DUPLICATE_CANDIDATES,
        revision=Revision(3),
    )
    record(state, attentive)
    with view(state) as reader:
        actual = reader.get_job(P, work.job_id)
        assert actual.state.value == "needs_attention" and actual.revision.value == 4
        assert actual.last_error_code is ErrorCode.DUPLICATE_CANDIDATES
        assert actual.attempt_count.value == 2
        assert reader.get_job(P, original.job_id).state.value == "needs_attention"
        assert reader.counts(P, None).confirmed_mappings.value == 0
    assert connection.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)
    assert get_attempt(state).claim_id == old.claim_id
    before = connection.total_changes
    record(state, attentive, guard=attentive.revision)
    assert connection.total_changes == before


@pytest.mark.parametrize(
    "bad", ["owner", "phase", "generation", "claim_revision", "deadline"]
)
def test_pending_attention_rejects_invalid_recovery_acquisition(state, bad):
    _, _, session, info = state
    _, _, _, old = ready(state)
    row = pending(old)
    record(state, row)
    work = recovery(state, row)
    acquired = Claim(
        lid(400),
        info.owner_run_id,
        NOW,
        old.generation,
        Revision(1),
        ClaimPhase.PREPARING,
    )
    with session.transaction() as uow:
        jobs.claim(uow, P, work.job_id, acquired, RevisionGuard(Revision(0)), NOW)
    fields = {
        "owner": ("job_claims", "owner_run_id", lid(999).value),
        "phase": ("job_claims", "phase", "dispatching"),
        "generation": ("job_claims", "thread_generation", 2),
        "claim_revision": ("job_claims", "job_revision", 0),
        "deadline": ("sync_jobs", "next_attempt_at", 0),
    }
    table, column, value = fields[bad]
    # Explicit hostile closed-metadata fixture, not a production bypass.
    if bad in {"owner", "generation", "claim_revision"}:
        # Immutable claim facts cannot be UPDATEd. Allocate a hostile test-only
        # replacement instead, without disabling any schema/trigger guard.
        replacement = replace(
            acquired,
            **{
                "owner": {"owner_run_id": lid(999)},
                "generation": {"thread_generation": type(old.generation)(2)},
                "claim_revision": {"job_revision": Revision(0)},
            }[bad],
        )
        state[1].execute("DELETE FROM job_claims WHERE job_id=?", (work.job_id.value,))
        state[1].execute(
            "INSERT INTO job_claims VALUES(?,?,?,?,?,?,?,?)",
            _encode_row("job_claims", JobClaimRow(P, work.job_id, replacement)),
        )
    else:
        state[1].execute(
            f"UPDATE {table} SET {column}=? WHERE job_id=?", (value, work.job_id.value)
        )
    attentive = replace(
        row,
        state=InsertState.NEEDS_ATTENTION,
        error_code=ErrorCode.DUPLICATE_CANDIDATES,
        revision=Revision(3),
    )
    with pytest.raises(StorageFailure):
        record(state, attentive)
    assert get_attempt(state) == row


@pytest.mark.parametrize(
    "failure", ["job", "recovery", "audit", "epoch_join", "caught_later"]
)
def test_result_group_rolls_back_every_partial_mutation_and_reopens(state, failure):
    path, connection, session, info = state
    original, _, _, old = ready(state)
    row = pending(old)
    if failure == "epoch_join":
        with session.transaction() as uow:
            epochs.start_epoch(uow, P, selected_epoch(700), ())
            jobs.enqueue(uow, P, replace(original, origin_epoch_id=lid(700)))
    if failure != "caught_later":
        target = {
            "job": "sync_jobs",
            "recovery": "sync_jobs",
            "audit": "audit_events",
            "epoch_join": "epoch_jobs",
        }[failure]
        verb = "UPDATE" if failure == "job" else "INSERT"
        connection.execute(
            f"CREATE TEMP TRIGGER fail_result AFTER {verb} ON {target} "
            "BEGIN SELECT RAISE(ABORT,'synthetic-private-exception'); END"
        )
    with (
        pytest.raises(StorageFailure),
        session.transaction() as uow,
        suppress(StorageFailure),
    ):
        intents.record_attempt_result(uow, P, row, NOW, RevisionGuard(old.revision))
        if failure == "caught_later":
            jobs.enqueue(uow, P.value, job(999))
    assert get_attempt(state) == old
    if failure != "caught_later":
        connection.execute("DROP TRIGGER fail_result")
    session.close()
    reopened = sqlite3.connect(path, autocommit=True)
    reopened_session = _attach_writer(reopened, info)
    try:
        reopened_state = path, reopened, reopened_session, info
        assert get_attempt(reopened_state) == old
        assert reopened.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (1,)
        assert reopened.execute(
            "SELECT phase FROM job_claims WHERE job_id=?", (original.job_id.value,)
        ).fetchone() == ("dispatching",)
    finally:
        reopened_session.close()


def test_result_failures_and_stored_files_never_forward_raw_exceptions(
    state, capsys, caplog
):
    _, _, _, old = ready(state)
    connection = state[1]
    row = pending(old)

    class Foreign:
        def __repr__(self):
            raise AssertionError("must not stringify arbitrary private object")

    with pytest.raises(StorageFailure) as error:
        record(state, row, observed=Foreign())
    assert_private_boundary(str(error.value), markers(), Profile.LOG)
    record(state, row)
    inspect_sqlite(connection, markers())
    inspect_files(state[0].parent, list(state[0].parent.iterdir()), markers())
    captured = capsys.readouterr()
    assert_private_boundary(captured.out, markers(), Profile.LOG)
    assert_private_boundary(captured.err, markers(), Profile.LOG)
    assert_private_boundary(caplog.text, markers(), Profile.LOG)


def test_result_recovery_joins_every_selected_epoch_without_changing_first_origin(
    state,
):
    _, connection, session, _ = state
    original, _, _, old = ready(state)
    for n in (700, 701, 702):
        with session.transaction() as uow:
            epochs.start_epoch(uow, P, selected_epoch(n), ())
            if n != 700:
                jobs.enqueue(
                    uow,
                    P,
                    replace(original, job_id=lid(n + 100), origin_epoch_id=lid(n)),
                )
    existing = replace(
        job(
            300,
            subject=JobSubjectRecoverInsert("recover_insert", old.attempt_id),
            priority=Priority.RECOVERY,
        ),
        origin_epoch_id=lid(700),
    )
    with session.transaction() as uow:
        jobs.enqueue(uow, P, existing)
    before_revision = existing.revision
    record(state, pending(old))
    work = recovery(state, old)
    assert work == existing and work.revision == before_revision
    assert connection.execute(
        "SELECT epoch_id FROM epoch_jobs WHERE job_id=? ORDER BY epoch_id",
        (work.job_id.value,),
    ).fetchall() == [(lid(n).value,) for n in (700, 701, 702)]
    assert get_attempt(state).state is InsertState.PENDING_RECOVERY
    changes = connection.total_changes
    row = get_attempt(state)
    record(state, row, guard=row.revision)
    assert connection.total_changes == changes


@pytest.mark.parametrize(
    "bad",
    ["blocked", "retry_wait", "failed", "cancelled", "attention", "priority", "future"],
)
def test_first_unknown_result_cannot_resume_or_normalize_incompatible_recovery(
    state, bad
):
    _, _, session, _ = state
    _, _, _, old = ready(state)
    existing = job(
        300,
        subject=JobSubjectRecoverInsert("recover_insert", old.attempt_id),
        priority=Priority.REALTIME if bad == "priority" else Priority.RECOVERY,
    )
    if bad == "future":
        future = Timestamp(NOW.value + timedelta(seconds=1))
        existing = replace(existing, created_at=future, updated_at=future)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, existing)
    if bad in {"blocked", "retry_wait"}:
        with session.transaction() as uow:
            jobs.defer_job(
                uow,
                P,
                existing.job_id,
                bad,
                ErrorCode.NETWORK_UNAVAILABLE,
                NOW if bad == "retry_wait" else None,
                RevisionGuard(Revision(0)),
            )
    elif bad in {"failed", "cancelled", "attention"}:
        # Closed externally observed legacy row fixture: the ordinary recovery
        # defer method itself refuses to falsely fail an unknown effect.
        code = (
            ErrorCode.ATTRIBUTION_UNKNOWN
            if bad == "attention"
            else ErrorCode.NETWORK_UNAVAILABLE
        )
        state[1].execute(
            "UPDATE sync_jobs SET state=?,last_error_code=? WHERE job_id=?",
            (
                "needs_attention" if bad == "attention" else bad,
                code.value,
                existing.job_id.value,
            ),
        )
    with pytest.raises(StorageFailure):
        record(state, pending(old))
    assert get_attempt(state) == old
    with view(state) as reader:
        assert reader.get_job(P, old.job_id).state.value == "claimed"


@pytest.mark.parametrize("origin", ["prepared", "dispatch"])
def test_definite_noninsertion_facts_do_not_create_attempt_or_choose_retry(
    state, origin
):
    _, connection, _, _ = state
    original, _, _, old = ready(state, dispatched=origin == "dispatch")
    row = replace(
        old,
        state=InsertState.DEFINITE_NOT_INSERTED,
        certainty=OutcomeCertainty.DEFINITELY_NOT_INSERTED,
        result_at=NOW,
        error_code=ErrorCode.TARGET_AUTH_REQUIRED,
        revision=Revision(old.revision.value + 1),
    )
    record(state, row)
    assert get_attempt(state) == row
    with view(state) as reader:
        assert reader.get_job(P, original.job_id).state.value == "claimed"
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (1,)
    assert connection.execute("SELECT COUNT(*) FROM insert_attempts").fetchone() == (1,)


def test_predispatch_cancellation_is_a_local_fact_not_a_remote_result(state):
    _, _, _, old = ready(state, dispatched=False)
    row = replace(
        old,
        state=InsertState.CANCELLED_BEFORE_DISPATCH,
        result_at=NOW,
        error_code=ErrorCode.GENERATION_STALE,
        revision=Revision(1),
    )
    record(state, row)
    assert get_attempt(state) == row and row.dispatch_started_at is None
    with pytest.raises(StorageFailure):
        record(
            state,
            replace(
                row,
                revision=Revision(2),
                semantic_digest=Sha256Hex("c" * 64),
                semantic_version=PolicyVersion("synthetic-mime-v1"),
            ),
        )


@pytest.mark.parametrize("first", ["direct", "known"])
def test_inserted_attention_retains_target_facts_and_never_reports_success(
    state, first
):
    _, connection, _, _ = state
    original, _, _, old = ready(state)
    inserted = known(old)
    if first == "known":
        record(state, inserted)
        old = inserted
    row = replace(
        inserted,
        state=InsertState.NEEDS_ATTENTION,
        error_code=ErrorCode.FIDELITY_MISMATCH,
        revision=Revision(old.revision.value + 1),
    )
    record(state, row)
    assert get_attempt(state) == row
    with view(state) as reader:
        assert reader.get_job(P, original.job_id).state.value == "needs_attention"
        assert reader.counts(P, None).confirmed_mappings.value == 0
    assert recovery(state, row).state.value == "needs_attention"
    assert connection.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)


def test_result_revision_overflow_is_controlled_and_leaves_marker_unchanged(state):
    _, connection, _, _ = state
    _, _, _, old = ready(state)
    connection.execute(
        "UPDATE insert_attempts SET revision=? WHERE attempt_id=?",
        (MAX_INTEGER, old.attempt_id.value),
    )
    old = get_attempt(state)
    row = replace(known(replace(old, revision=Revision(0))), revision=old.revision)
    with pytest.raises(StorageFailure):
        record(state, row, guard=old.revision)
    assert get_attempt(state) == old


def test_attention_can_join_existing_attention_work_without_rewriting_its_facts(state):
    _, _, session, _ = state
    _, _, _, old = ready(state)
    existing = job(
        300,
        subject=JobSubjectRecoverInsert("recover_insert", old.attempt_id),
        priority=Priority.RECOVERY,
    )
    with session.transaction() as uow:
        jobs.enqueue(uow, P, existing)
        jobs.defer_job(
            uow,
            P,
            existing.job_id,
            "needs_attention",
            ErrorCode.DUPLICATE_CANDIDATES,
            None,
            RevisionGuard(Revision(0)),
        )
    before = recovery(state, old)
    row = replace(
        pending(old),
        state=InsertState.NEEDS_ATTENTION,
        error_code=ErrorCode.DUPLICATE_CANDIDATES,
    )
    record(state, row)
    assert recovery(state, row) == before


def test_result_time_cannot_precede_later_dispatch_even_when_observed_is_later(state):
    _, _, session, _ = state
    _, _, _, old = ready(state, dispatched=False)
    later_dispatch = Timestamp(NOW.value + timedelta(seconds=10))
    with session.transaction() as uow:
        intents.mark_dispatch(
            uow,
            P,
            old.attempt_id,
            old.claim_id,
            later_dispatch,
            RevisionGuard(old.revision),
        )
    old = get_attempt(state)
    row = replace(known(old), result_at=Timestamp(NOW.value + timedelta(seconds=9)))
    with pytest.raises(StorageFailure):
        record(state, row, observed=Timestamp(NOW.value + timedelta(seconds=11)))
    assert get_attempt(state) == old


@pytest.mark.parametrize("bad", ["counter", "deadline", "error"])
def test_same_state_known_result_cannot_patch_schedule_or_error(state, bad):
    _, _, _, old = ready(state)
    row = known(old)
    record(state, row)
    changed = replace(
        row,
        revision=Revision(3),
        **{
            "counter": {"recovery_checks": Count(1)},
            "deadline": {"next_recovery_at": NOW},
            "error": {"error_code": ErrorCode.NETWORK_UNAVAILABLE},
        }[bad],
    )
    with pytest.raises(StorageFailure):
        record(state, changed)
    assert get_attempt(state) == row
