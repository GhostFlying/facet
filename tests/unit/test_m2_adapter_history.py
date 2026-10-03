"""Offline evidence for the narrow M2 Gmail adapter and History normalizer."""

from datetime import UTC, datetime

from fakes.gmail import HttpFailure, InsertReply

from facet.contracts import ProjectionId, ProviderId, ProviderPageToken, Timestamp
from facet.gmail.retry import ProviderFailure
from facet.gmail.source import SourceAdapter
from facet.gmail.target import TargetAdapter
from facet.projection.history import _typed_events


def test_source_discovery_uses_fixed_window_and_typed_page(gmail_controller):
    source = gmail_controller.service("source")
    args = {
        "userId": "me",
        "q": "after:2026/01/01 before:2026/07/01",
        "includeSpamTrash": False,
        "maxResults": 100,
        "pageToken": "next",
    }
    gmail_controller.script(
        "source",
        "messages.list",
        args,
        {
            "messages": [{"id": "m-1", "threadId": "t-1"}],
            "nextPageToken": "later",
            "resultSizeEstimate": 999,
        },
    )
    page = SourceAdapter(source).discover(
        window_start=datetime(2026, 1, 1, tzinfo=UTC),
        window_end=datetime(2026, 7, 1, tzinfo=UTC),
        page_token=ProviderPageToken("next"),
    )
    assert page.items[0].message_id == ProviderId("m-1")
    assert page.next_page_token == ProviderPageToken("later")
    assert page.result_size_estimate == 999


def test_history_normalization_keeps_typed_events_and_deduplicates():
    projection = ProjectionId("p1")
    observed = Timestamp(datetime(2026, 7, 1, tzinfo=UTC))
    rows, jobs = _typed_events(
        projection,
        ProviderId("h-1"),
        (
            {
                "id": "h-1",
                "messagesAdded": [
                    {"message": {"id": "m-1", "threadId": "t-1", "labelIds": []}}
                ],
                "labelsAdded": [
                    {
                        "message": {"id": "m-1", "threadId": "t-1", "labelIds": []},
                        "labelIds": ["AI/AddSender"],
                    }
                ],
                "messages": [{"id": "generic-ignored", "threadId": "t-1"}],
            },
            {
                "id": "h-1",
                "messagesAdded": [
                    {"message": {"id": "m-1", "threadId": "t-1", "labelIds": []}}
                ],
            },
        ),
        observed,
    )
    assert len(rows) == 2
    assert len(jobs) == 2
    assert {row.event.key.tag for row in rows} == {"message_added", "label_changed"}


def test_target_adapter_has_insert_and_readback_only(gmail_controller):
    target = gmail_controller.service("target", scopes=frozenset({"gmail.insert"}))
    gmail_controller.script(
        "target",
        "messages.insert",
        {
            "userId": "me",
            "body": {"raw": "aGVsbG8"},
            "internalDateSource": "dateHeader",
            "neverMarkSpam": True,
        },
        InsertReply(thread_id="target-thread"),
    )
    result = TargetAdapter(target).insert(b"hello")
    assert result.message_id == ProviderId("inserted-1")
    assert result.thread_id == ProviderId("target-thread")
    assert not hasattr(TargetAdapter, "send")
    assert not hasattr(TargetAdapter, "delete")


def test_provider_failures_are_closed_and_do_not_expose_wire_text(gmail_controller):
    gmail_controller.script(
        "source",
        "messages.list",
        {
            "userId": "me",
            "q": "after:2026/01/01 before:2026/07/01",
            "includeSpamTrash": False,
            "maxResults": 100,
        },
        HttpFailure(429, b"PRIVATE_PROVIDER_BODY"),
    )
    try:
        SourceAdapter(gmail_controller.service("source")).discover(
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 7, 1, tzinfo=UTC),
        )
    except ProviderFailure as error:
        assert error.code.value == "source_rate_limited"
        assert "PRIVATE_PROVIDER_BODY" not in repr(error)
    else:
        raise AssertionError("expected a closed provider failure")
