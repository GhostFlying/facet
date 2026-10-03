"""M2 backfill operation journal: typed replay and preview lineage guards."""

from dataclasses import replace
from datetime import timedelta

import pytest
from test_command_bootstrap_storage import storage
from test_db_schema import NOW, P, lid

from facet.contracts import (
    Count,
    EpochKind,
    EpochState,
    ErrorCode,
    OperationState,
    PartitionProgress,
    PartitionState,
    PreviewPurpose,
    ProviderId,
    Revision,
    Sha256Hex,
    Timestamp,
)
from facet.contracts.records import (
    EpochDecisionRefBackfillStart,
    PartitionRefSourceWindow,
)
from facet.db.codecs import StorageFailure
from facet.db.command_records import (
    BackfillPayloadRow,
    LocalCommandKind,
    OperationRow,
)
from facet.db.command_store import (
    _backfill_digest,
    _find_backfill,
    _insert_backfill,
)
from facet.db.keys import partition_key
from facet.db.models import EpochPartitionRow, EpochRow
from facet.db.repositories import epochs


def operation(command, operation_id, nonce, preview=None, *, confirmation=False):
    return OperationRow(
        P,
        operation_id,
        lid(3),
        nonce,
        command,
        1,
        1,
        Sha256Hex("0" * 64),
        OperationState.ACCEPTED,
        Revision(1),
        NOW,
        NOW,
        None,
        None,
        False,
        Revision(1),
        Revision(0),
        preview,
        confirmation,
        False,
    )


def payload(operation_id, *, preview=None, scope="a" * 64):
    end = NOW
    start = Timestamp(NOW.value - timedelta(days=180))
    return BackfillPayloadRow(
        P,
        operation_id,
        PreviewPurpose.START_BACKFILL,
        preview,
        Revision(0),
        start,
        end,
        end,
        Sha256Hex(scope),
        Timestamp(NOW.value + timedelta(days=1)),
        Revision(0),
    )


def sealed_operation(command, operation_id, nonce, preview=None, *, confirmation=False):
    row = operation(command, operation_id, nonce, preview, confirmation=confirmation)
    child = payload(operation_id, preview=preview)
    return replace(row, digest=_backfill_digest(row, child)), child


def test_preview_insert_lookup_and_same_key_conflict_is_metadata_only():
    with storage() as (_, _, connection, session, _, *_):
        preview, child = sealed_operation(
            LocalCommandKind.BACKFILL_PREVIEW, lid(100), lid(101)
        )
        with session.transaction() as uow:
            _insert_backfill(uow, P, preview, child)
            assert _find_backfill(uow, P, lid(3), lid(101)) == (preview, child)
        replay_operation = replace(preview, operation_id=lid(102))
        replay_child = replace(child, operation_id=replay_operation.operation_id)
        replay_operation = replace(
            replay_operation, digest=_backfill_digest(replay_operation, replay_child)
        )
        with session.transaction() as uow:
            assert _insert_backfill(uow, P, replay_operation, replay_child) == preview
        assert connection.execute("SELECT COUNT(*) FROM operations").fetchone() == (3,)
        before = connection.execute(
            "SELECT revision,updated_at,digest FROM operations WHERE operation_id=?",
            (preview.operation_id.value,),
        ).fetchone()
        with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
            changed = replace(child, scope_digest=Sha256Hex("b" * 64))
            changed_operation = replace(
                preview, digest=_backfill_digest(preview, changed)
            )
            _insert_backfill(uow, P, changed_operation, changed)
        assert caught.value.code is ErrorCode.REQUEST_CONFLICT
        assert (
            connection.execute(
                "SELECT revision,updated_at,digest FROM operations "
                "WHERE operation_id=?",
                (preview.operation_id.value,),
            ).fetchone()
            == before
        )


def test_start_requires_existing_preview_and_exact_scope_lineage():
    with storage() as (_, _, connection, session, _, *_):
        preview, preview_child = sealed_operation(
            LocalCommandKind.BACKFILL_PREVIEW, lid(110), lid(111)
        )
        start, start_child = sealed_operation(
            LocalCommandKind.BACKFILL_START,
            lid(112),
            lid(113),
            preview=preview.operation_id,
            confirmation=True,
        )
        with session.transaction() as uow:
            _insert_backfill(uow, P, preview, preview_child)
            _insert_backfill(uow, P, start, start_child)
        assert connection.execute(
            "SELECT COUNT(*) FROM operation_backfill"
        ).fetchone() == (2,)
        with session.transaction() as uow:
            with pytest.raises(StorageFailure) as caught:
                _insert_backfill(
                    uow,
                    P,
                    replace(
                        start,
                        operation_id=lid(114),
                        request_nonce=lid(115),
                        expected_preview_id=lid(999),
                    ),
                    replace(start_child, operation_id=lid(114)),
                )
            assert caught.value.code is ErrorCode.INVALID_INPUT


def test_journal_backed_initial_epoch_requires_real_h0_and_preview():
    with storage() as (_, _, connection, session, _, *_):
        preview, preview_child = sealed_operation(
            LocalCommandKind.BACKFILL_PREVIEW, lid(120), lid(121)
        )
        start, start_child = sealed_operation(
            LocalCommandKind.BACKFILL_START,
            lid(122),
            lid(123),
            preview=preview.operation_id,
            confirmation=True,
        )
        with session.transaction() as uow:
            _insert_backfill(uow, P, preview, preview_child)
            _insert_backfill(uow, P, start, start_child)
        epoch = EpochRow(
            P,
            lid(124),
            EpochKind.INITIAL_BACKFILL,
            EpochState.PREPARED,
            Revision(0),
            NOW,
            start_child.window_start,
            start_child.window_end,
            start_child.discovery_cutoff,
            EpochDecisionRefBackfillStart(
                "backfill_start", start.operation_id, preview.operation_id, Revision(0)
            ),
            None,
            None,
            ProviderId("H0"),
            NOW,
            None,
            False,
            None,
        )
        ref = PartitionRefSourceWindow("source_window")
        partition = EpochPartitionRow(
            P,
            epoch.epoch_id,
            partition_key(P, ref),
            PartitionProgress(
                ref, PartitionState.NOT_STARTED, Count(0), Count(0), None, None
            ),
            Revision(0),
        )
        with session.transaction() as uow:
            receipt = epochs.start_epoch(uow, P, epoch, (partition,))
        assert receipt.object_id == epoch.epoch_id
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (1,)
        assert connection.execute("SELECT fence_history_id FROM epochs").fetchone() == (
            "H0",
        )
