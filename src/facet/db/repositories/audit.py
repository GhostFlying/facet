"""Append-only closed metadata. These are not arbitrary logs or payload stores."""

from uuid import uuid4

from facet.contracts import LocalId, Revision

from ..models import AuditEventRow, WriteReceipt
from .base import _insert, _mutating


@_mutating
def append_audit(uow, projection_id, row):
    _insert(uow, projection_id, "audit_events", row)
    return WriteReceipt("created", row.audit_id, Revision(0))


@_mutating
def append_error(uow, projection_id, row):
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
