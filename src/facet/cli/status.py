"""Offline aggregate status and doctor reads.

This module deliberately uses the same closed public DTOs as the Dashboard.
It only opens the managed SQLite database read-only, never takes the sync-owner
lease, refreshes OAuth, contacts Gmail, or returns private configuration.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from facet import __version__
from facet.config import ConfigError, load_config
from facet.contracts import (
    BindingState,
    EpochKind,
    EpochState,
    ErrorCode,
    Freshness,
    ProjectionId,
    PublicHealth,
    PublicPhase,
    Role,
    SourceMode,
    Timestamp,
)
from facet.db.codecs import StorageFailure, timestamp_from_sql
from facet.db.schema import _inspect
from facet.private_paths import inspect_state_root, read_managed_config, select_paths
from facet.status.errors import catalog_entry
from facet.status.models import (
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
    Status,
)
from facet.status.serialization import serialize_public

_JOB_STATES = (
    "queued",
    "claimed",
    "retry_wait",
    "blocked",
    "needs_attention",
    "completed",
    "cancelled",
    "source_missing",
    "failed",
)
_ISSUE_STATES = ("retry_wait", "blocked", "needs_attention", "failed", "source_missing")
_ERROR_CODES = frozenset(value.value for value in ErrorCode)


@dataclass(frozen=True, slots=True)
class StatusResult:
    """Internal result which keeps a doctor failure out of public data."""

    data: dict
    code: ErrorCode | None = None


def _now() -> Timestamp:
    return Timestamp(datetime.now(UTC))


def _time(value: int | None) -> Timestamp | None:
    if value is None:
        return None
    return timestamp_from_sql(value)


def _owner_only(path: Path, *, directory: bool = False, required: bool = True) -> None:
    """Validate a local state artifact without following symlinks."""

    try:
        info = path.lstat()
    except FileNotFoundError:
        if required:
            raise ConfigError(ErrorCode.OWNER_UNAVAILABLE) from None
        return
    except OSError:
        raise ConfigError(ErrorCode.OWNER_UNAVAILABLE) from None
    if (
        info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o77
        or (directory and not stat.S_ISDIR(info.st_mode))
        or (not directory and not stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise ConfigError(ErrorCode.SCOPE_REQUIRED)


def _check_private_artifacts(paths) -> None:
    _owner_only(paths.root, directory=True)
    _owner_only(paths.config)
    _owner_only(paths.db)
    _owner_only(paths.credentials, directory=True)
    # SQLite may create these coordination files while taking a read snapshot.
    # They are never copied, checkpointed, or treated as Facet business state.
    _owner_only(paths.db.with_name(paths.db.name + "-wal"), required=False)
    _owner_only(paths.db.with_name(paths.db.name + "-shm"), required=False)


def _open_read_only(path: Path) -> sqlite3.Connection:
    connection = None
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro", uri=True, autocommit=True
        )
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
        if connection.execute("PRAGMA query_only").fetchone() != (1,):
            raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE)
        if connection.execute("PRAGMA trusted_schema").fetchone() != (0,):
            raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE)
        if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
            raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE)
        if connection.execute("PRAGMA journal_mode").fetchone() != ("wal",):
            raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE)
        _inspect(connection)
        return connection
    except StorageFailure:
        if connection is not None:
            connection.close()
        raise
    except (OSError, sqlite3.Error):
        if connection is not None:
            connection.close()
        raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE) from None


def _check_config_artifact(
    connection: sqlite3.Connection, projection_id: str, raw: bytes
) -> None:
    try:
        rows = connection.execute(
            "SELECT b.config_artifact_digest "
            "FROM operation_bootstrap b "
            "JOIN operations o ON o.projection_id=b.projection_id "
            "AND o.operation_id=b.operation_id "
            "WHERE b.projection_id=? AND o.command=? AND o.state=? LIMIT 2",
            (projection_id, "facet_init", "completed"),
        ).fetchall()
    except sqlite3.Error:
        raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE) from None
    if len(rows) != 1:
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
    if rows[0][0] != hashlib.sha256(raw).hexdigest():
        raise StorageFailure(ErrorCode.REQUEST_CONFLICT)


def _counts(connection: sqlite3.Connection, projection_id: str) -> dict[str, int]:
    values = dict.fromkeys(_JOB_STATES, 0)
    rows = connection.execute(
        "SELECT state,COUNT(*) FROM sync_jobs WHERE projection_id=? GROUP BY state",
        (projection_id,),
    ).fetchall()
    for state, count in rows:
        if state not in values:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        values[state] = int(count)
    return values


def _issues(connection: sqlite3.Connection, projection_id: str) -> list[dict]:
    placeholders = ",".join("?" for _ in _ISSUE_STATES)
    rows = connection.execute(
        "SELECT last_error_code,COUNT(*),MIN(created_at),MAX(updated_at),"
        "MIN(next_attempt_at) FROM sync_jobs WHERE projection_id=? AND state IN("
        f"{placeholders}) AND last_error_code IS NOT NULL GROUP BY last_error_code "
        "ORDER BY last_error_code",
        (projection_id, *_ISSUE_STATES),
    ).fetchall()
    result = []
    for code, count, first_at, last_at, retry_at in rows:
        if code not in _ERROR_CODES:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        result.append(
            {
                "code": ErrorCode(code),
                "count": int(count),
                "first_at": timestamp_from_sql(first_at),
                "last_at": timestamp_from_sql(last_at),
                "retry_at": timestamp_from_sql(retry_at)
                if retry_at is not None
                else None,
            }
        )
    partitions = connection.execute(
        "SELECT COUNT(*) FROM epoch_partitions WHERE projection_id=? "
        "AND state='needs_attention'",
        (projection_id,),
    ).fetchone()[0]
    if partitions:
        now = _now()
        result.append(
            {
                "code": ErrorCode.MAINTENANCE_REQUIRED,
                "count": int(partitions),
                "first_at": now,
                "last_at": now,
                "retry_at": None,
            }
        )
    return result


def _check_addresses(
    connection: sqlite3.Connection, config, projection_id: str
) -> None:
    rows = connection.execute(
        "SELECT role,declared_address,verified_address FROM bindings "
        "WHERE projection_id=?",
        (projection_id,),
    ).fetchall()
    expected = {
        Role.SOURCE.value: config.projection.source_email,
        Role.TARGET.value: config.projection.target_email,
    }
    if {role for role, _, _ in rows} != set(expected):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    for role, address, verified_address in rows:
        if type(address) is not str or address.casefold() != expected[role].casefold():
            raise StorageFailure(ErrorCode.BINDING_MISMATCH)
        if verified_address is not None and (
            type(verified_address) is not str
            or verified_address.casefold() != expected[role].casefold()
        ):
            raise StorageFailure(ErrorCode.BINDING_MISMATCH)


def _read_snapshot(
    connection: sqlite3.Connection, config, sampled_at: Timestamp
) -> dict:
    projection_id = config.projection.id.value
    _check_addresses(connection, config, projection_id)
    projection = connection.execute(
        "SELECT source_mode,binding_state,restore_state,daemon_paused "
        "FROM projections WHERE projection_id=? LIMIT 2",
        (projection_id,),
    ).fetchall()
    if len(projection) != 1:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    source_mode, projection_binding_state, restore_state, paused = projection[0]
    binding_rows = connection.execute(
        "SELECT role,state,verified_at FROM bindings WHERE projection_id=?",
        (projection_id,),
    ).fetchall()
    bindings = {role: (state, verified_at) for role, state, verified_at in binding_rows}
    if set(bindings) != {Role.SOURCE.value, Role.TARGET.value}:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    epoch_rows = connection.execute(
        "SELECT epoch_id,kind,state,created_at,discovery_complete,known_message_total "
        "FROM epochs WHERE projection_id=? ORDER BY created_at DESC LIMIT 1",
        (projection_id,),
    ).fetchall()
    epoch = epoch_rows[0] if epoch_rows else None
    counts = _counts(connection, projection_id)
    mappings = connection.execute(
        "SELECT COUNT(*) FROM message_mappings WHERE projection_id=?",
        (projection_id,),
    ).fetchone()[0]
    last_poll = connection.execute(
        "SELECT MAX(finished_at) FROM history_polls WHERE projection_id=? "
        "AND state='completed'",
        (projection_id,),
    ).fetchone()[0]
    last_insert = connection.execute(
        "SELECT MAX(verified_at) FROM message_mappings WHERE projection_id=?",
        (projection_id,),
    ).fetchone()[0]
    schema_row = connection.execute(
        "SELECT schema_version FROM schema_metadata LIMIT 1"
    ).fetchone()
    epoch_counts = (None, None)
    if epoch is not None:
        epoch_counts = connection.execute(
            "SELECT COUNT(*),SUM(CASE WHEN j.state='completed' THEN 1 ELSE 0 END) "
            "FROM sync_jobs j JOIN epoch_jobs e ON e.projection_id=j.projection_id "
            "AND e.job_id=j.job_id WHERE j.projection_id=? AND e.epoch_id=? "
            "AND j.kind='expand_thread'",
            (projection_id, epoch[0]),
        ).fetchone()
        epoch_counts = (int(epoch_counts[0]), int(epoch_counts[1] or 0))
    issues = _issues(connection, projection_id)
    from facet.db.repositories.epochs import unresolved_gap_query

    unresolved_gap = connection.execute(
        unresolved_gap_query(), (projection_id,) * 3
    ).fetchone()
    ready_bindings = all(
        state == BindingState.VERIFIED.value for state, _ in bindings.values()
    )
    if source_mode != config.projection.source_mode.value:
        raise StorageFailure(ErrorCode.BINDING_MISMATCH)
    if (projection_binding_state == BindingState.VERIFIED.value) != ready_bindings:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)

    if (
        restore_state != "normal"
        or paused
        or (epoch is not None and epoch[2] == EpochState.PAUSED.value)
        or not ready_bindings
        or epoch is None
    ):
        health = PublicHealth.BLOCKED
    elif (
        unresolved_gap is not None
        or epoch[2]
        in {
            EpochState.NEEDS_ATTENTION.value,
            EpochState.COMPLETED_WITH_ISSUES.value,
        }
        or issues
    ):
        health = PublicHealth.DEGRADED
    else:
        # An offline read has no live-cycle heartbeat. Never present a clean
        # database snapshot as current/healthy.
        health = PublicHealth.UNKNOWN

    if restore_state != "normal":
        phase = PublicPhase.MAINTENANCE
    elif unresolved_gap is not None:
        phase = PublicPhase.RECOVERING
    elif paused or (epoch is not None and epoch[2] == EpochState.PAUSED.value):
        phase = PublicPhase.PAUSED
    elif epoch is None:
        phase = PublicPhase.INITIALIZING
    elif epoch[2] in {
        EpochState.PREPARED.value,
        EpochState.SCANNING.value,
        EpochState.CATCHING_UP.value,
    }:
        phase = PublicPhase.BACKFILL
    elif epoch[2] == EpochState.NEEDS_ATTENTION.value:
        phase = PublicPhase.RECOVERING
    else:
        phase = PublicPhase.INCREMENTAL

    source_status = RoleStatus(
        Role.SOURCE,
        PermissionMode.SOURCE_READONLY
        if config.projection.source_mode is SourceMode.READONLY
        else PermissionMode.SOURCE_CONVENIENCE,
        BindingState(bindings[Role.SOURCE.value][0]),
        _time(bindings[Role.SOURCE.value][1]),
        Freshness.STALE,
    )
    target_status = RoleStatus(
        Role.TARGET,
        PermissionMode.TARGET_INSERT_READONLY,
        BindingState(bindings[Role.TARGET.value][0]),
        _time(bindings[Role.TARGET.value][1]),
        Freshness.STALE,
    )
    status = Status(
        phase,
        health,
        source_status,
        target_status,
        _time(last_poll),
        _time(last_insert),
        None,
    )
    jobs = QueueCounts(*(counts[state] for state in _JOB_STATES))
    progress = Progress(
        None
        if epoch is None
        else EpochSummary(
            EpochKind(epoch[1]), EpochState(epoch[2]), timestamp_from_sql(epoch[3])
        ),
        bool(epoch[4]) if epoch is not None else False,
        None,
        epoch_counts[0],
        epoch_counts[1],
        int(epoch[5])
        if epoch is not None and epoch[4] and epoch[5] is not None
        else None,
        int(mappings),
        jobs,
        None,
        None,
        None,
        RateMetric(None, "messages_per_second", 60, 0),
        LatencyMetric(None, None, "milliseconds", 60, 0),
    )
    groups = []
    for item in issues:
        entry = catalog_entry(item["code"])
        role = None
        if item["code"] in {
            ErrorCode.SOURCE_AUTH_REQUIRED,
            ErrorCode.SOURCE_RATE_LIMITED,
        }:
            role = Role.SOURCE
        elif item["code"] in {
            ErrorCode.TARGET_AUTH_REQUIRED,
            ErrorCode.TARGET_RATE_LIMITED,
        }:
            role = Role.TARGET
        groups.append(
            IssueGroup(
                item["code"],
                entry.error_class,
                role,
                item["count"],
                item["first_at"],
                item["last_at"],
                entry.automatic_dependency_retry,
                item["retry_at"] if entry.automatic_dependency_retry else None,
                entry.suggestion,
            )
        )
    groups.sort(
        key=lambda value: (
            value.code.value,
            {None: 0, Role.SOURCE: 1, Role.TARGET: 2}[value.role],
        )
    )
    diagnostics = Diagnostics(
        __version__,
        int(schema_row[0]) if schema_row is not None else None,
        None,
        CheckState.OK,
        CheckState.UNKNOWN,
        config.projection.source_mode,
        CheckState.UNKNOWN,
        CheckState.UNKNOWN,
        Pressure.UNKNOWN,
        Pressure.UNKNOWN,
        None,
        sampled_at,
    )
    freshness = Freshness.STALE
    return {
        "status": serialize_public(
            PublicEnvelope(status, 1, sampled_at, freshness, 0, "projection")
        ),
        "progress": serialize_public(
            PublicEnvelope(progress, 1, sampled_at, freshness, 0, "projection")
        ),
        "issues": serialize_public(
            PublicEnvelope(
                Issues(tuple(groups)), 1, sampled_at, freshness, 0, "projection"
            )
        ),
        "diagnostics": serialize_public(
            PublicEnvelope(diagnostics, 1, sampled_at, freshness, 0, "projection")
        ),
    }


def _paths_and_config(options):
    paths = select_paths(getattr(options, "state_dir", None), None)
    if getattr(options, "config_path", None) is not None:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    if not inspect_state_root(paths.root):
        raise ConfigError(ErrorCode.OWNER_UNAVAILABLE)
    _check_private_artifacts(paths)
    raw = read_managed_config(paths)
    try:
        config = load_config(raw)
    except (ConfigError, TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    selector = getattr(options, "projection", None)
    if selector is not None:
        try:
            if ProjectionId(selector) != config.projection.id:
                raise ConfigError(ErrorCode.BINDING_MISMATCH)
        except ValueError:
            raise ConfigError(ErrorCode.INVALID_INPUT) from None
    return paths, raw, config


def read_status(options, *, doctor: bool = False) -> StatusResult:
    paths, raw, config = _paths_and_config(options)
    connection = None
    sampled_at = _now()
    try:
        connection = _open_read_only(paths.db)
        # Every state read, including the config digest and private role
        # consistency check, belongs to one deferred snapshot transaction.
        connection.execute("BEGIN")
        _check_config_artifact(connection, config.projection.id.value, raw)
        data = _read_snapshot(connection, config, sampled_at)
        connection.execute("COMMIT")
    except BaseException:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()
    if not doctor:
        return StatusResult(data)

    status_data = data["status"]["data"]
    source_ready = status_data["source"]["auth_state"] == BindingState.VERIFIED.value
    target_ready = status_data["target"]["auth_state"] == BindingState.VERIFIED.value
    projection_ok = status_data["health"] not in {
        PublicHealth.BLOCKED.value,
        PublicHealth.DEGRADED.value,
    }
    checks = [
        {"name": "config_artifact", "state": "ok", "code": None},
        {"name": "database", "state": "ok", "code": None},
        {
            "name": "bindings",
            "state": "ok" if source_ready and target_ready else "attention",
            "code": None
            if source_ready and target_ready
            else ErrorCode.BINDING_PENDING.value,
        },
        {
            "name": "projection",
            "state": "ok" if projection_ok else "attention",
            "code": None
            if projection_ok
            else (
                ErrorCode.MAINTENANCE_REQUIRED.value
                if status_data["phase"]
                in {
                    PublicPhase.INITIALIZING.value,
                    PublicPhase.PAUSED.value,
                    PublicPhase.MAINTENANCE.value,
                }
                else (
                    data["issues"]["data"]["groups"][0]["code"]
                    if data["issues"]["data"]["groups"]
                    else ErrorCode.CONSISTENCY_FAILURE.value
                )
            ),
        },
    ]
    code = None
    for check in checks:
        if check["code"] is not None:
            code = ErrorCode(check["code"])
            break
    return StatusResult(
        {
            "summary": data,
            "checks": checks,
            "version": __version__,
        },
        code,
    )


__all__ = ("StatusResult", "read_status")
