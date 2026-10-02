"""Fixed-scope metadata progress and gap observations on actual SQLite files."""

from dataclasses import replace
from datetime import timedelta

import pytest
from test_db_repositories import admit, job, publish, view
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
    Count,
    EpochKind,
    EpochState,
    PartitionProgress,
    PartitionState,
    ProviderId,
    Revision,
    Timestamp,
)
from facet.contracts.records import (
    EpochDecisionRefBackfillStart,
    EpochDecisionRefGapApproval,
    EpochDecisionRefScheduledReconcile,
    EpochDecisionRefScheduledTargetAudit,
    PartitionRefSourceThread,
    PartitionRefSourceWindow,
    PartitionRefTargetCatalog,
)
from facet.db.codecs import PollOrigin, PollState, StorageFailure
from facet.db.keys import partition_key
from facet.db.models import (
    EpochPartitionRow,
    EpochRow,
    HistoryGapRow,
    HistoryPollRow,
    RevisionGuard,
)
from facet.db.repositories import epochs, reads
from facet.db.repositories.base import _insert


def epoch(n=500, *, kind=EpochKind.SOURCE_RECONCILE):
    decision = EpochDecisionRefScheduledReconcile("scheduled_reconcile", Revision(0))
    if kind is EpochKind.TARGET_AUDIT:
        decision = EpochDecisionRefScheduledTargetAudit("scheduled_target_audit")
    return EpochRow(
        P,
        lid(n),
        kind,
        EpochState.PREPARED,
        Revision(0),
        NOW,
        None,
        None,
        None,
        decision,
        None,
        None,
        None,
        None,
        None,
        False,
        None,
    )


def partition(e, ref=None):
    if ref is None:
        ref = PartitionRefSourceWindow("source_window")
    progress = PartitionProgress(
        ref, PartitionState.NOT_STARTED, Count(0), Count(0), None, None
    )
    return EpochPartitionRow(
        P, e.epoch_id, partition_key(P, ref), progress, Revision(0)
    )


def test_scheduled_epoch_fixed_snapshot_and_complete_without_ghost_catchup(state):
    _, _, session, _ = state
    value = epoch(kind=EpochKind.TARGET_AUDIT)
    part = partition(value, PartitionRefTargetCatalog("target_catalog"))
    with session.transaction() as uow:
        epochs.start_epoch(uow, P, value, (part,))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_epoch(
            uow,
            P,
            value.epoch_id,
            EpochState.COMPLETED,
            True,
            Count(0),
            RevisionGuard(Revision(0)),
        )
    complete = replace(
        part,
        revision=Revision(1),
        progress=replace(
            part.progress, state=PartitionState.COMPLETE, completed_pages=Count(1)
        ),
    )
    with session.transaction() as uow:
        epochs.advance_partition(uow, P, complete, (), RevisionGuard(Revision(0)))
        epochs.advance_epoch(
            uow,
            P,
            value.epoch_id,
            EpochState.COMPLETED,
            True,
            Count(0),
            RevisionGuard(Revision(0)),
        )
    with view(state) as reader:
        result = reads.get_epoch(reader, P, value.epoch_id)
        assert (
            result.state is EpochState.COMPLETED and result.catchup_history_id is None
        )
        assert reads.counts(reader, P, value.epoch_id).known_total == Count(0)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_epoch(
            uow,
            P,
            value.epoch_id,
            EpochState.SCANNING,
            True,
            Count(0),
            RevisionGuard(Revision(1)),
        )


def test_partition_progress_and_derived_jobs_are_atomic_and_epoch_scoped(state):
    _, connection, session, _ = state
    publish(session)
    admit(session)
    value = replace(
        epoch(),
        decision=EpochDecisionRefScheduledReconcile("scheduled_reconcile", Revision(1)),
    )
    part = partition(
        value, PartitionRefSourceThread("source_thread", ProviderId("synthetic-thread"))
    )
    with session.transaction() as uow:
        epochs.start_epoch(uow, P, value, (part,))
    progressed = replace(
        part,
        revision=Revision(1),
        progress=replace(
            part.progress,
            state=PartitionState.COMPLETE,
            completed_pages=Count(1),
            observed_items=Count(1),
        ),
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_partition(
            uow,
            P,
            progressed,
            (replace(job(100), origin_epoch_id=lid(999)),),
            RevisionGuard(Revision(0)),
        )
    assert connection.execute(
        "SELECT observed_items FROM epoch_partitions"
    ).fetchone() == (0,)
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)
    with session.transaction() as uow:
        epochs.advance_partition(
            uow, P, progressed, (job(100),), RevisionGuard(Revision(0))
        )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_epoch(
            uow,
            P,
            value.epoch_id,
            EpochState.COMPLETED,
            True,
            Count(1),
            RevisionGuard(Revision(0)),
        )
    assert connection.execute("SELECT COUNT(*) FROM epoch_jobs").fetchone() == (1,)


@pytest.mark.parametrize("change", ["scope", "regression", "stale"])
def test_partition_scope_counter_and_revision_cannot_regress_or_change(state, change):
    _, connection, session, _ = state
    value, ref = epoch(), PartitionRefSourceWindow("source_window")
    part = partition(value, ref)
    with session.transaction() as uow:
        epochs.start_epoch(uow, P, value, (part,))
        first = replace(
            part,
            revision=Revision(1),
            progress=replace(
                part.progress,
                state=PartitionState.SCANNING,
                completed_pages=Count(1),
                observed_items=Count(1),
            ),
        )
        epochs.advance_partition(uow, P, first, (), RevisionGuard(Revision(0)))
    bad = replace(first, revision=Revision(2))
    guard = RevisionGuard(Revision(1))
    if change == "scope":
        bad = replace(
            bad,
            partition_key=partition_key(P, PartitionRefTargetCatalog("target_catalog")),
            progress=replace(
                bad.progress, partition=PartitionRefTargetCatalog("target_catalog")
            ),
        )
    elif change == "regression":
        bad = replace(bad, progress=replace(bad.progress, completed_pages=Count(0)))
    else:
        guard = RevisionGuard(Revision(0))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_partition(uow, P, bad, (), guard)
    assert connection.execute(
        "SELECT completed_pages,observed_items,revision FROM epoch_partitions"
    ).fetchone() == (1, 1, 1)


def failed_poll_and_gap(session, *, known=True):
    # Supplied test-only completed lifecycle, not a production cursor setter.
    cursor = ProviderId("expired-id") if known else None
    coverage = Timestamp(NOW.value - timedelta(minutes=10)) if known else None
    initial = None
    if not known:
        initial = replace(
            epoch(700, kind=EpochKind.INITIAL_BACKFILL),
            window_start=Timestamp(NOW.value.replace(month=4)),
            window_end=NOW,
            discovery_cutoff=NOW,
            fence_history_id=ProviderId("H0"),
            fence_recorded_at=NOW,
            decision=EpochDecisionRefBackfillStart(
                "backfill_start", lid(701), lid(702), Revision(0)
            ),
        )
    failed = HistoryPollRow(
        P,
        lid(600),
        PollOrigin.CHECKPOINT if known else PollOrigin.INITIAL_EPOCH,
        None if known else initial.epoch_id,
        cursor if known else ProviderId("H0"),
        Revision(0),
        NOW,
        PollState.ABANDONED,
        Count(0),
        None,
        None,
        NOW,
        Revision(1),
    )
    from facet.db.codecs import timestamp_to_sql

    with session.transaction() as uow:
        if initial is not None:
            _insert(uow, P, "epochs", initial)
        _insert(uow, P, "history_polls", failed)
        uow._execute(
            "UPDATE history_checkpoints SET cursor=?,reliable_coverage_at=?,revision=1 "
            "WHERE projection_id=?",
            (
                None if cursor is None else cursor.value,
                None if coverage is None else timestamp_to_sql(coverage),
                P.value,
            ),
        )
    return HistoryGapRow(
        P,
        lid(601),
        failed.poll_id,
        failed.start_cursor,
        cursor,
        Revision(1),
        NOW,
        coverage,
        ProviderId("H1"),
        NOW,
    )


def test_known_gap_observation_and_exact_overlap_scope(state):
    _, connection, session, _ = state
    gap = failed_poll_and_gap(session)
    with session.transaction() as uow:
        epochs.record_gap(uow, P, gap)
    value = replace(
        epoch(kind=EpochKind.HISTORY_GAP),
        gap_id=gap.gap_id,
        window_start=Timestamp(gap.reliable_coverage_at.value - timedelta(minutes=5)),
        window_end=gap.h1_recorded_at,
        recovery_margin_us=Count(300000000),
        fence_history_id=gap.h1,
        fence_recorded_at=gap.h1_recorded_at,
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.start_epoch(
            uow, P, replace(value, window_start=gap.reliable_coverage_at), ()
        )
    with session.transaction() as uow:
        epochs.start_epoch(uow, P, value, (partition(value),))
    assert connection.execute("SELECT cursor FROM history_checkpoints").fetchone() == (
        "expired-id",
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_epoch(
            uow,
            P,
            value.epoch_id,
            EpochState.COMPLETED,
            True,
            Count(0),
            RevisionGuard(Revision(0)),
        )


def test_unknown_gap_does_not_create_authorization_or_auto_range(state):
    _, connection, session, _ = state
    gap = failed_poll_and_gap(session, known=False)
    with session.transaction() as uow:
        epochs.record_gap(uow, P, gap)
    value = replace(
        epoch(kind=EpochKind.HISTORY_GAP),
        gap_id=gap.gap_id,
        window_start=Timestamp(NOW.value - timedelta(days=1)),
        window_end=NOW,
        fence_history_id=gap.h1,
        fence_recorded_at=NOW,
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.start_epoch(uow, P, value, ())
    value = replace(
        value,
        decision=EpochDecisionRefGapApproval(
            "gap_approval", lid(10), lid(11), Revision(0)
        ),
    )
    with (
        pytest.raises(StorageFailure, match="owner_unavailable"),
        session.transaction() as uow,
    ):
        epochs.start_epoch(uow, P, value, ())
    assert connection.execute(
        "SELECT COUNT(*) FROM epochs WHERE kind='history_gap'"
    ).fetchone() == (0,)
    assert connection.execute("SELECT cursor FROM history_checkpoints").fetchone() == (
        None,
    )


def test_gap_observation_requires_exact_abandoned_poll_checkpoint_lineage(state):
    _, connection, session, _ = state
    gap = failed_poll_and_gap(session)
    for bad in [
        replace(gap, failed_cursor=ProviderId("another")),
        replace(gap, checkpoint_revision=Revision(0)),
        replace(gap, checkpoint_cursor=ProviderId("another")),
    ]:
        with pytest.raises(StorageFailure), session.transaction() as uow:
            epochs.record_gap(uow, P, bad)
    assert connection.execute("SELECT COUNT(*) FROM history_gaps").fetchone() == (0,)


def test_start_epoch_with_bare_preview_ids_is_not_start_authority(state):
    _, connection, session, _ = state
    value = replace(
        epoch(kind=EpochKind.INITIAL_BACKFILL),
        decision=EpochDecisionRefBackfillStart(
            "backfill_start", lid(10), lid(11), Revision(0)
        ),
        window_start=Timestamp(NOW.value.replace(month=4)),
        window_end=NOW,
        discovery_cutoff=NOW,
        fence_history_id=ProviderId("H0"),
        fence_recorded_at=NOW,
    )
    with (
        pytest.raises(StorageFailure, match="owner_unavailable"),
        session.transaction() as uow,
    ):
        epochs.start_epoch(uow, P, value, ())
    assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (0,)


def test_gap_catchup_is_required_even_after_partitions_and_jobs_complete(state):
    _, _, session, _ = state
    gap = failed_poll_and_gap(session)
    with session.transaction() as uow:
        epochs.record_gap(uow, P, gap)
    value = replace(
        epoch(kind=EpochKind.HISTORY_GAP),
        gap_id=gap.gap_id,
        window_start=Timestamp(gap.reliable_coverage_at.value - timedelta(minutes=5)),
        window_end=NOW,
        recovery_margin_us=Count(300000000),
        fence_history_id=gap.h1,
        fence_recorded_at=NOW,
    )
    part = partition(value)
    with session.transaction() as uow:
        epochs.start_epoch(uow, P, value, (part,))
        complete = replace(
            part,
            revision=Revision(1),
            progress=replace(
                part.progress, state=PartitionState.COMPLETE, completed_pages=Count(1)
            ),
        )
        epochs.advance_partition(uow, P, complete, (), RevisionGuard(Revision(0)))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_epoch(
            uow,
            P,
            value.epoch_id,
            EpochState.COMPLETED,
            True,
            Count(0),
            RevisionGuard(Revision(0)),
        )


def test_extending_partitions_dedupes_identity_and_guards_epoch_revision(state):
    _, connection, session, _ = state
    value = epoch()
    part = partition(value)
    with session.transaction() as uow:
        epochs.start_epoch(uow, P, value, ())
        epochs.extend_partitions(
            uow, P, value.epoch_id, (part,), RevisionGuard(Revision(0))
        )
        epochs.extend_partitions(
            uow, P, value.epoch_id, (part,), RevisionGuard(Revision(1))
        )
    assert connection.execute("SELECT COUNT(*) FROM epoch_partitions").fetchone() == (
        1,
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.extend_partitions(
            uow, P, value.epoch_id, (part,), RevisionGuard(Revision(1))
        )


def test_partition_key_cannot_lie_about_normalized_scope(state):
    _, connection, session, _ = state
    value = epoch()
    part = replace(
        partition(value),
        partition_key=partition_key(P, PartitionRefTargetCatalog("target_catalog")),
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.start_epoch(uow, P, value, (part,))
    assert connection.execute("SELECT COUNT(*) FROM epochs").fetchone() == (0,)
