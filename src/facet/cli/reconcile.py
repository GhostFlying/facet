"""CLI entry points for explicit, source-only full reconcile."""

import signal
import sqlite3
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from facet.config import load_config
from facet.contracts import (
    BindingState,
    Count,
    EpochKind,
    EpochState,
    ErrorCode,
    Generation,
    JobKind,
    JobState,
    LocalId,
    PartitionProgress,
    PartitionState,
    Priority,
    Revision,
    Role,
    Timestamp,
)
from facet.contracts.records import (
    AdmissionRefFutureRule,
    EpochDecisionRefRequestedReconcile,
    JobSubjectExpandThread,
    JobSubjectProjectMessage,
    PartitionRefSourceWindow,
    ThreadGenerationGuardUntracked,
)
from facet.db.codecs import PrivateAddress, timestamp_from_sql, timestamp_to_sql
from facet.db.keys import job_key, partition_key
from facet.db.models import (
    EpochPartitionRow,
    EpochRow,
    RevisionGuard,
    SyncJobRow,
    ThreadAdmissionRow,
    TrackedThreadRow,
)
from facet.db.repositories import epochs, jobs, policy
from facet.db.repositories.base import _get
from facet.db.repositories.history_convergence import historical_warning_count
from facet.gmail.credentials import CredentialManager
from facet.gmail.service_factory import GoogleGmailServiceFactory
from facet.gmail.source import SourceAdapter
from facet.private_paths import read_managed_config, select_paths
from facet.reconcile import ReconcileScope, SourceReconciler
from facet.runtime.foreground_runtime import load_persisted_admission
from facet.runtime.maintenance import acquire_marker, release
from facet.runtime.maintenance import active as maintenance_active
from facet.runtime.private_root import LockFailure
from facet.runtime.state_owner import StateOwner


def _timestamp(value):
    return Timestamp(value)


def _scope(owner, config):
    end = datetime.now(UTC)
    initial = owner._connection.execute(
        "SELECT window_start FROM epochs WHERE projection_id=? "
        "AND kind='initial_backfill' ORDER BY created_at,epoch_id LIMIT 1",
        (owner.projection_id.value,),
    ).fetchone()
    if initial is None or initial[0] is None:
        raise ValueError("scope_required")
    revision = owner._connection.execute(
        "SELECT ruleset_revision FROM projections WHERE projection_id=?",
        (owner.projection_id.value,),
    ).fetchone()[0]
    return ReconcileScope(
        Revision(revision),
        timestamp_from_sql(initial[0]),
        _timestamp(end),
        _timestamp(end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)),
    )


def _source_service(owner, config):
    from facet.gmail.credential_models import policy_scopes
    from facet.gmail.credentials import ProfileEvidence
    from facet.gmail.refresh_exchange import refresh_google
    from facet.runtime.foreground_runtime import _policy, _request_token_provider

    manager = CredentialManager(owner.state_dir, config, owner)
    factory = GoogleGmailServiceFactory()

    def exchange(role, old):
        return refresh_google(role, old, policy_scopes(_policy(config, role), role))

    def profile(role, secret, scopes):
        return ProfileEvidence(factory.profile_account(role, secret), scopes)

    manager.reconcile_interrupted_refresh(Role.SOURCE)
    manager.ensure_current(Role.SOURCE, exchange, profile)
    snapshot = manager.snapshot(Role.SOURCE)
    build = getattr(factory, "service_with_refresh", None)
    if callable(build):
        return build(
            Role.SOURCE,
            snapshot,
            _request_token_provider(owner, config, factory, snapshot),
        )
    return factory.service(Role.SOURCE, snapshot)


def _status(owner):
    row = owner._connection.execute(
        "SELECT state,run_id,ruleset_revision,window_start,window_end,listed_count,"
        "metadata_success_count,metadata_404_count,matched_count,mapped_count,"
        "queued_count,reset_count,remaining_issue_count,created_at,completed_at "
        "FROM reconcile_runs WHERE projection_id=? ORDER BY created_at DESC LIMIT 1",
        (owner.projection_id.value,),
    ).fetchone()
    if row is None:
        return {"state": "never_run"}
    with owner.session.transaction() as uow:
        warnings = historical_warning_count(uow, owner.projection_id)
    return {
        "state": row[0],
        "ruleset_revision": row[2],
        "window_start": row[3],
        "window_end": row[4],
        "listed": row[5],
        "metadata_success": row[6],
        "metadata_404": row[7],
        "matched": row[8],
        "mapped": row[9],
        "queued": row[10],
        "reset": row[11],
        "remaining_issue": row[12],
        "created_at": row[13],
        "completed_at": row[14],
        "historical_source_warning_count": warnings,
    }


def _prepare_epoch(owner, scope, epoch_id):
    now = Timestamp(datetime.now(UTC))
    reference = PartitionRefSourceWindow("source_window")
    epoch = EpochRow(
        owner.projection_id,
        epoch_id,
        EpochKind.SOURCE_RECONCILE,
        EpochState.PREPARED,
        Revision(0),
        now,
        scope.window_start,
        scope.window_end,
        scope.discovery_cutoff,
        EpochDecisionRefRequestedReconcile(
            "requested_reconcile", epoch_id, scope.ruleset_revision
        ),
        None,
        None,
        None,
        None,
        None,
        False,
        None,
    )
    partition = EpochPartitionRow(
        owner.projection_id,
        epoch_id,
        partition_key(owner.projection_id, reference),
        PartitionProgress(
            reference, PartitionState.NOT_STARTED, Count(0), Count(0), None, None
        ),
        Revision(0),
    )
    from facet.db.repositories import epochs

    with owner.session.transaction() as uow:
        existing = uow._execute(
            "SELECT 1 FROM epochs WHERE projection_id=? AND epoch_id=?",
            (owner.projection_id.value, epoch_id.value),
        ).fetchone()
        if existing is None:
            epochs.start_epoch(uow, owner.projection_id, epoch, (partition,))


def _close_epoch(owner, result):
    """Terminally close the reconcile lineage after its durable scan summary."""
    with owner.session.transaction() as uow:
        epoch = _get(uow, owner.projection_id, "epochs", (("epoch_id", result.run_id),))
        partition = _get(
            uow,
            owner.projection_id,
            "epoch_partitions",
            (("epoch_id", result.run_id),),
        )
        if epoch is None or partition is None:
            raise ValueError("reconcile_epoch_missing")
        if epoch.state in {
            EpochState.COMPLETED,
            EpochState.COMPLETED_WITH_ISSUES,
            EpochState.NEEDS_ATTENTION,
        }:
            return
        progress = replace(
            partition.progress,
            state=PartitionState.COMPLETE,
            completed_pages=Count(partition.progress.completed_pages.value + 1),
            observed_items=Count(result.listed),
            page_token=None,
            after_source_message_id=None,
        )
        epochs.advance_partition(
            uow,
            owner.projection_id,
            replace(
                partition,
                progress=progress,
                revision=Revision(partition.revision.value + 1),
            ),
            (),
            RevisionGuard(epoch.revision),
        )
        state = (
            EpochState.NEEDS_ATTENTION
            if result.queued or result.remaining_issue
            else EpochState.COMPLETED
        )
        epochs.advance_epoch(
            uow,
            owner.projection_id,
            result.run_id,
            state,
            True,
            Count(result.listed),
            RevisionGuard(epoch.revision),
        )


def _attention_epoch(owner, epoch_id):
    with owner.session.transaction() as uow:
        epoch = _get(uow, owner.projection_id, "epochs", (("epoch_id", epoch_id),))
        if epoch is None or epoch.state in {
            EpochState.COMPLETED,
            EpochState.COMPLETED_WITH_ISSUES,
            EpochState.NEEDS_ATTENTION,
        }:
            return
        epochs.advance_epoch(
            uow,
            owner.projection_id,
            epoch_id,
            EpochState.NEEDS_ATTENTION,
            False,
            None,
            RevisionGuard(epoch.revision),
        )


def _enqueue(owner, run_id):
    def enqueue(candidate, rule):
        message_id = candidate.source_message_id
        thread_id = candidate.source_thread_id
        now = Timestamp(datetime.now(UTC))
        with owner.session.transaction() as uow:
            existing = _get(
                uow,
                owner.projection_id,
                "tracked_threads",
                (("source_thread_id", thread_id),),
            )
            if existing is not None and not existing.active:
                return False
            if existing is not None:
                subject = JobSubjectProjectMessage(
                    "project_message", message_id, thread_id, existing.generation
                )
                row = SyncJobRow(
                    owner.projection_id,
                    LocalId(uuid4().hex),
                    JobKind.PROJECT_MESSAGE,
                    Count(1),
                    job_key(owner.projection_id, subject),
                    Priority.BACKFILL,
                    JobState.QUEUED,
                    Revision(0),
                    now,
                    now,
                    None,
                    Count(0),
                    None,
                    run_id,
                    subject,
                )
                jobs.enqueue(uow, owner.projection_id, row)
                return True
            if rule is None:
                return False
            rule_revision = _get(
                uow,
                owner.projection_id,
                "rule_revisions",
                (("rule_id", rule.rule_id), ("revision", rule.revision)),
            )
            if rule_revision is None or not rule_revision.enabled:
                return False
            thread = TrackedThreadRow(
                owner.projection_id,
                thread_id,
                True,
                Generation(1),
                now,
                None,
                None,
                Revision(1),
            )
            admission = ThreadAdmissionRow(
                owner.projection_id,
                thread_id,
                Revision(1),
                Generation(1),
                now,
                AdmissionRefFutureRule(
                    "future_rule", rule, rule_revision.policy_version
                ),
            )
            subject = JobSubjectExpandThread(
                "expand_thread", thread_id, run_id, Generation(1)
            )
            row = SyncJobRow(
                owner.projection_id,
                LocalId(uuid4().hex),
                JobKind.EXPAND_THREAD,
                Count(1),
                job_key(owner.projection_id, subject),
                Priority.BACKFILL,
                JobState.QUEUED,
                Revision(0),
                now,
                now,
                None,
                Count(0),
                None,
                run_id,
                subject,
            )
            policy.admit_thread(
                uow,
                owner.projection_id,
                thread,
                admission,
                (row,),
                ThreadGenerationGuardUntracked("untracked"),
            )
            return True

    return enqueue


def run_reconcile(options):
    paths = select_paths(
        getattr(options, "state_dir", None), getattr(options, "config_path", None)
    )
    raw = read_managed_config(paths)
    config = load_config(raw)
    request_id = LocalId(getattr(options, "request_id", None) or uuid4().hex)
    marker = None
    previous_sigterm = None
    if getattr(options, "action", None) != "status":
        try:
            marker = acquire_marker(paths.root, request_id.value)
        except RuntimeError as error:
            raise ValueError(str(error)) from None
    owner = None
    if marker is not None and threading.current_thread() is threading.main_thread():

        def interrupted(*_):
            raise KeyboardInterrupt

        previous_sigterm = signal.signal(signal.SIGTERM, interrupted)
    try:
        while owner is None:
            try:
                owner = StateOwner.open(paths.root, config)
            except LockFailure as error:
                if error.code is not ErrorCode.OWNER_BUSY:
                    raise
                if getattr(options, "action", None) == "status":
                    state = "maintenance" if maintenance_active(paths.root) else "busy"
                    return {"state": state, "schema_ready": True}, ()
                time.sleep(1)
        owner.verify_config_artifact(raw)
        if getattr(options, "action", None) == "status":
            try:
                return _status(owner), ()
            except sqlite3.OperationalError:
                return {"state": "unavailable", "schema_ready": False}, ()
        if not getattr(options, "source", False) or not getattr(options, "full", False):
            raise ValueError("invalid_input")
        if not getattr(options, "yes", False):
            raise ValueError("scope_required")
        owner.ensure_reconcile_schema(request_id, raw)
        request_key = getattr(options, "request_id", None) or request_id.value
        bindings = owner.bindings()
        source_binding = bindings.get(Role.SOURCE)
        if source_binding is None or source_binding.state is not BindingState.VERIFIED:
            raise ValueError("binding_pending")
        existing = owner._connection.execute(
            "SELECT ruleset_revision,source_binding_revision,window_start,window_end,"
            "discovery_cutoff "
            "FROM reconcile_runs WHERE projection_id=? AND request_key=?",
            (owner.projection_id.value, request_key),
        ).fetchone()
        if existing is None:
            scope = _scope(owner, config)
        else:
            scope = ReconcileScope(
                Revision(existing[0]),
                timestamp_from_sql(existing[2]),
                timestamp_from_sql(existing[3]),
                timestamp_from_sql(existing[4]),
            )
        admission = load_persisted_admission(
            owner, config, ruleset_revision=scope.ruleset_revision
        )
        reconciler = SourceReconciler(
            owner,
            None,
            None,
            scope,
            source_binding_revision=source_binding.binding_revision,
        )
        reconciler.prepare(request_key)
        _prepare_epoch(owner, scope, reconciler.run_id)
        try:
            service = _source_service(owner, config)
        except (KeyboardInterrupt, SystemExit):
            with owner.session.transaction() as uow:
                uow._execute(
                    "UPDATE reconcile_runs SET state='abandoned',completed_at=?,"
                    "revision=revision+1 WHERE projection_id=? AND run_id=? "
                    "AND state='prepared'",
                    (
                        timestamp_to_sql(Timestamp(datetime.now(UTC))),
                        owner.projection_id.value,
                        reconciler.run_id.value,
                    ),
                )
            raise
        except Exception as error:
            code = getattr(error, "code", None)
            stage = getattr(error, "provider_stage", None)
            reason = getattr(error, "reason", None)
            with owner.session.transaction() as uow:
                uow._execute(
                    "UPDATE reconcile_runs SET state='abandoned',"
                    "completed_at=?,last_error_code=?,last_provider_stage=?,"
                    "last_provider_reason=?,last_http_status=?,revision=revision+1 "
                    "WHERE projection_id=? AND run_id=? AND state='prepared'",
                    (
                        timestamp_to_sql(Timestamp(datetime.now(UTC))),
                        code.value if hasattr(code, "value") else None,
                        stage.value if hasattr(stage, "value") else None,
                        reason.value if hasattr(reason, "value") else None,
                        getattr(error, "status", None),
                        owner.projection_id.value,
                        reconciler.run_id.value,
                    ),
                )
            raise
        try:
            from facet.sync import SourceCandidateAdmission

            source = SourceAdapter(
                service, source_account=PrivateAddress(config.projection.source_email)
            )
            scan_started = False
            try:
                # Bind the live OAuth token to the configured source before
                # any mailbox scan. This is source-only; target OAuth is not
                # needed for a read-only reconcile.
                source.profile()
                reconciler.source = source
                reconciler.admission = SourceCandidateAdmission(source, admission)
                scan_started = True
                result = reconciler.run(
                    request_key, enqueue_candidate=_enqueue(owner, reconciler.run_id)
                )
                _close_epoch(owner, result)
            except (KeyboardInterrupt, SystemExit):
                with owner.session.transaction() as uow:
                    uow._execute(
                        "UPDATE reconcile_runs SET state='abandoned',completed_at=?,"
                        "revision=revision+1 WHERE projection_id=? "
                        "AND run_id=? AND state IN('prepared','running')",
                        (
                            timestamp_to_sql(Timestamp(datetime.now(UTC))),
                            owner.projection_id.value,
                            reconciler.run_id.value,
                        ),
                    )
                raise
            except Exception as error:
                if scan_started:
                    _attention_epoch(owner, reconciler.run_id)
                code = getattr(error, "code", None)
                stage = getattr(error, "provider_stage", None)
                reason = getattr(error, "reason", None)
                with owner.session.transaction() as uow:
                    totals = getattr(reconciler, "totals", {})
                    if totals:
                        assignments = ",".join(f"{name}_count=?" for name in totals)
                        uow._execute(
                            f"UPDATE reconcile_runs SET {assignments},"
                            "revision=revision+1 "
                            "WHERE projection_id=? AND run_id=?",
                            [
                                *totals.values(),
                                owner.projection_id.value,
                                reconciler.run_id.value,
                            ],
                        )
                    state = "completed_with_issues" if scan_started else "abandoned"
                    uow._execute(
                        f"UPDATE reconcile_runs SET state='{state}',"
                        "completed_at=?,last_error_code=?,last_provider_stage=?,"
                        "last_provider_reason=?,last_http_status=?,revision=revision+1 "
                        "WHERE projection_id=? AND run_id=? "
                        "AND state IN('prepared','running','draining')",
                        (
                            timestamp_to_sql(Timestamp(datetime.now(UTC))),
                            code.value if hasattr(code, "value") else None,
                            stage.value if hasattr(stage, "value") else None,
                            reason.value if hasattr(reason, "value") else None,
                            getattr(error, "status", None),
                            owner.projection_id.value,
                            reconciler.run_id.value,
                        ),
                    )
                raise
            return {
                "run_id": result.run_id.value,
                "listed": result.listed,
                "metadata_success": result.metadata_success,
                "metadata_404": result.metadata_404,
                "matched": result.matched,
                "mapped": result.mapped,
                "queued": result.queued,
                "reset": result.reset,
                "remaining_issue": result.remaining_issue,
                "retry_wait_seconds": round(reconciler.read_retries.waited, 3),
                "retry_success_count": reconciler.read_retries.retried_success,
            }, ()
        finally:
            close = getattr(service, "close", None)
            if callable(close):
                close()
    finally:
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        if owner is not None:
            owner.close()
        if marker is not None:
            release(paths.root)
