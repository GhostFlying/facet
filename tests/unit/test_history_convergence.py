"""Coverage closes old unadmitted notifications, not selected mail or faults."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from test_projection_worker import _ready_owner, _trusted_parent

from facet.cli.reconcile import _prepare_epoch, _scope
from facet.contracts import (
    Claim,
    ClaimPhase,
    Count,
    ErrorCode,
    Generation,
    JobKind,
    JobState,
    LocalId,
    PolicyVersion,
    Priority,
    ProviderId,
    Revision,
    Role,
    RuleRef,
    SourceEvent,
    Timestamp,
)
from facet.contracts.records import (
    AdmissionRefFutureRule,
    JobSubjectResolveEvent,
    SourceEventKeyMessageAdded,
    ThreadGenerationGuardUntracked,
)
from facet.db.codecs import (
    EventProcessing,
    StorageFailure,
    ThreadStopReason,
    timestamp_to_sql,
)
from facet.db.keys import event_key, job_key
from facet.db.models import (
    JobClaimRow,
    SourceEventRow,
    SyncJobRow,
    ThreadAdmissionRow,
    TrackedThreadRow,
)
from facet.db.repositories import history_convergence, policy
from facet.db.repositories.base import _insert
from facet.gmail.source import (
    CandidateExclusion,
    CandidateExclusionReason,
    CandidateResult,
    DiscoveryItem,
    DiscoveryPage,
)
from facet.reconcile import SourceReconciler
from facet.runtime.dashboard import snapshot_from_owner
from facet.runtime.foreground_runtime import load_persisted_admission
from facet.sync import SourceCandidateAdmission


class EmptySource:
    def __init__(self):
        self.calls = 0

    def discover(self, **kwargs):
        self.calls += 1
        return DiscoveryPage((), None, 0)

    def candidate(self, item):
        pytest.fail("legacy events must not become Gmail scan inputs")


@pytest.fixture
def state(monkeypatch):
    with TemporaryDirectory(dir=_trusted_parent()) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch, seed=False)
        try:
            owner.ensure_reconcile_schema(LocalId(uuid4().hex), b"synthetic-config")
            scope = _scope(owner, owner.config)
            source = EmptySource()
            r = SourceReconciler(
                owner,
                source,
                SourceCandidateAdmission(
                    source, load_persisted_admission(owner, owner.config)
                ),
                scope,
                source_binding_revision=owner.bindings()[Role.SOURCE].binding_revision,
            )
            key = uuid4().hex
            r.prepare(key)
            _prepare_epoch(owner, scope, r.run_id)
            yield owner, r, key
        finally:
            owner.close()


def legacy(
    owner, r, *, at=None, thread="SYNTHETIC_PRIVATE_THREAD", code=None, message=None
):
    at = at or Timestamp(r.scope.window_end.value - timedelta(days=1))
    code = code or ErrorCode.SOURCE_MISSING
    projection = owner.projection_id
    event_id, job_id = LocalId(uuid4().hex), LocalId(uuid4().hex)
    key = SourceEventKeyMessageAdded(
        "message_added",
        projection,
        ProviderId(uuid4().hex),
        ProviderId(message or uuid4().hex),
    )
    e = SourceEventRow(
        projection,
        event_id,
        event_key(projection, key),
        SourceEvent(key, at, ProviderId(thread) if thread else None),
        EventProcessing.SOURCE_MISSING,
        Revision(1),
        code,
    )
    subject = JobSubjectResolveEvent("resolve_event", key)
    j = SyncJobRow(
        projection,
        job_id,
        JobKind.RESOLVE_EVENT,
        Count(1),
        job_key(projection, subject),
        Priority.REALTIME,
        JobState.SOURCE_MISSING,
        Revision(1),
        at,
        at,
        None,
        Count(0),
        code,
        None,
        subject,
    )
    with owner.session.transaction() as uow:
        _insert(uow, projection, "source_events", e)
        _insert(uow, projection, "sync_jobs", j, event_id=event_id)
    return event_id, job_id


def close(owner, r):
    with owner.session.transaction() as uow:
        return history_convergence.converge_covered_history(
            uow, owner.projection_id, r.run_id, Timestamp(datetime.now(UTC))
        )


@pytest.mark.parametrize("reason", list(CandidateExclusionReason))
def test_reconcile_excluded_candidate_is_successful_no_rule(state, reason):
    owner, r, key = state
    item = DiscoveryItem(ProviderId("excluded-message"), ProviderId("excluded-thread"))
    r.source.discover = lambda **kwargs: DiscoveryPage((item,), None, 1)
    r.source.candidate = lambda item: CandidateResult(
        excluded=CandidateExclusion(reason, item.message_id, item.thread_id)
    )
    result = r.run(key, enqueue_candidate=lambda *args: pytest.fail("excluded enqueue"))
    assert (result.listed, result.metadata_success, result.remaining_issue) == (1, 1, 0)
    assert owner._connection.execute(
        "SELECT classification,provider_reason FROM reconcile_candidates"
    ).fetchone() == ("no_rule", reason.value)
    assert owner._connection.execute("SELECT state FROM reconcile_runs").fetchone() == (
        "completed",
    )


def test_successful_finalization_and_replay_preserve_warning(state):
    owner, r, key = state
    legacy(owner, r)
    before = snapshot_from_owner(owner, owner.config, cycle_verified=True)
    assert before["status"].data.health.value == "degraded"
    cursor = owner._connection.execute("SELECT * FROM history_checkpoints").fetchall()
    result = r.run(key)
    assert result.reset == 1
    assert owner._connection.execute(
        "SELECT processing,error_code FROM source_events"
    ).fetchall() == [("consumed", None)]
    assert owner._connection.execute(
        "SELECT state,last_error_code FROM sync_jobs"
    ).fetchall() == [("completed", None)]
    assert owner._connection.execute(
        "SELECT before_state,after_state,error_code FROM audit_events "
        "WHERE error_code='source_missing'"
    ).fetchall() == [("source_missing", "completed", "source_missing")]
    assert owner._connection.execute(
        "SELECT count(*) FROM epoch_jobs WHERE epoch_id=?", (r.run_id.value,)
    ).fetchone() == (1,)
    assert r.run(key) == result
    assert r.source.calls == 1
    snapshots = snapshot_from_owner(owner, owner.config, cycle_verified=True)
    assert snapshots["status"].data.health.value == "healthy"
    assert snapshots["issues"].data.historical_source_warning_count == 1
    assert snapshots["progress"].data.confirmed_messages == 0
    assert (
        owner._connection.execute("SELECT * FROM history_checkpoints").fetchall()
        == cursor
    )
    assert owner._connection.execute(
        "SELECT count(*) FROM insert_attempts"
    ).fetchone() == (0,)


def test_existing_successful_run_replay_closes_preexisting_failure(state, monkeypatch):
    owner, r, key = state
    original = __import__("facet.reconcile", fromlist=["converge_covered_history"])
    monkeypatch.setattr(original, "converge_covered_history", lambda *args: 0)
    legacy(owner, r)
    assert r.run(key).reset == 0
    monkeypatch.setattr(
        original,
        "converge_covered_history",
        history_convergence.converge_covered_history,
    )
    assert r.run(key).reset == 1
    assert r.run(key).reset == 1
    assert r.source.calls == 1


@pytest.mark.parametrize("case", ["late", "unknown_thread", "other_error"])
def test_unproven_notifications_stay_active(state, case):
    owner, r, key = state
    legacy(
        owner,
        r,
        at=Timestamp(r.scope.window_end.value + timedelta(microseconds=1))
        if case == "late"
        else None,
        thread=None if case == "unknown_thread" else "thread-old",
        code=ErrorCode.NETWORK_UNAVAILABLE if case == "other_error" else None,
    )
    assert r.run(key).reset == 0
    assert owner._connection.execute("SELECT state FROM sync_jobs").fetchone() == (
        "source_missing",
    )


@pytest.mark.parametrize(
    "corrupt",
    [
        "UPDATE reconcile_runs SET listed_count=1",
        "UPDATE reconcile_runs SET page_token='incomplete'",
        "UPDATE reconcile_runs SET last_error_code='network_unavailable'",
        "UPDATE reconcile_runs SET remaining_issue_count=1",
        "UPDATE reconcile_runs SET metadata_404_count=1",
        "UPDATE reconcile_runs SET completed_at=NULL",
        "UPDATE reconcile_runs SET ruleset_revision=99",
        "UPDATE reconcile_runs SET source_binding_revision=99",
        "UPDATE reconcile_runs SET created_at="
        "(SELECT applied_at-1 FROM schema_migrations WHERE version=7)",
        "UPDATE reconcile_runs SET window_start=0",
        "UPDATE reconcile_runs SET window_end=window_end+1",
    ],
)
def test_invalid_completed_proof_cannot_close(state, corrupt):
    owner, r, key = state
    r.run(key)
    legacy(owner, r)
    with owner.session.transaction() as uow:
        uow._execute(corrupt)
    with pytest.raises(StorageFailure):
        close(owner, r)
    assert owner._connection.execute("SELECT state FROM sync_jobs").fetchone() == (
        "source_missing",
    )


def test_transaction_failure_rolls_back_run_and_receipts(state, monkeypatch):
    owner, r, key = state
    legacy(owner, r)

    def fail(*args, **kwargs):
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)

    monkeypatch.setattr(history_convergence, "_audit", fail)
    with pytest.raises(StorageFailure):
        r.run(key)
    assert owner._connection.execute("SELECT state FROM reconcile_runs").fetchone() == (
        "draining",
    )
    assert owner._connection.execute("SELECT state FROM sync_jobs").fetchone() == (
        "source_missing",
    )
    assert owner._connection.execute("SELECT count(*) FROM epoch_jobs").fetchone() == (
        0,
    )


@pytest.mark.parametrize("stopped", [False, True])
def test_tracked_and_stopped_threads_are_never_closed(state, stopped):
    owner, r, key = state
    thread_id = ProviderId("thread-protected")
    legacy(owner, r, thread=thread_id.value)
    now = Timestamp(datetime.now(UTC))
    rule_id = LocalId(
        owner._connection.execute("SELECT rule_id FROM rules").fetchone()[0]
    )
    with owner.session.transaction() as uow:
        policy.admit_thread(
            uow,
            owner.projection_id,
            TrackedThreadRow(
                owner.projection_id,
                thread_id,
                True,
                Generation(1),
                now,
                None,
                None,
                Revision(1),
            ),
            ThreadAdmissionRow(
                owner.projection_id,
                thread_id,
                Revision(1),
                Generation(1),
                now,
                AdmissionRefFutureRule(
                    "future_rule",
                    RuleRef(rule_id, Revision(1)),
                    PolicyVersion("auth-v1"),
                ),
            ),
            (),
            ThreadGenerationGuardUntracked("untracked"),
        )
        if stopped:
            policy.stop_thread(
                uow,
                owner.projection_id,
                thread_id,
                Generation(1),
                now,
                ThreadStopReason.MANUAL_STOP,
            )
    assert r.run(key).reset == 0
    assert owner._connection.execute("SELECT state FROM sync_jobs").fetchone() == (
        "source_missing",
    )
    assert owner._connection.execute(
        "SELECT active FROM tracked_threads"
    ).fetchone() == (int(not stopped),)


def test_claimed_failure_is_not_closed(state):
    owner, r, key = state
    _, job_id = legacy(owner, r)
    now = Timestamp(datetime.now(UTC))
    with owner.session.transaction() as uow:
        uow._execute(
            "UPDATE sync_jobs SET state='claimed' WHERE job_id=?", (job_id.value,)
        )
        _insert(
            uow,
            owner.projection_id,
            "job_claims",
            JobClaimRow(
                owner.projection_id,
                job_id,
                Claim(
                    LocalId(uuid4().hex),
                    owner.owner_info.owner_run_id,
                    now,
                    None,
                    Revision(1),
                    ClaimPhase.PREPARING,
                ),
            ),
        )
    assert r.run(key).reset == 0
    assert owner._connection.execute("SELECT count(*) FROM job_claims").fetchone() == (
        1,
    )


def test_action_work_is_preserved(state):
    from facet.db.codecs import ActionKind, ActionState, CleanupState
    from facet.db.models import ActionCommandRow

    owner, r, key = state
    event_id, _ = legacy(owner, r)
    history_id = ProviderId(
        owner._connection.execute(
            "SELECT history_record_id FROM source_events"
        ).fetchone()[0]
    )
    with owner.session.transaction() as uow:
        _insert(
            uow,
            owner.projection_id,
            "action_commands",
            ActionCommandRow(
                owner.projection_id,
                LocalId(uuid4().hex),
                event_id,
                history_id,
                ProviderId("label-private"),
                ProviderId("SYNTHETIC_PRIVATE_THREAD"),
                ActionKind.ADD_SENDER,
                ActionState.PENDING,
                CleanupState.NOT_REQUESTED,
                Timestamp(datetime.now(UTC)),
                None,
                None,
                Revision(0),
            ),
        )
    assert r.run(key).reset == 0
    assert owner._connection.execute(
        "SELECT state FROM action_commands"
    ).fetchone() == ("pending",)


@pytest.mark.parametrize("relationship", ["event", "thread"])
def test_current_action_receipts_are_preserved(state, relationship):
    owner, r, key = state
    event_id, _ = legacy(owner, r)
    trigger = event_id
    thread = "unrelated-thread"
    if relationship == "thread":
        trigger, _ = legacy(owner, r, thread="different-thread")
        thread = "SYNTHETIC_PRIVATE_THREAD"
    with owner.session.transaction() as uow:
        uow._execute(
            "INSERT INTO current_action_receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                owner.projection_id.value,
                uuid4().hex,
                thread,
                "add_domain",
                "synthetic-label",
                1,
                trigger.value,
                timestamp_to_sql(Timestamp(datetime.now(UTC))),
                None,
                None,
                None,
                None,
                "suppressed",
            ),
        )
    before = owner._connection.execute(
        "SELECT * FROM current_action_receipts"
    ).fetchall()
    assert r.run(key).reset == 0
    assert (
        owner._connection.execute("SELECT * FROM current_action_receipts").fetchall()
        == before
    )
    assert set(owner._connection.execute("SELECT state FROM sync_jobs").fetchall()) == {
        ("source_missing",)
    }


@pytest.mark.parametrize("unknown", [False, True])
def test_mapping_and_unknown_intent_protect_even_conflicting_thread(
    gmail_controller, monkeypatch, unknown
):
    from test_projection_worker import (
        _payload,
        _raw,
        _UnknownInsertTarget,
        _worker_adapters,
    )

    from facet.projection.worker import ProjectionWorker

    raw = _raw("protected", "SYNTHETIC_PRIVATE_BODY")
    gmail_controller.seed("source", "m-new", "thread-1", raw, payload=_payload(raw))
    with TemporaryDirectory(dir=_trusted_parent()) as root:
        owner = _ready_owner(Path(root), gmail_controller, monkeypatch, seed=True)
        try:
            worker, _, target = _worker_adapters(gmail_controller, owner)
            assert worker.run().expanded == 1
            if unknown:
                worker = ProjectionWorker(
                    owner, worker._source, _UnknownInsertTarget(target)
                )
                assert worker.run().recovery == 1
            else:
                assert worker.run().verified == 1
            owner.ensure_reconcile_schema(LocalId(uuid4().hex), b"synthetic-config")
            source = EmptySource()
            r = SourceReconciler(
                owner,
                source,
                SourceCandidateAdmission(
                    source, load_persisted_admission(owner, owner.config)
                ),
                _scope(owner, owner.config),
                source_binding_revision=owner.bindings()[Role.SOURCE].binding_revision,
            )
            key = uuid4().hex
            r.prepare(key)
            _prepare_epoch(owner, r.scope, r.run_id)
            legacy(owner, r, thread="untracked-conflict", message="m-new")
            attempts = owner._connection.execute(
                "SELECT * FROM insert_attempts"
            ).fetchall()
            mappings = owner._connection.execute(
                "SELECT * FROM message_mappings"
            ).fetchall()
            assert r.run(key).reset == 0
            assert (
                owner._connection.execute("SELECT * FROM insert_attempts").fetchall()
                == attempts
            )
            assert (
                owner._connection.execute("SELECT * FROM message_mappings").fetchall()
                == mappings
            )
            assert owner._connection.execute(
                "SELECT processing FROM source_events"
            ).fetchone() == ("source_missing",)
        finally:
            owner.close()


@pytest.mark.parametrize(
    "state_value", ["completed_with_issues", "abandoned", "running"]
)
def test_unsuccessful_run_never_authorizes_closure(state, state_value):
    owner, r, key = state
    r.run(key)
    legacy(owner, r)
    with owner.session.transaction() as uow:
        uow._execute("UPDATE reconcile_runs SET state=?", (state_value,))
    assert close(owner, r) == 0
    assert owner._connection.execute("SELECT state FROM sync_jobs").fetchone() == (
        "source_missing",
    )


def test_warning_persists_after_later_run_and_active_fault(state):
    owner, r, key = state
    legacy(owner, r)
    assert r.run(key).reset == 1
    later = SourceReconciler(
        owner,
        r.source,
        r.admission,
        _scope(owner, owner.config),
        source_binding_revision=r.source_binding_revision,
    )
    later_key = uuid4().hex
    later.prepare(later_key)
    _prepare_epoch(owner, later.scope, later.run_id)
    assert later.run(later_key).reset == 0
    snapshots = snapshot_from_owner(owner, owner.config, cycle_verified=True)
    assert snapshots["issues"].data.historical_source_warning_count == 1
    assert snapshots["status"].data.health.value == "healthy"
    legacy(owner, later, at=Timestamp(datetime.now(UTC)))
    snapshots = snapshot_from_owner(owner, owner.config, cycle_verified=True)
    assert snapshots["status"].data.health.value == "degraded"
    assert snapshots["issues"].data.historical_source_warning_count == 1
    assert len(snapshots["issues"].data.groups) == 1
    from facet.status.serialization import public_json

    encoded = public_json(snapshots["issues"])
    assert "SYNTHETIC_PRIVATE_THREAD" not in encoded
    assert "source_message_id" not in encoded
