"""Real file-backed policy/queue/private-read operations, not live feature gates.

Test-only fixtures allocate already-validated origins and binding metadata. They
are not production bypasses for the deferred auth/preview/command registries.
"""

import json
import sqlite3
import subprocess
import sys
from contextlib import contextmanager, suppress
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

import pytest
from db_view_job_values import unpack_job
from test_db_schema import NOW, P, create_state, lid

from facet.contracts import (
    BindingState,
    Claim,
    ClaimPhase,
    Count,
    DatePolicy,
    ErrorClass,
    ErrorCode,
    Generation,
    InsertState,
    JobKind,
    JobState,
    OutcomeCertainty,
    PolicyVersion,
    Priority,
    ProjectionId,
    ProviderId,
    Revision,
    Role,
    RuleKind,
    RuleOrigin,
    RuleRef,
    Sha256Hex,
    SourceEvent,
    Timestamp,
    Visibility,
)
from facet.contracts.records import (
    AdmissionRefFutureRule,
    AdmissionRefManualThread,
    JobSubjectProjectMessage,
    JobSubjectRecoverInsert,
    JobSubjectResolveEvent,
    SourceEventKeyMessageAdded,
    ThreadGenerationGuardTracked,
    ThreadGenerationGuardUntracked,
)
from facet.db.codecs import (
    AttributionKind,
    AuditKind,
    AuditObjectKind,
    EventProcessing,
    PageLimit,
    RuleValue,
    StorageFailure,
    ThreadStopReason,
)
from facet.db.keys import event_key, job_key
from facet.db.models import (
    AuditEventRow,
    BindingRevisionRow,
    CountsSnapshot,
    ErrorEventRow,
    InsertAttemptRow,
    JobStateCount,
    ReadPage,
    RevisionGuard,
    RuleRevisionRow,
    RuleRow,
    RulesetMemberRow,
    RulesetRow,
    SourceEventRow,
    SyncJobRow,
    ThreadAdmissionRow,
    TrackedThreadRow,
)
from facet.db.repositories import jobs, policy, reads
from facet.db.repositories.audit import append_audit, append_error
from facet.db.repositories.base import _insert
from facet.db.repositories.serialization import _decode_row, _encode_row

T = ProviderId("synthetic-thread")


@pytest.fixture
def state(tmp_path):
    path = tmp_path / "metadata.db"
    connection, session, info = create_state(path)
    yield path, connection, session, info
    if not session._closed:
        session.close()


def _unpack_row(table, cells):
    if cells is None:
        return None
    assert type(cells) is list
    values = []
    for cell in cells:
        if type(cell) is dict:
            assert cell.keys() == {"hex"}
            assert type(cell["hex"]) is str and len(cell["hex"]) <= 16384
            values.append(bytes.fromhex(cell["hex"]))
        else:
            assert cell is None or type(cell) in {bool, int, str}
            values.append(cell)
    return _decode_row(table, tuple(values))


class SnapshotProbe:
    """Test-only committed snapshot materializer, explicitly NOT ReadSession.

    Named production methods execute in a fresh admitted child. Parent facade
    errors/type/thread checks are not counted as production guard evidence.
    """

    def __init__(self, root, instance):
        self.root = root
        self.instance = instance

    def call(self, case, projection, **selectors):
        # All callers below are fixed named methods. This is not a product IPC.
        request = {
            "instance": self.instance.value,
            "projection": projection.value,
            **selectors,
        }
        encoded = json.dumps(request)
        assert len(encoded.encode()) <= 32768
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                str(Path(__file__).with_name("db_view_bootstrap.py")),
                case,
                str(self.root),
            ],
            input=encoded,
            capture_output=True,
            text=True,
            close_fds=True,
            check=True,
            timeout=12,
        )
        assert result.stderr == "" and len(result.stdout.encode()) <= 2 * 1024 * 1024
        response = json.loads(result.stdout)
        if response["status"] != "ok":
            assert response.keys() == {"status"}
            raise StorageFailure(ErrorCode(response["status"]))
        assert response.keys() == {"status", "result"}
        return response["result"]

    def get_projection(self, projection):
        return _unpack_row("projections", self.call("row_projection", projection))

    def inspect_schema(self, projection):
        value = self.call("schema", projection)
        assert value.keys() == {"metadata", "ledger"} and len(value["ledger"]) <= 500
        return (
            _unpack_row("schema_metadata", value["metadata"]),
            tuple(_unpack_row("schema_migrations", row) for row in value["ledger"]),
        )

    def get_binding(self, projection, role):
        return _unpack_row(
            "bindings", self.call("row_binding", projection, role=role.value)
        )

    def get_binding_revision(self, projection, role, revision):
        return _unpack_row(
            "binding_revisions",
            self.call(
                "row_binding_revision",
                projection,
                role=role.value,
                revision=revision.value,
            ),
        )

    def get_rule(self, projection, id):
        return _unpack_row("rules", self.call("row_rule", projection, id=id.value))

    def get_epoch(self, projection, id):
        return _unpack_row("epochs", self.call("row_epoch", projection, id=id.value))

    def get_event(self, projection, id):
        return _unpack_row(
            "source_events", self.call("row_event", projection, id=id.value)
        )

    def get_job(self, projection, id):
        result = self.call("row_job", projection, id=id.value)
        return unpack_job(result, projection) if result is not None else None

    def get_attempt(self, projection, id):
        return _unpack_row(
            "insert_attempts", self.call("row_attempt", projection, id=id.value)
        )

    def get_action(self, projection, id):
        return _unpack_row(
            "action_commands", self.call("row_action", projection, id=id.value)
        )

    def get_thread(self, projection, id):
        return _unpack_row(
            "tracked_threads", self.call("row_thread", projection, id=id.value)
        )

    def get_mapping(self, projection, id):
        return _unpack_row(
            "message_mappings", self.call("row_mapping", projection, id=id.value)
        )

    def get_thread_target(self, projection, source, target):
        return _unpack_row(
            "thread_targets",
            self.call(
                "row_thread_target",
                projection,
                source=source.value,
                target=target.value,
            ),
        )

    def get_thread_anchor(self, projection, source):
        return _unpack_row(
            "thread_targets",
            self.call("row_thread_anchor", projection, source=source.value),
        )

    def get_checkpoint(self, projection):
        return _unpack_row(
            "history_checkpoints", self.call("row_checkpoint", projection)
        )

    def get_history_poll(self, projection, id):
        return _unpack_row(
            "history_polls", self.call("row_history_poll", projection, id=id.value)
        )

    def get_history_page(self, projection, id, ordinal):
        return _unpack_row(
            "history_pages",
            self.call(
                "row_history_page", projection, id=id.value, ordinal=ordinal.value
            ),
        )

    def _page(self, case, table, projection, limit, cursor):
        value = self.call(
            case,
            projection,
            limit=limit.value,
            cursor=cursor.hex() if cursor is not None else None,
        )
        assert value.keys() == {"items", "next"}
        assert len(value["items"]) <= min(limit.value, 500)
        return ReadPage(
            tuple(
                unpack_job(row, projection)
                if case == "page_jobs"
                else _unpack_row(table, row)
                for row in value["items"]
            ),
            bytes.fromhex(value["next"]) if value["next"] is not None else None,
        )

    def list_jobs(self, projection, limit, cursor):
        return self._page("page_jobs", "sync_jobs", projection, limit, cursor)

    def list_attempts(self, projection, limit, cursor):
        return self._page("page_attempts", "insert_attempts", projection, limit, cursor)

    def list_events(self, projection, limit, cursor):
        return self._page("page_events", "source_events", projection, limit, cursor)

    def list_audit(self, projection, limit, cursor):
        return self._page("page_audit", "audit_events", projection, limit, cursor)

    def counts(self, projection, epoch):
        value = self.call(
            "counts", projection, epoch=epoch.value if epoch is not None else None
        )
        assert value.keys() == {"confirmed", "states", "uncertain", "complete", "total"}
        assert len(value["states"]) == len(JobState)
        return CountsSnapshot(
            Count(value["confirmed"]),
            tuple(
                JobStateCount(JobState(state), Count(count))
                for state, count in value["states"]
            ),
            Count(value["uncertain"]),
            value["complete"],
            Count(value["total"]) if value["total"] is not None else None,
        )


@contextmanager
def view(state):
    _, source, session, info = state
    session._check()
    assert session._uow is None and not source.in_transaction
    with TemporaryDirectory(prefix="facet-synthetic-read-") as directory:
        root = Path(directory)
        for name in ("owner.lock", "view.lock"):
            (root / name).touch(mode=0o600)
        destination = root / "metadata.db"
        destination.touch(mode=0o600)
        copied = sqlite3.connect(destination, autocommit=True)
        try:
            # Fixed bounded backup behavior; this capture is test-owned, not a
            # claimed complete M6 bundle or live same-inode reader.
            from facet.db.migration_backup import _progress

            source.backup(copied, pages=128, progress=_progress, sleep=0)
        finally:
            copied.close()
        assert not any(
            (root / ("metadata.db" + s)).exists() for s in ("-wal", "-shm", "-journal")
        )
        yield SnapshotProbe(root, info.state_instance_id)


def publish(session, *, enabled=True, revision=1):
    row = RuleRow(
        P,
        lid(10),
        RuleKind.ALLOW_SENDER,
        RuleValue("synthetic@example.invalid"),
        Revision(revision),
    )
    rule_revision = RuleRevisionRow(
        P,
        row.rule_id,
        row.current_revision,
        enabled,
        NOW,
        RuleOrigin.CLI,
        PolicyVersion("synthetic-v1"),
    )
    snapshot = RulesetRow(P, Revision(revision), NOW, True)
    member = RulesetMemberRow(P, snapshot.revision, row.rule_id, row.current_revision)
    with session.transaction() as uow:
        policy.publish_rules(
            uow,
            P,
            (row,),
            (rule_revision,),
            snapshot,
            (member,),
            RevisionGuard(Revision(revision - 1)),
        )
    return row


def thread_rows(*, thread=T, generation=1, admission_revision=1, rule_revision=1):
    tracked = TrackedThreadRow(
        P,
        thread,
        True,
        Generation(generation),
        NOW,
        None,
        None,
        Revision(admission_revision),
    )
    admission = ThreadAdmissionRow(
        P,
        thread,
        Revision(admission_revision),
        Generation(generation),
        NOW,
        AdmissionRefFutureRule(
            "future_rule",
            RuleRef(lid(10), Revision(rule_revision)),
            PolicyVersion("synthetic-v1"),
        ),
    )
    return tracked, admission


def admit(session, *, thread=T, batch=()):
    tracked, admission = thread_rows(thread=thread)
    with session.transaction() as uow:
        policy.admit_thread(
            uow,
            P,
            tracked,
            admission,
            batch,
            ThreadGenerationGuardUntracked("untracked"),
        )
    return tracked, admission


def job(n, *, thread=T, generation=1, subject=None, priority=Priority.REALTIME):
    if subject is None:
        subject = JobSubjectProjectMessage(
            "project_message", ProviderId(f"msg-{n}"), thread, Generation(generation)
        )
    return SyncJobRow(
        P,
        lid(n),
        JobKind(subject.tag),
        Count(1),
        job_key(P, subject),
        priority,
        JobState.QUEUED,
        Revision(0),
        NOW,
        NOW,
        None,
        Count(0),
        None,
        None,
        subject,
    )


def ready_test_metadata(connection, session):
    # This is synthetic test allocation, not M104 auth/credential publication.
    with session.transaction() as uow:
        for role in Role:
            binding = reads.get_binding(uow, P, role)
            revision = BindingRevisionRow(
                P,
                role,
                Revision(2),
                binding.declared_address,
                binding.declared_address,
                BindingState.VERIFIED,
                NOW,
            )
            _insert(uow, P, "binding_revisions", revision)
            uow._execute(
                "UPDATE bindings SET state='verified',"
                "verified_address=declared_address,"
                "verified_at=?,binding_revision=2,credential_revision=1 "
                "WHERE projection_id=? AND role=?",
                (int(NOW.value.timestamp() * 1_000_000), P.value, role.value),
            )
        uow._execute(
            "UPDATE projections SET binding_state='verified',daemon_paused=0 "
            "WHERE projection_id=?",
            (P.value,),
        )


def claim(session, info, row, *, revision=0, generation=None):
    generation = row.subject.generation if generation is None else generation
    value = Claim(
        lid(100000 + int(row.job_id.value[-6:], 16)),
        info.owner_run_id,
        NOW,
        generation,
        Revision(revision + 1),
        ClaimPhase.PREPARING,
    )
    with session.transaction() as uow:
        result = jobs.claim(
            uow, P, row.job_id, value, RevisionGuard(Revision(revision)), NOW
        )
    return value, result


def attempt(row, claim_value, n, state):
    dispatched = state not in {
        InsertState.PREPARED,
        InsertState.CANCELLED_BEFORE_DISPATCH,
    }
    certainty = {
        InsertState.PREPARED: OutcomeCertainty.NOT_ATTEMPTED,
        InsertState.PENDING_RECOVERY: OutcomeCertainty.UNKNOWN,
        InsertState.DEFINITE_NOT_INSERTED: OutcomeCertainty.DEFINITELY_NOT_INSERTED,
    }[state]
    return InsertAttemptRow(
        P,
        lid(n),
        row.job_id,
        claim_value.claim_id,
        row.subject.source_message_id,
        row.subject.source_thread_id,
        row.subject.generation,
        Role.TARGET,
        Revision(2),
        NOW,
        NOW if dispatched else None,
        NOW if dispatched else None,
        None,
        Sha256Hex("a" * 64),
        None,
        None,
        None,
        DatePolicy.VALID_DATE_HEADER,
        state,
        certainty,
        None,
        None,
        AttributionKind.NONE,
        Visibility.UNKNOWN,
        None,
        None,
        Count(0),
        None,
        Revision(0),
    )


def test_private_typed_reads_schema_and_projection_are_no_create(state):
    _, connection, _, _ = state
    before = connection.total_changes
    with view(state) as reader:
        meta, ledger = reader.inspect_schema(P)
        assert meta.schema_version.value == 1 and len(ledger) == 1
        assert reader.get_projection(P).daemon_paused
        assert reader.get_checkpoint(P).cursor is None
        assert reader.get_projection(ProjectionId("other-projection")) is None
        assert (
            reader.get_binding_revision(P, Role.SOURCE, Revision(1)).state
            is BindingState.VERIFICATION_PENDING
        )
        assert reader.call("guard_binding_role", P) == {"actual_child_assertions": True}
        counts = reader.counts(P, None)
        assert counts.confirmed_mappings.value == 0
        assert not counts.discovery_complete and counts.known_total is None
        assert len(counts.by_job_state) == len(JobState)
    assert connection.total_changes == before


def test_rule_snapshot_revision_audit_and_caught_failure_roll_back(state):
    _, connection, session, _ = state
    publish(session)
    with view(state) as reader:
        assert reader.get_rule(P, lid(10)).current_revision == Revision(1)
        rows = reader.list_audit(P, PageLimit(100), None).items
        assert len(rows) == 1 and rows[0].kind is AuditKind.RULE_CHANGED
    before = connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()
    with (
        pytest.raises(StorageFailure),
        session.transaction() as uow,
        suppress(StorageFailure),
    ):
        policy.publish_rules(
            uow,
            P,
            (),
            (),
            RulesetRow(P, Revision(2), NOW, True),
            (),
            RevisionGuard(Revision(0)),
        )
    assert connection.execute(
        "SELECT ruleset_revision FROM projections"
    ).fetchone() == (1,)
    assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone() == before


def test_admit_replay_stop_and_retrack_exact_generations(state):
    _, connection, session, _ = state
    publish(session)
    first = job(100)
    tracked, admission = admit(session, batch=(first,))
    with session.transaction() as uow:
        replay = policy.admit_thread(
            uow,
            P,
            tracked,
            admission,
            (),
            ThreadGenerationGuardTracked("tracked", Generation(1)),
        )
        assert replay.disposition == "replayed"
    with session.transaction() as uow:
        policy.stop_thread(uow, P, T, Generation(1), NOW, ThreadStopReason.MANUAL_STOP)
    with (
        pytest.raises(StorageFailure, match="generation_stale"),
        session.transaction() as uow,
    ):
        policy.stop_thread(uow, P, T, Generation(1), NOW, ThreadStopReason.MANUAL_STOP)
    tracked, admission = thread_rows(generation=3, admission_revision=2)
    with session.transaction() as uow:
        policy.admit_thread(
            uow,
            P,
            tracked,
            admission,
            (job(101, generation=3),),
            ThreadGenerationGuardTracked("tracked", Generation(2)),
        )
    with view(state) as reader:
        assert reader.get_thread(P, T).generation == Generation(3)
        assert reader.get_job(P, first.job_id).state is JobState.CANCELLED
        assert reader.get_job(P, lid(101)).state is JobState.QUEUED
    assert connection.execute("SELECT COUNT(*) FROM thread_admissions").fetchone() == (
        2,
    )


@pytest.mark.parametrize("origin", ["manual", "disabled_rule"])
def test_unregistered_preview_or_disabled_rule_has_zero_disclosure_state(state, origin):
    _, connection, session, _ = state
    publish(session, enabled=origin != "disabled_rule")
    tracked, admission = thread_rows()
    if origin == "manual":
        admission = replace(
            admission, admission=AdmissionRefManualThread("manual_thread", lid(99))
        )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        policy.admit_thread(
            uow,
            P,
            tracked,
            admission,
            (job(100),),
            ThreadGenerationGuardUntracked("untracked"),
        )
    assert connection.execute("SELECT COUNT(*) FROM tracked_threads").fetchone() == (0,)
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)


def test_stable_queue_identity_preserves_allocation_and_rejects_changed_priority(state):
    _, _, session, _ = state
    publish(session)
    admit(session)
    row = job(100)
    with session.transaction() as uow:
        assert jobs.enqueue(uow, P, row).disposition == "created"
        replay = jobs.enqueue(uow, P, replace(row, job_id=lid(101)))
        assert replay.disposition == "replayed" and replay.object_id == row.job_id
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.enqueue(uow, P, replace(row, priority=Priority.BACKFILL))


def test_claim_binding_cas_and_defer_no_claim_steal(state):
    _, connection, session, info = state
    publish(session)
    row = job(100)
    admit(session, batch=(row,))
    proposed = Claim(
        lid(900),
        info.owner_run_id,
        NOW,
        Generation(1),
        Revision(1),
        ClaimPhase.PREPARING,
    )
    with (
        pytest.raises(StorageFailure, match="binding_pending"),
        session.transaction() as uow,
    ):
        jobs.claim(uow, P, row.job_id, proposed, RevisionGuard(Revision(0)), NOW)
    ready_test_metadata(connection, session)
    with session.transaction() as uow:
        jobs.claim(uow, P, row.job_id, proposed, RevisionGuard(Revision(0)), NOW)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.claim(
            uow,
            P,
            row.job_id,
            replace(proposed, claim_id=lid(901)),
            RevisionGuard(Revision(0)),
            NOW,
        )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.complete_noninsert_job(uow, P, row.job_id, RevisionGuard(Revision(1)))
    later = Timestamp(NOW.value + timedelta(seconds=5))
    with session.transaction() as uow:
        jobs.defer_job(
            uow,
            P,
            row.job_id,
            "retry_wait",
            ErrorCode.SOURCE_RATE_LIMITED,
            later,
            RevisionGuard(Revision(1)),
        )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.claim(
            uow,
            P,
            row.job_id,
            replace(proposed, job_revision=Revision(3)),
            RevisionGuard(Revision(2)),
            NOW,
        )
    assert connection.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)


def test_keyset_reads_are_bounded_table_and_projection_specific(state):
    _, _, session, _ = state
    publish(session)
    admit(session)
    with session.transaction() as uow:
        for n in range(100, 107):
            jobs.enqueue(uow, P, job(n))
    with view(state) as reader:
        ids, cursor = [], None
        while True:
            page = reader.list_jobs(P, PageLimit(2), cursor)
            ids.extend(row.job_id for row in page.items)
            cursor = page.next_key
            if cursor is None:
                break
        assert ids == [lid(n) for n in range(100, 107)]
        first = reader.list_jobs(P, PageLimit(2), None)
        for method, projection in [
            (reader.list_audit, P),
            (reader.list_jobs, ProjectionId("other")),
        ]:
            with pytest.raises(StorageFailure):
                method(projection, PageLimit(2), first.next_key)
        counts = reader.counts(P, None)
        assert sum(v.count.value for v in counts.by_job_state) == 7
        assert counts.confirmed_mappings.value == 0


def test_large_stop_cancels_all_unsent_but_not_another_thread(state):
    _, connection, session, _ = state
    publish(session)
    admit(session)
    other = ProviderId("other-thread")
    admit(session, thread=other, batch=(job(999, thread=other),))
    for start, end in [(1000, 1500), (1500, 1503)]:
        with session.transaction() as uow:
            for n in range(start, end):
                jobs.enqueue(uow, P, job(n))
    with session.transaction() as uow:
        policy.stop_thread(uow, P, T, Generation(1), NOW, ThreadStopReason.BLACKLIST)
    assert connection.execute(
        "SELECT COUNT(*) FROM sync_jobs WHERE state='cancelled'"
    ).fetchone() == (503,)
    with view(state) as reader:
        assert reader.get_job(P, lid(999)).state is JobState.QUEUED
        assert reader.get_thread(P, other).active


@pytest.mark.parametrize(
    "state_value",
    [
        InsertState.PREPARED,
        InsertState.PENDING_RECOVERY,
        InsertState.DEFINITE_NOT_INSERTED,
    ],
)
def test_stop_retains_actual_uncertain_effects_and_cancels_only_safe_work(
    state, state_value
):
    _, connection, session, info = state
    publish(session)
    row = job(100)
    admit(session, batch=(row,))
    ready_test_metadata(connection, session)
    claimed, _ = claim(session, info, row)
    value = attempt(row, claimed, 200, state_value)
    with session.transaction() as uow:
        _insert(uow, P, "insert_attempts", value)
    with session.transaction() as uow:
        policy.stop_thread(uow, P, T, Generation(1), NOW, ThreadStopReason.MANUAL_STOP)
    with view(state) as reader:
        actual = reader.get_attempt(P, value.attempt_id)
        job_row = reader.get_job(P, row.job_id)
        if state_value is InsertState.PENDING_RECOVERY:
            assert actual.state is state_value and job_row.state is JobState.CLAIMED
        else:
            assert job_row.state is JobState.CANCELLED
            if state_value is InsertState.PREPARED:
                assert actual.state is InsertState.CANCELLED_BEFORE_DISPATCH
            else:
                assert actual.state is state_value


def test_unknown_effect_deferral_not_safe_retry_and_recovery_checks_not_insert(state):
    _, connection, session, info = state
    publish(session)
    row = job(100)
    admit(session, batch=(row,))
    ready_test_metadata(connection, session)
    claimed, _ = claim(session, info, row)
    value = attempt(row, claimed, 200, InsertState.PENDING_RECOVERY)
    with session.transaction() as uow:
        _insert(uow, P, "insert_attempts", value)
    for target in ("retry_wait", "failed", "source_missing"):
        with (
            pytest.raises(StorageFailure, match="insert_result_unknown"),
            session.transaction() as uow,
        ):
            jobs.defer_job(
                uow,
                P,
                row.job_id,
                target,
                ErrorCode.INSERT_RESULT_UNKNOWN,
                NOW if target == "retry_wait" else None,
                RevisionGuard(Revision(1)),
            )
    recovering = job(
        300,
        subject=JobSubjectRecoverInsert("recover_insert", value.attempt_id),
        priority=Priority.RECOVERY,
    )
    with session.transaction() as uow:
        jobs.enqueue(uow, P, recovering)
        jobs.defer_job(
            uow,
            P,
            recovering.job_id,
            "retry_wait",
            ErrorCode.INSERT_RESULT_UNKNOWN,
            NOW,
            RevisionGuard(Revision(0)),
        )
    with (
        pytest.raises(StorageFailure, match="insert_result_unknown"),
        session.transaction() as uow,
    ):
        jobs.defer_job(
            uow,
            P,
            recovering.job_id,
            "failed",
            ErrorCode.INSERT_RESULT_UNKNOWN,
            None,
            RevisionGuard(Revision(1)),
        )


@pytest.mark.parametrize(
    "classification,expected",
    [
        (EventProcessing.RESOLVED, JobState.COMPLETED),
        (EventProcessing.SOURCE_MISSING, JobState.SOURCE_MISSING),
        (EventProcessing.NEEDS_ATTENTION, None),
    ],
)
def test_resolution_completion_requires_own_durable_classification(
    state, classification, expected
):
    _, connection, session, info = state
    ready_test_metadata(connection, session)
    key = SourceEventKeyMessageAdded(
        "message_added", P, ProviderId("history"), ProviderId("msg")
    )
    event = SourceEventRow(
        P,
        lid(50),
        event_key(P, key),
        SourceEvent(key, NOW, T),
        classification,
        Revision(0),
        None,
    )
    row = job(100, subject=JobSubjectResolveEvent("resolve_event", key))
    with session.transaction() as uow:
        _insert(uow, P, "source_events", event)
        jobs.enqueue(uow, P, row)
    value = Claim(
        lid(99), info.owner_run_id, NOW, None, Revision(1), ClaimPhase.PREPARING
    )
    with session.transaction() as uow:
        jobs.claim(uow, P, row.job_id, value, RevisionGuard(Revision(0)), NOW)
    if expected is None:
        with pytest.raises(StorageFailure), session.transaction() as uow:
            jobs.complete_noninsert_job(uow, P, row.job_id, RevisionGuard(Revision(1)))
    else:
        with session.transaction() as uow:
            jobs.complete_noninsert_job(uow, P, row.job_id, RevisionGuard(Revision(1)))
        with view(state) as reader:
            assert reader.get_job(P, row.job_id).state is expected


def test_exact_audit_enum_branch_and_fixed_failure_no_private_message(state):
    _, connection, session, _ = state
    value = AuditEventRow(
        P,
        lid(90),
        AuditKind.JOB_STATE_CHANGED,
        AuditObjectKind.JOB,
        lid(100),
        None,
        None,
        Revision(0),
        Revision(1),
        JobState.QUEUED,
        JobState.NEEDS_ATTENTION,
        None,
        NOW,
    )
    assert _decode_row("audit_events", _encode_row("audit_events", value)) == value
    publish(session)
    admit(session, batch=(job(100),))
    with pytest.raises(StorageFailure, match="invalid_input"):
        replace(value, after_state=InsertState.NEEDS_ATTENTION)
    with session.transaction() as uow:
        append_audit(uow, P, value)
    with pytest.raises(StorageFailure) as error, session.transaction() as uow:
        append_audit(uow, P, value)
    assert str(error.value) == "consistency_failure"
    assert "synthetic@example.invalid" not in repr(error.value)
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE audit_id=?", (value.audit_id.value,)
    ).fetchone() == (1,)


def job_audit(n, job_id, *, projection=P):
    return AuditEventRow(
        projection,
        lid(n),
        AuditKind.JOB_STATE_CHANGED,
        AuditObjectKind.JOB,
        job_id,
        None,
        None,
        Revision(0),
        Revision(1),
        JobState.QUEUED,
        JobState.NEEDS_ATTENTION,
        None,
        NOW,
    )


@pytest.mark.parametrize("mode", ["missing_object", "cross_projection"])
def test_audit_selector_failure_rolls_back_prior_work_and_audit(state, mode):
    _, connection, session, _ = state
    publish(session)
    admit(session)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.enqueue(uow, P, job(100))
        append_audit(uow, P, job_audit(900, lid(100)))
        with suppress(StorageFailure):
            bad = job_audit(
                901,
                lid(999) if mode == "missing_object" else lid(100),
                projection=P if mode == "missing_object" else ProjectionId("other"),
            )
            append_audit(uow, P, bad)
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE audit_id IN(?,?)",
        (lid(900).value, lid(901).value),
    ).fetchone() == (0,)


@pytest.mark.parametrize(
    "mode", ["wrong_job", "missing_attempt", "missing_job", "cross_projection"]
)
def test_error_job_attempt_pair_is_exact_same_projection_and_atomic(state, mode):
    _, connection, session, info = state
    publish(session)
    row = job(100)
    admit(session, batch=(row, job(101)))
    ready_test_metadata(connection, session)
    claimed, _ = claim(session, info, row)
    inserted = attempt(row, claimed, 200, InsertState.PENDING_RECOVERY)
    valid = ErrorEventRow(
        P,
        lid(900),
        ErrorCode.CONSISTENCY_FAILURE,
        ErrorClass.PERSISTENCE,
        None,
        NOW,
        row.job_id,
        inserted.attempt_id,
        Count(1),
    )
    with session.transaction() as uow:
        _insert(uow, P, "insert_attempts", inserted)
        append_error(uow, P, valid)
    changed = {
        "wrong_job": {"job_id": lid(101)},
        "missing_attempt": {"attempt_id": lid(999)},
        "missing_job": {"job_id": lid(999)},
        "cross_projection": {"projection_id": ProjectionId("other")},
    }[mode]
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.enqueue(uow, P, job(102))
        with suppress(StorageFailure):
            append_error(uow, P, replace(valid, error_id=lid(901), **changed))
    assert connection.execute("SELECT COUNT(*) FROM error_events").fetchone() == (1,)
    assert connection.execute(
        "SELECT COUNT(*) FROM sync_jobs WHERE job_id=?", (lid(102).value,)
    ).fetchone() == (0,)


@pytest.mark.parametrize("mode", ["raw_string", "foreign_projection"])
def test_caught_invalid_projection_poison_rolls_back_entire_owned_uow(state, mode):
    _, connection, session, _ = state
    publish(session)
    admit(session)

    class ForeignProjection:
        @property
        def value(self):
            pytest.fail("Foreign property must never execute")

    bad = P.value if mode == "raw_string" else ForeignProjection()
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.enqueue(uow, P, job(100))
        append_audit(uow, P, job_audit(900, lid(100)))
        with suppress(StorageFailure):
            jobs.enqueue(uow, bad, job(101))
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE audit_id=?", (lid(900).value,)
    ).fetchone() == (0,)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, job(102))


def test_wrong_thread_or_foreign_uow_rejection_cannot_poison_the_owner(state):
    _, connection, session, _ = state
    publish(session)
    admit(session)
    errors = []
    with session.transaction() as uow:
        jobs.enqueue(uow, P, job(100))

        def other_thread():
            try:
                jobs.enqueue(uow, P, job(101))
            except StorageFailure as error:
                errors.append(error.code)

        child = Thread(target=other_thread)
        child.start()
        child.join(timeout=5)
        assert not child.is_alive() and len(errors) == 1
        with pytest.raises(StorageFailure):
            jobs.enqueue(object(), P, job(101))
        append_audit(uow, P, job_audit(900, lid(100)))
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (1,)
