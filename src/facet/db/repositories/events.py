"""Idempotent source-event metadata and durable resolution/effect work."""

from facet.contracts import (
    ClaimPhase,
    ErrorCode,
    JobKind,
    JobState,
    LabelChange,
    ProviderId,
)
from facet.contracts.records import (
    JobSubjectResolveEvent,
    SourceEventKeyLabelChanged,
    SourceEventKeyMessageAdded,
    SourceEventKeyMessageDeleted,
)

from ..codecs import ActionState, EventProcessing, StorageFailure, next_revision
from ..keys import event_key, job_key
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
from .jobs import _thread_guard, complete_noninsert_job, enqueue


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
def consume_message_added_no_effect(uow, projection_id, event_id, guard):
    """Finish a resolver's ordinary no-op, without reopening terminal work."""
    row = _event(uow, projection_id, event_id, guard)
    if (
        type(row.event.key) is not SourceEventKeyMessageAdded
        or row.event.source_thread_id is None
        or row.error_code is not None
        or row.processing not in {EventProcessing.PENDING, EventProcessing.CONSUMED}
    ):
        _conflict()
    if row.processing is EventProcessing.CONSUMED:
        return WriteReceipt("replayed", event_id, row.revision)
    revision = next_revision(row.revision)
    uow._execute(
        "UPDATE source_events SET processing='consumed',revision=? "
        "WHERE projection_id=? AND event_id=? AND revision=?",
        (revision.value, projection_id.value, event_id.value, row.revision.value),
    )
    return WriteReceipt("updated", event_id, revision)


def _executed_label_alias_job(uow, projection_id, row):
    key = row.event.key
    if (
        type(key) is not SourceEventKeyLabelChanged
        or key.change is not LabelChange.ADDED
        or row.event.source_thread_id is None
    ):
        _conflict()
    action = _get(
        uow,
        projection_id,
        "action_commands",
        (
            ("history_record_id", key.history_record_id),
            ("label_id", key.label_id),
            ("source_thread_id", row.event.source_thread_id),
        ),
    )
    if action is None or action.event_id == row.event_id:
        _conflict()
    canonical = _get(
        uow, projection_id, "source_events", (("event_id", action.event_id),)
    )
    if (
        action.state is not ActionState.EXECUTED
        or canonical is None
        or canonical.processing is not EventProcessing.CONSUMED
        or canonical.error_code is not None
        or type(canonical.event.key) is not SourceEventKeyLabelChanged
        or canonical.event.key.change is not LabelChange.ADDED
        or canonical.event.key.history_record_id != key.history_record_id
        or canonical.event.key.label_id != key.label_id
        or canonical.event.source_thread_id != row.event.source_thread_id
    ):
        raise StorageFailure(ErrorCode.OWNER_BUSY)
    canonical_job = _get(
        uow,
        projection_id,
        "sync_jobs",
        (
            (
                "stable_key",
                job_key(
                    projection_id,
                    JobSubjectResolveEvent("resolve_event", canonical.event.key),
                ),
            ),
        ),
    )
    if canonical_job is None or canonical_job.state is not JobState.COMPLETED:
        raise StorageFailure(ErrorCode.OWNER_BUSY)
    alias_job = _get(
        uow,
        projection_id,
        "sync_jobs",
        (
            (
                "stable_key",
                job_key(projection_id, JobSubjectResolveEvent("resolve_event", key)),
            ),
        ),
    )
    if alias_job is None:
        _conflict()
    return alias_job


@_mutating
def consume_executed_label_alias(uow, projection_id, event_id, guard):
    """Close a per-message alias of a completed thread action, with no effect."""
    row = _event(uow, projection_id, event_id, guard)
    if row.error_code is not None or row.processing not in {
        EventProcessing.PENDING,
        EventProcessing.CONSUMED,
    }:
        _conflict()
    alias_job = _executed_label_alias_job(uow, projection_id, row)
    if row.processing is EventProcessing.CONSUMED:
        if alias_job.state is not JobState.COMPLETED:
            _conflict()
        return WriteReceipt("replayed", alias_job.job_id, alias_job.revision)
    claim = _get(uow, projection_id, "job_claims", (("job_id", alias_job.job_id),))
    if (
        alias_job.state is not JobState.CLAIMED
        or claim is None
        or claim.claim.owner_run_id != uow._session._info.owner_run_id
        or claim.claim.phase is not ClaimPhase.PREPARING
        or claim.claim.job_revision != alias_job.revision
    ):
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    revision = next_revision(row.revision)
    uow._execute(
        "UPDATE source_events SET processing='consumed',revision=? "
        "WHERE projection_id=? AND event_id=? AND revision=?",
        (revision.value, projection_id.value, event_id.value, row.revision.value),
    )
    from ..models import RevisionGuard

    return complete_noninsert_job(
        uow, projection_id, alias_job.job_id, RevisionGuard(alias_job.revision)
    )


@_mutating
def repair_executed_label_alias(uow, projection_id, event_id, event_guard, job_guard):
    """Explicit owner maintenance only; normal sync never calls this repair."""
    row = _event(uow, projection_id, event_id, event_guard)
    job = _executed_label_alias_job(uow, projection_id, row)
    _guard(job.revision, job_guard)
    if row.processing is EventProcessing.CONSUMED and job.state is JobState.COMPLETED:
        if row.error_code is not None or job.last_error_code is not None:
            _conflict()
        return WriteReceipt("replayed", job.job_id, job.revision)
    if (
        row.processing is not EventProcessing.NEEDS_ATTENTION
        or row.error_code is not ErrorCode.REQUEST_CONFLICT
        or job.state is not JobState.NEEDS_ATTENTION
        or job.last_error_code is not ErrorCode.REQUEST_CONFLICT
        or _get(uow, projection_id, "job_claims", (("job_id", job.job_id),)) is not None
    ):
        _conflict()
    event_revision = next_revision(row.revision)
    job_revision = next_revision(job.revision)
    uow._execute(
        "UPDATE source_events SET processing='consumed',error_code=NULL,revision=? "
        "WHERE projection_id=? AND event_id=? AND revision=?",
        (event_revision.value, projection_id.value, event_id.value, row.revision.value),
    )
    uow._execute(
        "UPDATE sync_jobs SET state='completed',last_error_code=NULL,"
        "revision=?,next_attempt_at=NULL "
        "WHERE projection_id=? AND job_id=? AND revision=?",
        (job_revision.value, projection_id.value, job.job_id.value, job.revision.value),
    )
    return WriteReceipt("updated", job.job_id, job_revision)


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
        # A completed BlackList action is itself the durable effect. It does
        # not allocate expansion work, but only this exact action may close
        # the source event without a projection job.
        key = row.event.key
        if type(key) is SourceEventKeyMessageDeleted:
            # A deletion for an untracked message has no Facet effect.  The
            # resolver may close that durable event without inventing an
            # action command or a projection job.
            pass
        else:
            from ..codecs import ActionKind, ActionState

            action = None
            if type(key) is SourceEventKeyLabelChanged:
                action = _get(
                    uow,
                    projection_id,
                    "action_commands",
                    (
                        ("event_id", row.event_id),
                        ("history_record_id", key.history_record_id),
                        ("label_id", key.label_id),
                        ("source_thread_id", row.event.source_thread_id),
                    ),
                )
            if (
                action is None
                or action.kind is not ActionKind.BLACKLIST
                or action.state is not ActionState.EXECUTED
                or action.source_thread_id != row.event.source_thread_id
            ):
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
