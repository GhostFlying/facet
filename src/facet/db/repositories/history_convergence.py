"""Retire unadmitted History failures under proven current source coverage."""

from facet.contracts import EpochKind, ErrorCode, JobState, LocalId, Revision, Timestamp

from ..codecs import (
    AuditKind,
    AuditObjectKind,
    StorageFailure,
    next_revision,
    timestamp_to_sql,
)
from .audit import _audit
from .base import _get, _mutating
from .jobs import _join_epoch


def historical_warning_count(uow, projection_id):
    """Count retained coverage receipts, not active errors or latest-run totals."""
    return uow._execute(
        "SELECT COUNT(DISTINCT a.local_object_id) FROM audit_events a "
        "JOIN sync_jobs j ON j.projection_id=a.projection_id "
        "AND j.job_id=a.local_object_id "
        "JOIN epoch_jobs x ON x.projection_id=j.projection_id AND x.job_id=j.job_id "
        "JOIN epochs e ON e.projection_id=x.projection_id AND e.epoch_id=x.epoch_id "
        "WHERE a.projection_id=? AND a.kind='job_state_changed' "
        "AND a.object_kind='job' AND a.error_code='source_missing' "
        "AND a.before_state='source_missing' AND a.after_state='completed' "
        "AND j.kind='resolve_event' AND e.kind='source_reconcile'",
        (projection_id.value,),
    ).fetchone()[0]


@_mutating
def converge_covered_history(uow, projection_id, run_id, observed_at):
    """Atomic terminal bookkeeping, never evidence of a copied/deleted message."""
    if type(run_id) is not LocalId or type(observed_at) is not Timestamp:
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    run = uow._execute(
        "SELECT state,revision,ruleset_revision,source_binding_revision,window_start,"
        "window_end,discovery_cutoff,created_at,completed_at,page_token,listed_count,"
        "metadata_success_count,metadata_404_count,matched_count,mapped_count,"
        "queued_count,remaining_issue_count,last_error_code,last_provider_stage,"
        "last_provider_reason,last_http_status FROM reconcile_runs "
        "WHERE projection_id=? AND run_id=?",
        (projection_id.value, run_id.value),
    ).fetchone()
    if run is None or run[0] != "completed":
        return 0
    fence = min(run[5], run[7])
    rows = uow._execute(
        "SELECT e.event_id,e.revision,j.job_id,j.revision "
        "FROM source_events e JOIN sync_jobs j ON j.projection_id=e.projection_id "
        "AND j.event_id=e.event_id AND j.kind='resolve_event' "
        "WHERE e.projection_id=? AND e.tag='message_added' "
        "AND e.processing='source_missing' AND e.error_code='source_missing' "
        "AND j.state='source_missing' AND j.last_error_code='source_missing' "
        "AND e.source_thread_id IS NOT NULL AND e.observed_at<=? "
        "AND j.created_at<=? AND j.updated_at<=? "
        "AND NOT EXISTS(SELECT 1 FROM tracked_threads t "
        "WHERE t.projection_id=e.projection_id "
        "AND t.source_thread_id=e.source_thread_id) "
        "AND NOT EXISTS(SELECT 1 FROM thread_admissions a "
        "WHERE a.projection_id=e.projection_id "
        "AND a.source_thread_id=e.source_thread_id) "
        "AND NOT EXISTS(SELECT 1 FROM message_mappings m "
        "WHERE m.projection_id=e.projection_id "
        "AND m.source_message_id=e.source_message_id) "
        "AND NOT EXISTS(SELECT 1 FROM insert_attempts i "
        "WHERE i.projection_id=e.projection_id "
        "AND i.source_message_id=e.source_message_id) "
        "AND NOT EXISTS(SELECT 1 FROM job_claims c "
        "WHERE c.projection_id=j.projection_id AND c.job_id=j.job_id) "
        "AND NOT EXISTS(SELECT 1 FROM action_commands a "
        "WHERE a.projection_id=e.projection_id "
        "AND (a.event_id=e.event_id OR a.source_thread_id=e.source_thread_id))",
        (projection_id.value, fence, fence, fence),
    ).fetchall()
    if not rows:
        return 0

    candidate_counts = uow._execute(
        "SELECT COUNT(*),SUM(classification='mapped'),SUM(classification='queued'),"
        "SUM(classification NOT IN('mapped','queued','no_rule')) "
        "FROM reconcile_candidates WHERE projection_id=? AND run_id=?",
        (projection_id.value, run_id.value),
    ).fetchone()
    epoch = _get(uow, projection_id, "epochs", (("epoch_id", run_id),))
    initial = uow._execute(
        "SELECT window_start FROM epochs WHERE projection_id=? "
        "AND kind='initial_backfill' ORDER BY created_at,epoch_id LIMIT 1",
        (projection_id.value,),
    ).fetchone()
    migration = uow._execute(
        "SELECT applied_at FROM schema_migrations WHERE version=7"
    ).fetchone()
    current = uow._execute(
        "SELECT p.ruleset_revision,b.binding_revision,b.state "
        "FROM projections p JOIN bindings b ON b.projection_id=p.projection_id "
        "AND b.role='source' WHERE p.projection_id=?",
        (projection_id.value,),
    ).fetchone()
    if (
        current != (run[2], run[3], "verified")
        or migration is None
        or run[7] < migration[0]
        or initial is None
        or initial[0] != run[4]
    ):
        raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
    if (
        run[8] is None
        or run[9] is not None
        or run[12] != 0
        or run[16] != 0
        or any(value is not None for value in run[17:])
        or run[11] != run[10]
        or run[13] != run[14] + run[15]
        or tuple(int(value or 0) for value in candidate_counts)
        != (run[10], run[14], run[15], 0)
        or epoch is None
        or epoch.kind is not EpochKind.SOURCE_RECONCILE
        or epoch.decision.tag != "requested_reconcile"
        or epoch.decision.operation_id != run_id
        or epoch.decision.ruleset_revision.value != run[2]
        or tuple(
            timestamp_to_sql(value) if value is not None else None
            for value in (epoch.window_start, epoch.window_end, epoch.discovery_cutoff)
        )
        != tuple(run[4:7])
    ):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)

    now = timestamp_to_sql(observed_at)
    for event_id, event_revision, job_id, job_revision in rows:
        next_event = next_revision(Revision(event_revision))
        next_job = next_revision(Revision(job_revision))
        changed_event = uow._execute(
            "UPDATE source_events SET processing='consumed',error_code=NULL,"
            "revision=? WHERE projection_id=? AND event_id=? AND revision=? "
            "AND processing='source_missing'",
            (next_event.value, projection_id.value, event_id, event_revision),
        ).rowcount
        changed_job = uow._execute(
            "UPDATE sync_jobs SET state='completed',last_error_code=NULL,"
            "revision=?,updated_at=?,next_attempt_at=NULL WHERE projection_id=? "
            "AND job_id=? AND revision=? AND state='source_missing'",
            (next_job.value, now, projection_id.value, job_id, job_revision),
        ).rowcount
        if changed_event != 1 or changed_job != 1:
            raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
        _join_epoch(uow, projection_id, run_id, LocalId(job_id))
        _audit(
            uow,
            projection_id,
            AuditKind.JOB_STATE_CHANGED,
            AuditObjectKind.JOB,
            observed_at,
            local_id=LocalId(job_id),
            before_revision=Revision(job_revision),
            after_revision=next_job,
            before_state=JobState.SOURCE_MISSING,
            after_state=JobState.COMPLETED,
            error=ErrorCode.SOURCE_MISSING,
        )
    if (
        uow._execute(
            "UPDATE reconcile_runs SET reset_count=reset_count+?,revision=revision+1 "
            "WHERE projection_id=? AND run_id=? AND revision=? AND state='completed'",
            (len(rows), projection_id.value, run_id.value, run[1]),
        ).rowcount
        != 1
    ):
        raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
    return len(rows)
