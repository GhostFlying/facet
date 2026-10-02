"""Closed p1-core-v1 values; persistence and relational guards belong to owners."""

from dataclasses import dataclass, fields
from functools import cache
from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints

from .enums import ClaimPhase, LabelChange, PartitionState, ReadTaskKind
from .primitives import (
    Count,
    Generation,
    LocalId,
    PolicyVersion,
    ProjectionId,
    ProviderId,
    ProviderPageToken,
    Revision,
    Timestamp,
)


@cache
def _hints(cls: type) -> dict:
    return get_type_hints(cls)


def _matches(value: object, annotation: object) -> bool:
    if get_origin(annotation) is Literal:
        return any(type(value) is type(a) and value == a for a in get_args(annotation))
    if get_origin(annotation) is UnionType:
        return any(_matches(value, a) for a in get_args(annotation))
    return type(value) is annotation


class _ClosedValue:
    __slots__ = ()

    def __post_init__(self) -> None:
        hints = _hints(type(self))
        if any(
            not _matches(getattr(self, f.name), hints[f.name]) for f in fields(self)
        ):
            raise ValueError("invalid_input")
        self._validate()

    def _validate(self) -> None:
        pass


def _positive_generation(generation: Generation) -> None:
    if generation.value < 1:
        raise ValueError("invalid_input")


@dataclass(frozen=True, slots=True, repr=False)
class RuleRef(_ClosedValue):
    rule_id: LocalId
    revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class AdmissionRefInitialBackfill(_ClosedValue):
    tag: Literal["initial_backfill"]
    epoch_id: LocalId
    rule: RuleRef
    policy_version: PolicyVersion


@dataclass(frozen=True, slots=True, repr=False)
class AdmissionRefFutureRule(_ClosedValue):
    tag: Literal["future_rule"]
    rule: RuleRef
    policy_version: PolicyVersion


@dataclass(frozen=True, slots=True, repr=False)
class AdmissionRefManualThread(_ClosedValue):
    tag: Literal["manual_thread"]
    preview_id: LocalId


@dataclass(frozen=True, slots=True, repr=False)
class AdmissionRefActionLabel(_ClosedValue):
    tag: Literal["action_label"]
    action_command_id: LocalId


AdmissionRef = (
    AdmissionRefInitialBackfill
    | AdmissionRefFutureRule
    | AdmissionRefManualThread
    | AdmissionRefActionLabel
)


@dataclass(frozen=True, slots=True, repr=False)
class EpochDecisionRefBackfillStart(_ClosedValue):
    tag: Literal["backfill_start"]
    operation_id: LocalId
    preview_id: LocalId
    ruleset_revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class EpochDecisionRefGapApproval(_ClosedValue):
    tag: Literal["gap_approval"]
    operation_id: LocalId
    preview_id: LocalId
    ruleset_revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class EpochDecisionRefScheduledReconcile(_ClosedValue):
    tag: Literal["scheduled_reconcile"]
    ruleset_revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class EpochDecisionRefRequestedReconcile(_ClosedValue):
    tag: Literal["requested_reconcile"]
    operation_id: LocalId
    ruleset_revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class EpochDecisionRefScheduledTargetAudit(_ClosedValue):
    tag: Literal["scheduled_target_audit"]


@dataclass(frozen=True, slots=True, repr=False)
class EpochDecisionRefRequestedTargetAudit(_ClosedValue):
    tag: Literal["requested_target_audit"]
    operation_id: LocalId


EpochDecisionRef = (
    EpochDecisionRefBackfillStart
    | EpochDecisionRefGapApproval
    | EpochDecisionRefScheduledReconcile
    | EpochDecisionRefRequestedReconcile
    | EpochDecisionRefScheduledTargetAudit
    | EpochDecisionRefRequestedTargetAudit
)


@dataclass(frozen=True, slots=True, repr=False)
class PartitionRefSourceWindow(_ClosedValue):
    tag: Literal["source_window"]


@dataclass(frozen=True, slots=True, repr=False)
class PartitionRefSourceThread(_ClosedValue):
    tag: Literal["source_thread"]
    source_thread_id: ProviderId


@dataclass(frozen=True, slots=True, repr=False)
class PartitionRefTargetCatalog(_ClosedValue):
    tag: Literal["target_catalog"]


@dataclass(frozen=True, slots=True, repr=False)
class PartitionRefMappedTargetSet(_ClosedValue):
    tag: Literal["mapped_target_set"]


PartitionRef = (
    PartitionRefSourceWindow
    | PartitionRefSourceThread
    | PartitionRefTargetCatalog
    | PartitionRefMappedTargetSet
)


@dataclass(frozen=True, slots=True, repr=False)
class PartitionProgress(_ClosedValue):
    partition: PartitionRef
    state: PartitionState
    completed_pages: Count
    observed_items: Count
    page_token: ProviderPageToken | None
    after_source_message_id: ProviderId | None

    def _validate(self) -> None:
        if self.page_token is not None and self.partition.tag not in {
            "source_window",
            "target_catalog",
        }:
            raise ValueError("invalid_input")
        if (
            self.after_source_message_id is not None
            and self.partition.tag != "mapped_target_set"
        ):
            raise ValueError("invalid_input")
        if self.state is PartitionState.NOT_STARTED and (
            self.completed_pages.value != 0
            or self.observed_items.value != 0
            or self.page_token is not None
            or self.after_source_message_id is not None
        ):
            raise ValueError("invalid_input")
        if self.state is PartitionState.COMPLETE and self.page_token is not None:
            raise ValueError("invalid_input")


@dataclass(frozen=True, slots=True, repr=False)
class SourceEventKeyMessageAdded(_ClosedValue):
    tag: Literal["message_added"]
    projection_id: ProjectionId
    history_record_id: ProviderId
    source_message_id: ProviderId


@dataclass(frozen=True, slots=True, repr=False)
class SourceEventKeyMessageDeleted(_ClosedValue):
    tag: Literal["message_deleted"]
    projection_id: ProjectionId
    history_record_id: ProviderId
    source_message_id: ProviderId


@dataclass(frozen=True, slots=True, repr=False)
class SourceEventKeyLabelChanged(_ClosedValue):
    tag: Literal["label_changed"]
    projection_id: ProjectionId
    history_record_id: ProviderId
    source_message_id: ProviderId
    label_id: ProviderId
    change: LabelChange


SourceEventKey = (
    SourceEventKeyMessageAdded
    | SourceEventKeyMessageDeleted
    | SourceEventKeyLabelChanged
)


@dataclass(frozen=True, slots=True, repr=False)
class SourceEvent(_ClosedValue):
    key: SourceEventKey
    observed_at: Timestamp
    source_thread_id: ProviderId | None


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectProjectMessage(_ClosedValue):
    tag: Literal["project_message"]
    source_message_id: ProviderId
    source_thread_id: ProviderId
    generation: Generation

    def _validate(self) -> None:
        _positive_generation(self.generation)


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectRepairMessage(_ClosedValue):
    tag: Literal["repair_message"]
    repair_operation_id: LocalId
    source_message_id: ProviderId
    source_thread_id: ProviderId
    generation: Generation

    def _validate(self) -> None:
        _positive_generation(self.generation)


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectExpandThread(_ClosedValue):
    tag: Literal["expand_thread"]
    source_thread_id: ProviderId
    epoch_id: LocalId
    generation: Generation

    def _validate(self) -> None:
        _positive_generation(self.generation)


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectResolveEvent(_ClosedValue):
    tag: Literal["resolve_event"]
    event_key: SourceEventKey


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectOperationRead(_ClosedValue):
    tag: Literal["operation_read"]
    operation_id: LocalId
    read_kind: ReadTaskKind


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectRecoverInsert(_ClosedValue):
    tag: Literal["recover_insert"]
    attempt_id: LocalId


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectScanDiscovery(_ClosedValue):
    tag: Literal["scan_discovery"]
    epoch_id: LocalId
    partition: PartitionRef

    def _validate(self) -> None:
        if self.partition.tag != "source_window":
            raise ValueError("invalid_input")


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectScanGap(_ClosedValue):
    tag: Literal["scan_gap"]
    epoch_id: LocalId
    partition: PartitionRef

    def _validate(self) -> None:
        if self.partition.tag not in {"source_window", "source_thread"}:
            raise ValueError("invalid_input")


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectReconcileSource(_ClosedValue):
    tag: Literal["reconcile_source"]
    epoch_id: LocalId
    partition: PartitionRef

    def _validate(self) -> None:
        if self.partition.tag not in {"source_window", "source_thread"}:
            raise ValueError("invalid_input")


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectAuditTarget(_ClosedValue):
    tag: Literal["audit_target"]
    epoch_id: LocalId
    partition: PartitionRef

    def _validate(self) -> None:
        if self.partition.tag not in {"target_catalog", "mapped_target_set"}:
            raise ValueError("invalid_input")


@dataclass(frozen=True, slots=True, repr=False)
class JobSubjectCleanupAction(_ClosedValue):
    tag: Literal["cleanup_action"]
    action_command_id: LocalId


JobSubject = (
    JobSubjectProjectMessage
    | JobSubjectRepairMessage
    | JobSubjectExpandThread
    | JobSubjectResolveEvent
    | JobSubjectOperationRead
    | JobSubjectRecoverInsert
    | JobSubjectScanDiscovery
    | JobSubjectScanGap
    | JobSubjectReconcileSource
    | JobSubjectAuditTarget
    | JobSubjectCleanupAction
)


@dataclass(frozen=True, slots=True, repr=False)
class ThreadGenerationGuardUntracked(_ClosedValue):
    tag: Literal["untracked"]


@dataclass(frozen=True, slots=True, repr=False)
class ThreadGenerationGuardTracked(_ClosedValue):
    tag: Literal["tracked"]
    generation: Generation

    def _validate(self) -> None:
        _positive_generation(self.generation)


ThreadGenerationGuard = ThreadGenerationGuardUntracked | ThreadGenerationGuardTracked


@dataclass(frozen=True, slots=True, repr=False)
class Claim(_ClosedValue):
    claim_id: LocalId
    owner_run_id: LocalId
    acquired_at: Timestamp
    thread_generation: Generation | None
    job_revision: Revision
    phase: ClaimPhase
