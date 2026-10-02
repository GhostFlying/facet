"""Bounded typed private reads; not Dashboard serializers or snapshot stores."""

from facet.contracts import (
    Count,
    ErrorCode,
    JobState,
    LocalId,
    ProjectionId,
    ProviderId,
    Role,
)

from ..codecs import PageLimit, StorageFailure, invalid
from ..connection import ReadSession
from ..keys import _parse_read_key, _read_key
from ..models import CountsSnapshot, JobStateCount, ReadPage
from .base import _context, _decode, _get, _query
from .serialization import COLUMNS


def get_projection(view, projection_id: ProjectionId):
    return _get(view, projection_id, "projections", ())


def inspect_schema(view, projection_id: ProjectionId):
    _context(view, projection_id)
    if type(view) is not ReadSession:
        invalid()
    if get_projection(view, projection_id) is None:
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    metadata = _query(
        view,
        "SELECT singleton,schema_version,registry_digest,"
        "created_at FROM schema_metadata",
        maximum=1,
    )
    migrations = _query(
        view,
        "SELECT version,name,checksum,applied_at "
        "FROM schema_migrations ORDER BY version",
    )
    if len(metadata) != 1:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    return (
        _decode(view, projection_id, "schema_metadata", metadata[0]),
        tuple(
            _decode(view, projection_id, "schema_migrations", row) for row in migrations
        ),
    )


def get_binding(view, projection_id: ProjectionId, role: Role):
    if type(role) is not Role:
        invalid()
    return _get(view, projection_id, "bindings", (("role", role),))


def get_binding_revision(view, projection_id, role, revision):
    return _get(
        view,
        projection_id,
        "binding_revisions",
        (("role", role), ("binding_revision", revision)),
    )


def get_rule(view, projection_id, id):
    return _get(view, projection_id, "rules", (("rule_id", id),))


def get_epoch(view, projection_id, id):
    return _get(view, projection_id, "epochs", (("epoch_id", id),))


def get_event(view, projection_id, id):
    return _get(view, projection_id, "source_events", (("event_id", id),))


def get_job(view, projection_id, id):
    return _get(view, projection_id, "sync_jobs", (("job_id", id),))


def get_attempt(view, projection_id, id):
    return _get(view, projection_id, "insert_attempts", (("attempt_id", id),))


def get_action(view, projection_id, id):
    return _get(view, projection_id, "action_commands", (("action_command_id", id),))


def get_thread(view, projection_id, id):
    return _get(view, projection_id, "tracked_threads", (("source_thread_id", id),))


def get_mapping(view, projection_id, id):
    return _get(view, projection_id, "message_mappings", (("source_message_id", id),))


def get_thread_target(view, projection_id, source_thread_id, target_thread_id):
    if (
        type(view) is not ReadSession
        or type(source_thread_id) is not ProviderId
        or type(target_thread_id) is not ProviderId
    ):
        invalid()
    return _get(
        view,
        projection_id,
        "thread_targets",
        (
            ("source_thread_id", source_thread_id),
            ("target_thread_id", target_thread_id),
        ),
    )


def get_thread_anchor(view, projection_id, source_thread_id):
    if type(view) is not ReadSession or type(source_thread_id) is not ProviderId:
        invalid()
    _context(view, projection_id)
    rows = _query(
        view,
        "SELECT "
        + ",".join(COLUMNS["thread_targets"])
        + " FROM thread_targets WHERE projection_id=? AND source_thread_id=? "
        "AND anchor=1",
        (projection_id.value, source_thread_id.value),
        maximum=1,
    )
    return _decode(view, projection_id, "thread_targets", rows[0]) if rows else None


def get_checkpoint(view, projection_id):
    return _get(view, projection_id, "history_checkpoints", ())


def get_history_poll(view: ReadSession, projection_id: ProjectionId, poll_id: LocalId):
    if type(view) is not ReadSession or type(poll_id) is not LocalId:
        invalid()
    _context(view, projection_id)
    return _get(view, projection_id, "history_polls", (("poll_id", poll_id),))


def get_history_page(
    view: ReadSession, projection_id: ProjectionId, poll_id: LocalId, ordinal: Count
):
    if (
        type(view) is not ReadSession
        or type(poll_id) is not LocalId
        or type(ordinal) is not Count
    ):
        invalid()
    _context(view, projection_id)
    if ordinal.value < 1:
        invalid()
    return _get(
        view,
        projection_id,
        "history_pages",
        (("poll_id", poll_id), ("ordinal", ordinal)),
    )


_LISTS = {
    "sync_jobs": ("created_at", "job_id"),
    "insert_attempts": ("prepared_at", "attempt_id"),
    "source_events": ("observed_at", "event_id"),
    "audit_events": ("observed_at", "audit_id"),
}


def _list(view, projection_id, table, limit, after):
    _context(view, projection_id)
    if type(view) is not ReadSession or type(limit) is not PageLimit:
        invalid()
    time, id = _LISTS[table]
    params = [projection_id.value]
    where = "projection_id=?"
    if after is not None:
        time_value, id_value = _parse_read_key(table, projection_id, after)
        where += f" AND ({time},{id})>(?,?)"
        params.extend((time_value, id_value))
    params.append(limit.value + 1)
    rows = _query(
        view,
        "SELECT "
        + ",".join(COLUMNS[table])
        + f" FROM {table} WHERE "
        + where
        + f" ORDER BY {time},{id} LIMIT ?",
        tuple(params),
        maximum=501,
    )
    has_more = len(rows) > limit.value
    retained = rows[: limit.value]
    next_key = None
    if has_more:
        last = dict(zip(COLUMNS[table], retained[-1], strict=True))
        next_key = _read_key(table, projection_id, last[time], LocalId(last[id]))
    items = tuple(_decode(view, projection_id, table, row) for row in retained)
    return ReadPage(items, next_key)


def list_jobs(view, projection_id, limit, after):
    return _list(view, projection_id, "sync_jobs", limit, after)


def list_attempts(view, projection_id, limit, after):
    return _list(view, projection_id, "insert_attempts", limit, after)


def list_events(view, projection_id, limit, after):
    return _list(view, projection_id, "source_events", limit, after)


def list_audit(view, projection_id, limit, after):
    return _list(view, projection_id, "audit_events", limit, after)


def counts(view, projection_id, epoch_id):
    _context(view, projection_id)
    if epoch_id is not None and type(epoch_id) is not LocalId:
        invalid()
    p = projection_id.value
    if epoch_id is None:
        maps = "SELECT COUNT(*) FROM message_mappings WHERE projection_id=:p"
        jobs = (
            "SELECT state,COUNT(*) AS n FROM sync_jobs "
            "WHERE projection_id=:p GROUP BY state"
        )
        epoch_sql = "SELECT 0 AS discovery_complete,NULL AS known_message_total"
        params = {"p": p}
    else:
        maps = (
            "SELECT COUNT(DISTINCT j.source_message_id) FROM sync_jobs j "
            "JOIN epoch_jobs e ON e.projection_id=j.projection_id "
            "AND e.job_id=j.job_id "
            "JOIN message_mappings m ON m.projection_id=j.projection_id "
            "AND m.source_message_id=j.source_message_id WHERE j.projection_id=:p "
            "AND e.epoch_id=:e AND j.kind IN('project_message','repair_message') "
            "AND j.state='completed'"
        )
        jobs = (
            "SELECT j.state,COUNT(*) AS n FROM sync_jobs j JOIN epoch_jobs e "
            "ON e.projection_id=j.projection_id AND e.job_id=j.job_id "
            "WHERE j.projection_id=:p AND e.epoch_id=:e GROUP BY j.state"
        )
        epoch_sql = (
            "SELECT discovery_complete,known_message_total FROM epochs "
            "WHERE projection_id=:p AND epoch_id=:e"
        )
        params = {"p": p, "e": epoch_id.value}
    # One materialized SQL result, hence one short snapshot for every aggregate.
    sql = (
        "WITH jobs AS (" + jobs + "),epoch AS (" + epoch_sql + ") "
        "SELECT 'summary',(" + maps + "),(SELECT COUNT(*) FROM insert_attempts "
        "WHERE projection_id=:p AND state IN('dispatch_started','pending_recovery',"
        "'known_inserted','needs_attention')),(SELECT discovery_complete FROM epoch),"
        "(SELECT known_message_total FROM epoch) UNION ALL "
        "SELECT state,n,NULL,NULL,NULL FROM jobs"
    )
    rows = _query(view, sql, params, maximum=10)
    summary = rows[0]
    if summary[3] is None:
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    by_state = {row[0]: row[1] for row in rows[1:]}
    complete = bool(summary[3])
    return CountsSnapshot(
        Count(summary[1]),
        tuple(
            JobStateCount(state, Count(by_state.get(state.value, 0)))
            for state in JobState
        ),
        Count(summary[2]),
        complete,
        Count(summary[4]) if complete and summary[4] is not None else None,
    )
