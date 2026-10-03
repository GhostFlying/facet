"""Owner-side durable consumer for readonly Gmail action labels.

This module composes the already reviewed typed producer and SQLite
repositories. Source reads happen outside transactions; only normalized rule,
thread, action and job metadata cross the persistence boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from facet.contracts import (
    Claim,
    ClaimPhase,
    Count,
    ErrorCode,
    Generation,
    JobKind,
    JobState,
    LocalId,
    Priority,
    ProjectionId,
    Revision,
    RuleKind,
    RuleOrigin,
    ThreadGenerationGuard,
    Timestamp,
)
from facet.contracts.records import (
    AdmissionRefActionLabel,
    JobSubjectExpandThread,
    JobSubjectResolveEvent,
    RuleRef,
    SourceEventKeyLabelChanged,
    ThreadGenerationGuardTracked,
    ThreadGenerationGuardUntracked,
)
from facet.db.codecs import (
    ActionKind,
    ActionState,
    CleanupState,
    EventProcessing,
    StorageFailure,
    ThreadStopReason,
)
from facet.db.keys import job_key
from facet.db.models import (
    ActionCommandRow,
    RevisionGuard,
    RuleRevisionRow,
    RuleRow,
    RulesetMemberRow,
    RulesetRow,
    SyncJobRow,
    ThreadAdmissionRow,
    TrackedThreadRow,
    WriteReceipt,
)
from facet.db.repositories import actions, events, jobs, policy, reads
from facet.db.repositories.base import _get
from facet.projection.actions import (
    ActionActivation,
    ActionAttention,
    ActionAttentionReason,
    ActionLabelProducer,
    ActionSourceReader,
    PrivateActionLabelMap,
)
from facet.projection.rules import (
    RuleInputError,
    learn_domain,
    load_rule_policy,
    normalize_rule,
)

__all__ = ("ActionEffectResult", "ActionEffectConsumer")


@dataclass(frozen=True, slots=True, repr=False)
class ActionEffectResult:
    """Redacted result of one durable action decision."""

    receipt: WriteReceipt | None = None
    attention: ActionAttentionReason | ErrorCode | None = None

    def __post_init__(self) -> None:
        if (self.receipt is None) == (self.attention is None):
            raise ValueError("invalid_input")
        if self.attention is not None and type(self.attention) not in {
            ActionAttentionReason,
            ErrorCode,
        }:
            raise ValueError("invalid_input")

    def __repr__(self) -> str:
        if self.receipt is not None:
            return "<action effect result: receipt>"
        return "<action effect result: attention>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class _Prepared:
    event_id: LocalId
    job_id: LocalId
    event: object
    job: SyncJobRow
    action: ActionCommandRow | None

    def __repr__(self) -> str:
        return "<prepared action effect>"


def _new_id() -> LocalId:
    return LocalId(uuid4().hex)


def _now(at_least: Timestamp | None = None) -> Timestamp:
    value = datetime.now(UTC)
    if at_least is not None and value < at_least.value:
        value = at_least.value
    return Timestamp(value)


def _attention_code(reason: ActionAttentionReason) -> ErrorCode:
    # The event table stores only the fixed public error inventory. The reason
    # remains available in the in-process result without persisting private
    # source facts.
    if reason is ActionAttentionReason.DUPLICATE_EVENT:
        return ErrorCode.CONSISTENCY_FAILURE
    return ErrorCode.REQUEST_CONFLICT


def _rule_kind(kind: ActionKind) -> RuleKind:
    return {
        ActionKind.ADD_SENDER: RuleKind.ALLOW_SENDER,
        ActionKind.ADD_DOMAIN: RuleKind.ALLOW_DOMAIN,
        ActionKind.BLACKLIST: RuleKind.BLACKLIST_SENDER,
    }[kind]


def _action(uow, projection_id: ProjectionId, row) -> ActionCommandRow | None:
    key = row.event.key
    if row.event.source_thread_id is None or not hasattr(key, "history_record_id"):
        return None
    return _get(
        uow,
        projection_id,
        "action_commands",
        (
            ("event_id", row.event_id),
            ("history_record_id", key.history_record_id),
            ("label_id", key.label_id),
            ("source_thread_id", row.event.source_thread_id),
        ),
    )


def _resolve_job(uow, projection_id: ProjectionId, row):
    subject = JobSubjectResolveEvent("resolve_event", row.event.key)
    return _get(
        uow,
        projection_id,
        "sync_jobs",
        (("stable_key", job_key(projection_id, subject)),),
    )


def _epoch_is_authorized(uow, projection_id: ProjectionId, epoch_id: LocalId) -> None:
    epoch = reads.get_epoch(uow, projection_id, epoch_id)
    if epoch is None or epoch.state.value in {
        "completed",
        "completed_with_issues",
        "needs_attention",
    }:
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)


def _require_owned_claim(uow, projection_id, job: SyncJobRow, owner_run_id) -> None:
    claim = _get(uow, projection_id, "job_claims", (("job_id", job.job_id),))
    if (
        claim is None
        or claim.claim.owner_run_id != owner_run_id
        or claim.claim.phase is not ClaimPhase.PREPARING
        or claim.claim.job_revision != job.revision
    ):
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)


class ActionEffectConsumer:
    """Consumes one persisted ``RESOLVE_EVENT`` job under the owner lock."""

    def __init__(
        self,
        labels: PrivateActionLabelMap,
        source: ActionSourceReader,
        own_addresses: tuple,
        source_primary: str,
    ) -> None:
        if (
            type(labels) is not PrivateActionLabelMap
            or not hasattr(source, "get_thread_facts")
            or type(own_addresses) is not tuple
            or not own_addresses
            or type(source_primary) is not str
        ):
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        self._labels = labels
        self._source = source
        self._own_addresses = own_addresses
        self._source_primary = source_primary
        self._producer = ActionLabelProducer()

    def process(
        self,
        owner,
        projection_id: ProjectionId,
        event_id: LocalId,
        *,
        epoch_id: LocalId | None = None,
    ) -> ActionEffectResult:
        if type(projection_id) is not ProjectionId or type(event_id) is not LocalId:
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        for _ in range(4):
            prepared = self._prepare(owner, projection_id, event_id)
            if prepared is None:
                continue
            if (
                prepared.action is not None
                and prepared.action.state is ActionState.NEEDS_ATTENTION
            ):
                return ActionEffectResult(
                    attention=prepared.action.error_code or ErrorCode.OWNER_UNAVAILABLE
                )
            if (
                prepared.action is not None
                and prepared.action.state is ActionState.EXECUTED
            ):
                return self._finalize(owner, projection_id, prepared, epoch_id)
            if prepared.event.processing in {
                EventProcessing.NEEDS_ATTENTION,
                EventProcessing.SOURCE_MISSING,
            }:
                return ActionEffectResult(attention=prepared.event.error_code)
            if prepared.event.event.source_thread_id is None:
                return self._attention(
                    owner,
                    projection_id,
                    prepared,
                    ActionAttentionReason.UNKNOWN_LABEL,
                )
            try:
                decision = self._producer.consume(
                    prepared.event.event,
                    self._labels,
                    self._source,
                    self._own_addresses,
                )
            except StorageFailure as error:
                return self._attention(
                    owner,
                    projection_id,
                    prepared,
                    error.code,
                )
            except Exception:
                return self._attention(
                    owner,
                    projection_id,
                    prepared,
                    ErrorCode.OWNER_UNAVAILABLE,
                )
            if isinstance(decision, ActionAttention):
                return self._attention(
                    owner,
                    projection_id,
                    prepared,
                    decision.reason,
                )
            try:
                normalized = self._normalize(decision)
            except StorageFailure as error:
                return self._attention(owner, projection_id, prepared, error.code)
            receipt = self._apply(
                owner,
                projection_id,
                prepared,
                decision,
                normalized,
                epoch_id,
            )
            return self._finalize(
                owner,
                projection_id,
                self._reload(owner, projection_id, event_id),
                epoch_id,
                receipt,
            )
        raise StorageFailure(ErrorCode.OWNER_BUSY)

    def _prepare(self, owner, projection_id, event_id) -> _Prepared | None:
        now = _now()
        with owner.transaction() as uow:
            event = reads.get_event(uow, projection_id, event_id)
            if event is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            key = event.event.key
            if type(key) is not SourceEventKeyLabelChanged:
                raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
            job = _resolve_job(uow, projection_id, event)
            if job is None or job.kind is not JobKind.RESOLVE_EVENT:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            action = _action(uow, projection_id, event)
            if action is not None and action.state not in {
                ActionState.PENDING,
                ActionState.EXECUTED,
            }:
                return _Prepared(event_id, job.job_id, event, job, action)
            if event.processing is EventProcessing.CONSUMED:
                if action is None or action.state is not ActionState.EXECUTED:
                    raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
                return _Prepared(event_id, job.job_id, event, job, action)
            if job.state in {JobState.NEEDS_ATTENTION, JobState.SOURCE_MISSING}:
                return _Prepared(event_id, job.job_id, event, job, action)
            if job.state is JobState.COMPLETED:
                if action is not None and action.state is ActionState.EXECUTED:
                    return _Prepared(event_id, job.job_id, event, job, action)
                raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
            if job.state is JobState.CLAIMED:
                claim = _get(
                    uow, projection_id, "job_claims", (("job_id", job.job_id),)
                )
                if claim is None:
                    raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
                if claim.claim.owner_run_id != owner._info.owner_run_id:
                    jobs.defer_job(
                        uow,
                        projection_id,
                        job.job_id,
                        "retry_wait",
                        ErrorCode.OWNER_BUSY,
                        now,
                        RevisionGuard(job.revision),
                    )
                    return None
                if (
                    claim.claim.phase is not ClaimPhase.PREPARING
                    or claim.claim.job_revision != job.revision
                ):
                    raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            elif job.state in {JobState.QUEUED, JobState.RETRY_WAIT}:
                claim = Claim(
                    _new_id(),
                    owner._info.owner_run_id,
                    now,
                    None,
                    Revision(job.revision.value + 1),
                    ClaimPhase.PREPARING,
                )
                jobs.claim(
                    uow,
                    projection_id,
                    job.job_id,
                    claim,
                    RevisionGuard(job.revision),
                    now,
                )
                job = _get(uow, projection_id, "sync_jobs", (("job_id", job.job_id),))
            else:
                raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
            return _Prepared(event_id, job.job_id, event, job, action)

    def _attention(self, owner, projection_id, prepared, reason) -> ActionEffectResult:
        code = reason if type(reason) is ErrorCode else _attention_code(reason)
        with owner.transaction() as uow:
            event = reads.get_event(uow, projection_id, prepared.event_id)
            job = reads.get_job(uow, projection_id, prepared.job_id)
            if event is None or job is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            if event.processing in {
                EventProcessing.PENDING,
                EventProcessing.RESOLVED,
            }:
                events.classify_event(
                    uow,
                    projection_id,
                    prepared.event_id,
                    EventProcessing.NEEDS_ATTENTION,
                    code,
                    (),
                    RevisionGuard(event.revision),
                )
            if job.state is JobState.CLAIMED:
                jobs.defer_job(
                    uow,
                    projection_id,
                    prepared.job_id,
                    "needs_attention",
                    code,
                    None,
                    RevisionGuard(job.revision),
                )
        return ActionEffectResult(attention=reason)

    def _apply(
        self,
        owner,
        projection_id,
        prepared: _Prepared,
        activation: ActionActivation,
        normalized,
        epoch_id: LocalId | None,
    ) -> WriteReceipt:
        if epoch_id is not None and type(epoch_id) is not LocalId:
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        now = _now(prepared.event.event.observed_at)
        with owner.transaction() as uow:
            event = reads.get_event(uow, projection_id, prepared.event_id)
            job = reads.get_job(uow, projection_id, prepared.job_id)
            if event is None or job is None or job.state is not JobState.CLAIMED:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            _require_owned_claim(uow, projection_id, job, owner._info.owner_run_id)
            if (
                event.event != prepared.event.event
                or event.event.key != activation.event
            ):
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            if event.processing is EventProcessing.PENDING:
                events.classify_event(
                    uow,
                    projection_id,
                    prepared.event_id,
                    EventProcessing.RESOLVED,
                    None,
                    (),
                    RevisionGuard(event.revision),
                )
                event = reads.get_event(uow, projection_id, prepared.event_id)
            if event.processing is not EventProcessing.RESOLVED:
                raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
            key = activation.event
            action = prepared.action
            if action is None:
                action = ActionCommandRow(
                    projection_id,
                    _new_id(),
                    prepared.event_id,
                    key.history_record_id,
                    key.label_id,
                    activation.source_thread_id,
                    activation.kind,
                    ActionState.PENDING,
                    CleanupState.NOT_REQUESTED,
                    event.event.observed_at,
                    None,
                    None,
                    Revision(0),
                )
            elif action.kind is not activation.kind:
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            actions.register_action(uow, projection_id, action)
            existing = actions._find_rule(
                uow, projection_id, normalized.kind, normalized.storage_value.value
            )
            projection = reads.get_projection(uow, projection_id)
            if projection is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            current_rule = None if existing is None else existing
            current_revision = (
                Revision(0) if current_rule is None else current_rule.current_revision
            )
            current_member = None
            if current_rule is not None:
                current_member = _get(
                    uow,
                    projection_id,
                    "ruleset_members",
                    (
                        ("ruleset_revision", projection.ruleset_revision),
                        ("rule_id", current_rule.rule_id),
                    ),
                )
            enabled = False
            if current_rule is not None and current_member is not None:
                version = _get(
                    uow,
                    projection_id,
                    "rule_revisions",
                    (
                        ("rule_id", current_rule.rule_id),
                        ("revision", current_member.rule_revision),
                    ),
                )
                enabled = version is not None and version.enabled
            rule_id = current_rule.rule_id if current_rule is not None else _new_id()
            rule_revision = (
                current_rule.current_revision
                if enabled and current_rule is not None
                else Revision(current_revision.value + 1)
            )
            selection_job = None
            if activation.kind is not ActionKind.BLACKLIST:
                if epoch_id is None:
                    raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
                _epoch_is_authorized(uow, projection_id, epoch_id)
                before = _get(
                    uow,
                    projection_id,
                    "tracked_threads",
                    (("source_thread_id", activation.source_thread_id),),
                )
                generation = (
                    Generation(1)
                    if before is None
                    else Generation(
                        before.generation.value
                        if before.active
                        else before.generation.value + 1
                    )
                )
                subject = JobSubjectExpandThread(
                    "expand_thread", activation.source_thread_id, epoch_id, generation
                )
                candidate = _get(
                    uow,
                    projection_id,
                    "sync_jobs",
                    (("stable_key", job_key(projection_id, subject)),),
                )
                if candidate is not None and candidate.state in {
                    JobState.COMPLETED,
                    JobState.CANCELLED,
                    JobState.FAILED,
                    JobState.SOURCE_MISSING,
                    JobState.NEEDS_ATTENTION,
                }:
                    raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
                selection_job = candidate or SyncJobRow(
                    projection_id,
                    _new_id(),
                    JobKind.EXPAND_THREAD,
                    Count(1),
                    job_key(projection_id, subject),
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
            selection = actions._ActionSelection(
                action.action_command_id,
                RuleRef(rule_id, rule_revision),
                None if selection_job is None else selection_job.job_id,
            )
            actions._begin_action_effect(
                uow,
                projection_id,
                selection,
                RevisionGuard(action.revision),
                self._producer,
            )
            if not enabled:
                rule = RuleRow(
                    projection_id,
                    rule_id,
                    normalized.kind,
                    normalized.storage_value,
                    rule_revision,
                )
                revision = RuleRevisionRow(
                    projection_id,
                    rule_id,
                    rule_revision,
                    True,
                    now,
                    RuleOrigin.ACTION_LABEL,
                    load_rule_policy().version,
                )
                snapshot = RulesetRow(
                    projection_id,
                    Revision(projection.ruleset_revision.value + 1),
                    now,
                    True,
                )
                members = tuple(
                    RulesetMemberRow(
                        projection_id,
                        snapshot.revision,
                        member.rule_id,
                        member.rule_revision,
                    )
                    for member in actions._ruleset_members(
                        uow, projection_id, projection.ruleset_revision
                    )
                    if member.rule_id != rule_id
                )
                policy.publish_rules(
                    uow,
                    projection_id,
                    (rule,),
                    (revision,),
                    snapshot,
                    (
                        *members,
                        RulesetMemberRow(
                            projection_id, snapshot.revision, rule_id, rule_revision
                        ),
                    ),
                    RevisionGuard(projection.ruleset_revision),
                )
            before = _get(
                uow,
                projection_id,
                "tracked_threads",
                (("source_thread_id", activation.source_thread_id),),
            )
            if activation.kind is ActionKind.BLACKLIST:
                if before is not None and before.active:
                    policy.stop_thread(
                        uow,
                        projection_id,
                        activation.source_thread_id,
                        before.generation,
                        now,
                        ThreadStopReason.BLACKLIST,
                    )
            else:
                if before is None or not before.active:
                    generation = Generation(
                        1 if before is None else before.generation.value + 1
                    )
                    admission_revision = Revision(
                        1 if before is None else before.admission_revision.value + 1
                    )
                    tracked = TrackedThreadRow(
                        projection_id,
                        activation.source_thread_id,
                        True,
                        generation,
                        now,
                        None,
                        None,
                        admission_revision,
                    )
                    admission = ThreadAdmissionRow(
                        projection_id,
                        activation.source_thread_id,
                        admission_revision,
                        generation,
                        now,
                        AdmissionRefActionLabel(
                            "action_label", action.action_command_id
                        ),
                    )
                    guard: ThreadGenerationGuard = (
                        ThreadGenerationGuardUntracked("untracked")
                        if before is None
                        else ThreadGenerationGuardTracked("tracked", before.generation)
                    )
                    policy.admit_thread(
                        uow, projection_id, tracked, admission, (), guard
                    )
                else:
                    admission = _get(
                        uow,
                        projection_id,
                        "thread_admissions",
                        (
                            ("source_thread_id", before.source_thread_id),
                            ("admission_revision", before.admission_revision),
                        ),
                    )
                    if admission is None:
                        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
                    policy.admit_thread(
                        uow,
                        projection_id,
                        before,
                        admission,
                        (),
                        ThreadGenerationGuardTracked("tracked", before.generation),
                    )
                jobs.enqueue(uow, projection_id, selection_job)
            return actions.complete_action(
                uow,
                projection_id,
                ActionCommandRow(
                    action.projection_id,
                    action.action_command_id,
                    action.event_id,
                    action.history_record_id,
                    action.label_id,
                    action.source_thread_id,
                    action.kind,
                    ActionState.EXECUTED,
                    action.cleanup,
                    action.observed_at,
                    now,
                    None,
                    Revision(action.revision.value + 1),
                ),
                RevisionGuard(action.revision),
            )

    def _normalize(self, activation: ActionActivation):
        try:
            if activation.kind is ActionKind.ADD_DOMAIN:
                learned = learn_domain(
                    activation.sender.value,
                    source_primary=self._source_primary,
                    own=tuple(address.value for address in self._own_addresses),
                )
                if learned.domain is None:
                    raise RuleInputError()
                return normalize_rule(RuleKind.ALLOW_DOMAIN, learned.domain.value)
            return normalize_rule(_rule_kind(activation.kind), activation.sender.value)
        except (RuleInputError, ValueError):
            raise StorageFailure(ErrorCode.REQUEST_CONFLICT) from None

    def _reload(self, owner, projection_id, event_id) -> _Prepared:
        with owner.transaction() as uow:
            event = reads.get_event(uow, projection_id, event_id)
            if event is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            job = _resolve_job(uow, projection_id, event)
            if job is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            return _Prepared(
                event_id,
                job.job_id,
                event,
                job,
                _action(uow, projection_id, event),
            )

    def _finalize(
        self,
        owner,
        projection_id,
        prepared: _Prepared,
        epoch_id: LocalId | None,
        receipt: WriteReceipt | None = None,
    ) -> ActionEffectResult:
        if prepared.action is None or prepared.action.state is not ActionState.EXECUTED:
            raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
        with owner.transaction() as uow:
            event = reads.get_event(uow, projection_id, prepared.event_id)
            job = reads.get_job(uow, projection_id, prepared.job_id)
            action = _action(uow, projection_id, event) if event is not None else None
            if event is None or job is None or action is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            if job.state is JobState.COMPLETED:
                return ActionEffectResult(
                    receipt=receipt
                    or WriteReceipt(
                        "replayed", action.action_command_id, action.revision
                    )
                )
            if job.state is not JobState.CLAIMED:
                raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
            _require_owned_claim(uow, projection_id, job, owner._info.owner_run_id)
            if event.processing is EventProcessing.RESOLVED:
                work = ()
                if action.kind is not ActionKind.BLACKLIST:
                    thread = _get(
                        uow,
                        projection_id,
                        "tracked_threads",
                        (("source_thread_id", action.source_thread_id),),
                    )
                    if thread is None or not thread.active or epoch_id is None:
                        jobs.defer_job(
                            uow,
                            projection_id,
                            prepared.job_id,
                            "needs_attention",
                            ErrorCode.GENERATION_STALE,
                            None,
                            RevisionGuard(job.revision),
                        )
                        return ActionEffectResult(attention=ErrorCode.GENERATION_STALE)
                    subject = JobSubjectExpandThread(
                        "expand_thread",
                        action.source_thread_id,
                        epoch_id,
                        thread.generation,
                    )
                    expansion = _get(
                        uow,
                        projection_id,
                        "sync_jobs",
                        (("stable_key", job_key(projection_id, subject)),),
                    )
                    if expansion is None:
                        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
                    work = (expansion,)
                events.classify_event(
                    uow,
                    projection_id,
                    prepared.event_id,
                    EventProcessing.CONSUMED,
                    None,
                    work,
                    RevisionGuard(event.revision),
                )
                job = reads.get_job(uow, projection_id, prepared.job_id)
            if job.state is not JobState.CLAIMED:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            final = jobs.complete_noninsert_job(
                uow,
                projection_id,
                prepared.job_id,
                RevisionGuard(job.revision),
            )
        return ActionEffectResult(receipt=receipt or final)
