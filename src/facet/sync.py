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
    EpochState,
    ErrorCode,
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
from facet.contracts.records import JobSubjectProjectMessage
from facet.db.codecs import (
    EventProcessing,
    PollOrigin,
    PollState,
    StorageFailure,
    timestamp_to_sql,
)
from facet.db.keys import event_key, job_key
from facet.db.models import HistoryPollRow, RevisionGuard, SyncJobRow
from facet.db.repositories import epochs, events, intents, jobs, reads
from facet.db.repositories.base import _decode, _get, _query
from facet.db.repositories.serialization import COLUMNS
from facet.gmail.retry import ProviderFailure
from facet.gmail.source import CandidateAttentionReason, DiscoveryQuery
from facet.projection.action_consumer import ActionEffectConsumer
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
        if any(rule.normalized.kind is RuleKind.ALLOW_DOMAIN for rule in rules):
            # Gmail's broad domain search semantics are not yet accepted as a
            # complete parent/subdomain candidate superset. Never fall back to
            # an unfiltered mailbox scan while that evidence gate is closed.
            raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
        clauses = tuple(
            sorted(
                {
                    'from:"'
                    + rule.normalized.value.value.replace("\\", "\\\\").replace(
                        '"', '\\"'
                    )
                    + '"'
                    for rule in rules
                    if rule.normalized.kind is RuleKind.ALLOW_SENDER
                }
            )
        )
        return DiscoveryQuery(clauses)

    def evaluate(self, item, epoch):
        from facet.projection.backfill import DiscoveryDecision

        try:
            result = self._source.candidate(item)
        except ProviderFailure as error:
            return DiscoveryDecision(False, attention=error.code)
        if result.attention is not None:
            code = (
                ErrorCode.SOURCE_AUTH_REQUIRED
                if result.attention.reason is CandidateAttentionReason.PROVIDER_FAILURE
                else ErrorCode.REQUEST_CONFLICT
            )
            return DiscoveryDecision(False, attention=code)
        decision = self._policy.evaluate(result.candidate, _now())
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
        max_raw_bytes: int = 35_000_000,
    ) -> None:
        if (
            not hasattr(owner, "session")
            or not hasattr(source, "profile")
            or not hasattr(source, "history")
            or not hasattr(target, "insert")
            or not hasattr(admission, "evaluate")
            or (admission_for_epoch is not None and not callable(admission_for_epoch))
        ):
            raise ValueError("invalid_input")
        if type(max_raw_bytes) is not int or not 1 <= max_raw_bytes <= 35_000_000:
            raise ValueError("invalid_input")
        self._owner = owner
        self._source = source
        self._target = target
        self._projection = owner.projection_id
        self._admission_for_epoch = admission_for_epoch
        self._admission = (
            SourceCandidateAdmission(source, admission)
            if isinstance(admission, PolicyAdmissionEvaluator)
            else admission
        )
        self._backfill = BackfillProducer(source, self._admission)
        self._history = HistoryProducer(source)
        self._worker = ProjectionWorker(
            owner, source, target, max_raw_bytes=max_raw_bytes
        )
        self._action = action_consumer

    def run_once(self, *, max_jobs: int = 1000, max_events: int = 1000):
        """Advance discovery, History and durable jobs once, then return counts."""
        if (
            type(max_jobs) is not int
            or not 1 <= max_jobs <= 10_000
            or type(max_events) is not int
            or not 1 <= max_events <= 10_000
        ):
            raise ValueError("invalid_input")
        self._require_ready()
        self._recover_pre_dispatch_claims()
        discovered = self._discover_initial_epoch()
        history_pages = self._poll_history()
        resolved, attention = self._resolve_events(max_events)
        projected = self._worker.run(max_jobs=max_jobs)
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
        return SyncCycleReceipt(
            discovered,
            history_pages,
            resolved,
            projected,
            attention,
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
        """Requeue only claims with no remote-dispatch evidence.

        Dispatch-started and pending-recovery attempts are intentionally absent
        from this transition and remain visible for explicit recovery.
        """
        with self._owner.session.transaction() as uow:
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

    def _discover_initial_epoch(self) -> int:
        with self._owner.session.transaction() as uow:
            rows = _query(
                uow,
                "SELECT epoch_id FROM epochs WHERE projection_id=? "
                "AND kind='initial_backfill' AND state NOT IN "
                "('completed','completed_with_issues','needs_attention') "
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
            self._admission = SourceCandidateAdmission(self._source, admission)
            self._backfill = BackfillProducer(self._source, self._admission)
        discovered = self._backfill.discover(
            self._owner.session, self._projection, epoch_id
        )
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
                poll = reads.get_history_poll(
                    uow, self._projection, checkpoint.active_poll_id
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
                "WHERE projection_id=? AND kind='resolve_event' AND state IN "
                "('queued','retry_wait') AND (next_attempt_at IS NULL OR "
                "next_attempt_at<=?) ORDER BY created_at,job_id LIMIT 1000",
                (self._projection.value, timestamp_to_sql(_now())),
                maximum=1000,
            )
            return tuple(
                _decode(uow, self._projection, "sync_jobs", row) for row in rows
            )

    def _resolve_events(self, limit: int) -> tuple[int, int]:
        resolved = attention = 0
        for job in self._pending_resolve_jobs()[:limit]:
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
                except StorageFailure as error:
                    retryable = error.code in {
                        ErrorCode.SOURCE_AUTH_REQUIRED,
                        ErrorCode.SOURCE_RATE_LIMITED,
                        ErrorCode.NETWORK_UNAVAILABLE,
                        ErrorCode.OWNER_BUSY,
                    }
                    self._defer_event_attention(job, error.code, retryable=retryable)
                    attention += 1
                    continue
                if result.attention is not None:
                    attention += 1
                else:
                    resolved += 1
                continue
            if key.tag != "message_added":
                self._defer_event_attention(job, ErrorCode.REQUEST_CONFLICT)
                attention += 1
                continue
            if self._resolve_message_added(job):
                resolved += 1
            else:
                attention += 1
        return resolved, attention

    def _defer_event_attention(
        self,
        resolve_job: SyncJobRow,
        error: ErrorCode,
        *,
        retryable: bool = False,
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
                    EventProcessing.NEEDS_ATTENTION,
                    error,
                    (),
                    RevisionGuard(event.revision),
                )
            jobs.defer_job(
                uow,
                self._projection,
                claimed.job_id,
                "retry_wait" if retryable else "needs_attention",
                error,
                Timestamp(now.value + _RETRY_DELAY) if retryable else None,
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
        event_id = self._event_id(resolve_job)
        now = _now()
        with self._owner.session.transaction() as uow:
            event = reads.get_event(uow, self._projection, event_id)
            job = reads.get_job(uow, self._projection, resolve_job.job_id)
            if event is None or job is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
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
            if event.event.source_thread_id is None:
                events.classify_event(
                    uow,
                    self._projection,
                    event_id,
                    EventProcessing.NEEDS_ATTENTION,
                    ErrorCode.REQUEST_CONFLICT,
                    (),
                    RevisionGuard(event.revision),
                )
                jobs.defer_job(
                    uow,
                    self._projection,
                    job.job_id,
                    "needs_attention",
                    ErrorCode.REQUEST_CONFLICT,
                    None,
                    RevisionGuard(job.revision),
                )
                return False
            thread = reads.get_thread(
                uow, self._projection, event.event.source_thread_id
            )
            if thread is None or not thread.active:
                events.classify_event(
                    uow,
                    self._projection,
                    event_id,
                    EventProcessing.NEEDS_ATTENTION,
                    ErrorCode.REQUEST_CONFLICT,
                    (),
                    RevisionGuard(event.revision),
                )
                jobs.defer_job(
                    uow,
                    self._projection,
                    job.job_id,
                    "needs_attention",
                    ErrorCode.REQUEST_CONFLICT,
                    None,
                    RevisionGuard(job.revision),
                )
                return False
            key = event.event.key
            subject = JobSubjectProjectMessage(
                "project_message",
                key.source_message_id,
                event.event.source_thread_id,
                thread.generation,
            )
            mapped = reads.get_mapping(uow, self._projection, key.source_message_id)
            project = _get(
                uow,
                self._projection,
                "sync_jobs",
                (("stable_key", job_key(self._projection, subject)),),
            )
            if mapped is None:
                project = project or SyncJobRow(
                    self._projection,
                    _id(),
                    JobKind.PROJECT_MESSAGE,
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
                    resolve_job.origin_epoch_id,
                    subject,
                )
            if project is None:
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            events.classify_event(
                uow,
                self._projection,
                event_id,
                EventProcessing.RESOLVED,
                None,
                (project,),
                RevisionGuard(event.revision),
            )
            refreshed = reads.get_event(uow, self._projection, event_id)
            events.classify_event(
                uow,
                self._projection,
                event_id,
                EventProcessing.CONSUMED,
                None,
                (project,),
                RevisionGuard(refreshed.revision),
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


__all__ = ("ForegroundSync", "SyncCycleReceipt")
