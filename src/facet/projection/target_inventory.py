"""Cycle-local target precondition; labels/From classify, never prove ownership."""

from contextlib import suppress
from email.utils import getaddresses

from facet.contracts import BindingState, ErrorCode, Role
from facet.db.codecs import StorageFailure
from facet.db.repositories import reads
from facet.projection.rules import normalize_sender


class TargetInventory:
    def __init__(self, owner, target, *, progress=None):
        self.owner, self.target, self.progress = owner, target, progress
        self.checked = False
        self.missing = 0

    def require(self):
        if self.checked:
            return
        with self.owner.session.transaction() as uow:
            source = reads.get_binding(uow, self.owner.projection_id, Role.SOURCE)
            target = reads.get_binding(uow, self.owner.projection_id, Role.TARGET)
            if any(
                binding is None or binding.state is not BindingState.VERIFIED
                for binding in (source, target)
            ):
                raise StorageFailure(ErrorCode.BINDING_PENDING)
            source_address = source.verified_address.value
            projection = self.owner.projection_id.value
            mapped = {
                row[0]
                for row in uow._execute(
                    "SELECT target_message_id FROM message_mappings "
                    "WHERE projection_id=?",
                    (projection,),
                ).fetchall()
            }
            owned = mapped | {
                row[0]
                for row in uow._execute(
                    "SELECT target_message_id FROM insert_attempts "
                    "WHERE projection_id=? AND certainty='inserted' "
                    "AND attribution='direct_response' "
                    "AND target_message_id IS NOT NULL",
                    (projection,),
                ).fetchall()
            }
            # Retained proven mappings remain owned after explicit repair.
            owned.update(
                row[0]
                for row in uow._execute(
                    "SELECT target_message_id FROM target_ownership "
                    "WHERE projection_id=?",
                    (projection,),
                ).fetchall()
            )
        present, unexpected = set(), 0
        for page in self.target.inventory_pages():
            for message_id in page:
                if message_id.value in present:
                    continue
                present.add(message_id.value)
                if message_id.value in owned:
                    continue
                labels, headers = self.target.outbound_metadata(message_id)
                parsed = getaddresses(headers)
                permitted = False
                if len(headers) == len(parsed) == 1 and set(labels) & {"SENT", "DRAFT"}:
                    with suppress(ValueError):
                        permitted = normalize_sender(parsed[0][1]) == normalize_sender(
                            source_address
                        )
                unexpected += not permitted
                if self.progress:
                    self.progress()
            if self.progress:
                self.progress()
        from facet.status.logging import OperationStage, emit_operation

        self.missing = len(mapped - present)
        emit_operation(OperationStage.TARGET_INVENTORY, count=len(present))
        if self.missing:
            emit_operation(
                OperationStage.TARGET_INVENTORY, code=ErrorCode.TARGET_MISSING
            )
        if unexpected:
            emit_operation(
                OperationStage.TARGET_INVENTORY, code=ErrorCode.ATTRIBUTION_UNKNOWN
            )
            raise StorageFailure(ErrorCode.ATTRIBUTION_UNKNOWN)
        self.checked = True
