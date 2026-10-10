"""Single-process aggregate Dashboard snapshots.

The collector runs at the sync owner boundary and publishes immutable public
envelopes to an in-memory provider. HTTP requests never receive an owner,
SQLite handle, Gmail service, or private configuration value.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from threading import Lock
from time import monotonic

from facet import __version__
from facet.contracts import (
    BindingState,
    EpochState,
    ErrorCode,
    Freshness,
    JobState,
    PublicHealth,
    PublicPhase,
    Role,
    SourceMode,
    Timestamp,
)
from facet.db.codecs import timestamp_from_sql
from facet.db.repositories import epochs, reads
from facet.db.repositories.base import _decode, _query
from facet.db.repositories.serialization import COLUMNS
from facet.status.errors import catalog_entry
from facet.status.models import (
    Activity,
    ActivityEntry,
    CheckState,
    Diagnostics,
    EpochSummary,
    IssueGroup,
    Issues,
    LatencyMetric,
    PermissionMode,
    Pressure,
    Progress,
    PublicEnvelope,
    QueueCounts,
    RateMetric,
    RoleStatus,
    Rules,
    RuleSummary,
    Status,
)
from facet.status.serialization import serialize_public
from facet.web.server import _unavailable_envelopes


def _now() -> Timestamp:
    return Timestamp(datetime.now(UTC))


def _envelope(data, sampled_at: Timestamp) -> PublicEnvelope:
    return PublicEnvelope(data, 1, sampled_at, Freshness.FRESH, 0, "projection")


def _mode(config, role: Role) -> PermissionMode:
    if role is Role.SOURCE:
        return (
            PermissionMode.SOURCE_READONLY
            if config.projection.source_mode is SourceMode.READONLY
            else PermissionMode.SOURCE_CONVENIENCE
        )
    return PermissionMode.TARGET_INSERT_READONLY


def _latest_epoch(uow, projection_id):
    rows = _query(
        uow,
        "SELECT "
        + ",".join(COLUMNS["epochs"])
        + " FROM epochs WHERE projection_id=? ORDER BY created_at DESC LIMIT 1",
        (projection_id.value,),
        maximum=1,
    )
    return _decode(uow, projection_id, "epochs", rows[0]) if rows else None


def _queue_counts(snapshot) -> QueueCounts:
    values = {item.state: item.count.value for item in snapshot.by_job_state}
    return QueueCounts(*(values.get(state, 0) for state in JobState))


def _epoch_thread_counts(uow, projection_id, epoch_id):
    row = uow._execute(
        "SELECT COUNT(*),SUM(CASE WHEN state='completed' THEN 1 ELSE 0 END) "
        "FROM sync_jobs j JOIN epoch_jobs e ON e.projection_id=j.projection_id "
        "AND e.job_id=j.job_id WHERE j.projection_id=? AND e.epoch_id=? "
        "AND j.kind='expand_thread'",
        (projection_id.value, epoch_id.value),
    ).fetchone()
    return int(row[0]), int(row[1] or 0)


def _issue(code, count, first_at, last_at, retry_at=None):
    entry = catalog_entry(code)
    role = None
    if code in {ErrorCode.SOURCE_AUTH_REQUIRED, ErrorCode.SOURCE_RATE_LIMITED}:
        role = Role.SOURCE
    elif code in {ErrorCode.TARGET_AUTH_REQUIRED, ErrorCode.TARGET_RATE_LIMITED}:
        role = Role.TARGET
    return IssueGroup(
        code,
        entry.error_class,
        role,
        count,
        first_at,
        last_at,
        entry.automatic_dependency_retry,
        retry_at if entry.automatic_dependency_retry else None,
        entry.suggestion,
    )


def _issues(uow, projection_id, sampled_at, error_code) -> Issues:
    rows = _query(
        uow,
        "SELECT last_error_code,COUNT(*),MIN(created_at),MAX(updated_at),"
        "MIN(next_attempt_at) FROM sync_jobs WHERE projection_id=? "
        "AND state IN('retry_wait','blocked','needs_attention','failed',"
        "'source_missing') AND last_error_code IS NOT NULL "
        "GROUP BY last_error_code ORDER BY last_error_code",
        (projection_id.value,),
        maximum=96,
    )
    groups = {
        ErrorCode(code): _issue(
            ErrorCode(code),
            count,
            timestamp_from_sql(first_at),
            timestamp_from_sql(last_at),
            timestamp_from_sql(retry_at) if retry_at is not None else None,
        )
        for code, count, first_at, last_at, retry_at in rows
    }
    # Discovery currently retains only a partition-level attention fact, not
    # an authentication diagnosis. Never invent a more specific cause here.
    partitions = uow._execute(
        "SELECT COUNT(*) FROM epoch_partitions WHERE projection_id=? "
        "AND state='needs_attention'",
        (projection_id.value,),
    ).fetchone()[0]
    if partitions:
        code = ErrorCode.MAINTENANCE_REQUIRED
        previous = groups.get(code)
        groups[code] = _issue(
            code,
            partitions + (previous.count if previous else 0),
            previous.first_at if previous else sampled_at,
            sampled_at,
        )
    if error_code is not None and error_code not in groups:
        groups[error_code] = _issue(error_code, 1, sampled_at, sampled_at)
    return Issues(tuple(groups[code] for code in sorted(groups)))


def _activity(uow, projection_id) -> Activity:
    """Return first-verification batches attributed to their admission rule."""

    rows = uow._execute(
        "SELECT CASE WHEN r.kind IN('allow_sender','allow_domain') THEN r.kind "
        "ELSE 'other' END, "
        "CASE WHEN r.kind IN('allow_sender','allow_domain') THEN r.normalized_value "
        "ELSE 'Other authorized thread' END, COUNT(*), MAX(h.verified_at) "
        "FROM mapping_history h "
        "JOIN insert_attempts i ON i.projection_id=h.projection_id "
        "AND i.attempt_id=h.attempt_id "
        "LEFT JOIN thread_admissions a ON a.projection_id=i.projection_id "
        "AND a.source_thread_id=i.source_thread_id AND a.generation=i.generation "
        "LEFT JOIN rules r ON r.projection_id=a.projection_id AND r.rule_id=a.rule_id "
        "WHERE h.projection_id=? AND h.mapping_revision=1 "
        "GROUP BY CASE WHEN r.kind IN('allow_sender','allow_domain') THEN r.kind "
        "ELSE 'other' END, CASE WHEN r.kind IN('allow_sender','allow_domain') "
        "THEN r.normalized_value ELSE 'Other authorized thread' END, "
        "(h.verified_at / 60000000) "
        "ORDER BY MAX(h.verified_at) DESC,1 DESC,2 DESC "
        "LIMIT 100",
        (projection_id.value,),
    ).fetchall()
    entries = tuple(
        ActivityEntry(str(kind), str(value), int(count), timestamp_from_sql(observed))
        for kind, value, count, observed in rows
    )
    return Activity(entries)


def _resource_pressure(available, total) -> Pressure:
    if not isinstance(available, int) or not isinstance(total, int) or total <= 0:
        return Pressure.UNKNOWN
    ratio = available / total
    if ratio < 0.05:
        return Pressure.CRITICAL
    if ratio < 0.15:
        return Pressure.ELEVATED
    return Pressure.NORMAL


def _memory_pressure() -> Pressure:
    try:
        with open("/sys/fs/cgroup/memory.max", encoding="ascii") as limit_stream:
            limit = limit_stream.read().strip()
        with open("/sys/fs/cgroup/memory.current", encoding="ascii") as current_stream:
            current = int(current_stream.read().strip())
        if limit != "max":
            maximum = int(limit)
            if maximum > 0:
                return _resource_pressure(maximum - current, maximum)
    except (OSError, ValueError):
        pass
    try:
        values = {}
        with open("/proc/meminfo", encoding="ascii") as stream:
            for line in stream:
                key, separator, value = line.partition(":")
                if separator and key in {"MemTotal", "MemAvailable"}:
                    values[key] = int(value.strip().split()[0]) * 1024
        return _resource_pressure(values.get("MemAvailable"), values.get("MemTotal"))
    except (OSError, ValueError, IndexError):
        return Pressure.UNKNOWN


def _disk_pressure(owner) -> Pressure:
    try:
        usage = shutil.disk_usage(owner._state_dir)
        return _resource_pressure(usage.free, usage.total)
    except OSError:
        return Pressure.UNKNOWN


def _commit_sha() -> str | None:
    candidate = os.environ.get("FACET_COMMIT_SHA", "").strip().lower()
    return candidate if re.fullmatch(r"[0-9a-f]{40}", candidate) else None


def _scope_state(uow, projection_id, binding, config, role) -> CheckState:
    if binding is None:
        return CheckState.UNKNOWN
    if binding.state in {BindingState.AUTH_REQUIRED, BindingState.MISMATCH}:
        return CheckState.FAILED
    if binding.state is not BindingState.VERIFIED:
        return CheckState.UNKNOWN
    expected = (
        "source_readonly"
        if role is Role.SOURCE and config.projection.source_mode is SourceMode.READONLY
        else "source_convenience"
        if role is Role.SOURCE
        else "target_default"
    )
    row = uow._execute(
        "SELECT 1 FROM credential_changes WHERE projection_id=? AND role=? "
        "AND phase='committed' AND new_revision=? AND binding_revision=? "
        "AND scope_policy=? ORDER BY updated_at DESC LIMIT 1",
        (
            projection_id.value,
            role.value,
            binding.credential_revision.value,
            binding.binding_revision.value,
            expected,
        ),
    ).fetchone()
    return CheckState.OK if row is not None else CheckState.UNKNOWN


def _phase(projection, epoch) -> PublicPhase:
    if projection.restore_state.value != "normal":
        return PublicPhase.MAINTENANCE
    if projection.daemon_paused:
        return PublicPhase.PAUSED
    if epoch is None:
        return PublicPhase.INITIALIZING
    if epoch.state is EpochState.PAUSED:
        return PublicPhase.PAUSED
    if epoch.state in {
        EpochState.PREPARED,
        EpochState.SCANNING,
        EpochState.CATCHING_UP,
    }:
        return PublicPhase.BACKFILL
    if epoch.state is EpochState.NEEDS_ATTENTION:
        return PublicPhase.RECOVERING
    return PublicPhase.INCREMENTAL


def _health(projection, bindings, epoch, counts, issues) -> PublicHealth:
    if projection.restore_state.value != "normal" or projection.daemon_paused:
        return PublicHealth.BLOCKED
    if any(
        binding is None or binding.state is not BindingState.VERIFIED
        for binding in bindings
    ):
        return PublicHealth.BLOCKED
    if epoch is None:
        return PublicHealth.BLOCKED
    if epoch.state in {EpochState.NEEDS_ATTENTION, EpochState.COMPLETED_WITH_ISSUES}:
        return PublicHealth.DEGRADED
    if counts.unresolved_attempts.value or any(
        item.count.value
        for item in counts.by_job_state
        if item.state
        in {
            JobState.NEEDS_ATTENTION,
            JobState.FAILED,
            JobState.SOURCE_MISSING,
            JobState.BLOCKED,
            JobState.RETRY_WAIT,
        }
    ):
        return PublicHealth.DEGRADED
    if issues.groups:
        return PublicHealth.DEGRADED
    return PublicHealth.HEALTHY


def snapshot_from_owner(
    owner,
    config,
    *,
    error_code: ErrorCode | None = None,
    cycle_verified=False,
    cycle_in_progress=False,
):
    """Build all five public envelopes from one short private DB snapshot."""

    sampled_at = _now()
    with owner.session.transaction() as uow:
        projection = reads.get_projection(uow, owner.projection_id)
        bindings = tuple(
            reads.get_binding(uow, owner.projection_id, role) for role in Role
        )
        epoch = _latest_epoch(uow, owner.projection_id)
        counts = reads.counts(uow, owner.projection_id, None)
        epoch_counts = reads.counts(
            uow, owner.projection_id, epoch.epoch_id if epoch else None
        )
        discovered_threads, completed_threads = (
            _epoch_thread_counts(uow, owner.projection_id, epoch.epoch_id)
            if epoch is not None
            else (None, None)
        )
        issues = _issues(uow, owner.projection_id, sampled_at, error_code)
        activity = _activity(uow, owner.projection_id)
        rule_rows = uow._execute(
            "SELECT r.kind,r.normalized_value,rr.enabled FROM rules r "
            "JOIN rule_revisions rr ON rr.projection_id=r.projection_id "
            "AND rr.rule_id=r.rule_id AND rr.revision=r.current_revision "
            "WHERE r.projection_id=? ORDER BY r.kind,r.normalized_value",
            (owner.projection_id.value,),
        ).fetchall()
        schema_version = int(uow._execute("PRAGMA user_version").fetchone()[0])
        label_rows = (
            uow._execute(
                "SELECT action_kind,label_name FROM action_label_mappings "
                "WHERE projection_id=? AND label_name IS NOT NULL ORDER BY action_kind",
                (owner.projection_id.value,),
            ).fetchall()
            if schema_version >= 3
            else ()
        )
        rule_entries = [
            RuleSummary(str(kind), str(value), bool(enabled))
            for kind, value, enabled in rule_rows
        ]
        rule_entries.extend(
            RuleSummary(f"action_label_{kind}", str(name), True)
            for kind, name in label_rows
        )
        rule_entries.sort(key=lambda entry: (entry.kind, entry.value))
        rules = Rules(tuple(rule_entries))
        unresolved_gap = epochs._latest_unresolved_gap(uow, owner.projection_id)
        last_poll = uow._execute(
            "SELECT MAX(finished_at) FROM history_polls WHERE projection_id=? "
            "AND state='completed'",
            (owner.projection_id.value,),
        ).fetchone()[0]
        last_insert = uow._execute(
            "SELECT MAX(verified_at) FROM message_mappings WHERE projection_id=?",
            (owner.projection_id.value,),
        ).fetchone()[0]
        schema_row = uow._execute(
            "SELECT schema_version FROM schema_metadata LIMIT 1"
        ).fetchone()
        try:
            db_writable = (
                CheckState.OK
                if uow._execute("PRAGMA query_only").fetchone()[0] == 0
                else CheckState.FAILED
            )
        except Exception:
            db_writable = CheckState.UNKNOWN
        source_scope = _scope_state(
            uow, owner.projection_id, bindings[0], config, Role.SOURCE
        )
        target_scope = _scope_state(
            uow, owner.projection_id, bindings[1], config, Role.TARGET
        )

    if projection is None:
        raise ValueError("owner_unavailable")
    health = _health(projection, bindings, epoch, counts, issues)
    if error_code is not None:
        health = (
            PublicHealth.BLOCKED
            if error_code
            in {
                ErrorCode.BINDING_PENDING,
                ErrorCode.BINDING_MISMATCH,
                ErrorCode.SOURCE_AUTH_REQUIRED,
                ErrorCode.TARGET_AUTH_REQUIRED,
            }
            else PublicHealth.DEGRADED
        )
    if health is PublicHealth.HEALTHY and not cycle_verified:
        health = PublicHealth.UNKNOWN
    phase = _phase(projection, epoch)
    if unresolved_gap is not None:
        phase = PublicPhase.RECOVERING
        if health not in {PublicHealth.BLOCKED, PublicHealth.DEGRADED}:
            health = PublicHealth.DEGRADED
    role_status = tuple(
        RoleStatus(
            role,
            _mode(config, role),
            binding.state if binding else None,
            binding.verified_at if binding else None,
            (
                Freshness.FRESH
                if binding is not None and binding.state is BindingState.VERIFIED
                else Freshness.STALE
            ),
        )
        for role, binding in zip(Role, bindings, strict=True)
    )
    status = Status(
        phase,
        health,
        role_status[0],
        role_status[1],
        timestamp_from_sql(last_poll) if last_poll is not None else None,
        timestamp_from_sql(last_insert) if last_insert is not None else None,
        sampled_at,
        cycle_in_progress,
    )
    queue = _queue_counts(counts)
    progress = Progress(
        None
        if epoch is None
        else EpochSummary(epoch.kind, epoch.state, epoch.created_at),
        epoch_counts.discovery_complete,
        None,
        discovered_threads,
        completed_threads,
        epoch_counts.known_total.value
        if epoch_counts.discovery_complete and epoch_counts.known_total is not None
        else None,
        counts.confirmed_mappings.value,
        queue,
        None,
        None,
        None,
        RateMetric(None, "messages_per_second", 60, 0),
        LatencyMetric(None, None, "milliseconds", 60, 0),
    )
    diagnostics = Diagnostics(
        __version__,
        int(schema_row[0]) if schema_row is not None else None,
        1,
        CheckState.OK,
        db_writable,
        config.projection.source_mode,
        source_scope,
        target_scope,
        _memory_pressure(),
        _disk_pressure(owner),
        sampled_at,
        sampled_at,
        _commit_sha(),
    )
    return {
        "status": _envelope(status, sampled_at),
        "progress": _envelope(progress, sampled_at),
        "issues": _envelope(issues, sampled_at),
        "rules": _envelope(rules, sampled_at),
        "activity": _envelope(activity, sampled_at),
        "diagnostics": _envelope(diagnostics, sampled_at),
    }


class LiveSnapshotProvider:
    """Thread-safe in-memory provider consumed by the read-only HTTP server."""

    def __init__(self, *, stale_after=30.0):
        self._lock = Lock()
        self._snapshots = _unavailable_envelopes()
        self._ready = False
        self._published_at = monotonic()
        self._stale_after = stale_after

    def publish(self, snapshots) -> None:
        if type(snapshots) is not dict or set(snapshots) != set(self._snapshots):
            raise ValueError("invalid_input")
        for family, envelope in snapshots.items():
            if type(envelope.data) is not type(self._snapshots[family].data):
                raise ValueError("invalid_input")
            serialize_public(envelope)
        with self._lock:
            self._snapshots = dict(snapshots)
            self._ready = True
            self._published_at = monotonic()

    def publish_from_owner(self, owner, config, **kwargs) -> None:
        self.publish(snapshot_from_owner(owner, config, **kwargs))

    def invalidate(self):
        with self._lock:
            self._ready = False

    def snapshot(self, family: str) -> PublicEnvelope:
        with self._lock:
            envelope = self._snapshots[family]
            if envelope.freshness is Freshness.UNAVAILABLE:
                return envelope
            age = max(0, int(monotonic() - self._published_at))
            stale = not self._ready or age >= self._stale_after
            freshness = Freshness.STALE if stale else Freshness.FRESH
            data = envelope.data
            if stale and type(data) is Status:
                data = replace(
                    data,
                    health=PublicHealth.UNKNOWN,
                    source=replace(data.source, freshness=Freshness.STALE),
                    target=replace(data.target, freshness=Freshness.STALE),
                )
            return replace(envelope, data=data, freshness=freshness, age_seconds=age)

    def ready(self) -> bool:
        with self._lock:
            return self._ready and monotonic() - self._published_at < self._stale_after


__all__ = ("LiveSnapshotProvider", "snapshot_from_owner")
