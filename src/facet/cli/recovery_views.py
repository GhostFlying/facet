"""Owner-scoped inspection of uncertain insert outcomes.

These commands deliberately gather evidence only.  They never claim an
unknown Gmail insert, enqueue a replacement insert, or mutate the local
database.  Recovery execution remains an explicitly authorized operation.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC

from facet.config import ConfigError
from facet.contracts import ErrorCode, InsertState, JobKind, JobState, LocalId
from facet.db.codecs import StorageFailure, timestamp_from_sql
from facet.db.repositories.serialization import COLUMNS, _decode_row

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


def _decode(connection: sqlite3.Connection, table: str, row: tuple):
    try:
        return _decode_row(table, tuple(row))
    except StorageFailure:
        raise
    except (TypeError, ValueError, KeyError):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None


def _open_snapshot(options):
    paths, raw, config = _paths_and_config(options)
    connection = _open_read_only(paths.db)
    try:
        connection.execute("BEGIN")
        _check_config_artifact(connection, config.projection.id.value, raw)
        return paths, raw, config, connection
    except BaseException:
        connection.close()
        raise


def read_recovery_list(options) -> dict:
    """Return aggregate recovery facts without exposing item identifiers."""

    paths, raw, config, connection = _open_snapshot(options)
    del paths, raw
    try:
        projection = config.projection.id.value
        attempts = dict.fromkeys((state.value for state in InsertState), 0)
        for state, count in connection.execute(
            "SELECT state,COUNT(*) FROM insert_attempts "
            "WHERE projection_id=? GROUP BY state",
            (projection,),
        ).fetchall():
            try:
                attempts[InsertState(state).value] = int(count)
            except (TypeError, ValueError):
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None
        jobs = dict.fromkeys((state.value for state in JobState), 0)
        for state, count in connection.execute(
            "SELECT state,COUNT(*) FROM sync_jobs "
            "WHERE projection_id=? AND kind='recover_insert' GROUP BY state",
            (projection,),
        ).fetchall():
            try:
                jobs[JobState(state).value] = int(count)
            except (TypeError, ValueError):
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None
        return {
            "unknown_insert_attempts": attempts[InsertState.DISPATCH_STARTED.value]
            + attempts[InsertState.PENDING_RECOVERY.value],
            "attempts_by_state": attempts,
            "recovery_jobs_by_state": jobs,
            "target_writes": 0,
            "scope": "projection",
            "freshness": "offline_snapshot",
        }
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


def _selected_recovery(connection, config, job_id: LocalId):
    projection = config.projection.id.value
    rows = connection.execute(
        "SELECT "
        + ",".join(COLUMNS["sync_jobs"])
        + " FROM sync_jobs WHERE projection_id=? AND job_id=? LIMIT 2",
        (projection, job_id.value),
    ).fetchall()
    if len(rows) != 1:
        raise ConfigError(ErrorCode.OWNER_UNAVAILABLE)
    job = _decode(connection, "sync_jobs", rows[0])
    if job.kind is not JobKind.RECOVER_INSERT:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    attempt_rows = connection.execute(
        "SELECT "
        + ",".join(COLUMNS["insert_attempts"])
        + " FROM insert_attempts WHERE projection_id=? AND attempt_id=? LIMIT 2",
        (projection, job.subject.attempt_id.value),
    ).fetchall()
    if len(attempt_rows) != 1:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    attempt = _decode(connection, "insert_attempts", attempt_rows[0])
    if attempt.attempt_id != job.subject.attempt_id:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    # The recovery subject identifies the attempt; the attempt keeps the
    # original project job ID.  Verify that original job before exposing facts.
    original_rows = connection.execute(
        "SELECT kind FROM sync_jobs WHERE projection_id=? AND job_id=? LIMIT 2",
        (projection, attempt.job_id.value),
    ).fetchall()
    if len(original_rows) != 1 or original_rows[0][0] != JobKind.PROJECT_MESSAGE.value:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    linkage = connection.execute(
        "SELECT 1 FROM sync_jobs WHERE projection_id=? AND job_id=? "
        "AND kind='recover_insert' AND stable_key=? LIMIT 2",
        (projection, job_id.value, job.stable_key.value),
    ).fetchall()
    if len(linkage) != 1:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    return job, attempt


def _attempt_data(attempt):
    return {
        "attempt_id": attempt.attempt_id.value,
        "source_message_id": attempt.source_message_id.value,
        "source_thread_id": attempt.source_thread_id.value,
        "state": attempt.state.value,
        "certainty": attempt.certainty.value,
        "rfc_message_id": (
            None if attempt.rfc_message_id is None else attempt.rfc_message_id.value
        ),
        "target_message_id": (
            None
            if attempt.target_message_id is None
            else attempt.target_message_id.value
        ),
        "target_thread_id": (
            None if attempt.target_thread_id is None else attempt.target_thread_id.value
        ),
        "attribution": attempt.attribution.value,
        "visibility": attempt.visibility.value,
        "error_code": None if attempt.error_code is None else attempt.error_code.value,
        "recovery_checks": attempt.recovery_checks.value,
        "next_recovery_at": _time(
            None
            if attempt.next_recovery_at is None
            else int(attempt.next_recovery_at.value.timestamp() * 1_000_000)
        ),
        "prepared_at": _time(int(attempt.prepared_at.value.timestamp() * 1_000_000)),
        "dispatch_started_at": _time(
            None
            if attempt.dispatch_started_at is None
            else int(attempt.dispatch_started_at.value.timestamp() * 1_000_000)
        ),
        "result_at": _time(
            None
            if attempt.result_at is None
            else int(attempt.result_at.value.timestamp() * 1_000_000)
        ),
    }


def _job_data(job):
    return {
        "job_id": job.job_id.value,
        "kind": job.kind.value,
        "state": job.state.value,
        "priority": job.priority.value,
        "attempt_count": job.attempt_count.value,
        "last_error_code": (
            None if job.last_error_code is None else job.last_error_code.value
        ),
        "created_at": _time(int(job.created_at.value.timestamp() * 1_000_000)),
        "updated_at": _time(int(job.updated_at.value.timestamp() * 1_000_000)),
        "next_attempt_at": _time(
            None
            if job.next_attempt_at is None
            else int(job.next_attempt_at.value.timestamp() * 1_000_000)
        ),
    }


def read_recovery_job(options) -> dict:
    if not getattr(options, "private_metadata", False):
        raise ConfigError(ErrorCode.SCOPE_REQUIRED)
    try:
        job_id = LocalId(options.job)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    _paths, _raw, config, connection = _open_snapshot(options)
    try:
        job, attempt = _selected_recovery(connection, config, job_id)
        return {"job": _job_data(job), "attempt": _attempt_data(attempt)}
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


__all__ = ("read_recovery_list", "read_recovery_job")
