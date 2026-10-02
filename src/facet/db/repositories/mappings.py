"""Verified mapping facts and bounded target audit; never remote repair."""

from facet.contracts import ProviderId, Timestamp, Visibility

from ..codecs import invalid, timestamp_to_sql
from ..models import WriteReceipt
from .base import _conflict, _get, _guard, _mutating


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
