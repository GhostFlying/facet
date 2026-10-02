"""Closed, immutable storage records from persistence-schema-v1.

These are private metadata, NOT public DTOs. repr never serializes their fields.
Every nullable field is required; no caller-supplied partial row dictionaries.
"""

from dataclasses import dataclass, fields
from functools import cache
from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints

from facet.contracts import (
    AdmissionRef,
    BindingState,
    Claim,
    Count,
    DatePolicy,
    EpochDecisionRef,
    EpochKind,
    EpochState,
    ErrorClass,
    ErrorCode,
    Generation,
    InsertState,
    JobKind,
    JobState,
    JobSubject,
    LocalId,
    OutcomeCertainty,
    PartitionProgress,
    PartitionState,
    PolicyVersion,
    Priority,
    ProjectionId,
    ProviderId,
    ProviderPageToken,
    RestoreState,
    Revision,
    Role,
    RuleKind,
    RuleOrigin,
    Sha256Hex,
    SourceEvent,
    SourceMode,
    Timestamp,
    Visibility,
)

from .codecs import (
    ActionKind,
    ActionState,
    AttributionKind,
    AuditKind,
    AuditObjectKind,
    CleanupState,
    EventProcessing,
    ExpansionItemKind,
    KeyBytes,
    MigrationName,
    PollOrigin,
    PollState,
    PrivateAddress,
    RfcMessageId,
    RuleValue,
    SchemaVersion,
    ThreadStopReason,
    invalid,
)


@cache
def _hints(cls: type) -> dict:
    return get_type_hints(cls)


def _matches(value: object, annotation: object) -> bool:
    origin = get_origin(annotation)
    if origin is Literal:
        return any(type(value) is type(a) and value == a for a in get_args(annotation))
    if origin is UnionType:
        return any(_matches(value, a) for a in get_args(annotation))
    if origin is tuple:
        args = get_args(annotation)
        return (
            type(value) is tuple
            and args[-1] is Ellipsis
            and all(_matches(item, args[0]) for item in value)
        )
    return type(value) is annotation


class _Record:
    __slots__ = ()

    def __post_init__(self) -> None:
        hints = _hints(type(self))
        if any(
            not _matches(getattr(self, f.name), hints[f.name]) for f in fields(self)
        ):
            invalid()
        self._validate()

    def _validate(self) -> None:
        pass


@dataclass(frozen=True, slots=True, repr=False)
class SchemaMetadataRow(_Record):
    singleton: Count
    schema_version: SchemaVersion
    registry_digest: Sha256Hex
    created_at: Timestamp


@dataclass(frozen=True, slots=True, repr=False)
class SchemaMigrationRow(_Record):
    version: SchemaVersion
    name: MigrationName
    checksum: Sha256Hex
    applied_at: Timestamp


@dataclass(frozen=True, slots=True, repr=False)
class ProjectionRow(_Record):
    projection_id: ProjectionId
    singleton: Count
    state_instance_id: LocalId
    request_namespace: LocalId
    config_revision: Revision
    ruleset_revision: Revision
    source_mode: SourceMode
    binding_state: BindingState
    restore_state: RestoreState
    daemon_paused: bool
    last_owner_run_id: LocalId | None
    created_at: Timestamp


@dataclass(frozen=True, slots=True, repr=False)
class BindingRow(_Record):
    projection_id: ProjectionId
    role: Role
    declared_address: PrivateAddress
    verified_address: PrivateAddress | None
    credential_revision: Revision
    binding_revision: Revision
    state: BindingState
    verified_at: Timestamp | None


@dataclass(frozen=True, slots=True, repr=False)
class BindingRevisionRow(_Record):
    projection_id: ProjectionId
    role: Role
    binding_revision: Revision
    declared_address: PrivateAddress
    verified_address: PrivateAddress | None
    state: BindingState
    verified_at: Timestamp | None


@dataclass(frozen=True, slots=True, repr=False)
class RuleRow(_Record):
    projection_id: ProjectionId
    rule_id: LocalId
    kind: RuleKind
    normalized_value: RuleValue
    current_revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class RuleRevisionRow(_Record):
    projection_id: ProjectionId
    rule_id: LocalId
    revision: Revision
    enabled: bool
    effective_at: Timestamp
    origin: RuleOrigin
    policy_version: PolicyVersion


@dataclass(frozen=True, slots=True, repr=False)
class RulesetRow(_Record):
    projection_id: ProjectionId
    revision: Revision
    created_at: Timestamp
    sealed: bool


@dataclass(frozen=True, slots=True, repr=False)
class RulesetMemberRow(_Record):
    projection_id: ProjectionId
    ruleset_revision: Revision
    rule_id: LocalId
    rule_revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class TrackedThreadRow(_Record):
    projection_id: ProjectionId
    source_thread_id: ProviderId
    active: bool
    generation: Generation
    admitted_at: Timestamp
    stopped_at: Timestamp | None
    stop_reason: ThreadStopReason | None
    admission_revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class ThreadAdmissionRow(_Record):
    projection_id: ProjectionId
    source_thread_id: ProviderId
    admission_revision: Revision
    generation: Generation
    admitted_at: Timestamp
    admission: AdmissionRef


@dataclass(frozen=True, slots=True, repr=False)
class EpochRow(_Record):
    projection_id: ProjectionId
    epoch_id: LocalId
    kind: EpochKind
    state: EpochState
    revision: Revision
    created_at: Timestamp
    window_start: Timestamp | None
    window_end: Timestamp | None
    discovery_cutoff: Timestamp | None
    decision: EpochDecisionRef
    gap_id: LocalId | None
    recovery_margin_us: Count | None
    fence_history_id: ProviderId | None
    fence_recorded_at: Timestamp | None
    catchup_history_id: ProviderId | None
    discovery_complete: bool
    known_message_total: Count | None


@dataclass(frozen=True, slots=True, repr=False)
class HistoryGapRow(_Record):
    projection_id: ProjectionId
    gap_id: LocalId
    failed_poll_id: LocalId
    failed_cursor: ProviderId
    checkpoint_cursor: ProviderId | None
    checkpoint_revision: Revision
    observed_at: Timestamp
    reliable_coverage_at: Timestamp | None
    h1: ProviderId
    h1_recorded_at: Timestamp


@dataclass(frozen=True, slots=True, repr=False)
class EpochPartitionRow(_Record):
    projection_id: ProjectionId
    epoch_id: LocalId
    partition_key: KeyBytes
    progress: PartitionProgress
    revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class SourceEventRow(_Record):
    projection_id: ProjectionId
    event_id: LocalId
    event_key: KeyBytes
    event: SourceEvent
    processing: EventProcessing
    revision: Revision
    error_code: ErrorCode | None

    def _validate(self) -> None:
        from .keys import event_key

        if self.event.key.projection_id != self.projection_id:
            invalid()
        if self.event_key != event_key(self.projection_id, self.event.key):
            invalid()


@dataclass(frozen=True, slots=True, repr=False)
class HistoryCheckpointRow(_Record):
    projection_id: ProjectionId
    cursor: ProviderId | None
    reliable_coverage_at: Timestamp | None
    revision: Revision
    active_poll_id: LocalId | None


@dataclass(frozen=True, slots=True, repr=False)
class HistoryPollRow(_Record):
    projection_id: ProjectionId
    poll_id: LocalId
    origin: PollOrigin
    origin_epoch_id: LocalId | None
    start_cursor: ProviderId
    start_checkpoint_revision: Revision
    started_at: Timestamp
    state: PollState
    completed_pages: Count
    next_page_token: ProviderPageToken | None
    final_history_id: ProviderId | None
    finished_at: Timestamp | None
    revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class HistoryPageRow(_Record):
    projection_id: ProjectionId
    poll_id: LocalId
    ordinal: Count
    response_history_id: ProviderId
    input_page_token: ProviderPageToken | None
    next_page_token: ProviderPageToken | None
    received_at: Timestamp
    metadata_digest: Sha256Hex
    expected_event_count: Count
    complete: bool


@dataclass(frozen=True, slots=True, repr=False)
class HistoryPageEventRow(_Record):
    projection_id: ProjectionId
    poll_id: LocalId
    ordinal: Count
    event_id: LocalId


@dataclass(frozen=True, slots=True, repr=False)
class SyncJobRow(_Record):
    projection_id: ProjectionId
    job_id: LocalId
    kind: JobKind
    key_version: Count
    stable_key: KeyBytes
    priority: Priority
    state: JobState
    revision: Revision
    created_at: Timestamp
    updated_at: Timestamp
    next_attempt_at: Timestamp | None
    attempt_count: Count
    last_error_code: ErrorCode | None
    origin_epoch_id: LocalId | None
    subject: JobSubject

    def _validate(self) -> None:
        from .keys import job_key

        if self.kind.value != self.subject.tag or self.key_version.value != 1:
            invalid()
        if self.stable_key != job_key(self.projection_id, self.subject):
            invalid()


@dataclass(frozen=True, slots=True, repr=False)
class EpochJobRow(_Record):
    projection_id: ProjectionId
    epoch_id: LocalId
    job_id: LocalId


@dataclass(frozen=True, slots=True, repr=False)
class JobClaimRow(_Record):
    projection_id: ProjectionId
    job_id: LocalId
    claim: Claim


@dataclass(frozen=True, slots=True, repr=False)
class InsertAttemptRow(_Record):
    projection_id: ProjectionId
    attempt_id: LocalId
    job_id: LocalId
    claim_id: LocalId
    source_message_id: ProviderId
    source_thread_id: ProviderId
    generation: Generation
    binding_role: Role
    binding_revision: Revision
    prepared_at: Timestamp
    dispatch_started_at: Timestamp | None
    result_at: Timestamp | None
    requested_target_thread_id: ProviderId | None
    raw_digest: Sha256Hex
    semantic_digest: Sha256Hex | None
    semantic_version: PolicyVersion | None
    rfc_message_id: RfcMessageId | None
    date_policy: DatePolicy
    state: InsertState
    certainty: OutcomeCertainty
    target_message_id: ProviderId | None
    target_thread_id: ProviderId | None
    attribution: AttributionKind
    visibility: Visibility
    verified_at: Timestamp | None
    error_code: ErrorCode | None
    recovery_checks: Count
    next_recovery_at: Timestamp | None
    revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class MessageMappingRow(_Record):
    projection_id: ProjectionId
    source_message_id: ProviderId
    source_thread_id: ProviderId
    mapping_revision: Revision
    attempt_id: LocalId
    target_message_id: ProviderId
    target_thread_id: ProviderId
    verified_at: Timestamp
    visibility: Visibility
    last_audit_at: Timestamp | None
    target_present: bool | None


@dataclass(frozen=True, slots=True, repr=False)
class MappingHistoryRow(_Record):
    projection_id: ProjectionId
    source_message_id: ProviderId
    mapping_revision: Revision
    source_thread_id: ProviderId
    attempt_id: LocalId
    target_message_id: ProviderId
    target_thread_id: ProviderId
    verified_at: Timestamp
    superseded_at: Timestamp | None


@dataclass(frozen=True, slots=True, repr=False)
class TargetOwnershipRow(_Record):
    projection_id: ProjectionId
    target_message_id: ProviderId
    source_message_id: ProviderId
    first_attempt_id: LocalId
    recorded_at: Timestamp


@dataclass(frozen=True, slots=True, repr=False)
class ThreadTargetRow(_Record):
    projection_id: ProjectionId
    source_thread_id: ProviderId
    target_thread_id: ProviderId
    anchor: bool
    first_attempt_id: LocalId
    created_at: Timestamp


@dataclass(frozen=True, slots=True, repr=False)
class ActionCommandRow(_Record):
    projection_id: ProjectionId
    action_command_id: LocalId
    event_id: LocalId
    history_record_id: ProviderId
    label_id: ProviderId
    source_thread_id: ProviderId
    kind: ActionKind
    state: ActionState
    cleanup: CleanupState
    observed_at: Timestamp
    executed_at: Timestamp | None
    error_code: ErrorCode | None
    revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class ErrorEventRow(_Record):
    projection_id: ProjectionId
    error_id: LocalId
    code: ErrorCode
    error_class: ErrorClass
    role: Role | None
    observed_at: Timestamp
    job_id: LocalId | None
    attempt_id: LocalId | None
    count: Count


@dataclass(frozen=True, slots=True, repr=False)
class AuditEventRow(_Record):
    projection_id: ProjectionId
    audit_id: LocalId
    kind: AuditKind
    object_kind: AuditObjectKind
    local_object_id: LocalId | None
    source_thread_id: ProviderId | None
    source_message_id: ProviderId | None
    before_revision: Revision | None
    after_revision: Revision | None
    before_state: BindingState | EpochState | JobState | InsertState | None
    after_state: BindingState | EpochState | JobState | InsertState | None
    error_code: ErrorCode | None
    observed_at: Timestamp


@dataclass(frozen=True, slots=True, repr=False)
class ThreadExpansionRunRow(_Record):
    projection_id: ProjectionId
    run_id: LocalId
    job_id: LocalId
    source_thread_id: ProviderId
    epoch_id: LocalId
    generation: Generation
    current: bool
    state: PartitionState
    snapshot_digest: Sha256Hex
    expected_messages: Count
    started_at: Timestamp
    completed_at: Timestamp | None
    revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class ThreadExpansionItemRow(_Record):
    projection_id: ProjectionId
    run_id: LocalId
    source_message_id: ProviderId
    kind: ExpansionItemKind
    project_job_id: LocalId | None
    mapped_source_message_id: ProviderId | None
    mapping_revision: Revision | None


@dataclass(frozen=True, slots=True, repr=False)
class RevisionGuard(_Record):
    expected: Revision


@dataclass(frozen=True, slots=True, repr=False)
class WriteReceipt(_Record):
    disposition: Literal["created", "replayed", "updated"]
    object_id: LocalId | ProviderId | ProjectionId
    revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class OwnerSessionInfo(_Record):
    owner_run_id: LocalId
    state_instance_id: LocalId
    request_namespace: LocalId


@dataclass(frozen=True, slots=True, repr=False)
class BootstrapInitContext(_Record):
    owner: OwnerSessionInfo
    bootstrap_nonce: LocalId


@dataclass(frozen=True, slots=True, repr=False)
class ReadPage[T]:
    items: tuple[T, ...]
    next_key: bytes | None

    def __post_init__(self) -> None:
        if (
            type(self.items) is not tuple
            or len(self.items) > 500
            or (self.next_key is not None and type(self.next_key) is not bytes)
            or any(type(row) not in _ROW_TYPES for row in self.items)
        ):
            invalid()


@dataclass(frozen=True, slots=True, repr=False)
class JobStateCount(_Record):
    state: JobState
    count: Count


@dataclass(frozen=True, slots=True, repr=False)
class CountsSnapshot(_Record):
    confirmed_mappings: Count
    by_job_state: tuple[JobStateCount, ...]
    unresolved_attempts: Count
    discovery_complete: bool
    known_total: Count | None

    def _validate(self) -> None:
        if tuple(v.state for v in self.by_job_state) != tuple(JobState):
            invalid()
        if not self.discovery_complete and self.known_total is not None:
            invalid()


@dataclass(frozen=True, slots=True, repr=False)
class MigrationBackupReceipt(_Record):
    bundle_id: LocalId
    manifest_digest: Sha256Hex
    state_instance_id: LocalId
    request_namespace: LocalId
    schema_version: SchemaVersion
    config_revision: Revision
    source_credential_revision: Revision
    target_credential_revision: Revision


@dataclass(frozen=True, slots=True, repr=False)
class DatabaseSnapshotInfo(_Record):
    schema_version: SchemaVersion
    state_instance_id: LocalId
    request_namespace: LocalId
    integrity_ok: Literal[True]


_ROW_TYPES = frozenset(
    {
        SchemaMetadataRow,
        SchemaMigrationRow,
        ProjectionRow,
        BindingRow,
        BindingRevisionRow,
        RuleRow,
        RuleRevisionRow,
        RulesetRow,
        RulesetMemberRow,
        TrackedThreadRow,
        ThreadAdmissionRow,
        EpochRow,
        HistoryGapRow,
        EpochPartitionRow,
        SourceEventRow,
        HistoryCheckpointRow,
        HistoryPollRow,
        HistoryPageRow,
        HistoryPageEventRow,
        SyncJobRow,
        EpochJobRow,
        JobClaimRow,
        InsertAttemptRow,
        MessageMappingRow,
        MappingHistoryRow,
        TargetOwnershipRow,
        ThreadTargetRow,
        ActionCommandRow,
        ErrorEventRow,
        AuditEventRow,
        ThreadExpansionRunRow,
        ThreadExpansionItemRow,
    }
)
