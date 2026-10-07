"""M2 owner transaction: typed preview/start lineage and replay guards."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import pytest
from fakes.privacy import inspect_files, inspect_sqlite, markers
from test_command_bootstrap_storage import storage
from test_db_history import page, poll
from test_db_repositories import T, admit, job, publish, ready_test_metadata
from test_db_schema import NOW, P, lid

from facet.contracts import (
    Count,
    EpochKind,
    EpochState,
    ErrorCode,
    Generation,
    PartitionState,
    ProviderId,
    Revision,
    Sha256Hex,
    Timestamp,
)
from facet.db.codecs import PollOrigin, StorageFailure, ThreadStopReason
from facet.db.command_records import (
    BackfillPreviewRequest,
    BackfillStartRequest,
)
from facet.db.command_store import _find_backfill, preview_backfill, start_backfill
from facet.db.models import RevisionGuard
from facet.db.repositories import epochs, history, policy, reads
from facet.db.repositories.base import _get


@contextmanager
def owner_storage():
    import facet.db.command_store as command_store

    with (
        patch.object(command_store, "_owner_now", return_value=NOW),
        storage() as value,
    ):
        ready_test_metadata(value[2], value[3])
        yield value


def preview_request(n, *, scope="a" * 64):
    return BackfillPreviewRequest(
        lid(n),
        lid(n + 1),
        Timestamp(NOW.value.replace(month=4, day=1)),
        NOW,
        Timestamp(NOW.value - timedelta(minutes=1)),
        Sha256Hex(scope),
        Timestamp(NOW.value + timedelta(minutes=10)),
        Revision(0),
        NOW,
    )


def start_request(n, preview_id, *, fence_at=None, accepted_at=None, history_id="H0"):
    fence_at = fence_at or NOW
    accepted_at = accepted_at or NOW
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
    with owner_storage() as (_, _, connection, session, _, *_):
        request = preview_request(100)
        with session.transaction() as uow:
            preview = preview_backfill(uow, P, request)
            assert _find_backfill(uow, P, lid(3), lid(101))[0] == preview
        with session.transaction() as uow:
            assert (
                preview_backfill(uow, P, replace(request, operation_id=lid(102)))
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
    with owner_storage() as (_, _, connection, session, _, *_):
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
        # A lost first response can be looked up after preview expiry; the
        # committed request is authoritative and must not rerun H0 work.
        late_replay = replace(
            request,
            operation_id=lid(120),
            epoch_id=lid(121),
            accepted_at=Timestamp(NOW.value + timedelta(days=2)),
        )
        with session.transaction() as uow:
            late, late_epoch = start_backfill(uow, P, late_replay)
        assert late.operation_id == start.operation_id
        assert late_epoch.epoch_id == epoch.epoch_id


def test_fence_at_discovery_cutoff_is_valid_when_other_guards_match():
    with owner_storage() as (_, _, connection, session, _, *_):
        with session.transaction() as uow:
            request = preview_request(125)
            preview = preview_backfill(uow, P, request)
            cutoff = request.discovery_cutoff
            _, epoch = start_backfill(
                uow,
                P,
                start_request(127, preview.operation_id, fence_at=cutoff),
            )
        assert epoch.fence_recorded_at == cutoff
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (1,)


def test_fresh_start_request_cannot_publish_a_second_initial_epoch():
    with owner_storage() as (_, _, connection, session, _, *_):
        with session.transaction() as uow:
            preview = preview_backfill(uow, P, preview_request(128))
            start_backfill(uow, P, start_request(130, preview.operation_id))
        with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
            start_backfill(uow, P, start_request(132, preview.operation_id))
        assert caught.value.code is ErrorCode.REQUEST_CONFLICT
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (1,)


def test_preview_invalidation_revision_must_match_current_owner_control():
    with owner_storage() as (_, _, connection, session, _, *_):
        stale = replace(preview_request(160), invalidating_revision=Revision(1))
        with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
            preview_backfill(uow, P, stale)
        assert caught.value.code is ErrorCode.PREVIEW_INVALID
        publish(session)
        admit(session)
        with session.transaction() as uow:
            preview = preview_backfill(
                uow,
                P,
                replace(preview_request(162), invalidating_revision=Revision(1)),
            )
        with session.transaction() as uow:
            policy.stop_thread(
                uow,
                P,
                T,
                Generation(1),
                NOW,
                ThreadStopReason.MANUAL_STOP,
            )
        with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
            start_backfill(uow, P, start_request(164, preview.operation_id))
        assert caught.value.code is ErrorCode.PREVIEW_INVALID
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (0,)


def test_pending_bindings_cannot_create_preview_authority():
    with storage() as (_, _, _, session, _, *_):
        with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
            preview_backfill(uow, P, preview_request(166))
        assert caught.value.code is ErrorCode.PREVIEW_INVALID


def test_owner_clock_rejects_expired_preview_even_with_current_timestamp():
    import facet.db.command_store as command_store

    with owner_storage() as (_, _, _, session, _, *_):
        with session.transaction() as uow:
            preview = preview_backfill(uow, P, preview_request(168))
        owner_late = Timestamp(NOW.value + timedelta(minutes=16))
        request = start_request(
            170,
            preview.operation_id,
            fence_at=owner_late,
            accepted_at=owner_late,
        )
        with (
            patch.object(command_store, "_owner_now", return_value=owner_late),
            pytest.raises(StorageFailure) as caught,
            session.transaction() as uow,
        ):
            start_backfill(uow, P, request)
        assert caught.value.code is ErrorCode.PREVIEW_INVALID


def test_start_rejects_invalid_fence_without_publishing():
    with owner_storage() as (_, _, connection, session, _, *_):
        with session.transaction() as uow:
            preview = preview_backfill(uow, P, preview_request(120))
        with pytest.raises(ValueError):
            start_request(122, preview.operation_id, history_id="")
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (0,)


def test_start_rolls_back_operation_and_h0_when_epoch_guard_fails():
    with owner_storage() as (_, _, connection, session, _, *_):
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
    with owner_storage() as (root, _, connection, session, _, *_):
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
    with owner_storage() as (_, _, connection, session, _, *_):
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


def finish_poll(session, value, revision):
    with session.transaction() as uow:
        history.begin_history_poll(uow, P, value, RevisionGuard(Revision(revision)))
        row = page(value)
        begun = history.begin_history_page(uow, P, row, RevisionGuard(Revision(0)))
        finished = history.finish_history_page(
            uow,
            P,
            value.poll_id,
            row.ordinal,
            row.metadata_digest,
            RevisionGuard(begun.revision),
        )
        history.finish_history_poll(
            uow,
            P,
            value.poll_id,
            row.response_history_id,
            RevisionGuard(finished.revision),
        )


def establish_initial(session):
    with session.transaction() as uow:
        preview = preview_backfill(uow, P, preview_request(400))
        _, initial = start_backfill(uow, P, start_request(402, preview.operation_id))
    finish_poll(
        session,
        poll(
            406,
            origin=PollOrigin.INITIAL_EPOCH,
            origin_epoch_id=initial.epoch_id,
            cursor=initial.fence_history_id,
        ),
        0,
    )


def test_expansion_needs_established_checkpoint_and_preserves_it_on_start():
    with owner_storage() as (_, _, connection, session, _, *_):
        with session.transaction() as uow:
            first = preview_backfill(uow, P, preview_request(410))
            _, initial = start_backfill(uow, P, start_request(412, first.operation_id))
            fresh = preview_backfill(uow, P, preview_request(416))
        with pytest.raises(StorageFailure), session.transaction() as uow:
            start_backfill(uow, P, start_request(418, fresh.operation_id))
        finish_poll(
            session,
            poll(
                423,
                origin=PollOrigin.INITIAL_EPOCH,
                origin_epoch_id=initial.epoch_id,
                cursor=initial.fence_history_id,
            ),
            0,
        )
        before = connection.execute("SELECT * FROM history_checkpoints").fetchall()
        with session.transaction() as uow:
            _, expansion = start_backfill(
                uow, P, start_request(418, fresh.operation_id)
            )
        assert expansion.kind is EpochKind.HISTORICAL_EXPANSION
        assert (
            connection.execute("SELECT * FROM history_checkpoints").fetchall() == before
        )
        with pytest.raises(StorageFailure), session.transaction() as uow:
            start_backfill(uow, P, start_request(425, fresh.operation_id))
        assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (2,)


@pytest.mark.parametrize("linked_state", [None, "queued", "failed"])
def test_expansion_completion_requires_fence_coverage_and_terminal_linked_work(
    linked_state,
):
    with owner_storage() as (_, _, connection, session, _, *_):
        establish_initial(session)
        invalidation = 0
        if linked_state:
            publish(session)
            admit(session)
            invalidation = 1
        fence = Timestamp(NOW.value + timedelta(seconds=1))
        with session.transaction() as uow:
            preview = preview_backfill(
                uow,
                P,
                replace(
                    preview_request(430), invalidating_revision=Revision(invalidation)
                ),
            )
            _, expansion = start_backfill(
                uow,
                P,
                start_request(
                    432, preview.operation_id, fence_at=fence, accepted_at=fence
                ),
            )
            partition = _get(
                uow, P, "epoch_partitions", (("epoch_id", expansion.epoch_id),)
            )
            complete = replace(
                partition,
                revision=Revision(1),
                progress=replace(
                    partition.progress,
                    state=PartitionState.COMPLETE,
                    completed_pages=Count(1),
                ),
            )
            batch = (
                (replace(job(440), origin_epoch_id=expansion.epoch_id),)
                if linked_state
                else ()
            )
            epochs.advance_partition(
                uow, P, complete, batch, RevisionGuard(Revision(0))
            )
            epochs.advance_epoch(
                uow,
                P,
                expansion.epoch_id,
                EpochState.CATCHING_UP,
                True,
                Count(0),
                RevisionGuard(Revision(0)),
            )
        # Earlier complete coverage cannot finish a newly fenced expansion.
        with pytest.raises(StorageFailure), session.transaction() as uow:
            epochs.advance_epoch(
                uow,
                P,
                expansion.epoch_id,
                EpochState.COMPLETED,
                True,
                Count(0),
                RevisionGuard(Revision(1)),
            )
        later = replace(
            poll(445, cursor=ProviderId("response-1"), checkpoint_revision=1),
            started_at=Timestamp(NOW.value + timedelta(seconds=2)),
        )
        with session.transaction() as uow:
            history.begin_history_poll(uow, P, later, RevisionGuard(Revision(1)))
        with pytest.raises(StorageFailure), session.transaction() as uow:
            epochs.advance_epoch(
                uow,
                P,
                expansion.epoch_id,
                EpochState.COMPLETED,
                True,
                Count(0),
                RevisionGuard(Revision(1)),
            )
        with session.transaction() as uow:
            row = page(later)
            begun = history.begin_history_page(uow, P, row, RevisionGuard(Revision(0)))
            finished = history.finish_history_page(
                uow,
                P,
                later.poll_id,
                row.ordinal,
                row.metadata_digest,
                RevisionGuard(begun.revision),
            )
            history.finish_history_poll(
                uow,
                P,
                later.poll_id,
                row.response_history_id,
                RevisionGuard(finished.revision),
            )
        if linked_state == "queued":
            with pytest.raises(StorageFailure), session.transaction() as uow:
                epochs.advance_epoch(
                    uow,
                    P,
                    expansion.epoch_id,
                    EpochState.COMPLETED,
                    True,
                    Count(0),
                    RevisionGuard(Revision(1)),
                )
            with session.transaction() as uow:
                assert (
                    reads.get_epoch(uow, P, expansion.epoch_id).state
                    is EpochState.CATCHING_UP
                )
            return
        if linked_state == "failed":
            # Bounded synthetic terminal-failure injection, not a CLI shortcut.
            with session.transaction() as uow:
                uow._execute(
                    "UPDATE sync_jobs SET state='failed' WHERE job_id=?",
                    (lid(440).value,),
                )
            with pytest.raises(StorageFailure), session.transaction() as uow:
                epochs.advance_epoch(
                    uow,
                    P,
                    expansion.epoch_id,
                    EpochState.COMPLETED,
                    True,
                    Count(0),
                    RevisionGuard(Revision(1)),
                )
        final = (
            EpochState.COMPLETED_WITH_ISSUES if linked_state else EpochState.COMPLETED
        )
        with session.transaction() as uow:
            epochs.advance_epoch(
                uow,
                P,
                expansion.epoch_id,
                final,
                True,
                Count(0),
                RevisionGuard(Revision(1)),
            )
        assert connection.execute(
            "SELECT state FROM epochs WHERE epoch_id=?", (expansion.epoch_id.value,)
        ).fetchone() == (final.value,)
