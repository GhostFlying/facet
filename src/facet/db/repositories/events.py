"""Idempotent source-event metadata and durable resolution/effect work."""

from facet.contracts import ErrorCode, JobKind, JobState, ProviderId

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
    _require_row,
)
from .history import _advance_poll_revision, _page, _page_work, _poll
from .jobs import _thread_guard, enqueue


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
    changed = False
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
            changed = True
            selected = incoming
        else:
            selected = old
            if incoming.event.source_thread_id is not None:
                from ..models import RevisionGuard

                receipt = enrich_event(
                    uow,
                    projection_id,
                    old.event_id,
                    incoming.event.source_thread_id,
                    RevisionGuard(old.revision),
                )
                changed |= receipt.disposition != "replayed"
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
            changed = True
    for job in jobs:
        old = _get(uow, projection_id, "sync_jobs", (("stable_key", job.stable_key),))
        # enqueue can retain an existing job while adding this poll's epoch work.
        # Its replay receipt alone therefore cannot prove a zero-write chunk.
        changed |= old is None or (
            poll.origin_epoch_id is not None
            and _get(
                uow,
                projection_id,
                "epoch_jobs",
                (("epoch_id", poll.origin_epoch_id), ("job_id", old.job_id)),
            )
            is None
        )
        enqueue(uow, projection_id, job)
    # Every selected event needs its exact resolution work, not an unrelated
    # job somewhere in the database. A chunk cannot silently truncate a page.
    observed, missing = _page_work(uow, projection_id, poll, ordinal)
    if observed > page.expected_event_count.value or missing:
        _conflict()
    if not changed:
        return WriteReceipt("replayed", poll_id, poll.revision)
    revision = _advance_poll_revision(uow, projection_id, poll)
    return WriteReceipt("updated", poll_id, revision)


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
    if processing is row.processing and error == row.error_code:
        # A genuine completed classification can be inspected/replayed after
        # stop. It cannot enqueue work or join a new epoch. Every supplied
        # effect must already exist with exactly the recorded semantic identity.
        for job in jobs:
            old = _get(
                uow, projection_id, "sync_jobs", (("stable_key", job.stable_key),)
            )
            if old is None or (old.subject, old.kind, old.priority) != (
                job.subject,
                job.kind,
                job.priority,
            ):
                _conflict()
        return WriteReceipt("replayed", event_id, row.revision)
    for job in jobs:
        # enqueue's historical stable-key replay is intentionally not scheduling
        # authority. A NEW consumption needs current admission/generation and a
        # still-valid durable effect, even if this key existed before stop/fail.
        _thread_guard(uow, projection_id, job)
        old = _get(uow, projection_id, "sync_jobs", (("stable_key", job.stable_key),))
        if old is not None and old.state in {
            JobState.CANCELLED,
            JobState.FAILED,
            JobState.SOURCE_MISSING,
            JobState.NEEDS_ATTENTION,
        }:
            _conflict()
    for job in jobs:
        enqueue(uow, projection_id, job)
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
