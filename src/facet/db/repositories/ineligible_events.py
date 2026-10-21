"""Narrow repair of legacy untracked automatic-admission notifications."""

from facet.contracts import ErrorCode, JobState, Timestamp
from facet.contracts.records import SourceEventKeyMessageAdded

from ..codecs import AuditKind, AuditObjectKind, EventProcessing, timestamp_to_sql
from .audit import _audit
from .base import _get, _mutating


def repairable(uow, projection_id, event_id, job_id):
    if uow._execute("PRAGMA user_version").fetchone()[0] < 4:
        return None
    event = _get(uow, projection_id, "source_events", (("event_id", event_id),))
    job = _get(uow, projection_id, "sync_jobs", (("job_id", job_id),))
    if (
        event is None
        or job is None
        or type(event.event.key) is not SourceEventKeyMessageAdded
        or event.event.source_thread_id is None
        or job.kind.value != "resolve_event"
        or job.subject.event_key != event.event.key
        or event.processing is not EventProcessing.NEEDS_ATTENTION
        or job.state is not JobState.NEEDS_ATTENTION
        or event.error_code is not ErrorCode.REQUEST_CONFLICT
        or job.last_error_code is not ErrorCode.REQUEST_CONFLICT
    ):
        return None
    protected = uow._execute(
        "WITH s(p,m,t,e,j) AS (VALUES(?,?,?,?,?)) "
        "SELECT 1 FROM tracked_threads a,s WHERE a.projection_id=s.p "
        "AND a.source_thread_id=s.t UNION ALL "
        "SELECT 1 FROM thread_admissions a,s WHERE a.projection_id=s.p "
        "AND a.source_thread_id=s.t UNION ALL "
        "SELECT 1 FROM message_mappings a,s WHERE a.projection_id=s.p "
        "AND (a.source_message_id=s.m OR a.source_thread_id=s.t) UNION ALL "
        "SELECT 1 FROM insert_attempts a,s WHERE a.projection_id=s.p "
        "AND (a.source_message_id=s.m OR a.source_thread_id=s.t) UNION ALL "
        "SELECT 1 FROM job_claims a,s WHERE a.projection_id=s.p "
        "AND a.job_id=s.j UNION ALL "
        "SELECT 1 FROM sync_jobs a,s WHERE a.projection_id=s.p "
        "AND a.job_id<>s.j AND (a.source_message_id=s.m "
        "OR a.source_thread_id=s.t) UNION ALL "
        "SELECT 1 FROM action_commands a,s WHERE a.projection_id=s.p "
        "AND (a.event_id=s.e OR a.source_thread_id=s.t) UNION ALL "
        "SELECT 1 FROM current_action_receipts a,s WHERE a.projection_id=s.p "
        "AND (a.trigger_event_id=s.e OR a.source_thread_id=s.t) LIMIT 1",
        (
            projection_id.value,
            event.event.key.source_message_id.value,
            event.event.source_thread_id.value,
            event_id.value,
            job_id.value,
        ),
    ).fetchone()
    return None if protected else (event, job)


@_mutating
def consume_excluded(uow, projection_id, event, job, observed_at):
    """Caller holds fresh positive exclusion; revalidate every durable guard."""
    if repairable(uow, projection_id, event.event_id, job.job_id) != (event, job):
        return False
    if type(observed_at) is not Timestamp or observed_at.value < job.updated_at.value:
        return False
    uow._execute(
        "UPDATE source_events SET processing='consumed',error_code=NULL,"
        "revision=revision+1 WHERE projection_id=? AND event_id=? AND revision=?",
        (projection_id.value, event.event_id.value, event.revision.value),
    )
    uow._execute(
        "UPDATE sync_jobs SET state='completed',last_error_code=NULL,"
        "next_attempt_at=NULL,updated_at=?,revision=revision+1 "
        "WHERE projection_id=? AND job_id=? AND revision=?",
        (
            timestamp_to_sql(observed_at),
            projection_id.value,
            job.job_id.value,
            job.revision.value,
        ),
    )
    from ..codecs import next_revision

    _audit(
        uow,
        projection_id,
        AuditKind.JOB_STATE_CHANGED,
        AuditObjectKind.JOB,
        observed_at,
        local_id=job.job_id,
        before_revision=job.revision,
        after_revision=next_revision(job.revision),
        before_state=JobState.NEEDS_ATTENTION,
        after_state=JobState.COMPLETED,
        error=ErrorCode.REQUEST_CONFLICT,
    )
    return True
