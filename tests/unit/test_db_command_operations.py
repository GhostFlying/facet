"""M2 owner transaction: typed preview/start lineage and replay guards."""

from dataclasses import replace
from datetime import timedelta

import pytest
from fakes.privacy import inspect_files, inspect_sqlite, markers
from test_command_bootstrap_storage import storage
from test_db_history import poll
from test_db_schema import NOW, P, lid

from facet.contracts import (
    EpochKind,
    ErrorCode,
    ProviderId,
    Revision,
    Sha256Hex,
    Timestamp,
)
from facet.db.codecs import PollOrigin, StorageFailure
from facet.db.command_records import BackfillPreviewRequest, BackfillStartRequest
from facet.db.command_store import _find_backfill, preview_backfill, start_backfill
from facet.db.models import RevisionGuard
from facet.db.repositories import history


def preview_request(n, *, scope="a" * 64):
    return BackfillPreviewRequest(
        lid(n),
        lid(n + 1),
        Timestamp(NOW.value - timedelta(days=180)),
        NOW,
        Timestamp(NOW.value - timedelta(minutes=1)),
        Sha256Hex(scope),
        Timestamp(NOW.value + timedelta(days=1)),
        Revision(0),
        NOW,
    )


def start_request(n, preview_id, *, fence_at=None, accepted_at=None, history_id="H0"):
    fence_at = fence_at or Timestamp(NOW.value + timedelta(minutes=2))
    accepted_at = accepted_at or Timestamp(NOW.value + timedelta(minutes=3))
    return BackfillStartRequest(
        lid(n),
        lid(n + 1),
        preview_id,
        lid(n + 2),
        ProviderId(history_id),
        fence_at,
        accepted_at,
    )


def test_preview_request_replay_and_conflict_are_metadata_only():
    with storage() as (_, _, connection, session, _, *_):
        with session.transaction() as uow:
            preview = preview_backfill(uow, P, preview_request(100))
            assert _find_backfill(uow, P, lid(3), lid(101))[0] == preview
        with session.transaction() as uow:
            assert (
                preview_backfill(
                    uow, P, replace(preview_request(102), request_nonce=lid(101))
                )
                == preview
            )
        before = connection.execute(
            "SELECT revision,updated_at,digest FROM operations WHERE operation_id=?",
            (preview.operation_id.value,),
        ).fetchone()
        with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
            preview_backfill(
                uow,
                P,
                replace(preview_request(104, scope="b" * 64), request_nonce=lid(101)),
            )
        assert caught.value.code is ErrorCode.REQUEST_CONFLICT
        assert (
            connection.execute(
                "SELECT revision,updated_at,digest FROM operations "
                "WHERE operation_id=?",
                (preview.operation_id.value,),
            ).fetchone()
            == before
        )
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM history_polls").fetchone() == (
            0,
        )
        assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)


def test_start_is_one_owner_transaction_and_replays_lost_response():
    with storage() as (_, _, connection, session, _, *_):
        with session.transaction() as uow:
            preview = preview_backfill(uow, P, preview_request(110))
            request = start_request(112, preview.operation_id)
            start, epoch = start_backfill(uow, P, request)
        assert connection.execute(
            "SELECT COUNT(*) FROM operation_backfill"
        ).fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM epoch_partitions"
        ).fetchone() == (1,)
        assert epoch.decision.preview_id == preview.operation_id
        assert epoch.fence_recorded_at.value > epoch.discovery_cutoff.value
        replay_request = replace(request, operation_id=lid(116), epoch_id=lid(118))
        with session.transaction() as uow:
            replay, replay_epoch = start_backfill(uow, P, replay_request)
        assert replay.operation_id == start.operation_id
        assert replay_epoch.epoch_id == epoch.epoch_id
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (1,)
        assert connection.execute("SELECT fence_history_id FROM epochs").fetchone() == (
            "H0",
        )


def test_start_rejects_invalid_fence_without_publishing():
    with storage() as (_, _, connection, session, _, *_):
        with session.transaction() as uow:
            preview = preview_backfill(uow, P, preview_request(120))
        with pytest.raises(ValueError):
            start_request(122, preview.operation_id, history_id="")
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (0,)


def test_start_rolls_back_operation_and_h0_when_epoch_guard_fails():
    with storage() as (_, _, connection, session, _, *_):
        with session.transaction() as uow:
            preview = preview_backfill(uow, P, preview_request(130))
        # The request is syntactically valid but its fence predates the
        # discovery cutoff.  Epoch validation runs after the journal insert;
        # the owner transaction must remove both the start child and epoch.
        early_fence = Timestamp(NOW.value - timedelta(minutes=2))
        request = start_request(132, preview.operation_id, fence_at=early_fence)
        with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
            start_backfill(uow, P, request)
        assert caught.value.code is ErrorCode.REQUEST_CONFLICT
        assert connection.execute(
            "SELECT COUNT(*) FROM operations WHERE command='backfill_start'"
        ).fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (0,)
        assert connection.execute(
            "SELECT cursor,active_poll_id FROM history_checkpoints"
        ).fetchone() == (None, None)


def test_start_error_is_fixed_and_private_h0_text_stays_out_of_metadata():
    sentinel = "SYNTHETIC_PRIVATE_PROVIDER_EXCEPTION"
    with storage() as (root, _, connection, session, _, *_):
        with session.transaction() as uow:
            preview = preview_backfill(uow, P, preview_request(140))
        request = start_request(
            142,
            preview.operation_id,
            fence_at=Timestamp(NOW.value - timedelta(minutes=2)),
            history_id=sentinel,
        )
        with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
            start_backfill(uow, P, request)
        assert caught.value.code is ErrorCode.REQUEST_CONFLICT
        assert str(caught.value) == ErrorCode.REQUEST_CONFLICT.value
        assert sentinel not in str(caught.value)
        assert connection.execute(
            "SELECT COUNT(*) FROM epochs WHERE fence_history_id=?", (sentinel,)
        ).fetchone() == (0,)
        inspect_sqlite(connection, markers())
        inspect_files(
            root, [path for path in root.iterdir() if path.is_file()], markers()
        )


def test_initial_history_poll_consumes_owner_committed_h0_epoch():
    with storage() as (_, _, connection, session, _, *_):
        with session.transaction() as uow:
            preview = preview_backfill(uow, P, preview_request(150))
            _, epoch = start_backfill(uow, P, start_request(152, preview.operation_id))
        assert epoch.kind is EpochKind.INITIAL_BACKFILL
        value = poll(
            155,
            origin=PollOrigin.INITIAL_EPOCH,
            origin_epoch_id=epoch.epoch_id,
            cursor=epoch.fence_history_id,
        )
        with session.transaction() as uow:
            history.begin_history_poll(uow, P, value, RevisionGuard(Revision(0)))
        assert connection.execute(
            "SELECT active_poll_id,cursor FROM history_checkpoints"
        ).fetchone() == (value.poll_id.value, None)
