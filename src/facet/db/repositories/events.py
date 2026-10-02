"""Idempotent source-event metadata and durable resolution/effect work."""

from facet.contracts import ErrorCode, JobKind, ProviderId

from ..codecs import EventProcessing, StorageFailure, next_revision
from ..keys import event_key
from ..models import HistoryPageEventRow, SourceEventRow, SyncJobRow, WriteReceipt
from .base import (
    _batch,
    _conflict,
    _get,
    _guard,
    _insert,
    _mutating,
    _query,
    _require_row,
)
from .history import _page, _poll
from .jobs import enqueue


def _event(uow, projection_id, event_id, guard):
    row = _get(uow, projection_id, "source_events", (("event_id", event_id),))
    if row is None:
        _conflict()
    _guard(row.revision, guard)
    return row


@_mutating
def enrich_event(uow, projection_id, event_id, source_thread_id, guard):
    if type(source_thread_id) is not ProviderId:
        _conflict()
    row = _event(uow, projection_id, event_id, guard)
    current = row.event.source_thread_id
    if current == source_thread_id:
        return WriteReceipt("replayed", row.event_id, row.revision)
    revision = next_revision(row.revision)
    if current is None:
        uow._execute(
            "UPDATE source_events SET source_thread_id=?,revision=? "
            "WHERE projection_id=? AND event_id=? AND revision=?",
            (
                source_thread_id.value,
                revision.value,
                projection_id.value,
                event_id.value,
                row.revision.value,
            ),
        )
    else:
        # A contradictory response is an explainable durable attention state,
        # never permission to replace the original immutable event context.
        uow._execute(
            "UPDATE source_events SET processing='needs_attention',error_code=?,"
            "revision=? WHERE projection_id=? AND event_id=? AND revision=?",
            (
                ErrorCode.CONSISTENCY_FAILURE.value,
                revision.value,
                projection_id.value,
                event_id.value,
                row.revision.value,
            ),
        )
    return WriteReceipt("updated", row.event_id, revision)


@_mutating
def ingest_history_chunk(uow, projection_id, poll_id, ordinal, events, jobs, guard):
    _batch(events, SourceEventRow)
    _batch(jobs, SyncJobRow)
    poll, _ = _poll(uow, projection_id, poll_id, guard)
    page = _page(uow, projection_id, poll, ordinal)
    keys = set()
    for incoming in events:
        _require_row(projection_id, "source_events", incoming)
        if (
            incoming.processing is not EventProcessing.PENDING
            or incoming.revision.value != 0
            or incoming.error_code is not None
        ):
            _conflict()
        keys.add(incoming.event_key)
    for job in jobs:
        _require_row(projection_id, "sync_jobs", job)
        if (
            job.kind is not JobKind.RESOLVE_EVENT
            or job.origin_epoch_id != poll.origin_epoch_id
            or event_key(projection_id, job.subject.event_key) not in keys
        ):
            _conflict()
    for incoming in events:
        old = _get(
            uow, projection_id, "source_events", (("event_key", incoming.event_key),)
        )
        if old is None:
            _insert(uow, projection_id, "source_events", incoming)
            selected = incoming
        else:
            selected = old
            if incoming.event.source_thread_id is not None:
                from ..models import RevisionGuard

                enrich_event(
                    uow,
                    projection_id,
                    old.event_id,
                    incoming.event.source_thread_id,
                    RevisionGuard(old.revision),
                )
            # Allocation IDs/observed_at from a later provider response do not
            # change the original stable activation identity or first timestamp.
        membership = _get(
            uow,
            projection_id,
            "history_page_events",
            (
                ("poll_id", poll_id),
                ("ordinal", ordinal),
                ("event_id", selected.event_id),
            ),
        )
        if membership is None:
            _insert(
                uow,
                projection_id,
                "history_page_events",
                HistoryPageEventRow(projection_id, poll_id, ordinal, selected.event_id),
            )
    for job in jobs:
        enqueue(uow, projection_id, job)
    # Every selected event needs its exact resolution work, not an unrelated
    # job somewhere in the database. A chunk cannot silently truncate a page.
    observed, missing = _query(
        uow,
        "SELECT COUNT(*),COALESCE(SUM(NOT EXISTS(SELECT 1 FROM sync_jobs j "
        "WHERE j.projection_id=m.projection_id AND j.event_id=m.event_id "
        "AND j.kind='resolve_event')),0) FROM history_page_events m "
        "WHERE m.projection_id=? AND m.poll_id=? AND m.ordinal=?",
        (projection_id.value, poll_id.value, ordinal.value),
        maximum=1,
    )[0]
    if observed > page.expected_event_count.value or missing:
        _conflict()
    return WriteReceipt("updated", poll_id, poll.revision)


def _effect_matches(event, job):
    subject = job.subject
    thread = event.event.source_thread_id
    if thread is None:
        return False
    if job.kind is JobKind.PROJECT_MESSAGE:
        return (
            subject.source_message_id == event.event.key.source_message_id
            and subject.source_thread_id == thread
        )
    if job.kind is JobKind.EXPAND_THREAD:
        return subject.source_thread_id == thread
    return False


@_mutating
def classify_event(uow, projection_id, event_id, processing, error, jobs, guard):
    _batch(jobs, SyncJobRow)
    if (
        type(processing) is not EventProcessing
        or error is not None
        and type(error) is not ErrorCode
    ):
        _conflict()
    row = _event(uow, projection_id, event_id, guard)
    if processing is EventProcessing.PENDING:
        _conflict()
    if (
        processing in {EventProcessing.NEEDS_ATTENTION, EventProcessing.SOURCE_MISSING}
    ) != (error is not None):
        _conflict()
    if (
        processing is EventProcessing.SOURCE_MISSING
        and error is not ErrorCode.SOURCE_MISSING
    ):
        _conflict()
    if processing is EventProcessing.RESOLVED and row.event.source_thread_id is None:
        _conflict()
    if (
        row.processing in {EventProcessing.CONSUMED, EventProcessing.SOURCE_MISSING}
        and row.processing is not processing
    ):
        _conflict()
    if row.processing is EventProcessing.NEEDS_ATTENTION and processing not in {
        EventProcessing.NEEDS_ATTENTION,
        EventProcessing.SOURCE_MISSING,
    }:
        # There is no reviewed attention-override/decision registry in v1.
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    for job in jobs:
        _require_row(projection_id, "sync_jobs", job)
        if not _effect_matches(row, job):
            _conflict()
    if processing is EventProcessing.CONSUMED and not jobs:
        # No-admission decisions are not allocated in the v1 inventory. An
        # empty list or a job for another event is not a durable decision.
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    for job in jobs:
        enqueue(uow, projection_id, job)
    if processing is row.processing and error == row.error_code:
        return WriteReceipt("replayed", event_id, row.revision)
    revision = next_revision(row.revision)
    uow._execute(
        "UPDATE source_events SET processing=?,error_code=?,revision=? "
        "WHERE projection_id=? AND event_id=? AND revision=?",
        (
            processing.value,
            None if error is None else error.value,
            revision.value,
            projection_id.value,
            event_id.value,
            row.revision.value,
        ),
    )
    return WriteReceipt("updated", event_id, revision)
