from datetime import UTC, datetime

import pytest

from facet.contracts import ErrorCode
from facet.db.codecs import ActionKind, PrivateAddress
from facet.gmail.retry import ProviderFailure
from facet.gmail.source import CandidateAttentionReason, SourceAdapter


def _list_args():
    return {
        "userId": "me",
        "q": "after:2026/01/01 before:2026/07/01",
        "includeSpamTrash": False,
        "maxResults": 100,
    }


def _metadata(message_id="m-1", thread_id="t-1", *, labels=None, headers=None):
    return {
        "id": message_id,
        "threadId": thread_id,
        "labelIds": list(labels or ()),
        "internalDate": "1767225600000",
        "payload": {"headers": list(headers or ())},
    }


def _adapter(gmail_controller):
    return SourceAdapter(
        gmail_controller.service("source"),
        source_account=PrivateAddress("source@example.invalid"),
    )


def _candidates(gmail_controller, metadata):
    gmail_controller.script(
        "source",
        "messages.list",
        _list_args(),
        {"messages": [{"id": "m-1", "threadId": "t-1"}]},
    )
    gmail_controller.script(
        "source",
        "messages.get",
        {"userId": "me", "id": "m-1", "format": "metadata"},
        metadata,
    )
    return _adapter(gmail_controller).discover_candidates(
        window_start=datetime(2026, 1, 1, tzinfo=UTC),
        window_end=datetime(2026, 7, 1, tzinfo=UTC),
    )


def test_profile_rejects_provider_account_mismatch(gmail_controller):
    gmail_controller.profile(
        "source",
        {
            "emailAddress": "wrong@example.invalid",
            "messagesTotal": 0,
            "threadsTotal": 0,
            "historyId": "701",
        },
    )

    with pytest.raises(ProviderFailure) as error:
        _adapter(gmail_controller).profile()

    assert error.value.code is ErrorCode.BINDING_MISMATCH


def test_matching_metadata_candidate_does_not_fetch_raw_or_expose_headers(
    gmail_controller,
):
    result = _candidates(
        gmail_controller,
        _metadata(
            headers=(
                {"name": "From", "value": "Sender@Example.COM"},
                {
                    "name": "Authentication-Results",
                    "value": "forged.invalid; dkim=fail",
                },
            )
        ),
    )
    item = result.items[0]
    assert item.candidate is not None
    assert item.candidate.sender.value == "Sender@example.com"
    assert result.next_page_token is None
    assert "Sender" not in repr(item)


def test_constructor_binding_cannot_be_overridden(gmail_controller):
    with pytest.raises(ProviderFailure) as error:
        _adapter(gmail_controller).discover_candidates(
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 7, 1, tzinfo=UTC),
            source_account=PrivateAddress("other@example.invalid"),
        )
    assert error.value.code is ErrorCode.BINDING_MISMATCH


@pytest.mark.parametrize(
    ("headers", "labels", "reason"),
    [
        ((), (), CandidateAttentionReason.MISSING_METADATA),
        (
            (
                {"name": "From", "value": "one@example.invalid"},
                {"name": "FROM", "value": "two@example.invalid"},
            ),
            (),
            CandidateAttentionReason.MULTIPLE_FROM,
        ),
        (
            ({"name": "From", "value": "not-an-address"},),
            (),
            CandidateAttentionReason.MALFORMED_FROM,
        ),
        (
            ({"name": "From", "value": "one@example.invalid"},),
            ("UNKNOWN_LABEL",),
            CandidateAttentionReason.UNSUPPORTED_LABELS,
        ),
    ],
)
def test_candidate_metadata_attention_is_typed(
    gmail_controller, headers, labels, reason
):
    page = _candidates(gmail_controller, _metadata(labels=labels, headers=headers))
    assert page.items[0].candidate is None
    assert page.items[0].attention.reason is reason


def test_malformed_timestamp_is_attention_not_now_fallback(gmail_controller):
    page = _candidates(
        gmail_controller,
        _metadata(headers=({"name": "From", "value": "one@example.invalid"},))
        | {"internalDate": "not-a-timestamp"},
    )
    assert page.items[0].attention.reason is CandidateAttentionReason.INVALID_METADATA


def test_page_enumeration_failure_is_not_partial(gmail_controller):
    from fakes.gmail import HttpFailure

    gmail_controller.script("source", "messages.list", _list_args(), HttpFailure(503))
    with pytest.raises(Exception) as error:
        _adapter(gmail_controller).discover_candidates(
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 7, 1, tzinfo=UTC),
        )
    assert getattr(error.value, "code", None).value == "network_unavailable"


def test_action_label_map_is_optional_when_fixed_labels_are_absent(gmail_controller):
    gmail_controller.labels(
        "source", [{"id": "other", "name": "Other", "type": "user"}]
    )
    assert _adapter(gmail_controller).action_label_map() is None


def test_action_label_map_resolves_all_fixed_labels(gmail_controller):
    gmail_controller.labels(
        "source",
        [
            {"id": "add-sender", "name": "AI/AddSender", "type": "user"},
            {"id": "add-domain", "name": "AI/AddDomain", "type": "user"},
            {"id": "blacklist", "name": "AI/BlackList", "type": "user"},
        ],
    )
    labels = _adapter(gmail_controller).action_label_map()
    assert labels is not None
    assert labels.add_sender_label_id.value == "add-sender"
    assert labels.add_domain_label_id.value == "add-domain"
    assert labels.blacklist_label_id.value == "blacklist"


def test_action_label_map_rejects_duplicate_fixed_labels(gmail_controller):
    gmail_controller.labels(
        "source",
        [
            {"id": "add-sender-1", "name": "AI/AddSender", "type": "user"},
            {"id": "add-sender-2", "name": "AI/AddSender", "type": "user"},
            {"id": "add-domain", "name": "AI/AddDomain", "type": "user"},
            {"id": "blacklist", "name": "AI/BlackList", "type": "user"},
        ],
    )
    with pytest.raises(ProviderFailure) as error:
        _adapter(gmail_controller).action_label_map()
    assert error.value.code is ErrorCode.CONSISTENCY_FAILURE


def test_action_label_map_resolves_custom_names_read_only(gmail_controller):
    names = {
        ActionKind.ADD_SENDER: "Facet/AddSender",
        ActionKind.ADD_DOMAIN: "Facet/AddDomain",
        ActionKind.BLACKLIST: "Facet/BlackList",
    }
    gmail_controller.labels(
        "source",
        [
            {"id": "custom-sender", "name": "Facet/AddSender", "type": "user"},
            {"id": "custom-domain", "name": "Facet/AddDomain", "type": "user"},
            {"id": "custom-blacklist", "name": "Facet/BlackList", "type": "user"},
        ],
    )
    labels = _adapter(gmail_controller).action_label_map(names)
    assert labels is not None
    assert labels.add_sender_label_id.value == "custom-sender"
    assert labels.add_domain_label_id.value == "custom-domain"
    assert labels.blacklist_label_id.value == "custom-blacklist"


def test_action_label_map_custom_name_missing_is_typed_no_match(gmail_controller):
    names = {
        ActionKind.ADD_SENDER: "Facet/AddSender",
        ActionKind.ADD_DOMAIN: "Facet/AddDomain",
        ActionKind.BLACKLIST: "Facet/BlackList",
    }
    gmail_controller.labels(
        "source",
        [
            {"id": "custom-sender", "name": "Facet/AddSender", "type": "user"},
            {"id": "custom-domain", "name": "Facet/AddDomain", "type": "user"},
        ],
    )
    assert _adapter(gmail_controller).action_label_map(names) is None


def test_action_label_map_rejects_duplicate_custom_names(gmail_controller):
    names = {
        ActionKind.ADD_SENDER: "Facet/AddSender",
        ActionKind.ADD_DOMAIN: "Facet/AddDomain",
        ActionKind.BLACKLIST: "Facet/BlackList",
    }
    gmail_controller.labels(
        "source",
        [
            {"id": "custom-sender-1", "name": "Facet/AddSender", "type": "user"},
            {"id": "custom-sender-2", "name": "Facet/AddSender", "type": "user"},
            {"id": "custom-domain", "name": "Facet/AddDomain", "type": "user"},
            {"id": "custom-blacklist", "name": "Facet/BlackList", "type": "user"},
        ],
    )
    with pytest.raises(ProviderFailure) as error:
        _adapter(gmail_controller).action_label_map(names)
    assert error.value.code is ErrorCode.CONSISTENCY_FAILURE
