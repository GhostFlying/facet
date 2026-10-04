"""Offline aggregate status and doctor reads.

This module intentionally opens the managed database read-only.  It does not
take the sync owner lease, import a Gmail adapter, refresh credentials, or
return identifiers and private configuration values.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from facet import __version__
from facet.config import ConfigError, load_config
from facet.contracts import ErrorCode, Role
from facet.db.codecs import StorageFailure, timestamp_from_sql
from facet.db.schema import _inspect
from facet.private_paths import inspect_state_root, read_managed_config, select_paths

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


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _time(value: int | None) -> str | None:
    if value is None:
        return None
    return (
        timestamp_from_sql(value)
        .value.isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _open_read_only(path: Path) -> sqlite3.Connection:
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
        raise
    except (OSError, sqlite3.Error):
        raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE) from None


def _check_config_artifact(
    connection: sqlite3.Connection, projection_id: str, raw: bytes
):
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
        "SELECT last_error_code,COUNT(*),MIN(created_at),MAX(updated_at) "
        f"FROM sync_jobs WHERE projection_id=? AND state IN({placeholders}) "
        "AND last_error_code IS NOT NULL GROUP BY last_error_code "
        "ORDER BY last_error_code",
        (projection_id, *_ISSUE_STATES),
    ).fetchall()
    result = []
    for code, count, first_at, last_at in rows:
        if code not in _ERROR_CODES:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        result.append(
            {
                "code": code,
                "count": int(count),
                "first_at": _time(first_at),
                "last_at": _time(last_at),
            }
        )
    partitions = connection.execute(
        "SELECT COUNT(*) FROM epoch_partitions WHERE projection_id=? "
        "AND state='needs_attention'",
        (projection_id,),
    ).fetchone()[0]
    if partitions:
        result.append(
            {
                "code": ErrorCode.MAINTENANCE_REQUIRED.value,
                "count": int(partitions),
                "first_at": None,
                "last_at": None,
            }
        )
    return result


def _read_snapshot(connection: sqlite3.Connection, config) -> dict:
    projection_id = config.projection.id.value
    projection = connection.execute(
        "SELECT source_mode,binding_state,restore_state,daemon_paused "
        "FROM projections WHERE projection_id=? LIMIT 2",
        (projection_id,),
    ).fetchall()
    if len(projection) != 1:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    source_mode, binding_state, restore_state, paused = projection[0]
    binding_rows = connection.execute(
        "SELECT role,state,verified_at FROM bindings WHERE projection_id=?",
        (projection_id,),
    ).fetchall()
    bindings = {role: (state, verified_at) for role, state, verified_at in binding_rows}
    if set(bindings) != {Role.SOURCE.value, Role.TARGET.value}:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    epoch_rows = connection.execute(
        "SELECT kind,state,created_at,discovery_complete,known_message_total "
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
    issues = _issues(connection, projection_id)

    ready_bindings = all(bindings[role][0] == "verified" for role in bindings)
    if restore_state != "normal":
        health, phase = "blocked", "maintenance"
    elif paused:
        health, phase = "blocked", "paused"
    elif not ready_bindings or epoch is None:
        health, phase = "blocked", "initializing"
    elif epoch[1] in {"needs_attention", "completed_with_issues"} or issues:
        health, phase = (
            "degraded",
            "recovering" if epoch[1] == "needs_attention" else "incremental",
        )
    elif epoch[1] in {"prepared", "scanning", "catching_up"}:
        health, phase = "unknown", "backfill"
    else:
        health, phase = "healthy", "incremental"

    return {
        "sampled_at": _now(),
        "phase": phase,
        "health": health,
        "source_mode": source_mode,
        "binding_states": {
            role: {
                "state": values[0],
                "last_verified_at": _time(values[1]),
            }
            for role, values in sorted(bindings.items())
        },
        "epoch": None
        if epoch is None
        else {
            "kind": epoch[0],
            "state": epoch[1],
            "started_at": _time(epoch[2]),
            "discovery_complete": bool(epoch[3]),
            "known_message_total": epoch[4],
        },
        "confirmed_mappings": int(mappings),
        "queue": counts,
        "issues": issues,
        "last_history_poll_at": _time(last_poll),
        "last_verified_insert_at": _time(last_insert),
    }


def _paths_and_config(options):
    paths = select_paths(getattr(options, "state_dir", None), None)
    if getattr(options, "config_path", None) is not None:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    if not inspect_state_root(paths.root):
        raise ConfigError(ErrorCode.OWNER_UNAVAILABLE)
    raw = read_managed_config(paths)
    try:
        config = load_config(raw)
    except (ConfigError, TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    return paths, raw, config


def read_status(options, *, doctor: bool = False) -> dict:
    paths, raw, config = _paths_and_config(options)
    connection = None
    checked_at = _now()
    try:
        connection = _open_read_only(paths.db)
        _check_config_artifact(connection, config.projection.id.value, raw)
        snapshot = _read_snapshot(connection, config)
    finally:
        if connection is not None:
            connection.close()
    if not doctor:
        return snapshot
    checks = [
        {"name": "config_artifact", "state": "ok", "code": None},
        {"name": "database", "state": "ok", "code": None},
        {
            "name": "bindings",
            "state": "ok"
            if all(
                item["state"] == "verified"
                for item in snapshot["binding_states"].values()
            )
            else "attention",
            "code": None
            if all(
                item["state"] == "verified"
                for item in snapshot["binding_states"].values()
            )
            else ErrorCode.BINDING_PENDING.value,
        },
        {
            "name": "projection",
            "state": "ok" if snapshot["health"] == "healthy" else "attention",
            "code": None if snapshot["health"] == "healthy" else snapshot["health"],
        },
    ]
    return {
        "checked_at": checked_at,
        "summary": snapshot,
        "checks": checks,
        "version": __version__,
    }


__all__ = ("read_status",)
