"""Finite action metadata and same-transaction effects, not a learning actor.

The compiled producer inventory contains only the reviewed readonly action
label producer. A syntactic action, rule, receipt, or UUID is not authority to
disclose source mail. All fields are private normalized metadata; no content,
arbitrary payload, callback, or remote work.
"""

from dataclasses import dataclass
from enum import Enum

from facet.contracts import (
    ClaimPhase,
    ErrorCode,
    JobKind,
    JobState,
    LabelChange,
    LocalId,
    ProjectionId,
    Revision,
    RuleKind,
    RuleOrigin,
    SourceMode,
)
from facet.contracts.records import (
    AdmissionRefActionLabel,
    JobSubjectExpandThread,
    RuleRef,
    SourceEventKeyLabelChanged,
)
from facet.projection.actions import ActionLabelProducer

from ..codecs import (
    ActionKind,
    ActionState,
    CleanupState,
    EventProcessing,
    StorageFailure,
    ThreadStopReason,
    invalid,
    next_revision,
    timestamp_to_sql,
)
from ..models import (
    ActionCommandRow,
    RuleRevisionRow,
    RuleRow,
    RulesetMemberRow,
    SyncJobRow,
    ThreadAdmissionRow,
    TrackedThreadRow,
    WriteReceipt,
)
from ..transactions import UnitOfWork
from .base import _decode, _get, _guard, _insert, _mutating, _query, _require_row
from .serialization import COLUMNS

# Only a separately reviewed, compiled M5 producer may change this tuple. No
# registration API, configurable type name, environment switch, or plugin.
_ACTION_PRODUCER_TYPES: tuple[type, ...] = (ActionLabelProducer,)


def _inconsistent():
    raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)


@dataclass(frozen=True, slots=True, repr=False)
class _ActionSelection:
    action_id: LocalId
    rule: RuleRef
    expansion_job_id: LocalId | None

    def __post_init__(self):
        if (
            type(self.action_id) is not LocalId
            or type(self.rule) is not RuleRef
            or (
                self.expansion_job_id is not None
                and type(self.expansion_job_id) is not LocalId
            )
        ):
            invalid()


class _Phase(Enum):
    OPEN = 1
    CONSUMED = 2


@dataclass(eq=False, frozen=True, slots=True, repr=False, init=False)
class _ActionScope:
    uow: UnitOfWork
    projection_id: ProjectionId
    selection: _ActionSelection
    before_action: ActionCommandRow
    before_rule: RuleRow | None
    before_rule_revision: RuleRevisionRow | None
    before_ruleset_revision: Revision
    before_member: RulesetMemberRow | None
    before_thread: TrackedThreadRow | None
    before_admission: ThreadAdmissionRow | None
    before_job: SyncJobRow | None
    rule_receipt: WriteReceipt | None
    thread_receipt: WriteReceipt | None
    enqueue_receipt: WriteReceipt | None
    phase: _Phase

    def __init__(self):
        # The sole allocator below enrolls identity after reading actual facts.
        invalid()

    def __repr__(self):
        return "<private action scope>"


_ENROLLED_SCOPES: set[_ActionScope] = set()


def _scope(uow, projection_id=None):
    value = uow._action_scope
    if value is None:
        return None
    if (
        type(value) is not _ActionScope
        or value not in _ENROLLED_SCOPES
        or value.uow is not uow
        or (projection_id is not None and value.projection_id != projection_id)
        or value.phase not in {_Phase.OPEN, _Phase.CONSUMED}
    ):
        _inconsistent()
    return value


def _check_action_mutation(uow):
    scope = _scope(uow)
    if scope is not None and scope.phase is not _Phase.OPEN:
        _inconsistent()


def _validate_action_commit(uow):
    scope = _scope(uow)
    if scope is not None and scope.phase is _Phase.OPEN:
        _inconsistent()


def _invalidate_action_scope(uow):
    uow._session._check_creator()
    if uow._session._uow is not uow:
        _inconsistent()
    scope = uow._action_scope
    if type(scope) is _ActionScope:
        _ENROLLED_SCOPES.discard(scope)
    uow._action_scope = None
    uow._action_business_touched = False
    uow._action_attention_completed = False


def _rule_revision(uow, projection, rule):
    if rule is None:
        return None
    return _get(
        uow,
        projection,
        "rule_revisions",
        (("rule_id", rule.rule_id), ("revision", rule.current_revision)),
    )


def _admission(uow, projection, thread):
    if thread is None:
        return None
    return _get(
        uow,
        projection,
        "thread_admissions",
        (
            ("source_thread_id", thread.source_thread_id),
            ("admission_revision", thread.admission_revision),
        ),
    )


def _find_rule(uow, projection_id, kind, value):
    rows = _query(
        uow,
        "SELECT "
        + ",".join(COLUMNS["rules"])
        + " FROM rules WHERE projection_id=? AND kind=? AND normalized_value=?",
        (projection_id.value, kind.value, value),
        maximum=2,
    )
    if len(rows) > 1:
        _inconsistent()
    return None if not rows else _decode(uow, projection_id, "rules", rows[0])


def _ruleset_members(uow, projection_id, revision):
    rows = _query(
        uow,
        "SELECT "
        + ",".join(COLUMNS["ruleset_members"])
        + " FROM ruleset_members WHERE projection_id=? AND ruleset_revision=?",
        (projection_id.value, revision.value),
    )
    return tuple(_decode(uow, projection_id, "ruleset_members", row) for row in rows)


@_mutating
def _begin_action_effect(uow, projection_id, selection, guard, producer):
    if (
        uow._action_scope is not None
        or uow._action_business_touched
        or uow._action_attention_completed
    ):
        _inconsistent()
    if type(producer) not in _ACTION_PRODUCER_TYPES:
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    if type(selection) is not _ActionSelection:
        invalid()
    action = _get(
        uow,
        projection_id,
        "action_commands",
        (("action_command_id", selection.action_id),),
    )
    if action is None:
        _inconsistent()
    _guard(action.revision, guard)
    if action.state is not ActionState.PENDING or (
        (action.kind is ActionKind.BLACKLIST) != (selection.expansion_job_id is None)
    ):
        _inconsistent()
    projection = _get(uow, projection_id, "projections", ())
    if projection is None:
        _inconsistent()
    sealed = _get(
        uow, projection_id, "rulesets", (("revision", projection.ruleset_revision),)
    )
    if sealed is None or not sealed.sealed:
        _inconsistent()
    scope = object.__new__(_ActionScope)
    object.__setattr__(scope, "uow", uow)
    object.__setattr__(scope, "projection_id", projection_id)
    object.__setattr__(scope, "selection", selection)
    object.__setattr__(scope, "before_action", action)
    rule = _get(uow, projection_id, "rules", (("rule_id", selection.rule.rule_id),))
    object.__setattr__(scope, "before_rule", rule)
    object.__setattr__(
        scope, "before_rule_revision", _rule_revision(uow, projection_id, rule)
    )
    object.__setattr__(scope, "before_ruleset_revision", projection.ruleset_revision)
    member = _get(
        uow,
        projection_id,
        "ruleset_members",
        (
            ("ruleset_revision", projection.ruleset_revision),
            ("rule_id", selection.rule.rule_id),
        ),
    )
    object.__setattr__(scope, "before_member", member)
    thread = _get(
        uow,
        projection_id,
        "tracked_threads",
        (("source_thread_id", action.source_thread_id),),
    )
    object.__setattr__(scope, "before_thread", thread)
    object.__setattr__(
        scope, "before_admission", _admission(uow, projection_id, thread)
    )
    job = (
        None
        if selection.expansion_job_id is None
        else _get(
            uow,
            projection_id,
            "sync_jobs",
            (("job_id", selection.expansion_job_id),),
        )
    )
    object.__setattr__(scope, "before_job", job)
    object.__setattr__(scope, "rule_receipt", None)
    object.__setattr__(scope, "thread_receipt", None)
    object.__setattr__(scope, "enqueue_receipt", None)
    object.__setattr__(scope, "phase", _Phase.OPEN)
    _ENROLLED_SCOPES.add(scope)
    uow._action_scope = scope


def _business(uow, projection_id):
    if uow._action_attention_completed:
        # Attention is no-business in either order, including semantic no-ops.
        # Historical exact replay does not arm this per-transaction boundary.
        _inconsistent()
    scope = _scope(uow, projection_id)
    if scope is not None and scope.phase is not _Phase.OPEN:
        _inconsistent()
    # Even successful no-ops disqualify the no-business attention branch.
    uow._action_business_touched = True
    return scope


def _preserves_enabled_rule(scope):
    # Select the branch from captured facts, not the proposed after-row or
    # caller's RuleRef revision. An enabled current member cannot be retagged
    # by manufacturing its next revision to attach this action.
    return (
        scope.before_rule is not None
        and scope.before_rule_revision is not None
        and scope.before_rule_revision.enabled
        and scope.before_member is not None
        and scope.before_member.rule_revision == scope.before_rule.current_revision
    )


def _before_publish(uow, projection_id, rules, revisions, snapshot, members):
    scope = _business(uow, projection_id)
    if scope is None:
        return
    selected = scope.selection.rule
    if (
        _preserves_enabled_rule(scope)
        or scope.rule_receipt is not None
        or any(row.rule_id != selected.rule_id for row in rules)
        or len(revisions) != 1
        or revisions[0].rule_id != selected.rule_id
        or revisions[0].revision != selected.revision
        or snapshot.revision != next_revision(scope.before_ruleset_revision)
    ):
        _inconsistent()


def _same_other_members(uow, projection, before, after, selected_id):
    # Both EXCEPT directions consume the entire sealed relation, not a read
    # page. A late missing member beyond 500 is still a contradiction.
    relation = (
        "SELECT rule_id,rule_revision FROM ruleset_members WHERE "
        "projection_id=? AND ruleset_revision=? AND rule_id<>?"
    )
    old = (projection.value, before.value, selected_id.value)
    new = (projection.value, after.value, selected_id.value)
    if _query(
        uow,
        "SELECT 1 WHERE EXISTS(" + relation + " EXCEPT " + relation + ") "
        "OR EXISTS(" + relation + " EXCEPT " + relation + ")",
        (*old, *new, *new, *old),
        maximum=1,
    ):
        _inconsistent()


def _after_publish(uow, projection_id, receipt):
    scope = _scope(uow, projection_id)
    if scope is not None:
        _same_other_members(
            uow,
            projection_id,
            scope.before_ruleset_revision,
            receipt.revision,
            scope.selection.rule.rule_id,
        )
        object.__setattr__(scope, "rule_receipt", receipt)
    return receipt


def _before_admit(uow, projection_id, thread, admission):
    scope = _business(uow, projection_id)
    if scope is not None and (
        scope.before_action.kind is ActionKind.BLACKLIST
        or scope.thread_receipt is not None
        or thread.source_thread_id != scope.before_action.source_thread_id
        or (
            (scope.before_thread is None or not scope.before_thread.active)
            and admission.admission
            != AdmissionRefActionLabel(
                "action_label", scope.before_action.action_command_id
            )
        )
    ):
        _inconsistent()


def _before_stop(uow, projection_id, thread_id, generation, stopped_at, reason):
    scope = _business(uow, projection_id)
    if scope is not None and (
        scope.before_action.kind is not ActionKind.BLACKLIST
        or scope.thread_receipt is not None
        or scope.before_thread is None
        or not scope.before_thread.active
        or thread_id != scope.before_action.source_thread_id
        or generation != scope.before_thread.generation
        or reason is not ThreadStopReason.BLACKLIST
    ):
        _inconsistent()


def _after_thread(uow, projection_id, receipt):
    scope = _scope(uow, projection_id)
    if scope is not None:
        object.__setattr__(scope, "thread_receipt", receipt)
    return receipt


def _before_enqueue(uow, projection_id, row):
    scope = _business(uow, projection_id)
    if scope is not None and (
        scope.before_action.kind is ActionKind.BLACKLIST
        or scope.enqueue_receipt is not None
        or row.job_id != scope.selection.expansion_job_id
        or type(row.subject) is not JobSubjectExpandThread
        or row.subject.source_thread_id != scope.before_action.source_thread_id
        or row.origin_epoch_id != row.subject.epoch_id
    ):
        _inconsistent()


def _after_enqueue(uow, projection_id, receipt):
    scope = _scope(uow, projection_id)
    if scope is not None:
        object.__setattr__(scope, "enqueue_receipt", receipt)
    return receipt


@_mutating
def register_action(uow, projection_id, row: ActionCommandRow):
    _require_row(projection_id, "action_commands", row)
    if (
        row.state is not ActionState.PENDING
        or row.revision != Revision(0)
        or row.cleanup is not CleanupState.NOT_REQUESTED
        or row.executed_at is not None
        or row.error_code is not None
    ):
        _inconsistent()
    event = _get(uow, projection_id, "source_events", (("event_id", row.event_id),))
    if event is None:
        _inconsistent()
    key = event.event.key
    if (
        type(key) is not SourceEventKeyLabelChanged
        or key.change is not LabelChange.ADDED
        or event.processing not in {EventProcessing.RESOLVED, EventProcessing.CONSUMED}
        or event.event.source_thread_id is None
        or (key.history_record_id, key.label_id, event.event.source_thread_id)
        != (row.history_record_id, row.label_id, row.source_thread_id)
        or event.event.observed_at != row.observed_at
    ):
        _inconsistent()
    by_id = _get(
        uow,
        projection_id,
        "action_commands",
        (("action_command_id", row.action_command_id),),
    )
    selectors = (
        ("history_record_id", row.history_record_id),
        ("label_id", row.label_id),
        ("source_thread_id", row.source_thread_id),
    )
    existing = _get(uow, projection_id, "action_commands", selectors)
    if by_id is not None and by_id != existing:
        _inconsistent()
    if existing is not None:
        if existing.kind is not row.kind:
            _inconsistent()
        return WriteReceipt("replayed", existing.action_command_id, existing.revision)
    _insert(uow, projection_id, "action_commands", row)
    return WriteReceipt("created", row.action_command_id, row.revision)


def _immutable_action(row):
    return (
        row.projection_id,
        row.action_command_id,
        row.event_id,
        row.history_record_id,
        row.label_id,
        row.source_thread_id,
        row.kind,
        row.observed_at,
    )


def _verify_rule(uow, projection_id, scope, executed_at):
    ref = scope.selection.rule
    rule = _get(uow, projection_id, "rules", (("rule_id", ref.rule_id),))
    revision = _rule_revision(uow, projection_id, rule)
    projection = _get(uow, projection_id, "projections", ())
    snapshot = _get(
        uow, projection_id, "rulesets", (("revision", projection.ruleset_revision),)
    )
    member = _get(
        uow,
        projection_id,
        "ruleset_members",
        (("ruleset_revision", projection.ruleset_revision), ("rule_id", ref.rule_id)),
    )
    kind = {
        ActionKind.ADD_SENDER: RuleKind.ALLOW_SENDER,
        ActionKind.ADD_DOMAIN: RuleKind.ALLOW_DOMAIN,
        ActionKind.BLACKLIST: RuleKind.BLACKLIST_SENDER,
    }[scope.before_action.kind]
    if (
        rule is None
        or rule.kind is not kind
        or rule.current_revision != ref.revision
        or revision is None
        or not revision.enabled
        or snapshot is None
        or not snapshot.sealed
        or member is None
        or member.rule_revision != ref.revision
    ):
        _inconsistent()
    unchanged = (
        scope.before_rule == rule
        and scope.before_rule_revision == revision
        and scope.before_member == member
        and scope.before_ruleset_revision == snapshot.revision
    )
    if _preserves_enabled_rule(scope):
        if not unchanged or scope.rule_receipt is not None:
            _inconsistent()
    elif (
        scope.rule_receipt != WriteReceipt("created", projection_id, snapshot.revision)
        or revision.origin is not RuleOrigin.ACTION_LABEL
        or revision.effective_at != executed_at
        or snapshot.created_at != executed_at
    ):
        _inconsistent()
    _same_other_members(
        uow,
        projection_id,
        scope.before_ruleset_revision,
        snapshot.revision,
        ref.rule_id,
    )


def _verify_expansion(uow, projection_id, scope, thread, executed_at):
    receipt = scope.enqueue_receipt
    if receipt is None:
        _inconsistent()
    job = _get(uow, projection_id, "sync_jobs", (("job_id", receipt.object_id),))
    if (
        job is None
        or job.kind is not JobKind.EXPAND_THREAD
        or type(job.subject) is not JobSubjectExpandThread
        or job.subject.source_thread_id != thread.source_thread_id
        or job.subject.generation != thread.generation
        or job.state
        not in {
            JobState.QUEUED,
            JobState.CLAIMED,
            JobState.RETRY_WAIT,
            JobState.BLOCKED,
        }
        or receipt.revision != job.revision
        or job.created_at.value > executed_at.value
        or job.updated_at.value > executed_at.value
    ):
        _inconsistent()
    epoch = _get(uow, projection_id, "epochs", (("epoch_id", job.subject.epoch_id),))
    link = _get(
        uow,
        projection_id,
        "epoch_jobs",
        (("epoch_id", job.subject.epoch_id), ("job_id", job.job_id)),
    )
    claim = _get(uow, projection_id, "job_claims", (("job_id", job.job_id),))
    if epoch is None or link is None:
        _inconsistent()
    if job.state is JobState.CLAIMED:
        if (
            claim is None
            or claim.claim.job_revision != job.revision
            or claim.claim.thread_generation != thread.generation
            or claim.claim.phase is not ClaimPhase.PREPARING
            or claim.claim.acquired_at.value > executed_at.value
            or job.next_attempt_at is not None
        ):
            _inconsistent()
    elif claim is not None:
        _inconsistent()
    if job.state is JobState.QUEUED and (
        job.next_attempt_at is not None
        or job.last_error_code is not None
        or job.attempt_count.value != 0
    ):
        _inconsistent()
    if job.state is JobState.RETRY_WAIT and (
        job.next_attempt_at is None or job.last_error_code is None
    ):
        _inconsistent()
    if job.state is JobState.BLOCKED and (
        job.next_attempt_at is not None or job.last_error_code is None
    ):
        _inconsistent()


def _verify_thread(uow, projection_id, scope, executed_at):
    action = scope.before_action
    before = scope.before_thread
    thread = _get(
        uow,
        projection_id,
        "tracked_threads",
        (("source_thread_id", action.source_thread_id),),
    )
    admission = _admission(uow, projection_id, thread)
    if action.kind is ActionKind.BLACKLIST:
        if before is None or not before.active:
            if (
                thread != before
                or admission != scope.before_admission
                or scope.thread_receipt is not None
            ):
                _inconsistent()
        elif (
            thread is None
            or thread.active
            or thread.generation.value
            != next_revision(Revision(before.generation.value)).value
            or thread.stopped_at != executed_at
            or thread.stop_reason is not ThreadStopReason.BLACKLIST
            or thread.admitted_at != before.admitted_at
            or thread.admission_revision != before.admission_revision
            or admission != scope.before_admission
            or scope.thread_receipt
            != WriteReceipt(
                "updated", action.source_thread_id, Revision(thread.generation.value)
            )
        ):
            _inconsistent()
        if scope.enqueue_receipt is not None:
            _inconsistent()
        return
    if thread is None or not thread.active or admission is None:
        _inconsistent()
    if before is not None and before.active:
        if (
            thread != before
            or admission != scope.before_admission
            or scope.thread_receipt
            not in (
                None,
                WriteReceipt(
                    "replayed", thread.source_thread_id, thread.admission_revision
                ),
            )
        ):
            _inconsistent()
    elif (
        scope.thread_receipt
        != WriteReceipt(
            "created" if before is None else "updated",
            thread.source_thread_id,
            thread.admission_revision,
        )
        or thread.admitted_at != executed_at
        or admission.admitted_at != executed_at
        or admission.generation != thread.generation
        or admission.admission_revision != thread.admission_revision
        or admission.admission
        != AdmissionRefActionLabel("action_label", action.action_command_id)
    ):
        _inconsistent()
    _verify_expansion(uow, projection_id, scope, thread, executed_at)


@_mutating
def complete_action(uow, projection_id, row: ActionCommandRow, guard):
    _require_row(projection_id, "action_commands", row)
    old = _get(
        uow,
        projection_id,
        "action_commands",
        (("action_command_id", row.action_command_id),),
    )
    if old is None:
        _inconsistent()
    _guard(old.revision, guard)
    if _immutable_action(old) != _immutable_action(row):
        _inconsistent()
    if row == old:
        return WriteReceipt("replayed", old.action_command_id, old.revision)
    if (
        old.state is not ActionState.PENDING
        or row.revision != next_revision(old.revision)
        or row.cleanup is not CleanupState.NOT_REQUESTED
    ):
        _inconsistent()
    scope = _scope(uow, projection_id)
    if row.state is ActionState.NEEDS_ATTENTION:
        if (
            row.executed_at is not None
            or type(row.error_code) is not ErrorCode
            or scope is not None
            or uow._action_business_touched
        ):
            _inconsistent()
    elif row.state is ActionState.EXECUTED:
        if (
            row.executed_at is None
            or row.executed_at.value < row.observed_at.value
            or row.error_code is not None
        ):
            _inconsistent()
        if scope is None:
            raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
        if (
            scope.before_action != old
            or scope.selection.action_id != old.action_command_id
        ):
            _inconsistent()
        _verify_rule(uow, projection_id, scope, row.executed_at)
        _verify_thread(uow, projection_id, scope, row.executed_at)
    else:
        _inconsistent()
    uow._execute(
        "UPDATE action_commands SET state=?,executed_at=?,error_code=?,revision=? "
        "WHERE projection_id=? AND action_command_id=?",
        (
            row.state.value,
            None if row.executed_at is None else timestamp_to_sql(row.executed_at),
            None if row.error_code is None else row.error_code.value,
            row.revision.value,
            projection_id.value,
            row.action_command_id.value,
        ),
    )
    if scope is not None:
        object.__setattr__(scope, "phase", _Phase.CONSUMED)
    else:
        uow._action_attention_completed = True
    return WriteReceipt("updated", row.action_command_id, row.revision)


@_mutating
def record_cleanup(uow, projection_id, action_id, cleanup, error, guard):
    if (
        type(action_id) is not LocalId
        or type(cleanup) is not CleanupState
        or (error is not None and type(error) is not ErrorCode)
    ):
        invalid()
    old = _get(
        uow, projection_id, "action_commands", (("action_command_id", action_id),)
    )
    if old is None:
        _inconsistent()
    _guard(old.revision, guard)
    if old.state is not ActionState.EXECUTED:
        _inconsistent()
    if (old.cleanup, old.error_code) == (cleanup, error):
        return WriteReceipt("replayed", old.action_command_id, old.revision)
    failure = (
        old.cleanup is CleanupState.QUEUED
        and cleanup is CleanupState.BLOCKED
        and error is not None
    )
    schedule = (
        old.cleanup in {CleanupState.NOT_REQUESTED, CleanupState.BLOCKED}
        and cleanup is CleanupState.QUEUED
        and error is None
    )
    completion = (
        old.cleanup is CleanupState.QUEUED
        and cleanup is CleanupState.COMPLETED
        and error is None
    )
    if not (failure or schedule or completion):
        _inconsistent()
    projection = _get(uow, projection_id, "projections", ())
    if projection is None or (
        not failure and projection.source_mode is not SourceMode.CONVENIENCE
    ):
        _inconsistent()
    revision = next_revision(old.revision)
    uow._execute(
        "UPDATE action_commands SET cleanup=?,error_code=?,revision=? "
        "WHERE projection_id=? AND action_command_id=?",
        (
            cleanup.value,
            None if error is None else error.value,
            revision.value,
            projection_id.value,
            action_id.value,
        ),
    )
    return WriteReceipt("updated", action_id, revision)
