"""Single-process foreground composition of the production projection path.

This module deliberately contains orchestration only.  Gmail calls are made by
the typed adapters, and every SQLite mutation remains in the existing typed
repositories.  The supported deployment owns one instance of this runner in a
foreground container; it is not a daemon or an IPC service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from facet.contracts import (
    BindingState,
    Claim,
    ClaimPhase,
    Count,
    EpochKind,
    EpochState,
    ErrorCode,
    Generation,
    JobKind,
    JobState,
    LocalId,
    Priority,
    ProviderId,
    RestoreState,
    Revision,
    Role,
    RuleKind,
    Timestamp,
)
from facet.contracts.records import (
    AdmissionRefFutureRule,
    JobSubjectExpandThread,
    JobSubjectProjectMessage,
    SourceEventKeyLabelChanged,
    SourceEventKeyMessageDeleted,
    ThreadGenerationGuardUntracked,
)
from facet.db.codecs import (
    EventProcessing,
    PollOrigin,
    PollState,
    StorageFailure,
    timestamp_to_sql,
)
from facet.db.keys import event_key, job_key
from facet.db.models import (
    HistoryPollRow,
    RevisionGuard,
    SyncJobRow,
    ThreadAdmissionRow,
    TrackedThreadRow,
)
from facet.db.repositories import epochs, events, intents, jobs, policy, reads
from facet.db.repositories.base import _decode, _get, _query
from facet.db.repositories.serialization import COLUMNS
from facet.gmail.retry import ProviderFailure, blocks_sync
from facet.gmail.source import CandidateAttentionReason, DiscoveryItem, DiscoveryQuery
from facet.projection.action_consumer import ActionEffectConsumer
from facet.projection.admission import (
    AdmissionAttentionReason,
)
from facet.projection.admission import (
    AdmissionEvaluator as PolicyAdmissionEvaluator,
)
from facet.projection.backfill import BackfillProducer
from facet.projection.history import HistoryProducer
from facet.projection.worker import ProjectionWorker, WorkerReceipt


def _now() -> Timestamp:
    return Timestamp(datetime.now(UTC))


def _id() -> LocalId:
    return LocalId(uuid4().hex)


_RETRY_DELAY = timedelta(seconds=1)


class SourceCandidateAdmission:
    """Adapt the Gmail metadata candidate seam to the admission policy.

    The adapter performs provider reads before ``BackfillProducer`` opens its
    write transaction. Disclosure is decided from typed mailbox metadata and
    the configured rules; Facet does not authenticate the sender.
    """

    def __init__(self, source, policy: PolicyAdmissionEvaluator) -> None:
        if not hasattr(source, "candidate") or not isinstance(
            policy, PolicyAdmissionEvaluator
        ):
            raise ValueError("invalid_input")
        self._source = source
        self._policy = policy

    def discovery_query(self, epoch=None) -> DiscoveryQuery | None:
        """Plan one bounded provider query from the sealed allow snapshot."""

        policy_revision = self._policy.ruleset_revision
        epoch_revision = getattr(
            getattr(epoch, "decision", None), "ruleset_revision", None
        )
        if (
            epoch is not None
            and type(policy_revision) is Revision
            and epoch_revision != policy_revision
        ):
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        rules = self._policy.enabled_allow_rules
        if not rules:
            return None
        clauses = tuple(
            sorted(
                {
                    'from:"'
                    + rule.normalized.value.value.replace("\\", "\\\\").replace(
                        '"', '\\"'
                    )
                    + '"'
                    for rule in rules
                    if rule.normalized.kind
                    in {RuleKind.ALLOW_SENDER, RuleKind.ALLOW_DOMAIN}
                }
            )
        )
        return DiscoveryQuery(clauses)

    def evaluate(self, item, epoch):
        from facet.projection.backfill import DiscoveryDecision

        recovering = getattr(epoch, "kind", None) is EpochKind.HISTORY_GAP
        try:
            result = (
                self._source.history_candidate(item)
                if recovering
                else self._source.candidate(item)
            )
        except ProviderFailure as error:
            if blocks_sync(error):
                raise
            if (
                recovering
                and error.code
                in {
                    ErrorCode.SOURCE_AUTH_REQUIRED,
                    ErrorCode.SOURCE_RATE_LIMITED,
                    ErrorCode.NETWORK_UNAVAILABLE,
                }
                and error.status != 404
            ):
                raise
            return DiscoveryDecision(False, attention=error.code)
        if result.attention is not None:
            code = (
                ErrorCode.SOURCE_AUTH_REQUIRED
                if result.attention.reason is CandidateAttentionReason.PROVIDER_FAILURE
                else ErrorCode.REQUEST_CONFLICT
            )
            return DiscoveryDecision(False, attention=code)
        if recovering and not (
            epoch.window_start.value
            <= result.candidate.observed_at.value
            <= epoch.window_end.value
        ):
            return DiscoveryDecision(False)
        decision = self._policy.evaluate(
            result.candidate, _now(), prospective=recovering
        )
        if decision.admit:
            return DiscoveryDecision(True, decision.rule)
        return DiscoveryDecision(False)


@dataclass(frozen=True, slots=True, repr=False)
class SyncCycleReceipt:
    """Aggregate, privacy-safe result of one foreground cycle."""

    discovered: int = 0
    history_pages: int = 0
    resolved_events: int = 0
    projected: WorkerReceipt = WorkerReceipt()
    attention: int = 0
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            any(
                type(value) is not int or value < 0
                for value in (
                    self.discovered,
                    self.history_pages,
                    self.resolved_events,
                    self.attention,
                )
            )
            or type(self.projected) is not WorkerReceipt
            or type(self.warnings) is not tuple
            or any(
                warning
                not in {
                    "history_gap_scan_pending",
                    "expired_action_events_not_reconstructable",
                    "target_missing",
                }
                for warning in self.warnings
            )
        ):
            raise ValueError("invalid_input")

    def __repr__(self) -> str:
        return (
            f"<sync cycle discovered={self.discovered} "
            f"history_pages={self.history_pages} resolved={self.resolved_events} "
            f"projected={self.projected.processed}>"
        )

    __str__ = __repr__


class ForegroundSync:
    """Run one bounded, restartable sync cycle under an existing owner."""

    def __init__(
        self,
        owner,
        source,
        target,
        admission,
        *,
        action_consumer: ActionEffectConsumer | None = None,
        admission_for_epoch=None,
        admission_for_history=None,
        max_raw_bytes: int = 35_000_000,
        progress=None,
        should_stop=None,
    ) -> None:
        if (
            not hasattr(owner, "session")
            or not hasattr(source, "profile")
            or not hasattr(source, "history")
            or not hasattr(target, "insert")
            or not hasattr(admission, "evaluate")
            or (admission_for_epoch is not None and not callable(admission_for_epoch))
            or (
                admission_for_history is not None
                and not callable(admission_for_history)
            )
        ):
            raise ValueError("invalid_input")
        if type(max_raw_bytes) is not int or not 1 <= max_raw_bytes <= 35_000_000:
            raise ValueError("invalid_input")
        self._owner = owner
        self._source = source
        self._target = target
        self._max_raw_bytes = max_raw_bytes
        self._progress = progress
        self._should_stop = should_stop
        self._projection = owner.projection_id
        self._admission_for_epoch = admission_for_epoch
        self._admission_for_history = admission_for_history
        self._history_admission = (
            admission if isinstance(admission, PolicyAdmissionEvaluator) else None
        )
        self._admission = (
            SourceCandidateAdmission(source, admission)
            if isinstance(admission, PolicyAdmissionEvaluator)
            else admission
        )
        self._backfill = BackfillProducer(source, self._admission, progress=progress)
        self._history = HistoryProducer(source, progress=progress)
        self._worker = ProjectionWorker(
            owner,
            source,
            target,
            max_raw_bytes=max_raw_bytes,
            progress=progress,
            should_stop=should_stop,
        )
        self._action = action_consumer

    def run_once(
        self, *, max_jobs: int = 1000, max_events: int = 1000, verify_known_only=False
    ):
        """Advance discovery, History and durable jobs once, then return counts."""
        if (
            type(max_jobs) is not int
            or not 1 <= max_jobs <= 10_000
            or type(max_events) is not int
            or not 1 <= max_events <= 10_000
        ):
            raise ValueError("invalid_input")
        self._require_ready()
        from facet.projection.target_inventory import TargetInventory
        from facet.status.logging import OperationStage, emit_operation

        self._worker._inventory = self._worker._shared_inventory = TargetInventory(
            self._owner,
            self._target,
            progress=self._progress,
        )
        emit_operation(OperationStage.RECOVERY)
        if verify_known_only:
            return SyncCycleReceipt(
                projected=self._worker.verify_known(max_jobs=max_jobs)
            )
        if callable(getattr(self._action, "begin_cycle", None)):
            self._action.begin_cycle()
        self._recover_pre_dispatch_claims()
        known = self._worker.verify_known(max_jobs=max_jobs)
        from facet.projection.recovery import UnknownInsertChecks

        UnknownInsertChecks(
            self._owner,
            self._source,
            self._target,
            max_raw_bytes=self._max_raw_bytes,
            progress=self._progress,
            should_stop=self._should_stop,
        ).run(limit=min(max_jobs, 100))
        converged = self._converge_completed_events(max_events)
        if self._progress:
            self._progress()
        from facet.projection.gap_recovery import GapRecovery

        recovery = GapRecovery(
            self._owner,
            self._source,
            self._worker,
            self._admission_for_epoch,
            self._history_admission,
            progress=self._progress,
        )
        recovery_epoch = recovery.prepare()
        recovery_pages = 0
        if recovery_epoch is not None:
            if not recovery.scan(recovery_epoch, max_jobs=max_jobs):
                return SyncCycleReceipt(
                    attention=1,
                    warnings=(
                        "history_gap_scan_pending",
                        "expired_action_events_not_reconstructable",
                    ),
                )
            recovery_pages = recovery.catchup(recovery_epoch, self._history)
        emit_operation(OperationStage.DISCOVERY)
        discovered = self._discover_backfill_epoch()
        emit_operation(OperationStage.HISTORY)
        history_pages = (
            recovery_pages if recovery_epoch is not None else self._poll_history()
        )
        resolved, attention = self._resolve_events(max_events)
        resolved += converged
        if self._progress:
            self._progress()
        emit_operation(OperationStage.PROJECTION)
        projected = self._worker.run(max_jobs=max_jobs)
        projected = WorkerReceipt(
            **{
                field: getattr(projected, field) + getattr(known, field)
                for field in WorkerReceipt.__dataclass_fields__
            }
        )
        # An action effect may enqueue a thread expansion.  Drain the newly
        # visible event work and projection work in the same foreground cycle.
        more_resolved, more_attention = self._resolve_events(max_events)
        if more_resolved or more_attention:
            resolved += more_resolved
            attention += more_attention
            follow_up = self._worker.run(max_jobs=max_jobs)
            projected = WorkerReceipt(
                **{
                    field: getattr(projected, field) + getattr(follow_up, field)
                    for field in WorkerReceipt.__dataclass_fields__
                }
            )
        self._retain_live_epoch()
        self._finish_historical_epochs()
        return SyncCycleReceipt(
            discovered,
            history_pages,
            resolved,
            projected,
            attention,
            recovery.warnings()
            + (("target_missing",) if self._worker._inventory.missing else ()),
        )

    def _require_ready(self) -> None:
        """Reject a cycle before it can read Gmail or mutate queue state."""
        with self._owner.session.transaction() as uow:
            projection = reads.get_projection(uow, self._projection)
            if projection is None:
                raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
            if projection.binding_state is not BindingState.VERIFIED:
                raise StorageFailure(ErrorCode.BINDING_PENDING)
            if (
                projection.daemon_paused
                or projection.restore_state is not RestoreState.NORMAL
            ):
                raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
            for role in Role:
                binding = reads.get_binding(uow, self._projection, role)
                if binding is None or binding.state is not BindingState.VERIFIED:
                    raise StorageFailure(ErrorCode.BINDING_PENDING)

    def _recover_pre_dispatch_claims(self) -> int:
        """Hand off dead-owner claims; never replay a dispatched request."""
        with self._owner.session.transaction() as uow:
            stale = _query(
                uow,
                "SELECT a.attempt_id FROM insert_attempts a JOIN job_claims c "
                "ON c.projection_id=a.projection_id AND c.job_id=a.job_id "
                "WHERE a.projection_id=? AND c.owner_run_id<>? "
                "AND a.claim_id=c.claim_id AND a.state IN "
                "('prepared','dispatch_started','known_inserted')",
                (self._projection.value, self._owner.owner_info.owner_run_id.value),
                maximum=10_000,
            )
            for (attempt_id,) in stale:
                intents.handoff_previous_owner_attempt(
                    uow, self._projection, LocalId(attempt_id), _now()
                )
            orphaned = _query(
                uow,
                "SELECT "
                + ",".join(COLUMNS["insert_attempts"])
                + " FROM insert_attempts a WHERE a.projection_id=? "
                "AND a.state='dispatch_started' AND NOT EXISTS ("
                "SELECT 1 FROM job_claims c WHERE c.projection_id=a.projection_id "
                "AND c.job_id=a.job_id)",
                (self._projection.value,),
                maximum=10_000,
            )
            for values in orphaned:
                attempt = _decode(uow, self._projection, "insert_attempts", values)
                intents.reconcile_orphaned_attempt(
                    uow, self._projection, attempt.attempt_id, _now()
                )
            return jobs.requeue_preparing_claims(uow, self._projection)

    def _discover_backfill_epoch(self) -> int:
        with self._owner.session.transaction() as uow:
            rows = _query(
                uow,
                "SELECT epoch_id FROM epochs WHERE projection_id=? "
                "AND kind IN ('initial_backfill','historical_expansion') "
                "AND discovery_complete=0 AND state NOT IN "
                "('completed','completed_with_issues','needs_attention','paused') "
                "ORDER BY created_at,epoch_id LIMIT 1",
                (self._projection.value,),
                maximum=1,
            )
        if not rows:
            return 0
        epoch_id = LocalId(rows[0][0])
        if self._admission_for_epoch is not None:
            with self._owner.session.transaction() as uow:
                epoch = _get(uow, self._projection, "epochs", (("epoch_id", epoch_id),))
            if epoch is None:
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            admission = self._admission_for_epoch(epoch)
            if not isinstance(admission, PolicyAdmissionEvaluator):
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            backfill = BackfillProducer(
                self._source,
                SourceCandidateAdmission(self._source, admission),
                progress=self._progress,
            )
        else:
            backfill = self._backfill
        discovered = backfill.discover(self._owner.session, self._projection, epoch_id)
        with self._owner.session.transaction() as uow:
            epoch = _get(uow, self._projection, "epochs", (("epoch_id", epoch_id),))
            partition = _get(
                uow,
                self._projection,
                "epoch_partitions",
                (("epoch_id", epoch_id),),
            )
            if (
                epoch is not None
                and partition is not None
                and partition.progress.state.value == "complete"
                and not epoch.discovery_complete
            ):
                epochs.advance_epoch(
                    uow,
                    self._projection,
                    epoch_id,
                    EpochState.CATCHING_UP,
                    True,
                    Count(partition.progress.observed_items.value),
                    RevisionGuard(epoch.revision),
                )
        return discovered

    def _active_live_epoch(self):
        with self._owner.session.transaction() as uow:
            rows = _query(
                uow,
                "SELECT epoch_id FROM epochs WHERE projection_id=? "
                "AND kind='initial_backfill' AND state='draining' "
                "ORDER BY created_at DESC,epoch_id DESC LIMIT 1",
                (self._projection.value,),
                maximum=1,
            )
            return None if not rows else LocalId(rows[0][0])

    def _poll_history(self) -> int:
        with self._owner.session.transaction() as uow:
            checkpoint = reads.get_checkpoint(uow, self._projection)
            if checkpoint.active_poll_id is not None:
                # ``get_history_poll`` is a committed ReadSession facade.  We
                # are already inside the owner transaction here; use the
                # typed UoW getter so a resumed poll can actually continue.
                poll = _get(
                    uow,
                    self._projection,
                    "history_polls",
                    (("poll_id", checkpoint.active_poll_id),),
                )
                if poll is None:
                    raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            else:
                epoch_id = None
                if checkpoint.cursor is None:
                    row = _query(
                        uow,
                        "SELECT epoch_id,fence_history_id FROM epochs "
                        "WHERE projection_id=? AND kind='initial_backfill' "
                        "AND fence_history_id IS NOT NULL ORDER BY created_at "
                        "DESC,epoch_id DESC LIMIT 1",
                        (self._projection.value,),
                        maximum=1,
                    )
                    if not row:
                        return 0
                    epoch_id = LocalId(row[0][0])
                    cursor = row[0][1]
                    origin = PollOrigin.INITIAL_EPOCH
                else:
                    cursor = checkpoint.cursor.value
                    origin = PollOrigin.CHECKPOINT
                poll = HistoryPollRow(
                    self._projection,
                    _id(),
                    origin,
                    epoch_id,
                    ProviderId(cursor),
                    checkpoint.revision,
                    _now(),
                    PollState.READING,
                    Count(0),
                    None,
                    None,
                    None,
                    Revision(0),
                )
                from facet.db.repositories import history

                history.begin_history_poll(
                    uow,
                    self._projection,
                    poll,
                    RevisionGuard(checkpoint.revision),
                )
        before = poll.completed_pages.value
        self._history.consume(self._owner.session, self._projection, poll)
        return max(0, self._history_page_count(poll.poll_id) - before)

    def _history_page_count(self, poll_id: LocalId) -> int:
        with self._owner.session.transaction() as uow:
            row = _query(
                uow,
                "SELECT completed_pages FROM history_polls WHERE projection_id=? "
                "AND poll_id=?",
                (self._projection.value, poll_id.value),
                maximum=1,
            )
            return 0 if not row else row[0][0]

    def _pending_resolve_jobs(self):
        with self._owner.session.transaction() as uow:
            rows = _query(
                uow,
                "SELECT " + ",".join(COLUMNS["sync_jobs"]) + " FROM sync_jobs "
                "WHERE projection_id=? AND kind='resolve_event' AND (state IN "
                "('queued','retry_wait') OR (? AND state='needs_attention' "
                "AND last_error_code IN "
                "('request_conflict','owner_unavailable','invalid_input') "
                "AND EXISTS (SELECT 1 FROM source_events e WHERE "
                "e.projection_id=sync_jobs.projection_id AND "
                "e.event_id=sync_jobs.event_id AND e.tag='label_changed'))) "
                "AND (next_attempt_at IS NULL OR "
                "next_attempt_at<=?) ORDER BY created_at,job_id LIMIT 1000",
                (
                    self._projection.value,
                    int(callable(getattr(self._action, "begin_cycle", None))),
                    timestamp_to_sql(_now()),
                ),
                maximum=1000,
            )
            return tuple(
                _decode(uow, self._projection, "sync_jobs", row) for row in rows
            )

    def _resolve_events(self, limit: int) -> tuple[int, int]:
        resolved = attention = 0
        for job in self._pending_resolve_jobs()[:limit]:
            if self._should_stop and self._should_stop():
                break
            if self._progress:
                self._progress()
            key = job.subject.event_key
            if hasattr(key, "label_id"):
                if self._action is None:
                    self._defer_event_attention(job, ErrorCode.OWNER_UNAVAILABLE)
                    attention += 1
                    continue
                try:
                    result = self._action.process(
                        self._owner.session,
                        self._projection,
                        self._event_id(job),
                        epoch_id=self._active_live_epoch() or job.origin_epoch_id,
                    )
                except (StorageFailure, ProviderFailure) as error:
                    if (
                        isinstance(error, ProviderFailure)
                        and error.role is Role.SOURCE
                        and error.status == 404
                    ):
                        error = error.with_code(ErrorCode.SOURCE_MISSING)
                    retryable = error.code in {
                        ErrorCode.SOURCE_AUTH_REQUIRED,
                        ErrorCode.SOURCE_RATE_LIMITED,
                        ErrorCode.NETWORK_UNAVAILABLE,
                        ErrorCode.OWNER_BUSY,
                    }
                    self._defer_event_attention(
                        job,
                        error.code,
                        retryable=retryable,
                        retry_after_seconds=(
                            error.retry_after_seconds
                            if isinstance(error, ProviderFailure)
                            else None
                        ),
                    )
                    if isinstance(error, ProviderFailure) and blocks_sync(error):
                        raise
                    attention += 1
                    continue
                if result.attention is not None:
                    attention += 1
                else:
                    resolved += 1
                continue
            if key.tag != "message_added":
                if isinstance(
                    key, SourceEventKeyMessageDeleted
                ) and self._ignore_untracked_deletion(job):
                    resolved += 1
                    continue
                self._defer_event_attention(job, ErrorCode.REQUEST_CONFLICT)
                attention += 1
                continue
            try:
                if callable(getattr(self._action, "begin_cycle", None)):
                    self._action.process(
                        self._owner.session,
                        self._projection,
                        self._event_id(job),
                        epoch_id=self._active_live_epoch() or job.origin_epoch_id,
                    )
                self._resolve_message_added(job)
            except (ProviderFailure, StorageFailure) as error:
                # A vanished source message is not malformed input. Keep this
                # local: History 404 and target 404 have different recovery.
                if (
                    isinstance(error, ProviderFailure)
                    and error.role is Role.SOURCE
                    and error.status == 404
                ):
                    error = error.with_code(ErrorCode.SOURCE_MISSING)
                retryable = error.code in {
                    ErrorCode.SOURCE_AUTH_REQUIRED,
                    ErrorCode.SOURCE_RATE_LIMITED,
                    ErrorCode.NETWORK_UNAVAILABLE,
                    ErrorCode.OWNER_BUSY,
                }
                self._defer_event_attention(
                    job,
                    error.code,
                    retryable=retryable,
                    retry_after_seconds=(
                        error.retry_after_seconds
                        if isinstance(error, ProviderFailure)
                        else None
                    ),
                )
                if isinstance(error, ProviderFailure) and blocks_sync(error):
                    raise
                attention += 1
            else:
                resolved += 1
        return resolved, attention

    def _converge_completed_events(self, limit):
        """Repair only false attention backed by an exact existing durable effect."""
        with self._owner.session.transaction() as uow:
            rows = _query(
                uow,
                "SELECT "
                + ",".join(COLUMNS["sync_jobs"])
                + " FROM sync_jobs WHERE projection_id=? AND kind='resolve_event' "
                "AND state='needs_attention' AND last_error_code='request_conflict' "
                "ORDER BY created_at,job_id LIMIT ?",
                (self._projection.value, limit),
                maximum=limit,
            )
            selected = tuple(
                _decode(uow, self._projection, "sync_jobs", row) for row in rows
            )
        resolved = 0
        for job in selected:
            # Failed evidence guards poison a UoW, so each candidate owns a
            # separate transaction. No swallowing a failed guard then committing.
            try:
                event_id = self._event_id(job)
                with self._owner.session.transaction() as uow:
                    event = reads.get_event(uow, self._projection, event_id)
                    if job.subject.event_key.tag == "label_changed":
                        events.repair_executed_label_alias(
                            uow,
                            self._projection,
                            event.event_id,
                            RevisionGuard(event.revision),
                            RevisionGuard(job.revision),
                            observed_at=_now(),
                        )
                    else:
                        events.consume_message_added_existing_effect(
                            uow,
                            self._projection,
                            event.event_id,
                            RevisionGuard(event.revision),
                            RevisionGuard(job.revision),
                            _now(),
                        )
            except StorageFailure as error:
                if error.code not in {ErrorCode.REQUEST_CONFLICT, ErrorCode.OWNER_BUSY}:
                    raise
            else:
                resolved += 1
        return resolved

    def _ignore_untracked_deletion(self, resolve_job: SyncJobRow) -> bool:
        """Close a deletion event only when its source thread was never tracked."""
        with self._owner.session.transaction() as uow:
            event = _get(
                uow,
                self._projection,
                "source_events",
                (
                    (
                        "event_key",
                        event_key(self._projection, resolve_job.subject.event_key),
                    ),
                ),
            )
            job = reads.get_job(uow, self._projection, resolve_job.job_id)
            if (
                event is None
                or job is None
                or job.state
                not in {
                    JobState.QUEUED,
                    JobState.RETRY_WAIT,
                }
            ):
                return False
            if event.event.source_thread_id is None:
                return False
            if (
                reads.get_thread(uow, self._projection, event.event.source_thread_id)
                is not None
            ):
                return False
            now = _now()
            claim = Claim(
                _id(),
                self._owner.owner_info.owner_run_id,
                now,
                None,
                Revision(job.revision.value + 1),
                ClaimPhase.PREPARING,
            )
            jobs.claim(
                uow,
                self._projection,
                job.job_id,
                claim,
                RevisionGuard(job.revision),
                now,
            )
            events.classify_event(
                uow,
                self._projection,
                event.event_id,
                EventProcessing.CONSUMED,
                None,
                (),
                RevisionGuard(event.revision),
            )
            completed = reads.get_job(uow, self._projection, job.job_id)
            jobs.complete_noninsert_job(
                uow,
                self._projection,
                job.job_id,
                RevisionGuard(completed.revision),
            )
            return True

    def _defer_event_attention(
        self,
        resolve_job: SyncJobRow,
        error: ErrorCode,
        *,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        """Persist review or retry state for event work that did not converge."""
        with self._owner.session.transaction() as uow:
            event_row = _get(
                uow,
                self._projection,
                "source_events",
                (
                    (
                        "event_key",
                        event_key(self._projection, resolve_job.subject.event_key),
                    ),
                ),
            )
            event = (
                None
                if event_row is None
                else reads.get_event(uow, self._projection, event_row.event_id)
            )
            job = reads.get_job(uow, self._projection, resolve_job.job_id)
            if (
                event is not None
                and job is not None
                and job.state is JobState.NEEDS_ATTENTION
                and callable(getattr(self._action, "begin_cycle", None))
                and isinstance(event.event.key, SourceEventKeyLabelChanged)
                and event.processing is EventProcessing.NEEDS_ATTENTION
                and event.error_code
                in {
                    ErrorCode.OWNER_UNAVAILABLE,
                    ErrorCode.REQUEST_CONFLICT,
                    ErrorCode.INVALID_INPUT,
                }
                and job.last_error_code
                in {
                    ErrorCode.OWNER_UNAVAILABLE,
                    ErrorCode.REQUEST_CONFLICT,
                    ErrorCode.INVALID_INPUT,
                }
            ):
                # A qualified current-state recheck is not a generic queue
                # retry. Reuse guarded deferral; never ACK or dispatch effects.
                now = _now()
                if error is ErrorCode.SOURCE_MISSING:
                    events.classify_event(
                        uow,
                        self._projection,
                        event.event_id,
                        EventProcessing.SOURCE_MISSING,
                        error,
                        (),
                        RevisionGuard(event.revision),
                    )
                jobs.defer_job(
                    uow,
                    self._projection,
                    job.job_id,
                    "retry_wait"
                    if retryable
                    else "source_missing"
                    if error is ErrorCode.SOURCE_MISSING
                    else "needs_attention",
                    error,
                    Timestamp(
                        now.value
                        + max(_RETRY_DELAY, timedelta(seconds=retry_after_seconds or 0))
                    )
                    if retryable
                    else None,
                    RevisionGuard(job.revision),
                )
                return
            if (
                event is None
                or job is None
                or job.state
                not in {
                    JobState.QUEUED,
                    JobState.RETRY_WAIT,
                }
            ):
                return
            now = _now()
            claim = Claim(
                _id(),
                self._owner.owner_info.owner_run_id,
                now,
                None,
                Revision(job.revision.value + 1),
                ClaimPhase.PREPARING,
            )
            jobs.claim(
                uow,
                self._projection,
                job.job_id,
                claim,
                RevisionGuard(job.revision),
                now,
            )
            claimed = reads.get_job(uow, self._projection, job.job_id)
            if not retryable and event.processing not in {
                EventProcessing.NEEDS_ATTENTION,
                EventProcessing.SOURCE_MISSING,
            }:
                events.classify_event(
                    uow,
                    self._projection,
                    event.event_id,
                    EventProcessing.SOURCE_MISSING
                    if error is ErrorCode.SOURCE_MISSING
                    else EventProcessing.NEEDS_ATTENTION,
                    error,
                    (),
                    RevisionGuard(event.revision),
                )
            jobs.defer_job(
                uow,
                self._projection,
                claimed.job_id,
                "retry_wait"
                if retryable
                else "source_missing"
                if error is ErrorCode.SOURCE_MISSING
                else "needs_attention",
                error,
                Timestamp(
                    now.value
                    + max(_RETRY_DELAY, timedelta(seconds=retry_after_seconds or 0))
                )
                if retryable
                else None,
                RevisionGuard(claimed.revision),
            )

    def _event_id(self, job: SyncJobRow) -> LocalId:
        with self._owner.session.transaction() as uow:
            row = _get(
                uow,
                self._projection,
                "sync_jobs",
                (("job_id", job.job_id),),
            )
            if row is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            event = _get(
                uow,
                self._projection,
                "source_events",
                (("event_key", event_key(self._projection, job.subject.event_key)),),
            )
            if event is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            return event.event_id

    def _resolve_message_added(self, resolve_job: SyncJobRow) -> bool:
        """Read outside SQL; atomically consume, project or admit one event."""
        event_id = self._event_id(resolve_job)
        with self._owner.session.transaction() as uow:
            event = reads.get_event(uow, self._projection, event_id)
            job = reads.get_job(uow, self._projection, resolve_job.job_id)
            if event is None or job is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            thread_id = event.event.source_thread_id
            if thread_id is None or event.processing is not EventProcessing.PENDING:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            thread = reads.get_thread(uow, self._projection, thread_id)
            mapped = reads.get_mapping(
                uow, self._projection, event.event.key.source_message_id
            )
            if mapped is not None and mapped.source_thread_id != thread_id:
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)

        # Existing projection work is already the durable effect of this
        # notification, including unknown-blocked work. Do not enqueue it twice.
        try:
            with self._owner.session.transaction() as uow:
                events.consume_message_added_existing_effect(
                    uow,
                    self._projection,
                    event_id,
                    RevisionGuard(event.revision),
                    RevisionGuard(job.revision),
                    _now(),
                )
            return True
        except StorageFailure as error:
            if error.code is not ErrorCode.REQUEST_CONFLICT:
                raise

        selected_policy = decision = metadata = None
        if mapped is None and (thread is None or thread.active):
            item = DiscoveryItem(event.event.key.source_message_id, thread_id)
            if thread is None:
                selected_policy = (
                    self._admission_for_history()
                    if self._admission_for_history is not None
                    else self._history_admission
                )
                if not isinstance(selected_policy, PolicyAdmissionEvaluator):
                    raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
                if selected_policy.enabled_allow_rules:
                    result = self._source.history_candidate(item)
                    if result.attention is not None:
                        raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
                    decision = selected_policy.evaluate(
                        result.candidate, _now(), prospective=True
                    )
                    if decision.attention_reason in {
                        AdmissionAttentionReason.SOURCE_ACCOUNT_MISMATCH,
                        AdmissionAttentionReason.CANDIDATE_INVALID,
                    }:
                        raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            else:
                metadata = self._source.message_metadata(item.message_id)
                if (
                    metadata.message_id != item.message_id
                    or metadata.thread_id != item.thread_id
                ):
                    raise StorageFailure(ErrorCode.REQUEST_CONFLICT)

        epoch_id = self._active_live_epoch() or resolve_job.origin_epoch_id
        now = _now()
        with self._owner.session.transaction() as uow:
            current_event = reads.get_event(uow, self._projection, event_id)
            current_job = reads.get_job(uow, self._projection, resolve_job.job_id)
            current_thread = reads.get_thread(uow, self._projection, thread_id)
            if current_event != event or current_job != job or current_thread != thread:
                raise StorageFailure(ErrorCode.OWNER_BUSY)
            if selected_policy is not None:
                projection = _get(uow, self._projection, "projections", ())
                if projection.ruleset_revision != selected_policy.ruleset_revision:
                    raise StorageFailure(ErrorCode.OWNER_BUSY)
            claim = Claim(
                _id(),
                self._owner.owner_info.owner_run_id,
                now,
                None,
                Revision(job.revision.value + 1),
                ClaimPhase.PREPARING,
            )
            if job.state in {JobState.QUEUED, JobState.RETRY_WAIT}:
                jobs.claim(
                    uow,
                    self._projection,
                    job.job_id,
                    claim,
                    RevisionGuard(job.revision),
                    now,
                )
                job = reads.get_job(uow, self._projection, job.job_id)
            subject = None
            if (
                mapped is None
                and thread is None
                and decision is not None
                and decision.admit
            ):
                epoch = (
                    _get(uow, self._projection, "epochs", (("epoch_id", epoch_id),))
                    if epoch_id is not None
                    else None
                )
                if (
                    epoch is None
                    or epoch.kind is not EpochKind.INITIAL_BACKFILL
                    or epoch.decision.tag != "backfill_start"
                    or epoch.state
                    not in {
                        EpochState.SCANNING,
                        EpochState.CATCHING_UP,
                        EpochState.DRAINING,
                    }
                ):
                    raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
                admitted = TrackedThreadRow(
                    self._projection,
                    thread_id,
                    True,
                    Generation(1),
                    now,
                    None,
                    None,
                    Revision(1),
                )
                rule = _get(
                    uow,
                    self._projection,
                    "rule_revisions",
                    (
                        ("rule_id", decision.rule.rule_id),
                        ("revision", decision.rule.revision),
                    ),
                )
                admission = ThreadAdmissionRow(
                    self._projection,
                    thread_id,
                    Revision(1),
                    Generation(1),
                    now,
                    AdmissionRefFutureRule(
                        "future_rule", decision.rule, rule.policy_version
                    ),
                )
                policy.admit_thread(
                    uow,
                    self._projection,
                    admitted,
                    admission,
                    (),
                    ThreadGenerationGuardUntracked("untracked"),
                )
                subject = JobSubjectExpandThread(
                    "expand_thread", thread_id, epoch_id, Generation(1)
                )
            elif (
                mapped is None
                and thread is not None
                and thread.active
                and "DRAFT" not in metadata.labels
            ):
                subject = JobSubjectProjectMessage(
                    "project_message",
                    event.event.key.source_message_id,
                    thread_id,
                    thread.generation,
                )
            projects = ()
            if subject is not None:
                project = _get(
                    uow,
                    self._projection,
                    "sync_jobs",
                    (("stable_key", job_key(self._projection, subject)),),
                ) or SyncJobRow(
                    self._projection,
                    _id(),
                    JobKind.EXPAND_THREAD
                    if thread is None
                    else JobKind.PROJECT_MESSAGE,
                    Count(1),
                    job_key(self._projection, subject),
                    Priority.REALTIME,
                    JobState.QUEUED,
                    Revision(0),
                    now,
                    now,
                    None,
                    Count(0),
                    None,
                    epoch_id,
                    subject,
                )
                projects = (project,)
                events.classify_event(
                    uow,
                    self._projection,
                    event_id,
                    EventProcessing.RESOLVED,
                    None,
                    projects,
                    RevisionGuard(event.revision),
                )
                refreshed = reads.get_event(uow, self._projection, event_id)
                events.classify_event(
                    uow,
                    self._projection,
                    event_id,
                    EventProcessing.CONSUMED,
                    None,
                    projects,
                    RevisionGuard(refreshed.revision),
                )
            else:
                events.consume_message_added_no_effect(
                    uow, self._projection, event_id, RevisionGuard(event.revision)
                )
            refreshed_job = reads.get_job(uow, self._projection, job.job_id)
            jobs.complete_noninsert_job(
                uow,
                self._projection,
                job.job_id,
                RevisionGuard(refreshed_job.revision),
            )
        return True

    def _retain_live_epoch(self) -> None:
        """Leave the initial epoch in DRAINING for future action authorization."""
        with self._owner.session.transaction() as uow:
            rows = _query(
                uow,
                "SELECT epoch_id FROM epochs WHERE projection_id=? "
                "AND kind='initial_backfill' AND discovery_complete=1 "
                "AND state='catching_up' ORDER BY created_at DESC,epoch_id DESC "
                "LIMIT 1",
                (self._projection.value,),
                maximum=1,
            )
            if not rows:
                return
            epoch = _get(
                uow,
                self._projection,
                "epochs",
                (("epoch_id", LocalId(rows[0][0])),),
            )
            epochs.advance_epoch(
                uow,
                self._projection,
                epoch.epoch_id,
                EpochState.DRAINING,
                True,
                epoch.known_message_total,
                RevisionGuard(epoch.revision),
            )

    def _finish_historical_epochs(self) -> None:
        with self._owner.session.transaction() as uow:
            rows = _query(
                uow,
                "SELECT epoch_id FROM epochs WHERE projection_id=? "
                "AND kind IN ('historical_expansion','history_gap') "
                "AND discovery_complete=1 "
                "AND state IN ('catching_up','draining') ORDER BY created_at,epoch_id",
                (self._projection.value,),
            )
            for (identifier,) in rows:
                epoch = _get(
                    uow,
                    self._projection,
                    "epochs",
                    (("epoch_id", LocalId(identifier)),),
                )
                if epoch.kind is EpochKind.HISTORY_GAP:
                    if epoch.catchup_history_id is None:
                        continue
                elif not epochs.historical_coverage_complete(
                    uow, self._projection, epoch
                ):
                    continue
                work = _query(
                    uow,
                    "SELECT DISTINCT j.state FROM sync_jobs j JOIN epoch_jobs e "
                    "ON e.projection_id=j.projection_id AND e.job_id=j.job_id "
                    "WHERE e.projection_id=? AND e.epoch_id=?",
                    (self._projection.value, identifier),
                    maximum=9,
                )
                if any(status not in epochs._TERMINAL for (status,) in work):
                    continue
                state = (
                    EpochState.COMPLETED_WITH_ISSUES
                    if any(status != "completed" for (status,) in work)
                    else EpochState.COMPLETED
                )
                epochs.advance_epoch(
                    uow,
                    self._projection,
                    epoch.epoch_id,
                    state,
                    True,
                    epoch.known_message_total,
                    RevisionGuard(epoch.revision),
                )


__all__ = ("ForegroundSync", "SyncCycleReceipt")
