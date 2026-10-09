"""Fixed scan scope and progress; no scan, policy decision or cursor reset."""

from datetime import timedelta

from facet.contracts import (
    Count,
    EpochKind,
    EpochState,
    ErrorCode,
    JobState,
    PartitionState,
    Revision,
)

from ..codecs import (
    MIN_TIMESTAMP,
    AuditKind,
    AuditObjectKind,
    StorageFailure,
    next_revision,
    timestamp_to_sql,
)
from ..models import EpochPartitionRow, SyncJobRow, WriteReceipt
from .audit import _audit
from .base import (
    _batch,
    _conflict,
    _decode,
    _get,
    _guard,
    _insert,
    _mutating,
    _query,
    _require_row,
)

_TERMINAL = {
    JobState.COMPLETED.value,
    JobState.CANCELLED.value,
    JobState.SOURCE_MISSING.value,
    JobState.FAILED.value,
    JobState.NEEDS_ATTENTION.value,
}


def _latest_unresolved_gap(uow, projection_id):
    # A later H1 may itself expire before recovery. Completion of its exact
    # descendant lineage closes ancestor polling gates, not their factual rows.
    # UNION deduplicates and strictly increasing checkpoint revisions exclude
    # cycles. Provider History IDs are only compared for identity, never ordered.
    rows = _query(
        uow,
        unresolved_gap_query(),
        (projection_id.value, projection_id.value, projection_id.value),
        maximum=1,
    )
    return None if not rows else _decode(uow, projection_id, "history_gaps", rows[0])


def unresolved_gap_query():
    """Share the exact read-only lineage predicate with offline status."""
    from .serialization import COLUMNS

    return (
        "WITH RECURSIVE resolved(gap_id) AS ("
        "SELECT g.gap_id FROM history_gaps g JOIN epochs e "
        "ON e.projection_id=g.projection_id AND e.gap_id=g.gap_id "
        "JOIN history_polls p ON p.projection_id=e.projection_id "
        "AND p.origin_epoch_id=e.epoch_id "
        "WHERE g.projection_id=? AND e.kind='history_gap' "
        "AND e.fence_history_id=g.h1 AND e.fence_recorded_at=g.h1_recorded_at "
        "AND p.origin='recovery_epoch' AND p.state='completed' "
        "AND p.start_cursor=g.h1 AND p.final_history_id=e.catchup_history_id "
        "AND p.start_checkpoint_revision>=g.checkpoint_revision "
        "UNION SELECT parent.gap_id FROM resolved r "
        "JOIN history_gaps child ON child.projection_id=? AND child.gap_id=r.gap_id "
        "JOIN history_polls failed ON failed.projection_id=child.projection_id "
        "AND failed.poll_id=child.failed_poll_id "
        "JOIN epochs prior ON prior.projection_id=failed.projection_id "
        "AND prior.epoch_id=failed.origin_epoch_id "
        "JOIN history_gaps parent ON parent.projection_id=prior.projection_id "
        "AND parent.gap_id=prior.gap_id "
        "WHERE failed.origin='recovery_epoch' AND failed.state='abandoned' "
        "AND prior.kind='history_gap' AND failed.start_cursor=parent.h1 "
        "AND prior.fence_history_id=parent.h1 "
        "AND prior.fence_recorded_at=parent.h1_recorded_at "
        "AND child.checkpoint_cursor IS parent.checkpoint_cursor "
        "AND child.reliable_coverage_at IS parent.reliable_coverage_at "
        "AND child.checkpoint_revision=failed.start_checkpoint_revision+1 "
        "AND child.checkpoint_revision>parent.checkpoint_revision) SELECT "
        + ",".join("g." + c for c in COLUMNS["history_gaps"])
        + " FROM history_gaps g WHERE g.projection_id=? "
        "AND NOT EXISTS(SELECT 1 FROM resolved r WHERE r.gap_id=g.gap_id) "
        "ORDER BY g.checkpoint_revision DESC LIMIT 1"
    )


@_mutating
def record_gap(uow, projection_id, gap):
    _require_row(projection_id, "history_gaps", gap)
    checkpoint = _get(uow, projection_id, "history_checkpoints", ())
    failed = _get(
        uow, projection_id, "history_polls", (("poll_id", gap.failed_poll_id),)
    )
    if (
        checkpoint is None
        or failed is None
        or failed.state.value != "abandoned"
        or checkpoint.active_poll_id is not None
        or gap.failed_cursor != failed.start_cursor
        or gap.checkpoint_revision != next_revision(failed.start_checkpoint_revision)
        or (gap.checkpoint_cursor, gap.checkpoint_revision, gap.reliable_coverage_at)
        != (checkpoint.cursor, checkpoint.revision, checkpoint.reliable_coverage_at)
        or gap.h1_recorded_at.value < gap.observed_at.value
        or gap.observed_at.value < failed.started_at.value
    ):
        _conflict()
    old = _get(
        uow, projection_id, "history_gaps", (("failed_poll_id", gap.failed_poll_id),)
    )
    if old is not None:
        if old != gap:
            _conflict()
        return WriteReceipt("replayed", old.gap_id, old.checkpoint_revision)
    _insert(uow, projection_id, "history_gaps", gap)
    return WriteReceipt("created", gap.gap_id, gap.checkpoint_revision)


def _decision(uow, projection_id, epoch):
    decision = epoch.decision
    if decision.tag == "backfill_start":
        _backfill_decision(uow, projection_id, epoch)
        return
    if decision.tag not in {"scheduled_reconcile", "scheduled_target_audit"}:
        # No preview/operation registry exists in v1; typed UUIDs are not proof.
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    if epoch.kind is EpochKind.HISTORY_GAP:
        gap = _latest_unresolved_gap(uow, projection_id)
        if (
            gap is None
            or epoch.gap_id != gap.gap_id
            or gap.reliable_coverage_at is None
        ):
            _conflict()
        start = max(
            MIN_TIMESTAMP, timestamp_to_sql(gap.reliable_coverage_at) - 300000000
        )
        if (
            epoch.recovery_margin_us != Count(300000000)
            or epoch.window_start is None
            or epoch.window_end is None
            or timestamp_to_sql(epoch.window_start) != start
            or epoch.window_end != gap.h1_recorded_at
            or (epoch.fence_history_id, epoch.fence_recorded_at)
            != (gap.h1, gap.h1_recorded_at)
            or start >= timestamp_to_sql(gap.h1_recorded_at)
            or gap.reliable_coverage_at.value > gap.h1_recorded_at.value
        ):
            _conflict()
    elif epoch.gap_id is not None or epoch.recovery_margin_us is not None:
        _conflict()
    if epoch.kind is EpochKind.TARGET_AUDIT:
        if decision.tag != "scheduled_target_audit" or any(
            v is not None
            for v in (
                epoch.window_start,
                epoch.window_end,
                epoch.discovery_cutoff,
                epoch.fence_history_id,
                epoch.fence_recorded_at,
            )
        ):
            _conflict()
    elif (
        epoch.kind not in {EpochKind.SOURCE_RECONCILE, EpochKind.HISTORY_GAP}
        or decision.tag != "scheduled_reconcile"
    ):
        _conflict()
    if hasattr(decision, "ruleset_revision"):
        projection = _get(uow, projection_id, "projections", ())
        snapshot = _get(
            uow,
            projection_id,
            "rulesets",
            (("revision", decision.ruleset_revision),),
        )
        if (
            projection is None
            or snapshot is None
            or not snapshot.sealed
            or projection.ruleset_revision != decision.ruleset_revision
        ):
            _conflict()


def _backfill_checkpoint_guard(uow, projection_id, kind):
    checkpoint = _get(uow, projection_id, "history_checkpoints", ())
    if checkpoint is None or checkpoint.active_poll_id is not None:
        _conflict()
    if kind is EpochKind.INITIAL_BACKFILL:
        if (
            checkpoint.cursor is not None
            or checkpoint.reliable_coverage_at is not None
            or checkpoint.revision.value != 0
        ):
            _conflict()
    elif kind is EpochKind.HISTORICAL_EXPANSION:
        if (
            checkpoint.cursor is None
            or checkpoint.reliable_coverage_at is None
            or _latest_unresolved_gap(uow, projection_id) is not None
            or not _query(
                uow,
                "SELECT 1 FROM epochs WHERE projection_id=? "
                "AND kind='initial_backfill' LIMIT 1",
                (projection_id.value,),
                maximum=1,
            )
        ):
            _conflict()
    else:
        _conflict()


def historical_coverage_complete(uow, projection_id, epoch):
    """A completed shared History poll covers the fence, without ID ordering."""
    checkpoint = _get(uow, projection_id, "history_checkpoints", ())
    return bool(
        checkpoint is not None
        and checkpoint.cursor is not None
        and checkpoint.reliable_coverage_at is not None
        and checkpoint.active_poll_id is None
        and epoch.fence_recorded_at is not None
        and checkpoint.reliable_coverage_at.value >= epoch.fence_recorded_at.value
        and _latest_unresolved_gap(uow, projection_id) is None
        and _query(
            uow,
            "SELECT 1 FROM history_polls WHERE projection_id=? "
            "AND state='completed' AND final_history_id=? AND started_at=? LIMIT 1",
            (
                projection_id.value,
                checkpoint.cursor.value,
                timestamp_to_sql(checkpoint.reliable_coverage_at),
            ),
            maximum=1,
        )
    )


def _backfill_decision(uow, projection_id, epoch):
    """Validate the journal-backed backfill fence before writing it."""
    from ..command_records import LocalCommandKind, _valid_backfill_window
    from ..command_store import (
        _backfill_digest,
        _find_backfill_by_id,
        _rule_scope_matches,
    )

    decision = epoch.decision
    if not _query(
        uow,
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='operations' LIMIT 1",
        maximum=1,
    ):
        # v1 has typed epoch decisions but deliberately has no operation journal.
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    operation, payload = _find_backfill_by_id(uow, projection_id, decision.operation_id)
    if operation is None or payload is None:
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    if (
        operation.command is not LocalCommandKind.BACKFILL_START
        or operation.state.value not in {"accepted", "executing", "completed"}
        or operation.code is not None
        or operation.digest != _backfill_digest(operation, payload)
        or operation.expected_preview_id != decision.preview_id
        or payload.preview_operation_id != decision.preview_id
        or payload.purpose.value != "start_backfill"
        or payload.ruleset_revision != decision.ruleset_revision
        or epoch.kind
        not in {EpochKind.INITIAL_BACKFILL, EpochKind.HISTORICAL_EXPANSION}
        or epoch.window_start != payload.window_start
        or epoch.window_end != payload.window_end
        or epoch.discovery_cutoff != payload.discovery_cutoff
        or epoch.fence_history_id is None
        or epoch.fence_recorded_at is None
        or epoch.fence_recorded_at.value < payload.discovery_cutoff.value
        or epoch.fence_history_id.value == ""
    ):
        _conflict()
    preview, preview_payload = _find_backfill_by_id(
        uow, projection_id, decision.preview_id
    )
    if (
        preview is None
        or preview_payload is None
        or preview.command is not LocalCommandKind.BACKFILL_PREVIEW
        or preview.code is not None
        or preview.state.value not in {"accepted", "executing", "completed"}
        or preview.expected_preview_id is not None
        or preview.digest != _backfill_digest(preview, preview_payload)
        or preview_payload.preview_operation_id is not None
        or preview_payload.purpose != payload.purpose
        or preview_payload.ruleset_revision != payload.ruleset_revision
        or preview_payload.window_start != payload.window_start
        or preview_payload.window_end != payload.window_end
        or preview_payload.discovery_cutoff != payload.discovery_cutoff
        or preview_payload.scope_digest != payload.scope_digest
        or preview_payload.expires_at != payload.expires_at
        or preview_payload.invalidating_revision != payload.invalidating_revision
        or not _valid_backfill_window(
            preview_payload.window_start,
            preview_payload.window_end,
            preview.accepted_at,
        )
        or preview_payload.expires_at.value
        > preview.accepted_at.value + timedelta(minutes=15)
        or preview.expected_binding_revision != operation.expected_binding_revision
        or preview.expected_config_revision != operation.expected_config_revision
    ):
        _conflict()
    projection = _get(uow, projection_id, "projections", ())
    snapshot = _get(
        uow, projection_id, "rulesets", (("revision", payload.ruleset_revision),)
    )
    runtime = _query(
        uow,
        "SELECT binding_guard FROM command_runtime WHERE projection_id=? LIMIT 2",
        (projection_id.value,),
        maximum=1,
    )
    invalidation = _query(
        uow,
        "SELECT COALESCE(SUM(generation),0) FROM tracked_threads WHERE projection_id=?",
        (projection_id.value,),
        maximum=1,
    )
    if (
        projection is None
        or snapshot is None
        or not snapshot.sealed
        or (
            projection.ruleset_revision != payload.ruleset_revision
            and not _rule_scope_matches(
                uow,
                projection_id,
                payload.ruleset_revision,
                payload.scope_digest,
                payload.window_start,
                payload.window_end,
                payload.discovery_cutoff,
            )
        )
        or len(runtime) != 1
        or len(invalidation) != 1
        or preview.expected_config_revision != projection.config_revision
        or preview.expected_binding_revision.value != runtime[0][0]
        or operation.expected_config_revision != projection.config_revision
        or operation.expected_binding_revision.value != runtime[0][0]
        or payload.invalidating_revision.value != invalidation[0][0]
        or payload.expires_at.value < epoch.created_at.value
        or epoch.fence_recorded_at.value > payload.expires_at.value
    ):
        _conflict()
    _backfill_checkpoint_guard(uow, projection_id, epoch.kind)


def _partition(uow, projection_id, epoch, row):
    from ..keys import partition_key

    _require_row(projection_id, "epoch_partitions", row)
    if row.epoch_id != epoch.epoch_id:
        _conflict()
    allowed = (
        {"target_catalog", "mapped_target_set"}
        if epoch.kind is EpochKind.TARGET_AUDIT
        else {"source_window", "source_thread"}
    )
    ref = row.progress.partition
    if ref.tag not in allowed or row.partition_key != partition_key(projection_id, ref):
        _conflict()
    # Historical selectors may name stopped/deleted/not-yet-admitted threads.
    # A selector itself grants no disclosure. Derived jobs independently require
    # current tracked admission/generation in enqueue, below.


@_mutating
def start_epoch(uow, projection_id, epoch, partitions):
    _require_row(projection_id, "epochs", epoch)
    _batch(partitions, EpochPartitionRow)
    if (
        epoch.state is not EpochState.PREPARED
        or epoch.revision != Revision(0)
        or epoch.catchup_history_id is not None
        or epoch.discovery_complete
        or epoch.known_message_total is not None
    ):
        _conflict()
    _decision(uow, projection_id, epoch)
    for row in partitions:
        _partition(uow, projection_id, epoch, row)
        if (
            row.revision != Revision(0)
            or row.progress.state is not PartitionState.NOT_STARTED
        ):
            _conflict()
    old = _get(uow, projection_id, "epochs", (("epoch_id", epoch.epoch_id),))
    if old is not None:
        if old != epoch or any(
            _get(
                uow,
                projection_id,
                "epoch_partitions",
                (("epoch_id", epoch.epoch_id), ("partition_key", r.partition_key)),
            )
            != r
            for r in partitions
        ):
            _conflict()
        return WriteReceipt("replayed", old.epoch_id, old.revision)
    _insert(uow, projection_id, "epochs", epoch)
    for row in partitions:
        _insert(uow, projection_id, "epoch_partitions", row)
    _audit(
        uow,
        projection_id,
        AuditKind.EPOCH_STARTED,
        AuditObjectKind.EPOCH,
        epoch.created_at,
        local_id=epoch.epoch_id,
        after_revision=epoch.revision,
        after_state=epoch.state,
    )
    return WriteReceipt("created", epoch.epoch_id, epoch.revision)


def _active(epoch):
    if epoch is None or epoch.state in {
        EpochState.COMPLETED,
        EpochState.COMPLETED_WITH_ISSUES,
        EpochState.NEEDS_ATTENTION,
    }:
        _conflict()


@_mutating
def extend_partitions(uow, projection_id, epoch_id, partitions, guard):
    _batch(partitions, EpochPartitionRow)
    epoch = _get(uow, projection_id, "epochs", (("epoch_id", epoch_id),))
    _active(epoch)
    _guard(epoch.revision, guard)
    for row in partitions:
        _partition(uow, projection_id, epoch, row)
        if (
            row.revision != Revision(0)
            or row.progress.state is not PartitionState.NOT_STARTED
        ):
            _conflict()
        old = _get(
            uow,
            projection_id,
            "epoch_partitions",
            (("epoch_id", epoch_id), ("partition_key", row.partition_key)),
        )
        if old is not None:
            if old.progress.partition != row.progress.partition:
                _conflict()
        else:
            if epoch.discovery_complete:
                _conflict()
            _insert(uow, projection_id, "epoch_partitions", row)
    revision = next_revision(epoch.revision)
    uow._execute(
        "UPDATE epochs SET revision=? WHERE projection_id=? AND epoch_id=?",
        (revision.value, projection_id.value, epoch_id.value),
    )
    return WriteReceipt("updated", epoch_id, revision)


@_mutating
def advance_partition(uow, projection_id, row, jobs, guard):
    _require_row(projection_id, "epoch_partitions", row)
    _batch(jobs, SyncJobRow)
    epoch = _get(uow, projection_id, "epochs", (("epoch_id", row.epoch_id),))
    _active(epoch)
    _partition(uow, projection_id, epoch, row)
    old = _get(
        uow,
        projection_id,
        "epoch_partitions",
        (("epoch_id", row.epoch_id), ("partition_key", row.partition_key)),
    )
    if old is None:
        _conflict()
    _guard(old.revision, guard)
    a, b = old.progress, row.progress
    if (
        row.revision != next_revision(old.revision)
        or a.partition != b.partition
        or a.state is PartitionState.COMPLETE
        or b.completed_pages.value < a.completed_pages.value
        or b.observed_items.value < a.observed_items.value
    ):
        _conflict()
    from .jobs import _join_epoch, enqueue

    for job in jobs:
        if job.origin_epoch_id is not None and job.origin_epoch_id != row.epoch_id:
            _conflict()
        subject = job.subject
        if hasattr(subject, "epoch_id") and subject.epoch_id != row.epoch_id:
            _conflict()
        ref = b.partition
        if ref.tag == "source_thread" and (
            not hasattr(subject, "source_thread_id")
            or subject.source_thread_id != ref.source_thread_id
        ):
            _conflict()
        if ref.tag in {"target_catalog", "mapped_target_set"} and jobs:
            # A target existence scan cannot authorize source projection/repair.
            _conflict()
        receipt = enqueue(uow, projection_id, job)
        _join_epoch(uow, projection_id, row.epoch_id, receipt.object_id)
    uow._execute(
        "UPDATE epoch_partitions SET state=?,completed_pages=?,observed_items=?,"
        "page_token=?,after_source_message_id=?,revision=? "
        "WHERE projection_id=? AND epoch_id=? AND partition_key=?",
        (
            b.state.value,
            b.completed_pages.value,
            b.observed_items.value,
            None if b.page_token is None else b.page_token.value,
            None
            if b.after_source_message_id is None
            else b.after_source_message_id.value,
            row.revision.value,
            projection_id.value,
            row.epoch_id.value,
            row.partition_key.value,
        ),
    )
    return WriteReceipt("updated", row.epoch_id, row.revision)


@_mutating
def advance_epoch(
    uow, projection_id, epoch_id, state, discovery_complete, known_total, guard
):
    if (
        type(state) is not EpochState
        or type(discovery_complete) is not bool
        or known_total is not None
        and type(known_total) is not Count
        or not discovery_complete
        and known_total is not None
    ):
        _conflict()
    epoch = _get(uow, projection_id, "epochs", (("epoch_id", epoch_id),))
    _active(epoch)
    _guard(epoch.revision, guard)
    if epoch.discovery_complete and (
        not discovery_complete or known_total != epoch.known_message_total
    ):
        _conflict()
    if state in {EpochState.COMPLETED, EpochState.COMPLETED_WITH_ISSUES}:
        if not discovery_complete:
            _conflict()
        if _query(
            uow,
            "SELECT 1 FROM epoch_partitions WHERE projection_id=? "
            "AND epoch_id=? AND state<>'complete' LIMIT 1",
            (projection_id.value, epoch_id.value),
            maximum=1,
        ):
            _conflict()
        work = _query(
            uow,
            "SELECT DISTINCT j.state FROM sync_jobs j JOIN epoch_jobs e "
            "ON e.projection_id=j.projection_id AND e.job_id=j.job_id "
            "WHERE e.projection_id=? AND e.epoch_id=?",
            (projection_id.value, epoch_id.value),
            maximum=9,
        )
        if any(status not in _TERMINAL for (status,) in work):
            _conflict()
        if state is EpochState.COMPLETED and any(
            status != "completed" for (status,) in work
        ):
            _conflict()
        requires_catchup = epoch.kind in {
            EpochKind.INITIAL_BACKFILL,
            EpochKind.HISTORY_GAP,
        }
        if requires_catchup and (
            epoch.catchup_history_id is None
            or not _query(
                uow,
                "SELECT 1 FROM history_polls WHERE projection_id=? "
                "AND origin_epoch_id=? AND origin=? AND state='completed' "
                "AND final_history_id=? LIMIT 1",
                (
                    projection_id.value,
                    epoch_id.value,
                    "initial_epoch"
                    if epoch.kind is EpochKind.INITIAL_BACKFILL
                    else "recovery_epoch",
                    epoch.catchup_history_id.value,
                ),
                maximum=1,
            )
        ):
            _conflict()
        if (
            epoch.kind is EpochKind.HISTORICAL_EXPANSION
            and not historical_coverage_complete(uow, projection_id, epoch)
        ):
            _conflict()
    revision = next_revision(epoch.revision)
    uow._execute(
        "UPDATE epochs SET state=?,discovery_complete=?,known_message_total=?,"
        "revision=? WHERE projection_id=? AND epoch_id=?",
        (
            state.value,
            int(discovery_complete),
            None if known_total is None else known_total.value,
            revision.value,
            projection_id.value,
            epoch_id.value,
        ),
    )
    return WriteReceipt("updated", epoch_id, revision)
