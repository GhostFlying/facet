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
    HistoryPageRow,
    HistoryPollRow,
    RevisionGuard,
    SourceEventRow,
    SyncJobRow,
)
from facet.db.repositories import events, history
from facet.db.repositories.base import _get


def _now() -> Timestamp:
    return Timestamp(datetime.now(UTC))


def _local_id() -> LocalId:
    return LocalId(uuid4().hex)


def _digest(keys) -> Sha256Hex:
    digest = hashlib.sha256()

    def fields_for(key):
        return tuple(
            getattr(key, field)
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
        fields = tuple(
            getattr(key, field)
            for field in (
                "tag",
                "history_record_id",
                "source_message_id",
                "label_id",
                "change",
            )
            if hasattr(key, field)
        )
        digest.update(repr(fields).encode("utf-8"))
        digest.update(b"\0")
    return Sha256Hex(digest.hexdigest())


def _message(value: dict) -> tuple[ProviderId, ProviderId]:
    return ProviderId(value["id"]), ProviderId(value["threadId"])


def _typed_events(
    projection_id,
    history_id: ProviderId,
    records: tuple[dict, ...],
    observed: Timestamp,
):
    """Normalize only Gmail typed history facts; generic ``messages`` is ignored."""
    selected = {}
    for record in records:
        record_id = ProviderId(str(record["id"]))
        for message in record.get("messagesAdded", ()):
            message_id, thread_id = _message(message["message"])
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
        for message in record.get("messagesDeleted", ()):
            message_id, thread_id = _message(message["message"])
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
        for field, change in (
            ("labelsAdded", LabelChange.ADDED),
            ("labelsRemoved", LabelChange.REMOVED),
        ):
            for message in record.get(field, ()):
                message_id, thread_id = _message(message["message"])
                for label_id in message.get("labelIds", ()):
                    label = ProviderId(str(label_id))
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
            None,
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
            begun = history.begin_history_poll(
                uow, projection_id, poll, RevisionGuard(poll.start_checkpoint_revision)
            )
            persisted = _get(
                uow, projection_id, "history_polls", (("poll_id", poll.poll_id),)
            )
        revision = persisted.revision if persisted is not None else begun.revision
        token = persisted.next_page_token if persisted is not None else None
        ordinal = persisted.completed_pages.value + 1 if persisted is not None else 1
        final_history_id = poll.start_cursor
        while True:
            page = self._source.history(poll.start_cursor, page_token=token)
            # The poll start is the stable observation timestamp for replay;
            # restarting after a page fault must reconstruct the same closed
            # page row rather than allocate a second local fact.
            now = poll.started_at
            rows, jobs = _typed_events(
                projection_id, page.history_id, page.records, now
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
