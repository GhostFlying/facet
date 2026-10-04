"""Stable queue facts and guarded claims. This is not a remote-effect scheduler."""

from facet.contracts import (
    BindingState,
    Claim,
    ClaimPhase,
    ErrorCode,
    JobKind,
    JobState,
    RestoreState,
    Revision,
    Role,
)

from ..codecs import StorageFailure, next_revision, timestamp_to_sql
from ..models import EpochJobRow, JobClaimRow, WriteReceipt
from .base import (
    _conflict,
    _get,
    _guard,
    _insert,
    _mutating,
    _query,
    _require_row,
)


def _thread_guard(uow, projection_id, job):
    subject = job.subject
    if hasattr(subject, "generation"):
        thread = _get(
            uow,
            projection_id,
            "tracked_threads",
            (("source_thread_id", subject.source_thread_id),),
        )
        if (
            thread is None
            or not thread.active
            or thread.generation != subject.generation
        ):
            raise StorageFailure(ErrorCode.GENERATION_STALE)
        return subject.generation
    if job.kind is JobKind.RECOVER_INSERT:
        attempt = _get(
            uow, projection_id, "insert_attempts", (("attempt_id", subject.attempt_id),)
        )
        if attempt is None:
            _conflict()
        return attempt.generation
    return None


def _ready(uow, projection_id, *, recovering=False):
    projection = _get(uow, projection_id, "projections", ())
    if projection is None:
        _conflict()
    if projection.binding_state is not BindingState.VERIFIED:
        raise StorageFailure(ErrorCode.BINDING_PENDING)
    for role in Role:
        binding = _get(uow, projection_id, "bindings", (("role", role),))
        if binding is None or binding.state is not BindingState.VERIFIED:
            raise StorageFailure(ErrorCode.BINDING_PENDING)
    if not recovering and (
        projection.daemon_paused or projection.restore_state is not RestoreState.NORMAL
    ):
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
    return projection


@_mutating
def enqueue(uow, projection_id, row):
    from .actions import _after_enqueue, _before_enqueue

    _require_row(projection_id, "sync_jobs", row)
    _before_enqueue(uow, projection_id, row)
    old = _get(uow, projection_id, "sync_jobs", (("stable_key", row.stable_key),))
    if old is not None:
        # Local allocation time/UUID are not provider identity. Preserve the
        # original values; every semantic immutable fact must still agree.
        if (old.subject, old.kind, old.priority) != (
            row.subject,
            row.kind,
            row.priority,
        ):
            _conflict()
        _join_epoch(uow, projection_id, row.origin_epoch_id, old.job_id)
        return _after_enqueue(
            uow, projection_id, WriteReceipt("replayed", old.job_id, old.revision)
        )
    if (
        row.state is not JobState.QUEUED
        or row.revision.value != 0
        or row.attempt_count.value != 0
        or row.next_attempt_at is not None
    ):
        _conflict()
    if row.kind in {JobKind.OPERATION_READ, JobKind.REPAIR_MESSAGE}:
        # Actual operation/repair authorization registries are not allocated in
        # schema v1. A syntactically valid UUID is not that authority.
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    _thread_guard(uow, projection_id, row)
    if row.kind is JobKind.PROJECT_MESSAGE:
        if (
            _get(
                uow,
                projection_id,
                "message_mappings",
                (("source_message_id", row.subject.source_message_id),),
            )
            is not None
        ):
            _conflict()
        blocker = _query(
            uow,
            "SELECT 1 FROM insert_attempts WHERE projection_id=? AND "
            "source_message_id=? AND state "
            "IN('dispatch_started','pending_recovery',"
            "'known_inserted','needs_attention') LIMIT 1",
            (projection_id.value, row.subject.source_message_id.value),
            maximum=1,
        )
        if blocker:
            raise StorageFailure(ErrorCode.INSERT_RESULT_UNKNOWN)
    event_id = None
    if row.kind is JobKind.RESOLVE_EVENT:
        from ..keys import event_key

        event = _get(
            uow,
            projection_id,
            "source_events",
            (("event_key", event_key(projection_id, row.subject.event_key)),),
        )
        if event is None:
            _conflict()
        event_id = event.event_id
    _insert(uow, projection_id, "sync_jobs", row, event_id=event_id)
    _join_epoch(uow, projection_id, row.origin_epoch_id, row.job_id)
    return _after_enqueue(
        uow, projection_id, WriteReceipt("created", row.job_id, row.revision)
    )


def _join_epoch(uow, projection_id, epoch_id, job_id):
    if (
        epoch_id is not None
        and _get(
            uow,
            projection_id,
            "epoch_jobs",
            (
                ("epoch_id", epoch_id),
                ("job_id", job_id),
            ),
        )
        is None
    ):
        _insert(
            uow,
            projection_id,
            "epoch_jobs",
            EpochJobRow(projection_id, epoch_id, job_id),
        )


@_mutating
def claim(uow, projection_id, job_id, claim: Claim, guard, now):
    if type(claim) is not Claim:
        _conflict()
    job = _get(uow, projection_id, "sync_jobs", (("job_id", job_id),))
    if job is None:
        _conflict()
    _guard(job.revision, guard)
    recovering = job.kind is JobKind.RECOVER_INSERT
    _ready(uow, projection_id, recovering=recovering)
    if job.state not in {JobState.QUEUED, JobState.RETRY_WAIT} or (
        job.next_attempt_at is not None
        and timestamp_to_sql(now) < timestamp_to_sql(job.next_attempt_at)
    ):
        _conflict()
    generation = _thread_guard(uow, projection_id, job)
    revision = next_revision(job.revision)
    # All closed claims start preparing. Recovery prepares checks on an old
    # attempt, not a new insert; dispatch admission independently rejects it.
    expected_phase = ClaimPhase.PREPARING
    if (
        claim.owner_run_id != uow._session._info.owner_run_id
        or claim.thread_generation != generation
        or claim.job_revision != revision
        or claim.phase is not expected_phase
        or claim.acquired_at != now
    ):
        _conflict()
    attempts = next_revision(Revision(job.attempt_count.value))
    uow._execute(
        "UPDATE sync_jobs SET "
        "state='claimed',revision=?,attempt_count=?,updated_at=?,"
        "next_attempt_at=NULL WHERE projection_id=? AND job_id=?",
        (
            revision.value,
            attempts.value,
            timestamp_to_sql(now),
            projection_id.value,
            job_id.value,
        ),
    )
    _insert(uow, projection_id, "job_claims", JobClaimRow(projection_id, job_id, claim))
    return WriteReceipt("updated", job_id, revision)


@_mutating
def requeue_preparing_claims(uow, projection_id):
    """Requeue only claims with no evidence of a remote insert dispatch.

    This is the restart boundary for the single foreground owner.  A claimed
    insert with dispatch/unknown/known evidence is intentionally excluded and
    remains available only to an explicit recovery path.
    """
    rows = _query(
        uow,
        "SELECT j.job_id,j.revision FROM sync_jobs j JOIN job_claims c "
        "ON c.projection_id=j.projection_id AND c.job_id=j.job_id "
        "WHERE j.projection_id=? AND j.state='claimed' AND NOT EXISTS("
        "SELECT 1 FROM insert_attempts a WHERE a.projection_id=j.projection_id "
        "AND a.job_id=j.job_id AND a.state IN "
        "('dispatch_started','pending_recovery','known_inserted',"
        "'needs_attention'))",
        (projection_id.value,),
        maximum=10_000,
    )
    for job_id, revision in rows:
        uow._execute(
            "DELETE FROM job_claims WHERE projection_id=? AND job_id=?",
            (projection_id.value, job_id),
        )
        uow._execute(
            "UPDATE sync_jobs SET state='queued',revision=?,"
            "next_attempt_at=NULL WHERE projection_id=? AND job_id=? "
            "AND state='claimed' AND revision=?",
            (revision + 1, projection_id.value, job_id, revision),
        )
    return len(rows)


@_mutating
def defer_job(uow, projection_id, job_id, state, error, retry_at, guard):
    if (
        type(state) is not str
        or state
        not in {"retry_wait", "blocked", "needs_attention", "failed", "source_missing"}
        or type(error) is not ErrorCode
    ):
        _conflict()
    if (state == "retry_wait") != (retry_at is not None):
        _conflict()
    job = _get(uow, projection_id, "sync_jobs", (("job_id", job_id),))
    if job is None or job.state in {
        JobState.COMPLETED,
        JobState.CANCELLED,
        JobState.SOURCE_MISSING,
        JobState.FAILED,
    }:
        _conflict()
    _guard(job.revision, guard)
    blockers = _query(
        uow,
        "SELECT 1 FROM insert_attempts WHERE projection_id=? AND job_id=? AND state "
        "IN('dispatch_started','pending_recovery',"
        "'known_inserted','needs_attention') LIMIT 1",
        (projection_id.value, job_id.value),
        maximum=1,
    )
    if blockers and state not in {"blocked", "needs_attention"}:
        raise StorageFailure(ErrorCode.INSERT_RESULT_UNKNOWN)
    if job.kind is JobKind.RECOVER_INSERT:
        original = _get(
            uow,
            projection_id,
            "insert_attempts",
            (("attempt_id", job.subject.attempt_id),),
        )
        if original is None:
            _conflict()
        if original.state.value in {
            "dispatch_started",
            "pending_recovery",
            "known_inserted",
            "needs_attention",
        } and state in {"failed", "source_missing"}:
            raise StorageFailure(ErrorCode.INSERT_RESULT_UNKNOWN)
        # A retry_wait recovery job retries matching/checking, never an insert.
    revision = next_revision(job.revision)
    uow._execute(
        "DELETE FROM job_claims WHERE projection_id=? AND job_id=?",
        (projection_id.value, job_id.value),
    )
    uow._execute(
        "UPDATE sync_jobs SET state=?,revision=?,next_attempt_at=?,last_error_code=? "
        "WHERE projection_id=? AND job_id=?",
        (
            state,
            revision.value,
            None if retry_at is None else timestamp_to_sql(retry_at),
            error.value,
            projection_id.value,
            job_id.value,
        ),
    )
    return WriteReceipt("updated", job_id, revision)


@_mutating
def complete_noninsert_job(uow, projection_id, job_id, guard):
    job = _get(uow, projection_id, "sync_jobs", (("job_id", job_id),))
    if job is None:
        _conflict()
    _guard(job.revision, guard)
    if job.state is not JobState.CLAIMED:
        _conflict()
    _thread_guard(uow, projection_id, job)
    subject, proved = job.subject, False
    completion = JobState.COMPLETED
    if job.kind in {JobKind.PROJECT_MESSAGE, JobKind.REPAIR_MESSAGE}:
        _conflict()
    elif job.kind is JobKind.EXPAND_THREAD:
        proved = bool(
            _query(
                uow,
                "SELECT 1 FROM thread_expansion_runs WHERE projection_id=? AND "
                "job_id=? AND source_thread_id=? AND epoch_id=? AND generation=? AND "
                "current=1 AND state='complete' LIMIT 1",
                (
                    projection_id.value,
                    job_id.value,
                    subject.source_thread_id.value,
                    subject.epoch_id.value,
                    subject.generation.value,
                ),
                maximum=1,
            )
        )
    elif job.kind is JobKind.RESOLVE_EVENT:
        from ..keys import event_key

        event = _get(
            uow,
            projection_id,
            "source_events",
            (("event_key", event_key(projection_id, subject.event_key)),),
        )
        proved = event is not None and event.processing.value in {
            "resolved",
            "consumed",
            "source_missing",
        }
        if event is not None and event.processing.value == "source_missing":
            completion = JobState.SOURCE_MISSING
    elif job.kind in {
        JobKind.SCAN_DISCOVERY,
        JobKind.SCAN_GAP,
        JobKind.RECONCILE_SOURCE,
        JobKind.AUDIT_TARGET,
    }:
        from ..keys import partition_key

        partition = _get(
            uow,
            projection_id,
            "epoch_partitions",
            (
                ("epoch_id", subject.epoch_id),
                ("partition_key", partition_key(projection_id, subject.partition)),
            ),
        )
        proved = partition is not None and partition.progress.state.value == "complete"
    elif job.kind is JobKind.CLEANUP_ACTION:
        action = _get(
            uow,
            projection_id,
            "action_commands",
            (("action_command_id", subject.action_command_id),),
        )
        proved = action is not None and action.cleanup.value == "completed"
    elif job.kind is JobKind.RECOVER_INSERT:
        attempt = _get(
            uow, projection_id, "insert_attempts", (("attempt_id", subject.attempt_id),)
        )
        proved = attempt is not None and attempt.state.value in {
            "verified",
            "definite_not_inserted",
        }
    elif job.kind is JobKind.OPERATION_READ:
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    if not proved:
        _conflict()
    revision = next_revision(job.revision)
    uow._execute(
        "DELETE FROM job_claims WHERE projection_id=? AND job_id=?",
        (projection_id.value, job_id.value),
    )
    uow._execute(
        "UPDATE sync_jobs SET state=?,revision=? WHERE projection_id=? AND job_id=?",
        (completion.value, revision.value, projection_id.value, job_id.value),
    )
    return WriteReceipt("updated", job_id, revision)
