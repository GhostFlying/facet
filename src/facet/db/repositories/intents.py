"""Insert intent and invocation-entry facts, never provider calls or retry policy."""

from facet.contracts import (
    ClaimPhase,
    ErrorCode,
    InsertState,
    JobKind,
    JobState,
    LocalId,
    Role,
    Timestamp,
)

from ..codecs import (
    AuditKind,
    AuditObjectKind,
    StorageFailure,
    next_revision,
    timestamp_to_sql,
)
from ..models import WriteReceipt
from .audit import _audit
from .base import _conflict, _get, _guard, _insert, _mutating, _query, _require_row
from .jobs import _ready, _thread_guard


def _claim(uow, projection_id, job_id):
    job = _get(uow, projection_id, "sync_jobs", (("job_id", job_id),))
    claimed = _get(uow, projection_id, "job_claims", (("job_id", job_id),))
    if (
        job is None
        or job.state is not JobState.CLAIMED
        or job.kind not in {JobKind.PROJECT_MESSAGE, JobKind.REPAIR_MESSAGE}
        or claimed is None
        or claimed.claim.owner_run_id != uow._session._info.owner_run_id
        or claimed.claim.job_revision != job.revision
        or claimed.claim.thread_generation != job.subject.generation
    ):
        _conflict()
    if job.kind is JobKind.REPAIR_MESSAGE:
        # The v1 schema has no reviewed repair authorization registry.
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    return job, claimed.claim


def _binding(uow, projection_id, attempt):
    _ready(uow, projection_id)
    binding = _get(uow, projection_id, "bindings", (("role", Role.TARGET),))
    if (
        attempt.binding_role is not Role.TARGET
        or attempt.binding_revision != binding.binding_revision
    ):
        raise StorageFailure(ErrorCode.BINDING_PENDING)


def _identity(job, claim, attempt):
    subject = job.subject
    if (
        attempt.claim_id != claim.claim_id
        or attempt.source_message_id != subject.source_message_id
        or attempt.source_thread_id != subject.source_thread_id
        or attempt.generation != subject.generation
        or attempt.prepared_at.value < claim.acquired_at.value
    ):
        _conflict()


@_mutating
def prepare_attempt(uow, projection_id, row, guard):
    _require_row(projection_id, "insert_attempts", row)
    job, claim = _claim(uow, projection_id, row.job_id)
    _guard(job.revision, guard)
    _thread_guard(uow, projection_id, job)
    _binding(uow, projection_id, row)
    _identity(job, claim, row)
    if (
        claim.phase is not ClaimPhase.PREPARING
        or row.state is not InsertState.PREPARED
        or row.revision.value != 0
        or row.recovery_checks.value != 0
        or row.next_recovery_at is not None
        or row.error_code is not None
    ):
        _conflict()
    old = _get(uow, projection_id, "insert_attempts", (("attempt_id", row.attempt_id),))
    if old is not None:
        if old != row:
            _conflict()
        return WriteReceipt("replayed", old.attempt_id, old.revision)
    if (
        _get(
            uow,
            projection_id,
            "message_mappings",
            (("source_message_id", row.source_message_id),),
        )
        is not None
    ):
        _conflict()
    if _query(
        uow,
        "SELECT 1 FROM insert_attempts WHERE projection_id=? AND "
        "(source_message_id=? OR source_thread_id=?) AND state "
        "IN('dispatch_started','pending_recovery','known_inserted','needs_attention') "
        "LIMIT 1",
        (projection_id.value, row.source_message_id.value, row.source_thread_id.value),
        maximum=1,
    ):
        raise StorageFailure(ErrorCode.INSERT_RESULT_UNKNOWN)
    _insert(uow, projection_id, "insert_attempts", row)
    _audit(
        uow,
        projection_id,
        AuditKind.ATTEMPT_STATE_CHANGED,
        AuditObjectKind.ATTEMPT,
        row.prepared_at,
        local_id=row.attempt_id,
        after_revision=row.revision,
        after_state=row.state,
    )
    return WriteReceipt("created", row.attempt_id, row.revision)


@_mutating
def mark_dispatch(uow, projection_id, attempt_id, claim_id, dispatched_at, guard):
    if type(claim_id) is not LocalId or type(dispatched_at) is not Timestamp:
        _conflict()
    attempt = _get(uow, projection_id, "insert_attempts", (("attempt_id", attempt_id),))
    if attempt is None:
        _conflict()
    _guard(attempt.revision, guard)
    job, claim = _claim(uow, projection_id, attempt.job_id)
    _identity(job, claim, attempt)
    _thread_guard(uow, projection_id, job)
    _binding(uow, projection_id, attempt)
    if claim_id != claim.claim_id or dispatched_at.value < attempt.prepared_at.value:
        _conflict()
    if attempt.state is InsertState.DISPATCH_STARTED:
        if (
            claim.phase is not ClaimPhase.DISPATCHING
            or attempt.dispatch_started_at != dispatched_at
        ):
            _conflict()
        # This is observation of a committed marker, NEVER authorization for a
        # second provider invocation. The future actor must distinguish replay.
        return WriteReceipt("replayed", attempt_id, attempt.revision)
    if (
        attempt.state is not InsertState.PREPARED
        or claim.phase is not ClaimPhase.PREPARING
    ):
        _conflict()
    revision = next_revision(attempt.revision)
    changed = uow._execute(
        "UPDATE insert_attempts SET state='dispatch_started',certainty='unknown',"
        "dispatch_started_at=?,revision=? WHERE projection_id=? AND attempt_id=? "
        "AND revision=?",
        (
            timestamp_to_sql(dispatched_at),
            revision.value,
            projection_id.value,
            attempt_id.value,
            attempt.revision.value,
        ),
    )
    if changed.rowcount != 1:
        _conflict()
    changed = uow._execute(
        "UPDATE job_claims SET phase='dispatching' WHERE projection_id=? AND job_id=? "
        "AND claim_id=? AND owner_run_id=? AND job_revision=? AND phase='preparing'",
        (
            projection_id.value,
            job.job_id.value,
            claim_id.value,
            claim.owner_run_id.value,
            claim.job_revision.value,
        ),
    )
    if changed.rowcount != 1:
        _conflict()
    _audit(
        uow,
        projection_id,
        AuditKind.ATTEMPT_STATE_CHANGED,
        AuditObjectKind.ATTEMPT,
        dispatched_at,
        local_id=attempt_id,
        before_revision=attempt.revision,
        after_revision=revision,
        before_state=attempt.state,
        after_state=InsertState.DISPATCH_STARTED,
    )
    return WriteReceipt("updated", attempt_id, revision)
