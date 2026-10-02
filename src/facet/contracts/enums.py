"""Closed enum inventory from the reviewed p1-core-v1 contract."""

from enum import StrEnum


class Role(StrEnum):
    SOURCE = "source"
    TARGET = "target"


class SourceMode(StrEnum):
    READONLY = "readonly"
    CONVENIENCE = "convenience"


class BindingState(StrEnum):
    VERIFICATION_PENDING = "verification_pending"
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    AUTH_REQUIRED = "auth_required"


class RestoreState(StrEnum):
    NORMAL = "normal"
    REVALIDATION_REQUIRED = "revalidation_required"
    MAINTENANCE_INCOMPLETE = "maintenance_incomplete"


class RuleOrigin(StrEnum):
    INITIAL_CONFIG = "initial_config"
    CLI = "cli"
    ACTION_LABEL = "action_label"


class RuleKind(StrEnum):
    ALLOW_SENDER = "allow_sender"
    ALLOW_DOMAIN = "allow_domain"
    BLACKLIST_SENDER = "blacklist_sender"


class AdmissionOrigin(StrEnum):
    INITIAL_BACKFILL = "initial_backfill"
    FUTURE_RULE = "future_rule"
    MANUAL_THREAD = "manual_thread"
    ACTION_LABEL = "action_label"


class EpochKind(StrEnum):
    INITIAL_BACKFILL = "initial_backfill"
    HISTORICAL_EXPANSION = "historical_expansion"
    HISTORY_GAP = "history_gap"
    SOURCE_RECONCILE = "source_reconcile"
    TARGET_AUDIT = "target_audit"


class EpochState(StrEnum):
    PREPARED = "prepared"
    SCANNING = "scanning"
    CATCHING_UP = "catching_up"
    DRAINING = "draining"
    PAUSED = "paused"
    COMPLETED = "completed"
    COMPLETED_WITH_ISSUES = "completed_with_issues"
    NEEDS_ATTENTION = "needs_attention"


class JobKind(StrEnum):
    PROJECT_MESSAGE = "project_message"
    REPAIR_MESSAGE = "repair_message"
    EXPAND_THREAD = "expand_thread"
    RESOLVE_EVENT = "resolve_event"
    OPERATION_READ = "operation_read"
    RECOVER_INSERT = "recover_insert"
    SCAN_DISCOVERY = "scan_discovery"
    SCAN_GAP = "scan_gap"
    RECONCILE_SOURCE = "reconcile_source"
    AUDIT_TARGET = "audit_target"
    CLEANUP_ACTION = "cleanup_action"


class JobState(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RETRY_WAIT = "retry_wait"
    BLOCKED = "blocked"
    NEEDS_ATTENTION = "needs_attention"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SOURCE_MISSING = "source_missing"
    FAILED = "failed"


class Priority(StrEnum):
    STOP = "stop"
    REALTIME = "realtime"
    RECOVERY = "recovery"
    BACKFILL = "backfill"
    AUDIT = "audit"


class InsertState(StrEnum):
    PREPARED = "prepared"
    DISPATCH_STARTED = "dispatch_started"
    DEFINITE_NOT_INSERTED = "definite_not_inserted"
    KNOWN_INSERTED = "known_inserted"
    PENDING_RECOVERY = "pending_recovery"
    VERIFIED = "verified"
    NEEDS_ATTENTION = "needs_attention"
    CANCELLED_BEFORE_DISPATCH = "cancelled_before_dispatch"


class OutcomeCertainty(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    DEFINITELY_NOT_INSERTED = "definitely_not_inserted"
    INSERTED = "inserted"
    UNKNOWN = "unknown"


class Visibility(StrEnum):
    NORMAL = "normal"
    SPAM = "spam"
    TRASH = "trash"
    UNKNOWN = "unknown"


class DatePolicy(StrEnum):
    VALID_DATE_HEADER = "valid_date_header"
    FALLBACK_RECEIVED_TIME = "fallback_received_time"


class OperationState(StrEnum):
    ACCEPTED = "accepted"
    EXECUTING = "executing"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    NEEDS_ATTENTION = "needs_attention"
    REJECTED = "rejected"


class PreviewPurpose(StrEnum):
    TRACK_THREAD = "track_thread"
    APPROVE_ADMISSION = "approve_admission"
    START_BACKFILL = "start_backfill"
    REPAIR_MISSING = "repair_missing"
    RETRY_UNKNOWN_INSERT = "retry_unknown_insert"
    APPROVE_GAP = "approve_gap"
    CHANGE_MODE = "change_mode"
    MAINTENANCE_RESTORE = "maintenance_restore"
    MAINTENANCE_MIGRATE = "maintenance_migrate"
    OPERATIONAL_CHANGE = "operational_change"


class ErrorClass(StrEnum):
    INPUT = "input"
    GUARD = "guard"
    OWNERSHIP = "ownership"
    DEPENDENCY = "dependency"
    ATTENTION = "attention"
    PERSISTENCE = "persistence"


class ErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_VERSION = "unsupported_version"
    REQUEST_CONFLICT = "request_conflict"
    REQUEST_NOT_RECEIVED = "request_not_received"
    REQUEST_OUTCOME_UNKNOWN = "request_outcome_unknown"
    REQUEST_LINEAGE_MISMATCH = "request_lineage_mismatch"
    CONFIRMATION_REQUIRED = "confirmation_required"
    SCOPE_REQUIRED = "scope_required"
    BINDING_MISMATCH = "binding_mismatch"
    BINDING_PENDING = "binding_pending"
    PREVIEW_INVALID = "preview_invalid"
    GENERATION_STALE = "generation_stale"
    OWNER_UNAVAILABLE = "owner_unavailable"
    OWNER_BUSY = "owner_busy"
    MAINTENANCE_INCOMPLETE = "maintenance_incomplete"
    WAIT_TIMEOUT = "wait_timeout"
    SOURCE_AUTH_REQUIRED = "source_auth_required"
    TARGET_AUTH_REQUIRED = "target_auth_required"
    SOURCE_RATE_LIMITED = "source_rate_limited"
    TARGET_RATE_LIMITED = "target_rate_limited"
    NETWORK_UNAVAILABLE = "network_unavailable"
    TARGET_STORAGE_FULL = "target_storage_full"
    INSERT_RESULT_UNKNOWN = "insert_result_unknown"
    DUPLICATE_CANDIDATES = "duplicate_candidates"
    ATTRIBUTION_UNKNOWN = "attribution_unknown"
    FIDELITY_MISMATCH = "fidelity_mismatch"
    SOURCE_MISSING = "source_missing"
    TARGET_MISSING = "target_missing"
    DATABASE_UNAVAILABLE = "database_unavailable"
    PERSISTENCE_FAILURE = "persistence_failure"
    CONSISTENCY_FAILURE = "consistency_failure"
    MAINTENANCE_REQUIRED = "maintenance_required"


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class PublicPhase(StrEnum):
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    BACKFILL = "backfill"
    INCREMENTAL = "incremental"
    RECOVERING = "recovering"
    PAUSED = "paused"
    MAINTENANCE = "maintenance"


class PublicHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class LabelChange(StrEnum):
    ADDED = "added"
    REMOVED = "removed"


class ReadTaskKind(StrEnum):
    THREAD_PREVIEW = "thread_preview"
    REVIEW_PREVIEW = "review_preview"
    BACKFILL_PREVIEW = "backfill_preview"
    REPAIR_PREVIEW = "repair_preview"
    RECOVERY_PREVIEW = "recovery_preview"
    GAP_PREVIEW = "gap_preview"
    DOCTOR_LIVE = "doctor_live"


class PartitionState(StrEnum):
    NOT_STARTED = "not_started"
    SCANNING = "scanning"
    COMPLETE = "complete"
    NEEDS_ATTENTION = "needs_attention"


class ClaimPhase(StrEnum):
    PREPARING = "preparing"
    DISPATCHING = "dispatching"
    VERIFYING = "verifying"
