"""Offline inspection of one persisted projection job."""

from __future__ import annotations

from datetime import UTC

from facet.config import ConfigError
from facet.contracts import ErrorCode, JobKind, JobState, LocalId, Priority
from facet.db.codecs import StorageFailure, timestamp_from_sql

from .status import _check_config_artifact, _open_read_only, _paths_and_config


def _time(value: int | None) -> str | None:
    if value is None:
        return None
    return (
        timestamp_from_sql(value)
        .value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def read_queue_job(options) -> dict:
    """Read one job's allowlisted private metadata without taking the writer lock."""

    try:
        job_id = LocalId(options.job_id)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    if not getattr(options, "private_metadata", False):
        raise ConfigError(ErrorCode.SCOPE_REQUIRED)

    paths, raw, config = _paths_and_config(options)
    connection = None
    try:
        connection = _open_read_only(paths.db)
        connection.execute("BEGIN")
        _check_config_artifact(connection, config.projection.id.value, raw)
        row = connection.execute(
            "SELECT job_id,kind,priority,state,attempt_count,last_error_code,"
            "created_at,updated_at,next_attempt_at,source_thread_id FROM sync_jobs "
            "WHERE projection_id=? AND job_id=? LIMIT 2",
            (config.projection.id.value, job_id.value),
        ).fetchall()
        if len(row) != 1:
            raise ConfigError(ErrorCode.OWNER_UNAVAILABLE)
        (
            stored_id,
            kind,
            priority,
            state,
            attempt_count,
            last_error_code,
            created_at,
            updated_at,
            next_attempt_at,
            source_thread_id,
        ) = row[0]
        try:
            typed_kind = JobKind(kind)
            typed_priority = Priority(priority)
            typed_state = JobState(state)
            typed_error = (
                None if last_error_code is None else ErrorCode(last_error_code)
            )
        except (TypeError, ValueError):
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None
        if stored_id != job_id.value or type(attempt_count) is not int:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        connection.execute("COMMIT")
        return {
            "job_id": stored_id,
            "kind": typed_kind.value,
            "priority": typed_priority.value,
            "state": typed_state.value,
            "attempt_count": attempt_count,
            "last_error_code": None if typed_error is None else typed_error.value,
            "created_at": _time(created_at),
            "updated_at": _time(updated_at),
            "next_attempt_at": _time(next_attempt_at),
            "source_thread_id": source_thread_id,
        }
    except BaseException:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()


__all__ = ("read_queue_job",)
