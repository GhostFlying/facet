"""Actual Google request construction with a synthetic HTTP boundary only."""

import base64
import json
from urllib.parse import parse_qs, urlparse

import httplib2
import pytest
from googleapiclient.discovery import build

from facet.contracts import ErrorCode, ProviderId, Role
from facet.gmail.retry import ProviderFailure
from facet.gmail.target import TargetAdapter


class _Http:
    def __init__(self, status=200):
        self.requests = []
        self.status = status

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        self.requests.append((uri, method, body, kwargs))
        return (
            httplib2.Response(
                {"status": str(self.status), "content-type": "application/json"}
            ),
            b'{"id":"target-message","threadId":"target-thread"}'
            if self.status == 200
            else b'{"error":{"message":"SYNTHETIC_PROVIDER_SENTINEL"}}',
        )


@pytest.mark.parametrize("date_header", [True, False])
@pytest.mark.parametrize("thread_id", [None, ProviderId("target-thread")])
def test_insert_uses_supported_actual_discovery_parameters(
    monkeypatch, date_header, thread_id
):
    def no_network(*args, **kwargs):
        raise AssertionError("unexpected_network_call")

    monkeypatch.setattr("socket.socket.connect", no_network)
    transport = _Http()
    service = build(
        "gmail", "v1", http=transport, cache_discovery=False, static_discovery=True
    )
    raw = b"From: sender@example.invalid\r\nSubject: Synthetic\r\n\r\nbody\r\n"
    result = TargetAdapter(service).insert(
        raw, thread_id=thread_id, date_header=date_header
    )
    assert result.message_id == ProviderId("target-message")
    assert result.thread_id == ProviderId("target-thread")
    assert len(transport.requests) == 1
    uri, method, body, kwargs = transport.requests[0]
    assert method == "POST"
    assert urlparse(uri).path == "/gmail/v1/users/me/messages"
    query = parse_qs(urlparse(uri).query)
    assert query["internalDateSource"] == [
        "dateHeader" if date_header else "receivedTime"
    ]
    assert "neverMarkSpam" not in query
    assert "deleted" not in query
    payload = json.loads(body)
    assert (
        base64.urlsafe_b64decode(payload["raw"] + "=" * (-len(payload["raw"]) % 4))
        == raw
    )
    assert payload == {
        "raw": base64.urlsafe_b64encode(raw).decode().rstrip("="),
        **({"threadId": thread_id.value} if thread_id else {}),
    }
    assert kwargs == {}


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, ErrorCode.TARGET_AUTH_REQUIRED),
        (429, ErrorCode.TARGET_RATE_LIMITED),
        (500, ErrorCode.NETWORK_UNAVAILABLE),
    ],
)
def test_actual_client_insert_failure_is_not_retried(status, code):
    transport = _Http(status)
    service = build(
        "gmail", "v1", http=transport, cache_discovery=False, static_discovery=True
    )
    with pytest.raises(ProviderFailure) as caught:
        TargetAdapter(service).insert(b"Subject: Synthetic\r\n\r\nbody\r\n")
    assert len(transport.requests) == 1
    assert caught.value.code is code
    assert caught.value.role is Role.TARGET
    assert caught.value.status == status
    assert "SYNTHETIC_PROVIDER_SENTINEL" not in str(caught.value)
