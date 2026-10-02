"""Append-only closed metadata. These are not arbitrary logs or payload stores."""

from uuid import uuid4

from facet.contracts import LocalId, Revision

from ..codecs import AuditObjectKind
from ..models import AuditEventRow, WriteReceipt
from .base import _conflict, _get, _insert, _mutating, _require_row


@_mutating
def append_audit(uow, projection_id, row):
    _require_row(projection_id, "audit_events", row)
    table, selector = {
        AuditObjectKind.PROJECTION: ("projections", ()),
        AuditObjectKind.RULE: ("rules", (("rule_id", row.local_object_id),)),
        AuditObjectKind.THREAD: (
            "tracked_threads",
            (("source_thread_id", row.source_thread_id),),
        ),
        AuditObjectKind.EPOCH: ("epochs", (("epoch_id", row.local_object_id),)),
        AuditObjectKind.EVENT: ("source_events", (("event_id", row.local_object_id),)),
        AuditObjectKind.JOB: ("sync_jobs", (("job_id", row.local_object_id),)),
        AuditObjectKind.ATTEMPT: (
            "insert_attempts",
            (("attempt_id", row.local_object_id),),
        ),
        AuditObjectKind.MAPPING: (
            "message_mappings",
            (("source_message_id", row.source_message_id),),
        ),
    }[row.object_kind]
    if _get(uow, projection_id, table, selector) is None:
        _conflict()
    _insert(uow, projection_id, "audit_events", row)
    return WriteReceipt("created", row.audit_id, Revision(0))


@_mutating
def append_error(uow, projection_id, row):
    _require_row(projection_id, "error_events", row)
    if (
        row.job_id is not None
        and _get(uow, projection_id, "sync_jobs", (("job_id", row.job_id),)) is None
    ):
        _conflict()
    if row.attempt_id is not None:
        attempt = _get(
            uow, projection_id, "insert_attempts", (("attempt_id", row.attempt_id),)
        )
        if attempt is None or row.job_id is not None and attempt.job_id != row.job_id:
            _conflict()
    _insert(uow, projection_id, "error_events", row)
    return WriteReceipt("created", row.error_id, Revision(0))


def _audit(
    uow,
    projection_id,
    kind,
    object_kind,
    observed_at,
    *,
    local_id=None,
    thread_id=None,
    message_id=None,
    before_revision=None,
    after_revision=None,
    before_state=None,
    after_state=None,
    error=None,
):
    append_audit(
        uow,
        projection_id,
        AuditEventRow(
            projection_id,
            LocalId(uuid4().hex),
            kind,
            object_kind,
            local_id,
            thread_id,
            message_id,
            before_revision,
            after_revision,
            before_state,
            after_state,
            error,
            observed_at,
        ),
    )
