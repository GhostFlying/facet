"""Normal Gmail History pagination and durable typed event ingestion."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from facet.contracts import (
    Count,
    JobKind,
    JobState,
    LabelChange,
    LocalId,
    Priority,
    ProviderId,
    Revision,
    Sha256Hex,
    SourceEvent,
    Timestamp,
)
from facet.contracts.records import (
    JobSubjectResolveEvent,
    SourceEventKeyLabelChanged,
    SourceEventKeyMessageAdded,
    SourceEventKeyMessageDeleted,
)
from facet.db.codecs import EventProcessing
from facet.db.keys import event_key, job_key
from facet.db.models import (
    HistoryGapRow,
    HistoryPageRow,
    HistoryPollRow,
    RevisionGuard,
    SourceEventRow,
    SyncJobRow,
)
from facet.db.repositories import epochs, events, history
from facet.db.repositories.base import _get
from facet.gmail.retry import ProviderFailure

_SYSTEM_LABEL_IDS = frozenset(
    {
        "CHAT",
        "DRAFT",
        "IMPORTANT",
        "INBOX",
        "SENT",
        "SPAM",
        "STARRED",
        "TRASH",
        "UNREAD",
        "CATEGORY_FORUMS",
        "CATEGORY_PERSONAL",
        "CATEGORY_PROMOTIONS",
        "CATEGORY_SOCIAL",
        "CATEGORY_UPDATES",
    }
)


def _is_system_label(label_id: ProviderId) -> bool:
    return label_id.value in _SYSTEM_LABEL_IDS


def _now() -> Timestamp:
    return Timestamp(datetime.now(UTC))


def _local_id() -> LocalId:
    return LocalId(uuid4().hex)


def _digest(keys) -> Sha256Hex:
    digest = hashlib.sha256()

    def fields_for(key):
        return tuple(
            getattr(getattr(key, field), "value", getattr(key, field))
            for field in (
                "tag",
                "history_record_id",
                "source_message_id",
                "label_id",
                "change",
            )
            if hasattr(key, field)
        )

    for key in sorted(keys, key=lambda value: repr(fields_for(value))):
        fields = fields_for(key)
        digest.update(repr(fields).encode("utf-8"))
        digest.update(b"\0")
    return Sha256Hex(digest.hexdigest())


def _typed_events(
    projection_id,
    history_id: ProviderId,
    records,
    observed: Timestamp,
    origin_epoch_id: LocalId | None = None,
):
    """Normalize only Gmail typed history facts; generic ``messages`` is ignored."""
    selected = {}
    for record in records:
        record_id = record.record_id
        for message in record.messages_added:
            message_id, thread_id = message.message_id, message.thread_id
            key = SourceEventKeyMessageAdded(
                "message_added", projection_id, record_id, message_id
            )
            selected[key] = SourceEventRow(
                projection_id,
                _local_id(),
                event_key(projection_id, key),
                SourceEvent(key, observed, thread_id),
                EventProcessing.PENDING,
                Revision(0),
                None,
            )
        for message in record.messages_deleted:
            message_id, thread_id = message.message_id, message.thread_id
            key = SourceEventKeyMessageDeleted(
                "message_deleted", projection_id, record_id, message_id
            )
            selected[key] = SourceEventRow(
                projection_id,
                _local_id(),
                event_key(projection_id, key),
                SourceEvent(key, observed, thread_id),
                EventProcessing.PENDING,
                Revision(0),
                None,
            )
        for messages, change in (
            (record.labels_added, LabelChange.ADDED),
            (record.labels_removed, LabelChange.REMOVED),
        ):
            for message in messages:
                message_id = message.message.message_id
                thread_id = message.message.thread_id
                for label in message.label_ids:
                    # Gmail emits ordinary mailbox state changes through the
                    # same History stream as Facet action labels.  The fixed
                    # system-label set cannot be a configured action label,
                    # so discard it before creating a business event. User
                    # labels, including stale action-label IDs, remain typed
                    # events and keep their existing attention semantics.
                    if _is_system_label(label):
                        continue
                    key = SourceEventKeyLabelChanged(
                        "label_changed",
                        projection_id,
                        record_id,
                        message_id,
                        label,
                        change,
                    )
                    selected[key] = SourceEventRow(
                        projection_id,
                        _local_id(),
                        event_key(projection_id, key),
                        SourceEvent(key, observed, thread_id),
                        EventProcessing.PENDING,
                        Revision(0),
                        None,
                    )
    rows = tuple(selected.values())
    jobs = tuple(
        SyncJobRow(
            projection_id,
            _local_id(),
            JobKind.RESOLVE_EVENT,
            Count(1),
            job_key(
                projection_id, JobSubjectResolveEvent("resolve_event", row.event.key)
            ),
            Priority.REALTIME,
            JobState.QUEUED,
            Revision(0),
            observed,
            observed,
            None,
            Count(0),
            None,
            origin_epoch_id,
            JobSubjectResolveEvent("resolve_event", row.event.key),
        )
        for row in rows
    )
    return rows, jobs


class HistoryProducer:
    """Consume a pre-authorized normal poll using the shipping repositories."""

    def __init__(self, source) -> None:
        self._source = source

    def consume(self, owner, projection_id, poll: HistoryPollRow) -> ProviderId:
        with owner.transaction() as uow:
            persisted = _get(
                uow, projection_id, "history_polls", (("poll_id", poll.poll_id),)
            )
            if persisted is None:
                history.begin_history_poll(
                    uow,
                    projection_id,
                    poll,
                    RevisionGuard(poll.start_checkpoint_revision),
                )
                persisted = _get(
                    uow, projection_id, "history_polls", (("poll_id", poll.poll_id),)
                )
            elif persisted.state.value != "reading":
                return persisted.final_history_id or persisted.start_cursor
        revision = persisted.revision
        token = persisted.next_page_token if persisted is not None else None
        ordinal = persisted.completed_pages.value + 1 if persisted is not None else 1
        final_history_id = poll.start_cursor
        if persisted.completed_pages.value > 0 and persisted.next_page_token is None:
            with owner.transaction() as uow:
                prior = history.get_history_page(
                    uow,
                    projection_id,
                    poll.poll_id,
                    Count(persisted.completed_pages.value),
                )
                if prior is not None:
                    final_history_id = prior.response_history_id
                history.finish_history_poll(
                    uow,
                    projection_id,
                    poll.poll_id,
                    final_history_id,
                    RevisionGuard(revision),
                )
            return final_history_id
        while True:
            try:
                page = self._source.history(poll.start_cursor, page_token=token)
            except ProviderFailure as error:
                if error.status != 404:
                    raise
                # A stale cursor is an explicit bounded attention state.  Fence
                # H1 from a fresh profile and persist the gap after abandoning
                # the poll; the old checkpoint remains unchanged.
                h1 = self._source.profile().history_id
                observed_at = _now()
                with owner.transaction() as uow:
                    current = _get(
                        uow,
                        projection_id,
                        "history_polls",
                        (("poll_id", poll.poll_id),),
                    )
                    checkpoint = _get(uow, projection_id, "history_checkpoints", ())
                    if current is None or checkpoint is None:
                        raise error.with_code(error.code) from None
                    history.abandon_history_poll(
                        uow,
                        projection_id,
                        poll.poll_id,
                        observed_at,
                        RevisionGuard(current.revision),
                    )
                    after = _get(uow, projection_id, "history_checkpoints", ())
                    gap = HistoryGapRow(
                        projection_id,
                        LocalId(uuid4().hex),
                        poll.poll_id,
                        poll.start_cursor,
                        checkpoint.cursor,
                        after.revision,
                        observed_at,
                        checkpoint.reliable_coverage_at,
                        h1,
                        observed_at,
                    )
                    epochs.record_gap(uow, projection_id, gap)
                raise
            # The poll start is the stable observation timestamp for replay;
            # restarting after a page fault must reconstruct the same closed
            # page row rather than allocate a second local fact.
            now = poll.started_at
            rows, jobs = _typed_events(
                projection_id, page.history_id, page.records, now, poll.origin_epoch_id
            )
            digest = _digest(tuple(row.event.key for row in rows))
            page_row = HistoryPageRow(
                projection_id,
                poll.poll_id,
                Count(ordinal),
                page.history_id,
                token,
                page.next_page_token,
                now,
                digest,
                Count(len(rows)),
                False,
            )
            with owner.transaction() as uow:
                page_receipt = history.begin_history_page(
                    uow, projection_id, page_row, RevisionGuard(revision)
                )
                ingest = events.ingest_history_chunk(
                    uow,
                    projection_id,
                    poll.poll_id,
                    Count(ordinal),
                    rows,
                    jobs,
                    RevisionGuard(page_receipt.revision),
                )
                revision = ingest.revision
            with owner.transaction() as uow:
                finished = history.finish_history_page(
                    uow,
                    projection_id,
                    poll.poll_id,
                    Count(ordinal),
                    digest,
                    RevisionGuard(revision),
                )
                revision = finished.revision
            final_history_id = page.history_id
            if page.next_page_token is None:
                break
            token = page.next_page_token
            ordinal += 1
        with owner.transaction() as uow:
            history.finish_history_poll(
                uow,
                projection_id,
                poll.poll_id,
                final_history_id,
                RevisionGuard(revision),
            )
        return final_history_id


HistoryPoller = HistoryProducer
