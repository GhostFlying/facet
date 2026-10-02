"""Real-file History pagination metadata, without Gmail calls or wire authority."""

from dataclasses import replace
from datetime import timedelta

import pytest
from test_db_epochs import epoch, failed_poll_and_gap, recovery_epoch, seed_scan
from test_db_repositories import admit, publish, view
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
    Count,
    EpochKind,
    ProviderId,
    ProviderPageToken,
    Revision,
    Sha256Hex,
    Timestamp,
)
from facet.contracts.records import EpochDecisionRefBackfillStart
from facet.db.codecs import PollOrigin, PollState, StorageFailure, timestamp_to_sql
from facet.db.models import HistoryPageRow, HistoryPollRow, RevisionGuard
from facet.db.repositories import epochs, history, reads
from facet.db.repositories.base import _insert


def initial_epoch(session):
    # Synthetic already-approved decision consumer; v1 start with bare preview
    # IDs remains unavailable. This is not a runtime authorization shortcut.
    initial = replace(
        epoch(900, kind=EpochKind.INITIAL_BACKFILL),
        decision=EpochDecisionRefBackfillStart(
            "backfill_start", lid(901), lid(902), Revision(0)
        ),
        window_start=Timestamp(NOW.value.replace(month=4)),
        window_end=NOW,
        discovery_cutoff=NOW,
        fence_history_id=ProviderId("z-H0-not-numeric"),
        fence_recorded_at=NOW,
    )
    with session.transaction() as uow:
        _insert(uow, P, "epochs", initial)
    return initial


def checkpoint_fixture(session):
    with session.transaction() as uow:
        uow._execute(
            "UPDATE history_checkpoints SET cursor=?,reliable_coverage_at=? "
            "WHERE projection_id=?",
            (
                "old-checkpoint",
                timestamp_to_sql(Timestamp(NOW.value - timedelta(minutes=10))),
                P.value,
            ),
        )


def poll(
    n=1000,
    *,
    origin=PollOrigin.CHECKPOINT,
    origin_epoch_id=None,
    cursor=None,
    checkpoint_revision=0,
):
    if cursor is None:
        cursor = ProviderId("old-checkpoint")
    return HistoryPollRow(
        P,
        lid(n),
        origin,
        origin_epoch_id,
        cursor,
        Revision(checkpoint_revision),
        NOW,
        PollState.READING,
        Count(0),
        None,
        None,
        None,
        Revision(0),
    )


def page(p, *, ordinal=1, input_token=None, next_token=None, count=0):
    return HistoryPageRow(
        P,
        p.poll_id,
        Count(ordinal),
        ProviderId(f"response-{ordinal}"),
        input_token,
        next_token,
        Timestamp(NOW.value + timedelta(minutes=ordinal)),
        Sha256Hex(str(ordinal) * 64),
        Count(count),
        False,
    )


def start(session):
    checkpoint_fixture(session)
    value = poll()
    with session.transaction() as uow:
        history.begin_history_poll(uow, P, value, RevisionGuard(Revision(0)))
    return value


def finish_page(session, value, row, *, revision=0):
    with session.transaction() as uow:
        history.begin_history_page(uow, P, row, RevisionGuard(Revision(revision)))
        history.finish_history_page(
            uow,
            P,
            value.poll_id,
            row.ordinal,
            row.metadata_digest,
            RevisionGuard(Revision(revision)),
        )


def test_empty_poll_advances_only_after_complete_page_and_uses_request_start(state):
    _, connection, session, _ = state
    value = start(session)
    row = page(value)
    with view(state) as reader:
        before = reads.get_checkpoint(reader, P)
    finish_page(session, value, row)
    with view(state) as reader:
        assert reads.get_checkpoint(reader, P) == before
    with session.transaction() as uow:
        history.finish_history_poll(
            uow, P, value.poll_id, row.response_history_id, RevisionGuard(Revision(1))
        )
    with view(state) as reader:
        checkpoint = reads.get_checkpoint(reader, P)
        assert checkpoint.cursor == row.response_history_id
        assert checkpoint.reliable_coverage_at == value.started_at
        assert checkpoint.revision == Revision(1) and checkpoint.active_poll_id is None
    assert connection.execute("SELECT state FROM history_polls").fetchone() == (
        "completed",
    )


def test_multi_page_token_chain_durable_before_cursor_and_no_numeric_max(state):
    _, _, session, _ = state
    value = start(session)
    first = replace(
        page(value, next_token=ProviderPageToken("synthetic-token")),
        response_history_id=ProviderId("z-999"),
    )
    finish_page(session, value, first)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        history.finish_history_poll(
            uow, P, value.poll_id, first.response_history_id, RevisionGuard(Revision(1))
        )
    second = replace(
        page(value, ordinal=2, input_token=first.next_page_token),
        response_history_id=ProviderId("a-1"),
    )
    finish_page(session, value, second, revision=1)
    with session.transaction() as uow:
        history.finish_history_poll(
            uow,
            P,
            value.poll_id,
            second.response_history_id,
            RevisionGuard(Revision(2)),
        )
    with view(state) as reader:
        assert reads.get_checkpoint(reader, P).cursor == ProviderId("a-1")


@pytest.mark.parametrize(
    "bad", ["ordinal", "token", "digest", "count", "complete", "time"]
)
def test_page_cannot_skip_or_change_immutable_response_identity(state, bad):
    _, connection, session, _ = state
    value = start(session)
    row = page(value)
    with session.transaction() as uow:
        history.begin_history_page(uow, P, row, RevisionGuard(Revision(0)))
    changes = {
        "ordinal": {"ordinal": Count(2)},
        "token": {"next_page_token": ProviderPageToken("changed")},
        "digest": {"metadata_digest": Sha256Hex("f" * 64)},
        "count": {"expected_event_count": Count(1)},
        "complete": {"complete": True},
        "time": {"received_at": Timestamp(NOW.value - timedelta(seconds=1))},
    }
    with pytest.raises(StorageFailure), session.transaction() as uow:
        history.begin_history_page(
            uow, P, replace(row, **changes[bad]), RevisionGuard(Revision(0))
        )
    assert connection.execute("SELECT complete FROM history_pages").fetchone() == (0,)
    assert connection.execute("SELECT cursor FROM history_checkpoints").fetchone() == (
        "old-checkpoint",
    )


@pytest.mark.parametrize(
    "bad", ["digest", "missing_membership", "wrong_final", "no_page", "stale"]
)
def test_failed_completion_leaves_checkpoint_and_page_progress_unchanged(state, bad):
    _, connection, session, _ = state
    value = start(session)
    row = page(value, count=1 if bad == "missing_membership" else 0)
    if bad != "no_page":
        with session.transaction() as uow:
            history.begin_history_page(uow, P, row, RevisionGuard(Revision(0)))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        if bad in {"digest", "missing_membership", "stale"}:
            history.finish_history_page(
                uow,
                P,
                value.poll_id,
                Count(1),
                Sha256Hex("f" * 64) if bad == "digest" else row.metadata_digest,
                RevisionGuard(Revision(1 if bad == "stale" else 0)),
            )
        else:
            if bad != "no_page":
                history.finish_history_page(
                    uow,
                    P,
                    value.poll_id,
                    Count(1),
                    row.metadata_digest,
                    RevisionGuard(Revision(0)),
                )
            history.finish_history_poll(
                uow,
                P,
                value.poll_id,
                ProviderId("caller-chosen-not-final"),
                RevisionGuard(Revision(0 if bad == "no_page" else 1)),
            )
    assert connection.execute(
        "SELECT cursor,revision FROM history_checkpoints"
    ).fetchone() == ("old-checkpoint", 0)
    assert connection.execute(
        "SELECT completed_pages FROM history_polls"
    ).fetchone() == (0,)


def test_abandon_keeps_partial_pages_old_checkpoint_and_allows_valid_restart(state):
    _, connection, session, _ = state
    value = start(session)
    first = page(value, next_token=ProviderPageToken("next"))
    finish_page(session, value, first)
    second = page(value, ordinal=2, input_token=first.next_page_token)
    with session.transaction() as uow:
        history.begin_history_page(uow, P, second, RevisionGuard(Revision(1)))
        history.abandon_history_poll(
            uow, P, value.poll_id, second.received_at, RevisionGuard(Revision(1))
        )
    assert connection.execute(
        "SELECT cursor,revision,active_poll_id FROM history_checkpoints"
    ).fetchone() == ("old-checkpoint", 1, None)
    assert connection.execute(
        "SELECT ordinal,complete FROM history_pages ORDER BY ordinal"
    ).fetchall() == [(1, 1), (2, 0)]
    retry = poll(1001, checkpoint_revision=1)
    with session.transaction() as uow:
        history.begin_history_poll(uow, P, retry, RevisionGuard(Revision(1)))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        history.finish_history_page(
            uow,
            P,
            value.poll_id,
            Count(2),
            second.metadata_digest,
            RevisionGuard(Revision(2)),
        )


def test_initial_h0_catchup_can_run_before_discovery_but_cannot_finish_epoch(state):
    _, _, session, _ = state
    initial = initial_epoch(session)
    value = poll(
        origin=PollOrigin.INITIAL_EPOCH,
        origin_epoch_id=initial.epoch_id,
        cursor=initial.fence_history_id,
    )
    with session.transaction() as uow:
        history.begin_history_poll(uow, P, value, RevisionGuard(Revision(0)))
    row = page(value)
    finish_page(session, value, row)
    with session.transaction() as uow:
        history.finish_history_poll(
            uow, P, value.poll_id, row.response_history_id, RevisionGuard(Revision(1))
        )
    with view(state) as reader:
        saved = reads.get_epoch(reader, P, initial.epoch_id)
        assert saved.fence_history_id == initial.fence_history_id
        assert saved.catchup_history_id == row.response_history_id
        assert not saved.discovery_complete


@pytest.mark.parametrize("known", [True, False])
def test_unresolved_gap_refuses_checkpoint_and_initial_h0_origin(state, known):
    _, connection, session, _ = state
    gap = failed_poll_and_gap(session, known=known)
    with session.transaction() as uow:
        epochs.record_gap(uow, P, gap)
    initial = initial_epoch(session)
    candidates = [
        poll(checkpoint_revision=1, cursor=gap.failed_cursor),
        poll(
            1001,
            origin=PollOrigin.INITIAL_EPOCH,
            origin_epoch_id=initial.epoch_id,
            cursor=initial.fence_history_id,
            checkpoint_revision=1,
        ),
    ]
    for value in candidates:
        with pytest.raises(StorageFailure), session.transaction() as uow:
            history.begin_history_poll(uow, P, value, RevisionGuard(Revision(1)))
    assert connection.execute(
        "SELECT active_poll_id FROM history_checkpoints"
    ).fetchone() == (None,)


def test_recovery_requires_actual_window_and_active_thread_scans_then_derives_catchup(
    state,
):
    _, _, session, _ = state
    gap = failed_poll_and_gap(session)
    with session.transaction() as uow:
        epochs.record_gap(uow, P, gap)
    value = recovery_epoch(gap, 950)
    seed_scan(session, value)
    recovering = poll(
        origin=PollOrigin.RECOVERY_EPOCH,
        origin_epoch_id=value.epoch_id,
        cursor=gap.h1,
        checkpoint_revision=1,
    )
    publish(session)
    tracked, _ = admit(session)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        history.begin_history_poll(uow, P, recovering, RevisionGuard(Revision(1)))
    # Only historical metadata, not a provider scan; explicit fixture proof.
    from test_db_epochs import partition

    from facet.contracts import PartitionState
    from facet.contracts.records import PartitionRefSourceThread

    part = partition(
        value, PartitionRefSourceThread("source_thread", tracked.source_thread_id)
    )
    with session.transaction() as uow:
        _insert(
            uow,
            P,
            "epoch_partitions",
            replace(
                part, progress=replace(part.progress, state=PartitionState.COMPLETE)
            ),
        )
        history.begin_history_poll(uow, P, recovering, RevisionGuard(Revision(1)))
    row = page(recovering)
    finish_page(session, recovering, row)
    with session.transaction() as uow:
        history.finish_history_poll(
            uow,
            P,
            recovering.poll_id,
            row.response_history_id,
            RevisionGuard(Revision(1)),
        )
        assert epochs._latest_unresolved_gap(uow, P) is None
    with view(state) as reader:
        assert (
            reads.get_epoch(reader, P, value.epoch_id).catchup_history_id
            == row.response_history_id
        )
        assert (
            reads.get_checkpoint(reader, P).reliable_coverage_at
            == recovering.started_at
        )


@pytest.mark.parametrize(
    "bad", ["active", "checkpoint_revision", "start_cursor", "clock_regression"]
)
def test_begin_poll_cas_one_active_and_saved_origin_no_partial_state(state, bad):
    _, connection, session, _ = state
    checkpoint_fixture(session)
    row = poll()
    if bad == "active":
        with session.transaction() as uow:
            history.begin_history_poll(uow, P, row, RevisionGuard(Revision(0)))
        row = replace(row, poll_id=lid(1001))
    elif bad == "checkpoint_revision":
        row = replace(row, start_checkpoint_revision=Revision(1))
    elif bad == "start_cursor":
        row = replace(row, start_cursor=ProviderId("not-the-origin"))
    else:
        row = replace(row, started_at=Timestamp(NOW.value - timedelta(days=1)))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        history.begin_history_poll(uow, P, row, RevisionGuard(Revision(0)))
    expected = 1 if bad == "active" else 0
    assert connection.execute("SELECT COUNT(*) FROM history_polls").fetchone() == (
        expected,
    )
