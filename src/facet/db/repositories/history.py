"""Durable History pagination; provider calls and normalization stay outside SQL."""

from facet.contracts import Count, EpochKind, ProviderId, Sha256Hex, Timestamp

from ..codecs import (
    AuditKind,
    AuditObjectKind,
    PollOrigin,
    PollState,
    next_revision,
    timestamp_to_sql,
)
from ..models import WriteReceipt
from .audit import _audit
from .base import (
    _conflict,
    _get,
    _guard,
    _insert,
    _mutating,
    _query,
    _require_row,
)
from .epochs import _latest_unresolved_gap


def _checkpoint(uow, projection_id):
    checkpoint = _get(uow, projection_id, "history_checkpoints", ())
    if checkpoint is None:
        _conflict()
    return checkpoint


def _origin(uow, projection_id, poll, checkpoint):
    if checkpoint.revision != poll.start_checkpoint_revision:
        _conflict()
    unresolved = _latest_unresolved_gap(uow, projection_id)
    if poll.origin is PollOrigin.CHECKPOINT:
        if (
            checkpoint.cursor is None
            or checkpoint.reliable_coverage_at is None
            or poll.start_cursor != checkpoint.cursor
            or poll.origin_epoch_id is not None
            or unresolved is not None
        ):
            _conflict()
        return None
    epoch = _get(uow, projection_id, "epochs", (("epoch_id", poll.origin_epoch_id),))
    if epoch is None or epoch.fence_history_id != poll.start_cursor:
        _conflict()
    if poll.origin is PollOrigin.INITIAL_EPOCH:
        if (
            checkpoint.cursor is not None
            or checkpoint.reliable_coverage_at is not None
            or unresolved is not None
            or epoch.kind is not EpochKind.INITIAL_BACKFILL
            or epoch.decision.tag != "backfill_start"
            or epoch.discovery_cutoff is None
            or epoch.fence_recorded_at is None
        ):
            _conflict()
        return epoch
    if (
        poll.origin is not PollOrigin.RECOVERY_EPOCH
        or epoch.kind is not EpochKind.HISTORY_GAP
        or unresolved is None
        or epoch.gap_id != unresolved.gap_id
        or (checkpoint.cursor, checkpoint.reliable_coverage_at)
        != (unresolved.checkpoint_cursor, unresolved.reliable_coverage_at)
        or (epoch.fence_history_id, epoch.fence_recorded_at)
        != (unresolved.h1, unresolved.h1_recorded_at)
        or not epoch.discovery_complete
        or epoch.decision.tag not in {"scheduled_reconcile", "gap_approval"}
    ):
        _conflict()
    # A stopped historical selector is not a new admission requirement. The
    # window and every currently active thread are the required recovery scans.
    missing = _query(
        uow,
        "SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM epoch_partitions "
        "WHERE projection_id=? AND epoch_id=? AND tag='source_window' "
        "AND state='complete') OR EXISTS(SELECT 1 FROM tracked_threads t "
        "WHERE t.projection_id=? AND t.active=1 AND NOT EXISTS(SELECT 1 "
        "FROM epoch_partitions p WHERE p.projection_id=t.projection_id "
        "AND p.epoch_id=? AND p.tag='source_thread' "
        "AND p.source_thread_id=t.source_thread_id AND p.state='complete'))",
        (
            projection_id.value,
            epoch.epoch_id.value,
            projection_id.value,
            epoch.epoch_id.value,
        ),
        maximum=1,
    )
    if missing:
        _conflict()
    return epoch


def _poll(uow, projection_id, poll_id, guard):
    poll = _get(uow, projection_id, "history_polls", (("poll_id", poll_id),))
    if poll is None or poll.state is not PollState.READING:
        _conflict()
    _guard(poll.revision, guard)
    checkpoint = _checkpoint(uow, projection_id)
    if checkpoint.active_poll_id != poll.poll_id:
        _conflict()
    _origin(uow, projection_id, poll, checkpoint)
    return poll, checkpoint


def _page(uow, projection_id, poll, ordinal):
    page = _get(
        uow,
        projection_id,
        "history_pages",
        (("poll_id", poll.poll_id), ("ordinal", ordinal)),
    )
    if (
        page is None
        or page.complete
        or page.ordinal.value != poll.completed_pages.value + 1
        or page.input_page_token != poll.next_page_token
    ):
        _conflict()
    return page


@_mutating
def begin_history_poll(uow, projection_id, row, guard):
    _require_row(projection_id, "history_polls", row)
    checkpoint = _checkpoint(uow, projection_id)
    _guard(checkpoint.revision, guard)
    if (
        row.state is not PollState.READING
        or row.revision.value != 0
        or row.completed_pages != Count(0)
        or row.next_page_token is not None
        or row.final_history_id is not None
        or row.finished_at is not None
        or (
            checkpoint.reliable_coverage_at is not None
            and row.started_at.value < checkpoint.reliable_coverage_at.value
        )
    ):
        _conflict()
    _origin(uow, projection_id, row, checkpoint)
    old = _get(uow, projection_id, "history_polls", (("poll_id", row.poll_id),))
    if old is not None:
        if old != row or checkpoint.active_poll_id != old.poll_id:
            _conflict()
        return WriteReceipt("replayed", row.poll_id, old.revision)
    if checkpoint.active_poll_id is not None:
        _conflict()
    _insert(uow, projection_id, "history_polls", row)
    uow._execute(
        "UPDATE history_checkpoints SET active_poll_id=? WHERE projection_id=? "
        "AND revision=? AND active_poll_id IS NULL",
        (row.poll_id.value, projection_id.value, checkpoint.revision.value),
    )
    return WriteReceipt("created", row.poll_id, row.revision)


@_mutating
def begin_history_page(uow, projection_id, page, guard):
    _require_row(projection_id, "history_pages", page)
    poll, _ = _poll(uow, projection_id, page.poll_id, guard)
    if (
        page.complete
        or page.ordinal.value != poll.completed_pages.value + 1
        or page.input_page_token != poll.next_page_token
        or page.received_at.value < poll.started_at.value
        or (poll.completed_pages.value > 0 and poll.next_page_token is None)
    ):
        _conflict()
    old = _get(
        uow,
        projection_id,
        "history_pages",
        (("poll_id", page.poll_id), ("ordinal", page.ordinal)),
    )
    if old is not None:
        if old != page:
            _conflict()
        return WriteReceipt("replayed", page.poll_id, poll.revision)
    _insert(uow, projection_id, "history_pages", page)
    revision = _advance_poll_revision(uow, projection_id, poll)
    return WriteReceipt("created", page.poll_id, revision)


def _advance_poll_revision(uow, projection_id, poll):
    revision = next_revision(poll.revision)
    cursor = uow._execute(
        "UPDATE history_polls SET revision=? "
        "WHERE projection_id=? AND poll_id=? AND revision=?",
        (revision.value, projection_id.value, poll.poll_id.value, poll.revision.value),
    )
    if cursor.rowcount != 1:
        _conflict()
    return revision


def _page_work(uow, projection_id, poll, ordinal):
    epoch = None if poll.origin_epoch_id is None else poll.origin_epoch_id.value
    return _query(
        uow,
        "SELECT COUNT(*),COALESCE(SUM(NOT EXISTS(SELECT 1 FROM sync_jobs j "
        "WHERE j.projection_id=m.projection_id AND j.kind='resolve_event' "
        "AND j.event_id=m.event_id AND (? IS NULL OR EXISTS(SELECT 1 FROM "
        "epoch_jobs e WHERE e.projection_id=j.projection_id AND e.job_id=j.job_id "
        "AND e.epoch_id=?)))),0) FROM history_page_events m "
        "WHERE m.projection_id=? AND m.poll_id=? AND m.ordinal=?",
        (epoch, epoch, projection_id.value, poll.poll_id.value, ordinal.value),
        maximum=1,
    )[0]


@_mutating
def finish_history_page(uow, projection_id, poll_id, ordinal, metadata_digest, guard):
    if type(metadata_digest) is not Sha256Hex:
        _conflict()
    poll, _ = _poll(uow, projection_id, poll_id, guard)
    page = _page(uow, projection_id, poll, ordinal)
    if metadata_digest != page.metadata_digest:
        _conflict()
    # This validates persisted distinct membership and required durable work,
    # not the caller's provider-response normalization algorithm/order. Shared
    # event rows can be enriched/reused without rewriting a saved page identity.
    observed, missing = _page_work(uow, projection_id, poll, ordinal)
    if observed != page.expected_event_count.value or missing:
        _conflict()
    revision = next_revision(poll.revision)
    uow._execute(
        "UPDATE history_pages SET complete=1 WHERE projection_id=? AND poll_id=? "
        "AND ordinal=? AND complete=0",
        (projection_id.value, poll_id.value, ordinal.value),
    )
    uow._execute(
        "UPDATE history_polls SET completed_pages=?,next_page_token=?,revision=? "
        "WHERE projection_id=? AND poll_id=? AND revision=?",
        (
            ordinal.value,
            None if page.next_page_token is None else page.next_page_token.value,
            revision.value,
            projection_id.value,
            poll_id.value,
            poll.revision.value,
        ),
    )
    _audit(
        uow,
        projection_id,
        AuditKind.PAGE_INGESTED,
        AuditObjectKind.PROJECTION,
        page.received_at,
    )
    return WriteReceipt("updated", poll_id, revision)


@_mutating
def finish_history_poll(uow, projection_id, poll_id, final_history_id, guard):
    if type(final_history_id) is not ProviderId:
        _conflict()
    poll, checkpoint = _poll(uow, projection_id, poll_id, guard)
    if poll.completed_pages.value < 1 or poll.next_page_token is not None:
        _conflict()
    final_page = _get(
        uow,
        projection_id,
        "history_pages",
        (("poll_id", poll_id), ("ordinal", poll.completed_pages)),
    )
    invalid_chain = _query(
        uow,
        "WITH ordered AS (SELECT ordinal,complete,input_page_token,next_page_token,"
        "LAG(next_page_token) OVER(ORDER BY ordinal) previous_token "
        "FROM history_pages WHERE projection_id=? AND poll_id=?) "
        "SELECT COUNT(*),COALESCE(SUM(complete=0 OR ordinal<1 OR "
        "(ordinal=1 AND input_page_token IS NOT NULL) OR "
        "(ordinal>1 AND (previous_token IS NULL OR input_page_token "
        "IS NOT previous_token))),0),MIN(ordinal),MAX(ordinal) FROM ordered",
        (projection_id.value, poll_id.value),
        maximum=1,
    )[0]
    if (
        final_page is None
        or not final_page.complete
        or final_page.next_page_token is not None
        or final_page.response_history_id != final_history_id
        or invalid_chain
        != (poll.completed_pages.value, 0, 1, poll.completed_pages.value)
        or (
            checkpoint.reliable_coverage_at is not None
            and poll.started_at.value < checkpoint.reliable_coverage_at.value
        )
    ):
        _conflict()
    unfinished = _query(
        uow,
        "SELECT 1 FROM history_pages p WHERE p.projection_id=? AND p.poll_id=? "
        "AND (p.expected_event_count<>(SELECT COUNT(*) FROM history_page_events m "
        "WHERE m.projection_id=p.projection_id AND m.poll_id=p.poll_id "
        "AND m.ordinal=p.ordinal) OR EXISTS(SELECT 1 FROM history_page_events m "
        "WHERE m.projection_id=p.projection_id AND m.poll_id=p.poll_id "
        "AND m.ordinal=p.ordinal AND NOT EXISTS(SELECT 1 FROM sync_jobs j "
        "WHERE j.projection_id=m.projection_id AND j.kind='resolve_event' "
        "AND j.event_id=m.event_id AND (? IS NULL OR EXISTS(SELECT 1 FROM "
        "epoch_jobs e WHERE e.projection_id=j.projection_id AND e.job_id=j.job_id "
        "AND e.epoch_id=?))))) LIMIT 1",
        (
            projection_id.value,
            poll_id.value,
            None if poll.origin_epoch_id is None else poll.origin_epoch_id.value,
            None if poll.origin_epoch_id is None else poll.origin_epoch_id.value,
        ),
        maximum=1,
    )
    if unfinished:
        _conflict()
    poll_revision, checkpoint_revision = (
        next_revision(poll.revision),
        next_revision(checkpoint.revision),
    )
    uow._execute(
        "UPDATE history_polls SET state='completed',final_history_id=?,finished_at=?,"
        "revision=? WHERE projection_id=? AND poll_id=? AND revision=?",
        (
            final_history_id.value,
            timestamp_to_sql(final_page.received_at),
            poll_revision.value,
            projection_id.value,
            poll_id.value,
            poll.revision.value,
        ),
    )
    uow._execute(
        "UPDATE history_checkpoints SET cursor=?,reliable_coverage_at=?,revision=?,"
        "active_poll_id=NULL WHERE projection_id=? AND revision=? AND active_poll_id=?",
        (
            final_history_id.value,
            timestamp_to_sql(poll.started_at),
            checkpoint_revision.value,
            projection_id.value,
            checkpoint.revision.value,
            poll_id.value,
        ),
    )
    if poll.origin_epoch_id is not None:
        epoch = _get(
            uow, projection_id, "epochs", (("epoch_id", poll.origin_epoch_id),)
        )
        if (
            epoch.catchup_history_id is not None
            and epoch.catchup_history_id != final_history_id
        ):
            _conflict()
        uow._execute(
            "UPDATE epochs SET catchup_history_id=?,revision=? WHERE projection_id=? "
            "AND epoch_id=? AND revision=?",
            (
                final_history_id.value,
                next_revision(epoch.revision).value,
                projection_id.value,
                epoch.epoch_id.value,
                epoch.revision.value,
            ),
        )
    _audit(
        uow,
        projection_id,
        AuditKind.CURSOR_ADVANCED,
        AuditObjectKind.PROJECTION,
        final_page.received_at,
    )
    return WriteReceipt("updated", poll_id, poll_revision)


@_mutating
def abandon_history_poll(uow, projection_id, poll_id, finished_at, guard):
    if type(finished_at) is not Timestamp:
        _conflict()
    # Abandonment must remain possible even when a new recovery gate appears.
    poll = _get(uow, projection_id, "history_polls", (("poll_id", poll_id),))
    if poll is None or poll.state is not PollState.READING:
        _conflict()
    _guard(poll.revision, guard)
    checkpoint = _checkpoint(uow, projection_id)
    if (
        checkpoint.active_poll_id != poll_id
        or checkpoint.revision != poll.start_checkpoint_revision
        or finished_at.value < poll.started_at.value
    ):
        _conflict()
    revision = next_revision(poll.revision)
    uow._execute(
        "UPDATE history_polls SET state='abandoned',finished_at=?,revision=? "
        "WHERE projection_id=? AND poll_id=? AND revision=?",
        (
            timestamp_to_sql(finished_at),
            revision.value,
            projection_id.value,
            poll_id.value,
            poll.revision.value,
        ),
    )
    uow._execute(
        "UPDATE history_checkpoints SET active_poll_id=NULL,revision=? "
        "WHERE projection_id=? AND revision=? AND active_poll_id=?",
        (
            next_revision(checkpoint.revision).value,
            projection_id.value,
            checkpoint.revision.value,
            poll_id.value,
        ),
    )
    return WriteReceipt("updated", poll_id, revision)
