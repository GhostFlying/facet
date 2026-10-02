"""Closed storage scalars and exact, privacy-safe SQLite conversions."""

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from facet.contracts import Count, ErrorCode, Revision, Timestamp

MIN_TIMESTAMP = -62135596800000000
MAX_TIMESTAMP = 253402300799999999
MAX_INTEGER = 2**63 - 1
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class StorageFailure(Exception):
    """Only a controlled code survives the exception boundary."""

    def __init__(self, code: ErrorCode):
        if type(code) is not ErrorCode:
            code = ErrorCode.CONSISTENCY_FAILURE
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"StorageFailure({self.code.value})"


def invalid() -> None:
    raise StorageFailure(ErrorCode.INVALID_INPUT)


def sqlite_failure(error: sqlite3.Error) -> StorageFailure:
    # Never inspect or forward the message, parameters, statement, or traceback.
    code = getattr(error, "sqlite_errorcode", 0) & 0xFF
    if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_CANTOPEN}:
        return StorageFailure(ErrorCode.DATABASE_UNAVAILABLE)
    if code in {sqlite3.SQLITE_CONSTRAINT, sqlite3.SQLITE_MISMATCH}:
        return StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    return StorageFailure(ErrorCode.PERSISTENCE_FAILURE)


@dataclass(frozen=True, slots=True, repr=False)
class SchemaVersion:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 1 <= self.value <= 2147483647:
            invalid()


@dataclass(frozen=True, slots=True, repr=False)
class MigrationName:
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or re.fullmatch(r"v[0-9]{4}", self.value) is None
        ):
            invalid()


@dataclass(frozen=True, slots=True, repr=False)
class _PrivateText:
    value: str

    def __post_init__(self) -> None:
        limits = {PrivateAddress: 320, RuleValue: 512, RfcMessageId: 998}
        if (
            type(self.value) is not str
            or not self.value
            or any(unicodedata.category(c) in {"Cc", "Cs"} for c in self.value)
            or len(self.value.encode("utf-8")) > limits[type(self)]
        ):
            invalid()


class PrivateAddress(_PrivateText):
    __slots__ = ()


class RuleValue(_PrivateText):
    __slots__ = ()


class RfcMessageId(_PrivateText):
    __slots__ = ()


@dataclass(frozen=True, slots=True, repr=False)
class KeyBytes:
    value: bytes

    def __post_init__(self) -> None:
        if type(self.value) is not bytes or not 1 <= len(self.value) <= 8192:
            invalid()


@dataclass(frozen=True, slots=True, repr=False)
class PageLimit:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 1 <= self.value <= 500:
            invalid()


def timestamp_to_sql(value: Timestamp) -> int:
    if type(value) is not Timestamp:
        invalid()
    delta = value.value - _EPOCH
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def timestamp_from_sql(value: int) -> Timestamp:
    if type(value) is not int or not MIN_TIMESTAMP <= value <= MAX_TIMESTAMP:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    return Timestamp(_EPOCH + timedelta(microseconds=value))


def next_revision(value: Revision) -> Revision:
    if type(value) is not Revision or value.value == MAX_INTEGER:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    return Revision(value.value + 1)


def encode_scalar(value: object) -> str | int | bytes | None:
    if value is None:
        return None
    if type(value) is bool:
        return int(value)
    if type(value) in _ENUM_TYPES:
        return value.value
    if type(value) is Timestamp:
        return timestamp_to_sql(value)
    # Only the registered scalar families, never repr(), dict(), or arbitrary .value.
    from facet.contracts.primitives import (
        Generation,
        LocalId,
        PolicyVersion,
        ProjectionId,
        ProviderId,
        ProviderPageToken,
        Sha256Hex,
    )

    if type(value) in {
        Count,
        Generation,
        Revision,
        LocalId,
        PolicyVersion,
        ProjectionId,
        ProviderId,
        ProviderPageToken,
        Sha256Hex,
        SchemaVersion,
        MigrationName,
        PrivateAddress,
        RuleValue,
        RfcMessageId,
        KeyBytes,
    }:
        return value.value
    invalid()


class EventProcessing(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    CONSUMED = "consumed"
    NEEDS_ATTENTION = "needs_attention"
    SOURCE_MISSING = "source_missing"


class PollState(StrEnum):
    READING = "reading"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class PollOrigin(StrEnum):
    CHECKPOINT = "checkpoint"
    INITIAL_EPOCH = "initial_epoch"
    RECOVERY_EPOCH = "recovery_epoch"


class ExpansionItemKind(StrEnum):
    PROJECT_JOB = "project_job"
    VERIFIED_MAPPING = "verified_mapping"


class ThreadStopReason(StrEnum):
    MANUAL_STOP = "manual_stop"
    BLACKLIST = "blacklist"
    QUEUE_CANCEL = "queue_cancel"


class ActionKind(StrEnum):
    ADD_SENDER = "add_sender"
    ADD_DOMAIN = "add_domain"
    BLACKLIST = "blacklist"


class ActionState(StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"
    NEEDS_ATTENTION = "needs_attention"


class CleanupState(StrEnum):
    NOT_REQUESTED = "not_requested"
    QUEUED = "queued"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class AttributionKind(StrEnum):
    NONE = "none"
    DIRECT_RESPONSE = "direct_response"


class AuditKind(StrEnum):
    INITIALIZED = "initialized"
    RULE_CHANGED = "rule_changed"
    THREAD_ADMITTED = "thread_admitted"
    THREAD_STOPPED = "thread_stopped"
    EPOCH_STARTED = "epoch_started"
    PAGE_INGESTED = "page_ingested"
    CURSOR_ADVANCED = "cursor_advanced"
    JOB_STATE_CHANGED = "job_state_changed"
    ATTEMPT_STATE_CHANGED = "attempt_state_changed"
    MAPPING_VERIFIED = "mapping_verified"
    BINDING_CHANGED = "binding_changed"
    RESTORE_FENCED = "restore_fenced"
    MAINTENANCE_COMPLETED = "maintenance_completed"


class AuditObjectKind(StrEnum):
    PROJECTION = "projection"
    RULE = "rule"
    THREAD = "thread"
    EPOCH = "epoch"
    EVENT = "event"
    JOB = "job"
    ATTEMPT = "attempt"
    MAPPING = "mapping"


from facet.contracts import enums as _core_enums  # noqa: E402

_ENUM_TYPES = frozenset(
    value
    for value in vars(_core_enums).values()
    if isinstance(value, type)
    and issubclass(value, StrEnum)
    and value.__module__ == _core_enums.__name__
) | frozenset(
    {
        EventProcessing,
        PollState,
        PollOrigin,
        ExpansionItemKind,
        ThreadStopReason,
        ActionKind,
        ActionState,
        CleanupState,
        AttributionKind,
        AuditKind,
        AuditObjectKind,
    }
)
