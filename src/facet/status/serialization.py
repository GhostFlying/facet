"""Explicit, complete output construction. No generic object encoder or I/O."""

import json
import unicodedata
from dataclasses import dataclass
from typing import Literal

from facet.contracts import BindingState, ErrorCode, Freshness, Role, Timestamp

from .errors import OutputBoundaryError
from .models import (
    Activity,
    CheckState,
    Component,
    Diagnostics,
    Issues,
    PermissionMode,
    Progress,
    PublicEnvelope,
    RoleStatus,
    Rules,
    Status,
    _exact,
    _record,
    _require,
    _role_code,
    _timestamp,
)

_MAX_PUBLIC_JSON_BYTES = 262144
_MAX_RULES_JSON_BYTES = 2097152


def _time(value):
    # Persisted instants remain UTC; public operational timestamps use the
    # sync server's local offset so all Dashboard viewers see the same clock.
    return value.value.astimezone().isoformat(timespec="microseconds")


def _RoleStatus(value):
    return {
        "role": value.role.value,
        "mode": None if value.mode is None else value.mode.value,
        "auth_state": None if value.auth_state is None else value.auth_state.value,
        "last_verified_at": None
        if value.last_verified_at is None
        else _time(value.last_verified_at),
        "freshness": value.freshness.value,
    }


def _Status(value):
    return {
        "phase": None if value.phase is None else value.phase.value,
        "health": value.health.value,
        "source": _RoleStatus(value.source),
        "target": _RoleStatus(value.target),
        "last_poll_at": None
        if value.last_poll_at is None
        else _time(value.last_poll_at),
        "last_verified_insert_at": None
        if value.last_verified_insert_at is None
        else _time(value.last_verified_insert_at),
        "heartbeat_at": None
        if value.heartbeat_at is None
        else _time(value.heartbeat_at),
    }


def _EpochSummary(value):
    return {
        "kind": value.kind.value,
        "state": value.state.value,
        "started_at": _time(value.started_at),
    }


def _QueueCounts(value):
    return {
        "queued": value.queued,
        "claimed": value.claimed,
        "retry_wait": value.retry_wait,
        "blocked": value.blocked,
        "needs_attention": value.needs_attention,
        "completed": value.completed,
        "cancelled": value.cancelled,
        "source_missing": value.source_missing,
        "failed": value.failed,
    }


def _RateMetric(value):
    return {
        "value": value.value,
        "unit": value.unit,
        "window_seconds": value.window_seconds,
        "sample_count": value.sample_count,
    }


def _LatencyMetric(value):
    return {
        "p50": value.p50,
        "p95": value.p95,
        "unit": value.unit,
        "window_seconds": value.window_seconds,
        "sample_count": value.sample_count,
    }


def _Progress(value):
    return {
        "epoch": None if value.epoch is None else _EpochSummary(value.epoch),
        "discovery_complete": value.discovery_complete,
        "scanned_threads": value.scanned_threads,
        "discovered_threads": value.discovered_threads,
        "completed_threads": value.completed_threads,
        "known_message_total": value.known_message_total,
        "confirmed_messages": value.confirmed_messages,
        "jobs": _QueueCounts(value.jobs),
        "oldest_runnable_job_age_seconds": value.oldest_runnable_job_age_seconds,
        "verified_last_hour": value.verified_last_hour,
        "verified_last_day": value.verified_last_day,
        "rate": _RateMetric(value.rate),
        "latency": _LatencyMetric(value.latency),
    }


def _IssueGroup(value):
    return {
        "code": value.code.value,
        "error_class": value.error_class.value,
        "role": None if value.role is None else value.role.value,
        "count": value.count,
        "first_at": _time(value.first_at),
        "last_at": _time(value.last_at),
        "retryable": value.retryable,
        "next_retry_at": None
        if value.next_retry_at is None
        else _time(value.next_retry_at),
        "suggestion": value.suggestion.value,
    }


def _Issues(value):
    return {
        "groups": [_IssueGroup(group) for group in value.groups],
    }


def _RuleSummary(value):
    return {
        "kind": value.kind,
        "value": value.value,
        "enabled": value.enabled,
    }


def _Rules(value):
    return {"entries": [_RuleSummary(entry) for entry in value.entries]}


def _ActivityEntry(value):
    return {
        "rule_kind": value.rule_kind,
        "rule_value": value.rule_value,
        "matched_count": value.matched_count,
        "observed_at": _time(value.observed_at),
    }


def _Activity(value):
    return {"entries": [_ActivityEntry(entry) for entry in value.entries]}


def _Diagnostics(value):
    return {
        "app_version": value.app_version,
        "schema_version": value.schema_version,
        "sync_owner_count": value.sync_owner_count,
        "db_readable": value.db_readable.value,
        "db_writable": value.db_writable.value,
        "source_mode": None if value.source_mode is None else value.source_mode.value,
        "source_scope_ready": value.source_scope_ready.value,
        "target_scope_ready": value.target_scope_ready.value,
        "memory_pressure": value.memory_pressure.value,
        "disk_pressure": value.disk_pressure.value,
        "heartbeat_at": None
        if value.heartbeat_at is None
        else _time(value.heartbeat_at),
        "checked_at": None if value.checked_at is None else _time(value.checked_at),
        "commit_sha": value.commit_sha,
    }


_SERIALIZERS = {
    Status: _Status,
    Progress: _Progress,
    Issues: _Issues,
    Rules: _Rules,
    Activity: _Activity,
    Diagnostics: _Diagnostics,
}


def serialize_public(envelope: PublicEnvelope) -> dict:
    _record(envelope, PublicEnvelope)
    result = {
        "data": _SERIALIZERS[type(envelope.data)](envelope.data),
        "schema_version": envelope.schema_version,
        "sampled_at": _time(envelope.sampled_at),
        "freshness": envelope.freshness.value,
        "age_seconds": envelope.age_seconds,
        "scope": envelope.scope,
    }
    _encode(
        result,
        maximum=(
            _MAX_RULES_JSON_BYTES
            if type(envelope.data) is Rules
            else _MAX_PUBLIC_JSON_BYTES
        ),
    )
    return result


def _encode(result, *, maximum=_MAX_PUBLIC_JSON_BYTES):
    try:
        encoded = json.dumps(
            result,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (ValueError, TypeError, OverflowError):
        raise OutputBoundaryError() from None
    if len(encoded.encode("ascii")) > maximum:
        raise OutputBoundaryError()
    return encoded


def public_json(envelope: PublicEnvelope) -> str:
    value = serialize_public(envelope)
    return _encode(
        value,
        maximum=(
            _MAX_RULES_JSON_BYTES
            if type(envelope.data) is Rules
            else _MAX_PUBLIC_JSON_BYTES
        ),
    )


def _private_text(value, maximum):
    _exact(value, str)
    _require(bool(value))
    _require(not any(unicodedata.category(c) in {"Cc", "Cs"} for c in value))
    _require(len(value.encode("utf-8")) <= maximum)


@dataclass(frozen=True, slots=True, repr=False)
class PrivateDoctorDetail:
    kind: Literal["binding", "state_root"]
    role: Role | None
    binding_address: str | None
    state_root: str | None

    def __post_init__(self):
        _exact(self, PrivateDoctorDetail)
        _exact(self.kind, str)
        if self.kind == "binding":
            _exact(self.role, Role)
            _require(self.state_root is None)
            _private_text(self.binding_address, 320)
            _require(self.binding_address.count("@") == 1)
            _require(all(self.binding_address.split("@")))
            _require(
                not any(c.isspace() or c in '<>(),;:"\\' for c in self.binding_address)
            )
        elif self.kind == "state_root":
            _require(self.role is None and self.binding_address is None)
            _private_text(self.state_root, 4096)
            _require(self.state_root.startswith("/"))
        else:
            raise OutputBoundaryError()


@dataclass(frozen=True, slots=True, repr=False)
class LocalDoctorFinding:
    component: Component
    role: Role | None
    code: ErrorCode | None
    state: CheckState
    checked_at: Timestamp | None
    detail: PrivateDoctorDetail | None

    def __post_init__(self):
        _exact(self, LocalDoctorFinding)
        _exact(self.component, Component)
        _role_code(self.role, self.code)
        _exact(self.state, CheckState)
        _timestamp(self.checked_at, nullable=True)
        if self.detail is not None:
            _record(self.detail, PrivateDoctorDetail)


@dataclass(frozen=True, slots=True, repr=False)
class AuthRoleFact:
    role: Role
    mode: PermissionMode | None
    binding_state: BindingState | None
    scope_ready: CheckState
    verified_at: Timestamp | None
    expires_at: Timestamp | None
    freshness: Freshness
    error: ErrorCode | None

    def __post_init__(self):
        _exact(self, AuthRoleFact)
        _exact(self.role, Role)
        _role_code(self.role, self.error)
        _exact(self.scope_ready, CheckState)
        _timestamp(self.expires_at, nullable=True)
        RoleStatus(
            self.role, self.mode, self.binding_state, self.verified_at, self.freshness
        )
        if (
            self.binding_state is BindingState.VERIFIED
            and self.freshness is Freshness.FRESH
        ):
            _require(self.error is None and self.scope_ready is CheckState.OK)


def role_status_from_fact(fact: AuthRoleFact) -> RoleStatus:
    _record(fact, AuthRoleFact)
    return RoleStatus(
        fact.role, fact.mode, fact.binding_state, fact.verified_at, fact.freshness
    )


def render_local_doctor(finding: LocalDoctorFinding, *, private_metadata: bool) -> dict:
    _record(finding, LocalDoctorFinding)
    _exact(private_metadata, bool)
    result = {
        "component": finding.component.value,
        "role": None if finding.role is None else finding.role.value,
        "code": None if finding.code is None else finding.code.value,
        "state": finding.state.value,
        "checked_at": None if finding.checked_at is None else _time(finding.checked_at),
    }
    detail = finding.detail
    if private_metadata and detail is not None:
        result["detail"] = {
            "kind": detail.kind,
            "role": None if detail.role is None else detail.role.value,
            "binding_address": detail.binding_address,
            "state_root": detail.state_root,
        }
    return result
