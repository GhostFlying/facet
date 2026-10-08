"""One narrow exception for retained, successfully checked aged unknowns."""

from facet.contracts import ErrorCode, Role
from facet.db.codecs import StorageFailure, timestamp_to_sql

from .base import _get, _query
from .jobs import _ready, _thread_guard


def enabled(uow):
    return _query(uow, "PRAGMA user_version", maximum=1)[0][0] == 5


def exclusion(uow):
    if not enabled(uow):
        return ""
    return (
        "AND NOT EXISTS(SELECT 1 FROM insert_absence_retries r "
        "WHERE r.projection_id=a.projection_id AND r.attempt_id=a.attempt_id) "
    )


def blockers(uow, projection, thread):
    return _query(
        uow,
        "SELECT 1 FROM insert_attempts a WHERE a.projection_id=? "
        "AND a.source_thread_id=? AND a.state IN('dispatch_started',"
        "'pending_recovery','known_inserted','needs_attention') "
        + exclusion(uow)
        + "LIMIT 1",
        (projection.value, thread.value),
        maximum=1,
    )


def record(uow, projection, attempt, job, checked_at):
    """Called in the owned check/requeue transaction after provider evidence."""
    if not enabled(uow):
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
    _ready(uow, projection)
    _thread_guard(uow, projection, job)
    target = _get(uow, projection, "bindings", (("role", Role.TARGET),))
    source = _get(uow, projection, "bindings", (("role", Role.SOURCE),))
    if target.binding_revision != attempt.binding_revision:
        raise StorageFailure(ErrorCode.BINDING_MISMATCH)
    if _get(
        uow,
        projection,
        "message_mappings",
        (("source_message_id", attempt.source_message_id),),
    ):
        raise StorageFailure(ErrorCode.INSERT_RESULT_UNKNOWN)
    uow._execute(
        "INSERT INTO insert_absence_retries VALUES(?,?,?,?,?)",
        (
            projection.value,
            attempt.attempt_id.value,
            timestamp_to_sql(checked_at),
            source.binding_revision.value,
            target.binding_revision.value,
        ),
    )
