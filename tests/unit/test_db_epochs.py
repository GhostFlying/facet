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
    Sha256Hex,
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
from facet.db.codecs import PollOrigin, PollState, StorageFailure, ThreadStopReason
from facet.db.keys import partition_key
from facet.db.models import (
    EpochPartitionRow,
    EpochRow,
    HistoryGapRow,
    HistoryPageRow,
    HistoryPollRow,
    RevisionGuard,
)
from facet.db.repositories import epochs, policy
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
        result = reader.get_epoch(P, value.epoch_id)
        assert (
            result.state is EpochState.COMPLETED and result.catchup_history_id is None
        )
        assert reader.counts(P, value.epoch_id).known_total == Count(0)
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


def recovery_epoch(gap, n):
    # Typed fixture for a completed scan/decision consumer not yet delivered.
    # Unknown-range authorization remains unavailable in production v1.
    known = gap.reliable_coverage_at is not None
    return replace(
        epoch(n, kind=EpochKind.HISTORY_GAP),
        state=EpochState.SCANNING,
        gap_id=gap.gap_id,
        window_start=Timestamp(
            (gap.reliable_coverage_at or Timestamp(NOW.value - timedelta(days=1))).value
            - (timedelta(minutes=5) if known else timedelta(0))
        ),
        window_end=gap.h1_recorded_at,
        recovery_margin_us=Count(300000000) if known else None,
        fence_history_id=gap.h1,
        fence_recorded_at=gap.h1_recorded_at,
        discovery_complete=True,
        known_message_total=Count(0),
        decision=(
            EpochDecisionRefScheduledReconcile("scheduled_reconcile", Revision(0))
            if known
            else EpochDecisionRefGapApproval(
                "gap_approval", lid(n + 1), lid(n + 2), Revision(0)
            )
        ),
    )


def seed_scan(session, value):
    part = partition(value)
    with session.transaction() as uow:
        _insert(uow, P, "epochs", value)
        _insert(
            uow,
            P,
            "epoch_partitions",
            replace(
                part, progress=replace(part.progress, state=PartitionState.COMPLETE)
            ),
        )


def seed_completed_recovery(session, value, gap, *, poll_id=800):
    from facet.db.codecs import timestamp_to_sql

    final = ProviderId("final-B-not-numerically-ordered")
    started = Timestamp(NOW.value + timedelta(minutes=3))
    poll = HistoryPollRow(
        P,
        lid(poll_id),
        PollOrigin.RECOVERY_EPOCH,
        value.epoch_id,
        gap.h1,
        gap.checkpoint_revision,
        started,
        PollState.COMPLETED,
        Count(1),
        None,
        final,
        started,
        Revision(1),
    )
    page = HistoryPageRow(
        P,
        poll.poll_id,
        Count(1),
        final,
        None,
        None,
        started,
        Sha256Hex("0" * 64),
        Count(0),
        True,
    )
    with session.transaction() as uow:
        _insert(uow, P, "history_polls", poll)
        _insert(uow, P, "history_pages", page)
        uow._execute(
            "UPDATE epochs SET catchup_history_id=? "
            "WHERE projection_id=? AND epoch_id=?",
            (final.value, P.value, value.epoch_id.value),
        )
        uow._execute(
            "UPDATE history_checkpoints SET cursor=?,reliable_coverage_at=?,revision=? "
            "WHERE projection_id=?",
            (
                final.value,
                timestamp_to_sql(started),
                gap.checkpoint_revision.value + 1,
                P.value,
            ),
        )


def gap_lineage(session, *, known=True, broken=None, complete=True):
    from facet.db.codecs import timestamp_to_sql

    first = failed_poll_and_gap(session, known=known)
    with session.transaction() as uow:
        epochs.record_gap(uow, P, first)
    prior = recovery_epoch(first, 750)
    seed_scan(session, prior)
    # A's committed H1 expires without moving its saved old/null checkpoint.
    failed = HistoryPollRow(
        P,
        lid(760),
        PollOrigin.RECOVERY_EPOCH,
        prior.epoch_id,
        ProviderId("unrelated-H1") if broken == "fence" else first.h1,
        Revision(0 if broken == "revision" else 1),
        NOW,
        PollState.ABANDONED,
        Count(0),
        None,
        None,
        NOW,
        Revision(1),
    )
    saved_cursor, saved_coverage = first.checkpoint_cursor, first.reliable_coverage_at
    if broken == "saved_checkpoint":
        saved_cursor, saved_coverage = ProviderId("unrelated-saved"), NOW
    elif broken == "coverage":
        saved_coverage = Timestamp(saved_coverage.value + timedelta(microseconds=1))
    next_revision = Revision(failed.start_checkpoint_revision.value + 1)
    with session.transaction() as uow:
        _insert(uow, P, "history_polls", failed)
        uow._execute(
            "UPDATE history_checkpoints SET cursor=?,reliable_coverage_at=?,revision=? "
            "WHERE projection_id=?",
            (
                None if saved_cursor is None else saved_cursor.value,
                None if saved_coverage is None else timestamp_to_sql(saved_coverage),
                next_revision.value,
                P.value,
            ),
        )
    second = HistoryGapRow(
        P,
        lid(761),
        failed.poll_id,
        failed.start_cursor,
        saved_cursor,
        next_revision,
        NOW,
        saved_coverage,
        ProviderId("H1-B"),
        NOW,
    )
    with session.transaction() as uow:
        epochs.record_gap(uow, P, second)
    current = recovery_epoch(second, 770)
    seed_scan(session, current)
    if complete:
        seed_completed_recovery(session, current, second)
    return first, second, current


@pytest.mark.parametrize("known", [True, False])
def test_completed_descendant_recovery_does_not_reactivate_ancestor_gap(state, known):
    _, connection, session, _ = state
    first, second, _ = gap_lineage(session, known=known)
    with session.transaction() as uow:
        assert epochs._latest_unresolved_gap(uow, P) is None
    assert connection.execute("SELECT COUNT(*) FROM history_gaps").fetchone() == (2,)
    assert connection.execute(
        "SELECT revision FROM history_checkpoints"
    ).fetchone() == (3,)
    # A new epoch cannot claim the old A merely because B has completed.
    if known:
        with pytest.raises(StorageFailure), session.transaction() as uow:
            epochs.start_epoch(
                uow,
                P,
                replace(
                    recovery_epoch(first, 900),
                    state=EpochState.PREPARED,
                    discovery_complete=False,
                    known_message_total=None,
                ),
                (),
            )
    assert first.gap_id != second.gap_id


@pytest.mark.parametrize("known", [True, False])
def test_incomplete_descendant_and_unrelated_completed_poll_keep_gate(state, known):
    _, _, session, _ = state
    _, second, _ = gap_lineage(session, known=known, complete=False)
    with session.transaction() as uow:
        assert epochs._latest_unresolved_gap(uow, P) == second
    unrelated = replace(
        epoch(850, kind=EpochKind.TARGET_AUDIT),
        state=EpochState.SCANNING,
        discovery_complete=True,
        known_message_total=Count(0),
    )
    with session.transaction() as uow:
        _insert(uow, P, "epochs", unrelated)
    # Even a completed poll referencing another epoch cannot clear this gap.
    seed_completed_recovery(session, unrelated, second, poll_id=860)
    with session.transaction() as uow:
        assert epochs._latest_unresolved_gap(uow, P) == second


@pytest.mark.parametrize(
    "broken,known",
    [
        (case, known)
        for case in ["fence", "revision", "saved_checkpoint"]
        for known in [True, False]
    ]
    + [("coverage", True)],
)
def test_completed_child_cannot_clear_broken_ancestor_lineage(state, broken, known):
    _, _, session, _ = state
    first, _, _ = gap_lineage(session, broken=broken, known=known)
    with session.transaction() as uow:
        assert epochs._latest_unresolved_gap(uow, P) == first


@pytest.mark.parametrize("known", [True, False])
def test_new_failed_checkpoint_after_descendant_completion_remains_unresolved(
    state, known
):
    _, _, session, _ = state
    _, _, _ = gap_lineage(session, known=known)
    started = Timestamp(NOW.value + timedelta(minutes=4))
    failed = HistoryPollRow(
        P,
        lid(880),
        PollOrigin.CHECKPOINT,
        None,
        ProviderId("final-B-not-numerically-ordered"),
        Revision(3),
        started,
        PollState.ABANDONED,
        Count(0),
        None,
        None,
        started,
        Revision(1),
    )
    with session.transaction() as uow:
        _insert(uow, P, "history_polls", failed)
        uow._execute(
            "UPDATE history_checkpoints SET revision=4 WHERE projection_id=?",
            (P.value,),
        )
    third = HistoryGapRow(
        P,
        lid(881),
        failed.poll_id,
        failed.start_cursor,
        failed.start_cursor,
        Revision(4),
        started,
        Timestamp(NOW.value + timedelta(minutes=3)),
        ProviderId("new-H1-C"),
        started,
    )
    with session.transaction() as uow:
        epochs.record_gap(uow, P, third)
        assert epochs._latest_unresolved_gap(uow, P) == third


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


@pytest.mark.parametrize(
    "terminal", [PartitionState.COMPLETE, PartitionState.NEEDS_ATTENTION]
)
def test_stopped_historical_partition_accepts_no_new_work_terminal_state(
    state, terminal
):
    _, connection, session, _ = state
    publish(session)
    tracked, _ = admit(session)
    value = replace(
        epoch(),
        decision=EpochDecisionRefScheduledReconcile("scheduled_reconcile", Revision(1)),
    )
    part = partition(
        value, PartitionRefSourceThread("source_thread", tracked.source_thread_id)
    )
    with session.transaction() as uow:
        epochs.start_epoch(uow, P, value, (part,))
        policy.stop_thread(
            uow,
            P,
            tracked.source_thread_id,
            tracked.generation,
            NOW,
            ThreadStopReason.MANUAL_STOP,
        )
    complete = replace(
        part, revision=Revision(1), progress=replace(part.progress, state=terminal)
    )
    with session.transaction() as uow:
        epochs.advance_partition(uow, P, complete, (), RevisionGuard(Revision(0)))
    assert connection.execute("SELECT state FROM epoch_partitions").fetchone() == (
        terminal.value,
    )
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)


@pytest.mark.parametrize("case", ["stopped", "untracked"])
def test_historical_partition_cannot_authorize_new_projection_job(state, case):
    _, connection, session, _ = state
    publish(session)
    selector = ProviderId("synthetic-thread")
    if case == "stopped":
        tracked, _ = admit(session)
        with session.transaction() as uow:
            policy.stop_thread(
                uow, P, selector, tracked.generation, NOW, ThreadStopReason.MANUAL_STOP
            )
    value = replace(
        epoch(),
        decision=EpochDecisionRefScheduledReconcile("scheduled_reconcile", Revision(1)),
    )
    part = partition(value, PartitionRefSourceThread("source_thread", selector))
    with session.transaction() as uow:
        epochs.start_epoch(uow, P, value, (part,))
    complete = replace(
        part,
        revision=Revision(1),
        progress=replace(part.progress, state=PartitionState.COMPLETE),
    )
    with (
        pytest.raises(StorageFailure, match="generation_stale"),
        session.transaction() as uow,
    ):
        epochs.advance_partition(
            uow, P, complete, (job(100),), RevisionGuard(Revision(0))
        )
    assert connection.execute("SELECT state FROM epoch_partitions").fetchone() == (
        "not_started",
    )
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)


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
