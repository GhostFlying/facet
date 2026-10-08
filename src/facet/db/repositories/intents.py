"""Insert intent/result facts, never provider calls or recovery scheduling."""

from dataclasses import fields, replace
from uuid import uuid4

from facet.contracts import (
    ClaimPhase,
    Count,
    ErrorCode,
    InsertState,
    JobKind,
    JobState,
    LocalId,
    OutcomeCertainty,
    Priority,
    Revision,
    Role,
    Timestamp,
    Visibility,
)
from facet.contracts.records import JobSubjectRecoverInsert

from ..codecs import (
    AuditKind,
    AuditObjectKind,
    StorageFailure,
    next_revision,
    timestamp_to_sql,
)
from ..keys import job_key
from ..models import RevisionGuard, SyncJobRow, WriteReceipt
from .audit import _audit
from .base import _conflict, _get, _guard, _insert, _mutating, _query, _require_row
from .jobs import _ready, _thread_guard
from .serialization import COLUMNS, _encode_row


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


_PREPARED_FACTS = (
    "projection_id",
    "attempt_id",
    "job_id",
    "claim_id",
    "source_message_id",
    "source_thread_id",
    "generation",
    "binding_role",
    "binding_revision",
    "prepared_at",
    "requested_target_thread_id",
    "raw_digest",
    "rfc_message_id",
    "date_policy",
    "dispatch_started_at",
)
_PRESERVED_FACTS = (
    "result_at",
    "target_message_id",
    "target_thread_id",
    "semantic_digest",
    "semantic_version",
    "verified_at",
)
_RESULT_EDGES = {
    InsertState.PREPARED: {
        InsertState.CANCELLED_BEFORE_DISPATCH,
        InsertState.DEFINITE_NOT_INSERTED,
    },
    InsertState.DISPATCH_STARTED: {
        InsertState.KNOWN_INSERTED,
        InsertState.PENDING_RECOVERY,
        InsertState.DEFINITE_NOT_INSERTED,
        InsertState.NEEDS_ATTENTION,
    },
    InsertState.KNOWN_INSERTED: {InsertState.NEEDS_ATTENTION},
    InsertState.PENDING_RECOVERY: {InsertState.NEEDS_ATTENTION},
}
_ATTENTION_ERRORS = {
    ErrorCode.SOURCE_MISSING,
    ErrorCode.INSERT_RESULT_UNKNOWN,
    ErrorCode.ATTRIBUTION_UNKNOWN,
    ErrorCode.DUPLICATE_CANDIDATES,
    ErrorCode.FIDELITY_MISMATCH,
    ErrorCode.CONSISTENCY_FAILURE,
    ErrorCode.INVALID_INPUT,
    ErrorCode.TARGET_AUTH_REQUIRED,
    ErrorCode.TARGET_RATE_LIMITED,
    ErrorCode.NETWORK_UNAVAILABLE,
    ErrorCode.TARGET_STORAGE_FULL,
}
_DEFINITE_ERRORS = {
    ErrorCode.SOURCE_AUTH_REQUIRED,
    ErrorCode.TARGET_AUTH_REQUIRED,
    ErrorCode.SCOPE_REQUIRED,
    ErrorCode.BINDING_MISMATCH,
    ErrorCode.BINDING_PENDING,
    ErrorCode.GENERATION_STALE,
    ErrorCode.OWNER_UNAVAILABLE,
    ErrorCode.OWNER_BUSY,
    ErrorCode.WAIT_TIMEOUT,
    ErrorCode.NETWORK_UNAVAILABLE,
    ErrorCode.INVALID_INPUT,
    ErrorCode.SOURCE_MISSING,
    ErrorCode.SOURCE_RATE_LIMITED,
    ErrorCode.TARGET_RATE_LIMITED,
    ErrorCode.TARGET_STORAGE_FULL,
}


def _result_time(row, observed_at, *extra):
    if type(observed_at) is not Timestamp:
        _conflict()
    times = (row.prepared_at, row.dispatch_started_at, row.result_at, row.verified_at)
    if any(t is not None and observed_at.value < t.value for t in (*times, *extra)):
        _conflict()
    if row.result_at is not None and (
        row.result_at.value < row.prepared_at.value
        or row.dispatch_started_at is not None
        and row.result_at.value < row.dispatch_started_at.value
    ):
        _conflict()


def _result_facts(old, row):
    if (
        old.certainty is OutcomeCertainty.INSERTED
        and row.certainty is not OutcomeCertainty.INSERTED
        or old.state is InsertState.PENDING_RECOVERY
        and row.certainty is not OutcomeCertainty.UNKNOWN
    ):
        _conflict()
    if any(getattr(old, f) != getattr(row, f) for f in _PREPARED_FACTS):
        _conflict()
    if any(
        getattr(old, f) is not None and getattr(old, f) != getattr(row, f)
        for f in _PRESERVED_FACTS
    ):
        _conflict()
    if (row.semantic_digest is None) != (row.semantic_version is None):
        _conflict()
    if (old.recovery_checks, old.next_recovery_at) != (
        row.recovery_checks,
        row.next_recovery_at,
    ):
        _conflict()
    if (
        old.visibility is not Visibility.UNKNOWN
        and old.visibility != row.visibility
        or row.certainty is not OutcomeCertainty.INSERTED
        and row.visibility is not Visibility.UNKNOWN
    ):
        _conflict()
    if old.state == row.state:
        # Only these finite nullable readback facts may enrich known insertion.
        allowed = {"revision", "semantic_digest", "semantic_version", "visibility"}
        if old.state is not InsertState.KNOWN_INSERTED or any(
            getattr(old, f.name) != getattr(row, f.name)
            for f in fields(old)
            if f.name not in allowed
        ):
            _conflict()
        if replace(row, revision=old.revision) == old:
            _conflict()
        return
    if row.state not in _RESULT_EDGES.get(old.state, set()):
        _conflict()
    errors = {
        InsertState.KNOWN_INSERTED: {None},
        InsertState.PENDING_RECOVERY: {ErrorCode.INSERT_RESULT_UNKNOWN},
        InsertState.NEEDS_ATTENTION: _ATTENTION_ERRORS,
        InsertState.CANCELLED_BEFORE_DISPATCH: {
            ErrorCode.GENERATION_STALE,
            ErrorCode.OWNER_UNAVAILABLE,
        },
        InsertState.DEFINITE_NOT_INSERTED: _DEFINITE_ERRORS,
    }
    if row.error_code not in errors[row.state]:
        _conflict()


def _result_binding(uow, projection_id, attempt):
    historical = _get(
        uow,
        projection_id,
        "binding_revisions",
        (
            ("role", Role.TARGET),
            ("binding_revision", attempt.binding_revision),
        ),
    )
    current = _get(uow, projection_id, "bindings", (("role", Role.TARGET),))
    historical_identity_matches = (
        historical is not None
        and current is not None
        and (
            historical.verified_address == current.declared_address
            or (
                historical.verified_address is None
                and historical.declared_address == current.declared_address
                and historical.state.value == "verification_pending"
            )
        )
    )
    if (
        historical is None
        or current is None
        or attempt.binding_role is not Role.TARGET
        or not historical_identity_matches
        or historical.declared_address != current.declared_address
    ):
        _conflict()


def _result_job(uow, projection_id, attempt, phase):
    job, claim = _claim(uow, projection_id, attempt.job_id)
    _identity(job, claim, attempt)
    if claim.phase is not phase:
        _conflict()
    return job, claim


def _recovery_identity(uow, projection_id, attempt, observed_at):
    subject = JobSubjectRecoverInsert("recover_insert", attempt.attempt_id)
    recovery = _get(
        uow,
        projection_id,
        "sync_jobs",
        (("stable_key", job_key(projection_id, subject)),),
    )
    if recovery is not None and (
        recovery.kind is not JobKind.RECOVER_INSERT
        or recovery.subject != subject
        or recovery.key_version != Count(1)
        or recovery.priority is not Priority.RECOVERY
        or recovery.next_attempt_at is not None
        or recovery.created_at.value > recovery.updated_at.value
        or recovery.updated_at.value > observed_at.value
    ):
        _conflict()
    return subject, recovery


def _recovery_claim(uow, projection_id, attempt, observed_at):
    _, recovery = _recovery_identity(uow, projection_id, attempt, observed_at)
    if recovery is None or recovery.state is not JobState.CLAIMED:
        _conflict()
    acquired = _get(uow, projection_id, "job_claims", (("job_id", recovery.job_id),))
    if (
        acquired is None
        or acquired.claim.phase is not ClaimPhase.PREPARING
        or acquired.claim.owner_run_id != uow._session._info.owner_run_id
        or acquired.claim.thread_generation != attempt.generation
        or acquired.claim.job_revision != recovery.revision
    ):
        _conflict()
    _result_time(attempt, observed_at, recovery.updated_at, acquired.claim.acquired_at)
    return recovery


def _result_disposition(uow, projection_id, job, state, error, observed_at):
    revision = next_revision(job.revision)
    changed = uow._execute(
        "UPDATE sync_jobs SET state=?,revision=?,updated_at=?,next_attempt_at=NULL,"
        "last_error_code=? WHERE projection_id=? AND job_id=? AND revision=?",
        (
            state.value,
            revision.value,
            timestamp_to_sql(observed_at),
            error.value,
            projection_id.value,
            job.job_id.value,
            job.revision.value,
        ),
    )
    if changed.rowcount != 1:
        _conflict()
    uow._execute(
        "DELETE FROM job_claims WHERE projection_id=? AND job_id=?",
        (projection_id.value, job.job_id.value),
    )
    _audit(
        uow,
        projection_id,
        AuditKind.JOB_STATE_CHANGED,
        AuditObjectKind.JOB,
        observed_at,
        local_id=job.job_id,
        before_revision=job.revision,
        after_revision=revision,
        before_state=job.state,
        after_state=state,
        error=error,
    )


def _result_recovery(uow, projection_id, original, row, observed_at, *, claimed=None):
    subject, recovery = _recovery_identity(uow, projection_id, row, observed_at)
    attention = row.state is InsertState.NEEDS_ATTENTION
    if claimed is not None:
        if recovery != claimed:
            _conflict()
        _result_disposition(
            uow,
            projection_id,
            recovery,
            JobState.NEEDS_ATTENTION,
            row.error_code,
            observed_at,
        )
    elif recovery is None:
        recovery = SyncJobRow(
            projection_id,
            LocalId(uuid4().hex),
            JobKind.RECOVER_INSERT,
            Count(1),
            job_key(projection_id, subject),
            Priority.RECOVERY,
            JobState.NEEDS_ATTENTION if attention else JobState.QUEUED,
            Revision(0),
            observed_at,
            observed_at,
            None,
            Count(0),
            row.error_code if attention else None,
            original.origin_epoch_id,
            subject,
        )
        _insert(uow, projection_id, "sync_jobs", recovery)
    else:
        if _get(uow, projection_id, "job_claims", (("job_id", recovery.job_id),)):
            _conflict()
        if recovery.state is JobState.QUEUED and recovery.last_error_code is None:
            if attention:
                _result_disposition(
                    uow,
                    projection_id,
                    recovery,
                    JobState.NEEDS_ATTENTION,
                    row.error_code,
                    observed_at,
                )
        elif not (
            attention
            and recovery.state is JobState.NEEDS_ATTENTION
            and recovery.last_error_code == row.error_code
        ):
            _conflict()
    # Fixed set SQL, no unbounded Python row buffer and no first-origin rewrite.
    uow._execute(
        "INSERT INTO epoch_jobs(projection_id,epoch_id,job_id) "
        "SELECT old.projection_id,old.epoch_id,? FROM epoch_jobs old "
        "WHERE old.projection_id=? AND old.job_id=? AND NOT EXISTS "
        "(SELECT 1 FROM epoch_jobs current "
        "WHERE current.projection_id=old.projection_id "
        "AND current.epoch_id=old.epoch_id AND current.job_id=?)",
        (
            recovery.job_id.value,
            projection_id.value,
            original.job_id.value,
            recovery.job_id.value,
        ),
    )


@_mutating
def record_attempt_result(uow, projection_id, row, observed_at, guard):
    _require_row(projection_id, "insert_attempts", row)
    old = _get(uow, projection_id, "insert_attempts", (("attempt_id", row.attempt_id),))
    if old is None:
        _conflict()
    _guard(old.revision, guard)
    _result_time(row, observed_at)
    if row == old:
        return WriteReceipt("replayed", old.attempt_id, old.revision)
    if row.revision != next_revision(old.revision):
        _conflict()
    _result_facts(old, row)
    _result_binding(uow, projection_id, old)
    recovering = None
    if old.state is InsertState.PENDING_RECOVERY:
        recovering = _recovery_claim(uow, projection_id, old, observed_at)
        original = _get(uow, projection_id, "sync_jobs", (("job_id", old.job_id),))
        if (
            original.state is not JobState.BLOCKED
            or original.last_error_code is not ErrorCode.INSERT_RESULT_UNKNOWN
            or _get(uow, projection_id, "job_claims", (("job_id", old.job_id),))
        ):
            _conflict()
        _result_time(row, observed_at, original.updated_at)
    else:
        phase = {
            InsertState.PREPARED: ClaimPhase.PREPARING,
            InsertState.DISPATCH_STARTED: ClaimPhase.DISPATCHING,
            InsertState.KNOWN_INSERTED: ClaimPhase.VERIFYING,
        }[old.state]
        original, claim = _result_job(uow, projection_id, old, phase)
        _result_time(row, observed_at, original.updated_at, claim.acquired_at)
    columns = COLUMNS["insert_attempts"]
    values = _encode_row("insert_attempts", row)
    changed = uow._execute(
        "UPDATE insert_attempts SET "
        + ",".join(c + "=?" for c in columns)
        + " WHERE projection_id=? AND attempt_id=? AND revision=?",
        (*values, projection_id.value, old.attempt_id.value, old.revision.value),
    )
    if changed.rowcount != 1:
        _conflict()
    if (
        old.state is InsertState.DISPATCH_STARTED
        and row.state is InsertState.KNOWN_INSERTED
    ):
        changed = uow._execute(
            "UPDATE job_claims SET phase='verifying' "
            "WHERE projection_id=? AND job_id=? "
            "AND claim_id=? AND phase='dispatching'",
            (projection_id.value, original.job_id.value, old.claim_id.value),
        )
        if changed.rowcount != 1:
            _conflict()
    if row.state in {InsertState.PENDING_RECOVERY, InsertState.NEEDS_ATTENTION}:
        _result_disposition(
            uow,
            projection_id,
            original,
            JobState.BLOCKED
            if row.state is InsertState.PENDING_RECOVERY
            else JobState.NEEDS_ATTENTION,
            row.error_code,
            observed_at,
        )
        _result_recovery(
            uow, projection_id, original, row, observed_at, claimed=recovering
        )
    _audit(
        uow,
        projection_id,
        AuditKind.ATTEMPT_STATE_CHANGED,
        AuditObjectKind.ATTEMPT,
        observed_at,
        local_id=row.attempt_id,
        before_revision=old.revision,
        after_revision=row.revision,
        before_state=old.state,
        after_state=row.state,
        error=row.error_code,
    )
    return WriteReceipt("updated", row.attempt_id, row.revision)


@_mutating
def record_recovery_check(
    uow, projection_id, attempt_id, code, observed_at, retry_at, guard
):
    """Record one owned check; never infer insertion or permission to resend."""
    if type(code) is not ErrorCode or type(observed_at) is not Timestamp:
        _conflict()
    if retry_at is not None and (
        type(retry_at) is not Timestamp or retry_at.value <= observed_at.value
    ):
        _conflict()
    attempt = _get(uow, projection_id, "insert_attempts", (("attempt_id", attempt_id),))
    if attempt is None:
        _conflict()
    _guard(attempt.revision, guard)
    if (
        attempt.state is not InsertState.PENDING_RECOVERY
        or attempt.certainty is not OutcomeCertainty.UNKNOWN
        or attempt.attribution.value != "none"
        or attempt.target_message_id is not None
        or attempt.target_thread_id is not None
    ):
        _conflict()
    _result_binding(uow, projection_id, attempt)
    recovery = _recovery_claim(uow, projection_id, attempt, observed_at)
    original = _get(uow, projection_id, "sync_jobs", (("job_id", attempt.job_id),))
    if (
        original is None
        or original.state is not JobState.BLOCKED
        or original.last_error_code is not ErrorCode.INSERT_RESULT_UNKNOWN
        or original.subject.source_message_id != attempt.source_message_id
        or original.subject.source_thread_id != attempt.source_thread_id
        or original.subject.generation != attempt.generation
        or _get(uow, projection_id, "job_claims", (("job_id", original.job_id),))
    ):
        _conflict()
    revision = next_revision(attempt.revision)
    checks = next_revision(Revision(attempt.recovery_checks.value))
    uow._execute(
        "UPDATE insert_attempts SET recovery_checks=?,next_recovery_at=?,revision=? "
        "WHERE projection_id=? AND attempt_id=? AND revision=?",
        (
            checks.value,
            None if retry_at is None else timestamp_to_sql(retry_at),
            revision.value,
            projection_id.value,
            attempt_id.value,
            attempt.revision.value,
        ),
    )
    _audit(
        uow,
        projection_id,
        AuditKind.ATTEMPT_STATE_CHANGED,
        AuditObjectKind.ATTEMPT,
        observed_at,
        local_id=attempt_id,
        before_revision=attempt.revision,
        after_revision=revision,
        before_state=attempt.state,
        after_state=attempt.state,
        error=code,
    )
    if retry_at is None:
        updated = _get(
            uow, projection_id, "insert_attempts", (("attempt_id", attempt_id),)
        )
        return record_attempt_result(
            uow,
            projection_id,
            replace(
                updated,
                state=InsertState.NEEDS_ATTENTION,
                error_code=code,
                revision=next_revision(updated.revision),
            ),
            observed_at,
            RevisionGuard(revision),
        )
    from .jobs import defer_job

    defer_job(
        uow,
        projection_id,
        recovery.job_id,
        "retry_wait",
        code,
        retry_at,
        RevisionGuard(recovery.revision),
    )
    return WriteReceipt("updated", attempt_id, revision)


@_mutating
def reconcile_orphaned_attempt(uow, projection_id, attempt_id, observed_at):
    """Materialize recovery for a dispatch marker whose claim was lost."""

    if type(attempt_id) is not LocalId or type(observed_at) is not Timestamp:
        _conflict()
    old = _get(uow, projection_id, "insert_attempts", (("attempt_id", attempt_id),))
    if old is None or old.state is not InsertState.DISPATCH_STARTED:
        _conflict()
    original = _get(uow, projection_id, "sync_jobs", (("job_id", old.job_id),))
    if (
        original is None
        or original.kind is not JobKind.PROJECT_MESSAGE
        or original.state not in {JobState.BLOCKED, JobState.NEEDS_ATTENTION}
        or _get(uow, projection_id, "job_claims", (("job_id", old.job_id),)) is not None
    ):
        _conflict()
    row = replace(
        old,
        state=InsertState.PENDING_RECOVERY,
        certainty=OutcomeCertainty.UNKNOWN,
        error_code=ErrorCode.INSERT_RESULT_UNKNOWN,
        result_at=old.result_at or observed_at,
        revision=next_revision(old.revision),
    )
    _result_time(row, observed_at)
    _result_facts(old, row)
    _result_binding(uow, projection_id, old)
    values = _encode_row("insert_attempts", row)
    changed = uow._execute(
        "UPDATE insert_attempts SET "
        + ",".join(column + "=?" for column in COLUMNS["insert_attempts"])
        + " WHERE projection_id=? AND attempt_id=? AND revision=?",
        (*values, projection_id.value, old.attempt_id.value, old.revision.value),
    )
    if changed.rowcount != 1:
        _conflict()
    _result_disposition(
        uow,
        projection_id,
        original,
        JobState.BLOCKED,
        ErrorCode.INSERT_RESULT_UNKNOWN,
        observed_at,
    )
    _result_recovery(uow, projection_id, original, row, observed_at)
    _audit(
        uow,
        projection_id,
        AuditKind.ATTEMPT_STATE_CHANGED,
        AuditObjectKind.ATTEMPT,
        observed_at,
        local_id=row.attempt_id,
        before_revision=old.revision,
        after_revision=row.revision,
        before_state=old.state,
        after_state=row.state,
        error=row.error_code,
    )
    return WriteReceipt("updated", row.attempt_id, row.revision)
