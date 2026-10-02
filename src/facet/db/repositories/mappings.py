"""Verified mapping facts and bounded target audit; never remote repair."""

from facet.contracts import (
    ClaimPhase,
    InsertState,
    JobKind,
    JobState,
    LocalId,
    OutcomeCertainty,
    ProviderId,
    Revision,
    Timestamp,
    Visibility,
)

from ..codecs import (
    AttributionKind,
    AuditKind,
    AuditObjectKind,
    invalid,
    next_revision,
    timestamp_to_sql,
)
from ..models import WriteReceipt
from .audit import _audit
from .base import _conflict, _get, _guard, _insert, _mutating, _query, _require_row
from .intents import (
    _ATTENTION_ERRORS,
    _recovery_identity,
    _result_binding,
    _result_job,
)
from .serialization import COLUMNS, _decode_row


def _target_provenance(uow, projection_id, row, verified_at):
    first = _get(
        uow,
        projection_id,
        "insert_attempts",
        (("attempt_id", row.first_attempt_id),),
    )
    if (
        first is None
        or first.state is not InsertState.VERIFIED
        or first.source_thread_id != row.source_thread_id
        or first.target_thread_id != row.target_thread_id
        or first.verified_at != row.created_at
        or row.created_at.value > verified_at.value
    ):
        _conflict()
    records = _query(
        uow,
        "SELECT "
        + ",".join(COLUMNS["mapping_history"])
        + " FROM mapping_history WHERE projection_id=? AND attempt_id=? "
        "AND source_message_id=?",
        (projection_id.value, first.attempt_id.value, first.source_message_id.value),
        maximum=1,
    )
    if not records:
        _conflict()
    history = _decode_row("mapping_history", records[0])
    if (
        history.source_thread_id != first.source_thread_id
        or history.target_message_id != first.target_message_id
        or history.target_thread_id != first.target_thread_id
        or history.verified_at != first.verified_at
    ):
        _conflict()


def _mapping_inputs(attempt, mapping, history, ownership, thread_target):
    if (
        mapping.source_message_id != attempt.source_message_id
        or mapping.source_thread_id != attempt.source_thread_id
        or mapping.attempt_id != attempt.attempt_id
        or mapping.target_message_id != attempt.target_message_id
        or mapping.target_thread_id != attempt.target_thread_id
        or mapping.mapping_revision != Revision(1)
        or history.source_message_id != mapping.source_message_id
        or history.source_thread_id != mapping.source_thread_id
        or history.attempt_id != mapping.attempt_id
        or history.target_message_id != mapping.target_message_id
        or history.target_thread_id != mapping.target_thread_id
        or history.mapping_revision != mapping.mapping_revision
        or history.verified_at != mapping.verified_at
        or history.superseded_at is not None
        or ownership.target_message_id != mapping.target_message_id
        or ownership.source_message_id != mapping.source_message_id
        or ownership.first_attempt_id != attempt.attempt_id
        or ownership.recorded_at != mapping.verified_at
        or thread_target.source_thread_id != mapping.source_thread_id
        or thread_target.target_thread_id != mapping.target_thread_id
    ):
        _conflict()


def _mapping_job(uow, projection_id, attempt):
    job = _get(uow, projection_id, "sync_jobs", (("job_id", attempt.job_id),))
    if (
        job is None
        or job.kind is not JobKind.PROJECT_MESSAGE
        or job.subject.source_message_id != attempt.source_message_id
        or job.subject.source_thread_id != attempt.source_thread_id
        or job.subject.generation != attempt.generation
    ):
        _conflict()
    return job


def _mapping_branch(uow, projection_id, attempt, original, verified_at):
    _, recovery = _recovery_identity(uow, projection_id, attempt, verified_at)
    original_claim = _get(
        uow, projection_id, "job_claims", (("job_id", original.job_id),)
    )
    recovery_claim = (
        _get(uow, projection_id, "job_claims", (("job_id", recovery.job_id),))
        if recovery is not None
        else None
    )
    if attempt.state is InsertState.KNOWN_INSERTED:
        original, acquired = _result_job(
            uow, projection_id, attempt, ClaimPhase.VERIFYING
        )
        if recovery is not None:
            _conflict()
        return original, acquired, None
    if attempt.state is InsertState.NEEDS_ATTENTION:
        if (
            attempt.error_code not in _ATTENTION_ERRORS
            or original.state is not JobState.NEEDS_ATTENTION
            or original_claim is not None
            or original.next_attempt_at is not None
            or original.last_error_code != attempt.error_code
            or recovery is None
            or recovery.state is not JobState.NEEDS_ATTENTION
            or recovery_claim is not None
            or recovery.last_error_code != attempt.error_code
        ):
            _conflict()
        return original, None, recovery
    if attempt.state is InsertState.VERIFIED:
        if (
            original.state is not JobState.COMPLETED
            or original_claim is not None
            or original.next_attempt_at is not None
            or original.last_error_code is not None
            or original.updated_at != verified_at
            or attempt.error_code is not None
            or attempt.next_recovery_at is not None
            or recovery is not None
            and (
                recovery.state is not JobState.COMPLETED
                or recovery_claim is not None
                or recovery.last_error_code is not None
                or recovery.updated_at != verified_at
            )
        ):
            _conflict()
        return original, None, recovery
    _conflict()


def _complete_mapping_job(uow, projection_id, job, verified_at):
    revision = next_revision(job.revision)
    changed = uow._execute(
        "UPDATE sync_jobs SET state='completed',revision=?,updated_at=?,"
        "next_attempt_at=NULL,last_error_code=NULL WHERE projection_id=? "
        "AND job_id=? AND revision=?",
        (
            revision.value,
            timestamp_to_sql(verified_at),
            projection_id.value,
            job.job_id.value,
            job.revision.value,
        ),
    ).rowcount
    if changed != 1:
        _conflict()
    _audit(
        uow,
        projection_id,
        AuditKind.JOB_STATE_CHANGED,
        AuditObjectKind.JOB,
        verified_at,
        local_id=job.job_id,
        before_revision=job.revision,
        after_revision=revision,
        before_state=job.state,
        after_state=JobState.COMPLETED,
    )


@_mutating
def verify_mapping(
    uow, projection_id, attempt_id, mapping, history, ownership, thread_target, guard
):
    if type(attempt_id) is not LocalId:
        invalid()
    for table, row in (
        ("message_mappings", mapping),
        ("mapping_history", history),
        ("target_ownership", ownership),
        ("thread_targets", thread_target),
    ):
        _require_row(projection_id, table, row)
    attempt = _get(uow, projection_id, "insert_attempts", (("attempt_id", attempt_id),))
    if attempt is None:
        _conflict()
    _guard(attempt.revision, guard)
    if (
        attempt.certainty is not OutcomeCertainty.INSERTED
        or attempt.attribution is not AttributionKind.DIRECT_RESPONSE
        or attempt.target_message_id is None
        or attempt.target_thread_id is None
        or attempt.semantic_digest is None
        or attempt.semantic_version is None
        or attempt.dispatch_started_at is None
        or attempt.result_at is None
    ):
        _conflict()
    _result_binding(uow, projection_id, attempt)
    _mapping_inputs(attempt, mapping, history, ownership, thread_target)
    original = _mapping_job(uow, projection_id, attempt)
    original, acquired, recovery = _mapping_branch(
        uow, projection_id, attempt, original, mapping.verified_at
    )
    if any(
        t is not None and mapping.verified_at.value < t.value
        for t in (
            attempt.prepared_at,
            attempt.dispatch_started_at,
            attempt.result_at,
            original.updated_at,
            acquired.acquired_at if acquired is not None else None,
            recovery.updated_at if recovery is not None else None,
        )
    ):
        _conflict()
    current = _get(
        uow,
        projection_id,
        "message_mappings",
        (("source_message_id", attempt.source_message_id),),
    )
    target = _get(
        uow,
        projection_id,
        "thread_targets",
        (
            ("source_thread_id", attempt.source_thread_id),
            ("target_thread_id", attempt.target_thread_id),
        ),
    )
    if attempt.state is InsertState.VERIFIED:
        if (
            current != mapping
            or attempt.verified_at != mapping.verified_at
            or _get(
                uow,
                projection_id,
                "mapping_history",
                (
                    ("source_message_id", attempt.source_message_id),
                    ("mapping_revision", mapping.mapping_revision),
                ),
            )
            != history
            or _get(
                uow,
                projection_id,
                "target_ownership",
                (("target_message_id", attempt.target_message_id),),
            )
            != ownership
            or target != thread_target
            or attempt.visibility is Visibility.UNKNOWN
            or mapping.last_audit_at is None
            and mapping.visibility is not attempt.visibility
        ):
            _conflict()
        _target_provenance(uow, projection_id, thread_target, mapping.verified_at)
        return WriteReceipt("replayed", attempt_id, attempt.revision)
    if (
        current is not None
        or mapping.last_audit_at is not None
        or mapping.target_present is not None
        or mapping.visibility is Visibility.UNKNOWN
        or attempt.visibility is not Visibility.UNKNOWN
        and attempt.visibility is not mapping.visibility
        or _query(
            uow,
            "SELECT 1 FROM mapping_history WHERE projection_id=? "
            "AND source_message_id=? LIMIT 1",
            (projection_id.value, attempt.source_message_id.value),
            maximum=1,
        )
        or _get(
            uow,
            projection_id,
            "target_ownership",
            (("target_message_id", attempt.target_message_id),),
        )
        is not None
    ):
        _conflict()
    if target is not None:
        if target != thread_target:
            _conflict()
        _target_provenance(uow, projection_id, target, mapping.verified_at)
    else:
        anchor = bool(
            _query(
                uow,
                "SELECT 1 FROM thread_targets WHERE projection_id=? "
                "AND source_thread_id=? AND anchor=1",
                (projection_id.value, attempt.source_thread_id.value),
                maximum=1,
            )
        )
        if (
            thread_target.first_attempt_id != attempt_id
            or thread_target.created_at != mapping.verified_at
            or thread_target.anchor is anchor
        ):
            _conflict()
    revision = next_revision(attempt.revision)
    next_revision(original.revision)
    if recovery is not None:
        next_revision(recovery.revision)
    for table, row in (
        ("mapping_history", history),
        ("message_mappings", mapping),
        ("target_ownership", ownership),
    ):
        _insert(uow, projection_id, table, row)
    if target is None:
        _insert(uow, projection_id, "thread_targets", thread_target)
    changed = uow._execute(
        "UPDATE insert_attempts SET state='verified',verified_at=?,visibility=?,"
        "error_code=NULL,next_recovery_at=NULL,revision=? WHERE projection_id=? "
        "AND attempt_id=? AND revision=?",
        (
            timestamp_to_sql(mapping.verified_at),
            mapping.visibility.value,
            revision.value,
            projection_id.value,
            attempt_id.value,
            attempt.revision.value,
        ),
    ).rowcount
    if changed != 1:
        _conflict()
    if acquired is not None:
        deleted = uow._execute(
            "DELETE FROM job_claims WHERE projection_id=? AND job_id=? AND claim_id=?",
            (projection_id.value, original.job_id.value, acquired.claim_id.value),
        ).rowcount
        if deleted != 1:
            _conflict()
    _complete_mapping_job(uow, projection_id, original, mapping.verified_at)
    if recovery is not None:
        _complete_mapping_job(uow, projection_id, recovery, mapping.verified_at)
    _audit(
        uow,
        projection_id,
        AuditKind.ATTEMPT_STATE_CHANGED,
        AuditObjectKind.ATTEMPT,
        mapping.verified_at,
        local_id=attempt_id,
        before_revision=attempt.revision,
        after_revision=revision,
        before_state=attempt.state,
        after_state=InsertState.VERIFIED,
    )
    _audit(
        uow,
        projection_id,
        AuditKind.MAPPING_VERIFIED,
        AuditObjectKind.MAPPING,
        mapping.verified_at,
        message_id=attempt.source_message_id,
        after_revision=mapping.mapping_revision,
    )
    return WriteReceipt("updated", attempt_id, revision)


@_mutating
def record_target_audit(
    uow, projection_id, source_message_id, present, visibility, audited_at, guard
):
    if (
        type(source_message_id) is not ProviderId
        or type(present) is not bool
        or type(visibility) is not Visibility
        or type(audited_at) is not Timestamp
    ):
        invalid()
    current = _get(
        uow,
        projection_id,
        "message_mappings",
        (("source_message_id", source_message_id),),
    )
    if current is None:
        _conflict()
    _guard(current.mapping_revision, guard)
    if (
        current.last_audit_at is not None
        and audited_at.value < current.last_audit_at.value
    ):
        _conflict()
    if (
        current.last_audit_at == audited_at
        and current.target_present is present
        and current.visibility is visibility
    ):
        return WriteReceipt("replayed", source_message_id, current.mapping_revision)
    changed = uow._execute(
        "UPDATE message_mappings SET target_present=?,visibility=?,last_audit_at=? "
        "WHERE projection_id=? AND source_message_id=? AND mapping_revision=?",
        (
            int(present),
            visibility.value,
            timestamp_to_sql(audited_at),
            projection_id.value,
            source_message_id.value,
            current.mapping_revision.value,
        ),
    ).rowcount
    if changed != 1:
        _conflict()
    # An audit changes presence/visibility observations, not mapping identity,
    # attempt certainty, admission, job state or authorization to repair.
    return WriteReceipt("updated", source_message_id, current.mapping_revision)
