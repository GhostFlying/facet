"""Closed, in-memory public values. No collectors, clocks, DB or provider access."""

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo

from facet import __version__
from facet.contracts import (
    BindingState,
    Count,
    EpochKind,
    EpochState,
    ErrorClass,
    ErrorCode,
    Freshness,
    PublicHealth,
    PublicPhase,
    Role,
    SourceMode,
    Timestamp,
)

from .errors import OutputBoundaryError, Suggestion, catalog_entry

PublicCount = int
Seconds = int
BuildVersion = str
MAX_PUBLIC_COUNT = 9007199254740991


class PermissionMode(StrEnum):
    SOURCE_READONLY = "source_readonly"
    SOURCE_CONVENIENCE = "source_convenience"
    TARGET_INSERT_READONLY = "target_insert_readonly"
    TARGET_INSERT_READONLY_LABELS = "target_insert_readonly_labels"


class CheckState(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class Pressure(StrEnum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class Component(StrEnum):
    RUNTIME = "runtime"
    SOURCE = "source"
    TARGET = "target"
    DATABASE = "database"
    STORAGE = "storage"
    MEMORY = "memory"
    CONFIGURATION = "configuration"


def _require(condition: bool) -> None:
    if not condition:
        raise OutputBoundaryError()


def _exact(value, cls, *, nullable=False):
    if nullable and value is None:
        return
    _require(type(value) is cls)


def public_count(value: int) -> int:
    _require(type(value) is int)
    _require(0 <= value <= MAX_PUBLIC_COUNT)
    return value


def count_from_core(value: Count) -> int:
    _exact(value, Count)
    return public_count(value.value)


def _count(value, *, nullable=False):
    if nullable and value is None:
        return
    public_count(value)


def _timestamp(value, *, nullable=False):
    if nullable and value is None:
        return
    _exact(value, Timestamp)
    _exact(value.value, datetime)
    # A custom tzinfo can execute arbitrary code even on an exact datetime.
    # Supported UTC values use the stdlib fixed-offset timezone, never callbacks.
    _require(
        type(value.value.tzinfo) is timezone or type(value.value.tzinfo) is ZoneInfo
    )
    _require(value.value.utcoffset() == timedelta(0))


def _number(value):
    _exact(value, float)
    _require(math.isfinite(value) and value >= 0)


def _metric(window, samples, values):
    _count(window)
    _require(1 <= window <= 86400)
    _count(samples)
    for value in values:
        if samples == 0:
            _require(value is None)
        else:
            _number(value)


def _role_code(role, code):
    _exact(role, Role, nullable=True)
    _exact(code, ErrorCode, nullable=True)
    if code in (ErrorCode.SOURCE_AUTH_REQUIRED, ErrorCode.SOURCE_RATE_LIMITED):
        _require(role is Role.SOURCE)
    if code in (ErrorCode.TARGET_AUTH_REQUIRED, ErrorCode.TARGET_RATE_LIMITED):
        _require(role is Role.TARGET)


@dataclass(frozen=True, slots=True, repr=False)
class RoleStatus:
    role: Role
    mode: PermissionMode | None
    auth_state: BindingState | None
    last_verified_at: Timestamp | None
    freshness: Freshness

    def __post_init__(self):
        _exact(self, RoleStatus)
        _exact(self.role, Role)
        _exact(self.mode, PermissionMode, nullable=True)
        _exact(self.auth_state, BindingState, nullable=True)
        _timestamp(self.last_verified_at, nullable=True)
        _exact(self.freshness, Freshness)
        if self.mode is not None:
            source = self.mode in (
                PermissionMode.SOURCE_READONLY,
                PermissionMode.SOURCE_CONVENIENCE,
            )
            _require(source == (self.role is Role.SOURCE))


@dataclass(frozen=True, slots=True, repr=False)
class Status:
    phase: PublicPhase | None
    health: PublicHealth
    source: RoleStatus
    target: RoleStatus
    last_poll_at: Timestamp | None
    last_verified_insert_at: Timestamp | None
    heartbeat_at: Timestamp | None
    cycle_in_progress: bool = False

    def __post_init__(self):
        _exact(self, Status)
        _exact(self.phase, PublicPhase, nullable=True)
        _exact(self.health, PublicHealth)
        _exact(self.cycle_in_progress, bool)
        _record(self.source, RoleStatus)
        _record(self.target, RoleStatus)
        _require(self.source.role is Role.SOURCE and self.target.role is Role.TARGET)
        for value in (
            self.last_poll_at,
            self.last_verified_insert_at,
            self.heartbeat_at,
        ):
            _timestamp(value, nullable=True)
        if self.health is PublicHealth.HEALTHY:
            _require(self.phase is not None)
            for role in (self.source, self.target):
                _require(role.freshness is Freshness.FRESH)
                _require(role.auth_state is BindingState.VERIFIED)


@dataclass(frozen=True, slots=True, repr=False)
class EpochSummary:
    kind: EpochKind
    state: EpochState
    started_at: Timestamp

    def __post_init__(self):
        _exact(self, EpochSummary)
        _exact(self.kind, EpochKind)
        _exact(self.state, EpochState)
        _timestamp(self.started_at)


@dataclass(frozen=True, slots=True, repr=False)
class QueueCounts:
    queued: PublicCount | None
    claimed: PublicCount | None
    retry_wait: PublicCount | None
    blocked: PublicCount | None
    needs_attention: PublicCount | None
    completed: PublicCount | None
    cancelled: PublicCount | None
    source_missing: PublicCount | None
    failed: PublicCount | None

    def __post_init__(self):
        _exact(self, QueueCounts)
        values = (
            self.queued,
            self.claimed,
            self.retry_wait,
            self.blocked,
            self.needs_attention,
            self.completed,
            self.cancelled,
            self.source_missing,
            self.failed,
        )
        _require(all(v is None for v in values) or all(v is not None for v in values))
        for value in values:
            _count(value, nullable=True)


@dataclass(frozen=True, slots=True, repr=False)
class RateMetric:
    value: float | None
    unit: Literal["messages_per_second"]
    window_seconds: Seconds
    sample_count: PublicCount

    def __post_init__(self):
        _exact(self, RateMetric)
        _exact(self.unit, str)
        _require(self.unit == "messages_per_second")
        _metric(self.window_seconds, self.sample_count, (self.value,))


@dataclass(frozen=True, slots=True, repr=False)
class LatencyMetric:
    p50: float | None
    p95: float | None
    unit: Literal["milliseconds"]
    window_seconds: Seconds
    sample_count: PublicCount

    def __post_init__(self):
        _exact(self, LatencyMetric)
        _exact(self.unit, str)
        _require(self.unit == "milliseconds")
        _metric(self.window_seconds, self.sample_count, (self.p50, self.p95))
        if self.sample_count:
            _require(self.p50 <= self.p95)


@dataclass(frozen=True, slots=True, repr=False)
class Progress:
    epoch: EpochSummary | None
    discovery_complete: bool
    scanned_threads: PublicCount | None
    discovered_threads: PublicCount | None
    completed_threads: PublicCount | None
    known_message_total: PublicCount | None
    confirmed_messages: PublicCount | None
    jobs: QueueCounts
    oldest_runnable_job_age_seconds: Seconds | None
    verified_last_hour: PublicCount | None
    verified_last_day: PublicCount | None
    rate: RateMetric
    latency: LatencyMetric

    def __post_init__(self):
        _exact(self, Progress)
        if self.epoch is not None:
            _record(self.epoch, EpochSummary)
        _exact(self.discovery_complete, bool)
        values = (
            self.scanned_threads,
            self.discovered_threads,
            self.completed_threads,
            self.known_message_total,
            self.confirmed_messages,
            self.oldest_runnable_job_age_seconds,
            self.verified_last_hour,
            self.verified_last_day,
        )
        for value in values:
            _count(value, nullable=True)
        _record(self.jobs, QueueCounts)
        _record(self.rate, RateMetric)
        _record(self.latency, LatencyMetric)
        if not self.discovery_complete:
            _require(self.known_message_total is None)
        if self.epoch is None:
            _require(not self.discovery_complete)
            _require(
                all(
                    v is None
                    for v in (
                        self.scanned_threads,
                        self.discovered_threads,
                        self.completed_threads,
                        self.known_message_total,
                    )
                )
            )
        if self.completed_threads is not None and self.discovered_threads is not None:
            _require(self.completed_threads <= self.discovered_threads)


@dataclass(frozen=True, slots=True, repr=False)
class IssueGroup:
    code: ErrorCode
    error_class: ErrorClass
    role: Role | None
    count: PublicCount
    first_at: Timestamp
    last_at: Timestamp
    retryable: bool
    next_retry_at: Timestamp | None
    suggestion: Suggestion

    def __post_init__(self):
        _exact(self, IssueGroup)
        _exact(self.code, ErrorCode)
        _exact(self.error_class, ErrorClass)
        _role_code(self.role, self.code)
        _count(self.count)
        _require(self.count >= 1)
        _timestamp(self.first_at)
        _timestamp(self.last_at)
        _require(self.first_at.value <= self.last_at.value)
        _timestamp(self.next_retry_at, nullable=True)
        _exact(self.retryable, bool)
        _exact(self.suggestion, Suggestion)
        entry = catalog_entry(self.code)
        _require(self.error_class is entry.error_class)
        _require(self.suggestion is entry.suggestion)
        _require(not self.retryable or entry.automatic_dependency_retry)
        _require(self.next_retry_at is None or self.retryable)


@dataclass(frozen=True, slots=True, repr=False)
class Issues:
    groups: tuple[IssueGroup, ...]

    def __post_init__(self):
        _exact(self, Issues)
        _exact(self.groups, tuple)
        _require(len(self.groups) <= 96)
        previous = None
        roles = {None: 0, Role.SOURCE: 1, Role.TARGET: 2}
        for group in self.groups:
            _record(group, IssueGroup)
            key = (group.code.value, roles[group.role])
            _require(previous is None or previous < key)
            previous = key


_PUBLIC_RULE_KINDS = frozenset(
    {
        "allow_sender",
        "allow_domain",
        "blacklist_sender",
        "action_label_add_sender",
        "action_label_add_domain",
        "action_label_blacklist",
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class RuleSummary:
    kind: str
    value: str
    enabled: bool

    def __post_init__(self):
        _exact(self, RuleSummary)
        _exact(self.kind, str)
        _require(self.kind in _PUBLIC_RULE_KINDS)
        _exact(self.value, str)
        _require(1 <= len(self.value.encode("utf-8")) <= 512)
        _require(
            not any(unicodedata.category(char).startswith("C") for char in self.value)
        )
        _exact(self.enabled, bool)


@dataclass(frozen=True, slots=True, repr=False)
class Rules:
    entries: tuple[RuleSummary, ...]

    def __post_init__(self):
        _exact(self, Rules)
        _exact(self.entries, tuple)
        _require(len(self.entries) <= 1024)
        previous = None
        for entry in self.entries:
            _record(entry, RuleSummary)
            key = (entry.kind, entry.value)
            _require(previous is None or previous < key)
            previous = key


@dataclass(frozen=True, slots=True, repr=False)
class ActivityEntry:
    rule_kind: str
    rule_value: str
    matched_count: PublicCount
    observed_at: Timestamp

    def __post_init__(self):
        _exact(self, ActivityEntry)
        _exact(self.rule_kind, str)
        _require(self.rule_kind in {"allow_sender", "allow_domain", "other"})
        _exact(self.rule_value, str)
        _require(1 <= len(self.rule_value.encode("utf-8")) <= 512)
        _require(
            not any(
                unicodedata.category(char).startswith("C") for char in self.rule_value
            )
        )
        _count(self.matched_count)
        _require(self.matched_count >= 1)
        _timestamp(self.observed_at)


@dataclass(frozen=True, slots=True, repr=False)
class Activity:
    entries: tuple[ActivityEntry, ...]

    def __post_init__(self):
        _exact(self, Activity)
        _exact(self.entries, tuple)
        _require(len(self.entries) <= 100)
        previous = None
        for entry in self.entries:
            _record(entry, ActivityEntry)
            key = (entry.observed_at.value, entry.rule_kind, entry.rule_value)
            _require(previous is None or key < previous)
            previous = key


@dataclass(frozen=True, slots=True, repr=False)
class Diagnostics:
    app_version: BuildVersion
    schema_version: PublicCount | None
    sync_owner_count: PublicCount | None
    db_readable: CheckState
    db_writable: CheckState
    source_mode: SourceMode | None
    source_scope_ready: CheckState
    target_scope_ready: CheckState
    memory_pressure: Pressure
    disk_pressure: Pressure
    heartbeat_at: Timestamp | None
    checked_at: Timestamp | None
    commit_sha: str | None = None

    def __post_init__(self):
        _exact(self, Diagnostics)
        _exact(self.app_version, str)
        _require(self.app_version == __version__ and len(self.app_version) <= 64)
        _require(
            re.fullmatch(
                r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", self.app_version
            )
            is not None
        )
        _count(self.schema_version, nullable=True)
        _count(self.sync_owner_count, nullable=True)
        for value in (
            self.db_readable,
            self.db_writable,
            self.source_scope_ready,
            self.target_scope_ready,
        ):
            _exact(value, CheckState)
        _exact(self.source_mode, SourceMode, nullable=True)
        _exact(self.memory_pressure, Pressure)
        _exact(self.disk_pressure, Pressure)
        _timestamp(self.heartbeat_at, nullable=True)
        _timestamp(self.checked_at, nullable=True)
        _exact(self.commit_sha, str, nullable=True)
        if self.commit_sha is not None:
            _require(re.fullmatch(r"[0-9a-f]{40}", self.commit_sha) is not None)


@dataclass(frozen=True, slots=True, repr=False)
class PublicEnvelope:
    data: Status | Progress | Issues | Rules | Activity | Diagnostics
    schema_version: Literal[1]
    sampled_at: Timestamp
    freshness: Freshness
    age_seconds: Seconds | None
    scope: Literal["projection"]

    def __post_init__(self):
        _exact(self, PublicEnvelope)
        _require(
            any(
                type(self.data) is cls
                for cls in (Status, Progress, Issues, Rules, Activity, Diagnostics)
            )
        )
        _record(self.data, type(self.data))
        _exact(self.schema_version, int)
        _require(self.schema_version == 1)
        _timestamp(self.sampled_at)
        _exact(self.freshness, Freshness)
        _count(self.age_seconds, nullable=True)
        _require(
            (self.age_seconds is None) == (self.freshness is Freshness.UNAVAILABLE)
        )
        _exact(self.scope, str)
        _require(self.scope == "projection")
        if type(self.data) is Status and self.data.health is PublicHealth.HEALTHY:
            _require(self.freshness is Freshness.FRESH)


def _record(value, cls):
    _exact(value, cls)
    # Revalidate at output as a defense against bypassed frozen constructors.
    try:
        cls.__post_init__(value)
    except AttributeError:
        raise OutputBoundaryError() from None
