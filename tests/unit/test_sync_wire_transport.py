"""Production Google SDK and Requests dispatch through actual TCP faults."""

from datetime import UTC, datetime

import pytest
from fakes.sync_wire import Mailbox, install_route

from facet.contracts import ErrorCode, Role
from facet.db.codecs import StorageFailure
from facet.gmail.retry import ProviderFailure, ProviderStage
from facet.gmail.service_factory import GoogleGmailServiceFactory
from facet.gmail.source import DiscoveryQuery, SourceAdapter
from facet.gmail.sync_transport import SyncHttp
from facet.gmail.target import TargetAdapter


@pytest.fixture
def wire(monkeypatch):
    import requests

    original = requests.Session.request
    with Mailbox() as mailbox:
        monkeypatch.setenv("FACET_TEST_WIRE_ORIGIN", mailbox.origin)
        install_route()
        try:
            yield mailbox
        finally:
            requests.Session.request = original


@pytest.mark.parametrize("fault", ["lost_response", 401, 429, 503, 307, 308])
def test_real_sdk_insert_has_one_wire_attempt_and_closed_error(wire, fault, caplog):
    wire.fault = fault
    service = GoogleGmailServiceFactory._build(Role.TARGET, "synthetic-target-access")
    raw = b"From: synthetic@example.com\r\n\r\nWIRE_BODY_SENTINEL"
    try:
        with pytest.raises(ProviderFailure) as caught:
            TargetAdapter(service).insert(raw)
        expected = {
            "lost_response": ErrorCode.NETWORK_UNAVAILABLE,
            401: ErrorCode.TARGET_AUTH_REQUIRED,
            429: ErrorCode.TARGET_RATE_LIMITED,
            503: ErrorCode.NETWORK_UNAVAILABLE,
            307: ErrorCode.INVALID_INPUT,
            308: ErrorCode.INVALID_INPUT,
        }
        assert caught.value.code is expected[fault]
        assert caught.value.provider_stage is ProviderStage.TARGET_INSERT
        assert caught.value.attempt == 1
        if fault == 429:
            assert caught.value.retry_after_seconds == 123
        assert wire.calls == [("POST", "/gmail/v1/users/me/messages")]
        assert wire.inserted_raw == [raw]
        assert "WIRE_ERROR_SENTINEL" not in repr(caught.value)
        assert "WIRE_BODY_SENTINEL" not in caplog.text
        assert "synthetic-target-access" not in caplog.text
    finally:
        service.close()


def test_actual_sdk_long_discovery_query_uses_read_only_post_override(wire):
    service = GoogleGmailServiceFactory._build(Role.SOURCE, "synthetic-source-access")
    try:
        source = SourceAdapter(service)
        query = DiscoveryQuery(
            tuple(f'from:"person{n:02}@example.com"' for n in range(60))
        )
        page = source.discover(
            window_start=datetime(2026, 4, 7, tzinfo=UTC),
            window_end=datetime(2026, 10, 7, tzinfo=UTC),
            query=query,
        )
        assert page.items == ()
        assert wire.calls == [("POST", "/gmail/v1/users/me/messages")]
        assert wire.inserted_raw == []
    finally:
        service.close()


@pytest.mark.parametrize(
    "role,uri,method,headers",
    [
        (
            Role.SOURCE,
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            "POST",
            {},
        ),
        (
            Role.TARGET,
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            "POST",
            {},
        ),
        (
            Role.TARGET,
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/mail",
            "DELETE",
            {},
        ),
        (
            Role.SOURCE,
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            "POST",
            {"x-http-method-override": "DELETE"},
        ),
        (
            Role.SOURCE,
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            "POST",
            {"x-http-method-override": "GET"},
        ),
        (
            Role.TARGET,
            "https://other.example.com/gmail/v1/users/me/messages",
            "GET",
            {},
        ),
    ],
)
def test_transport_refuses_out_of_scope_requests_without_dispatch(
    wire, role, uri, method, headers
):
    transport = SyncHttp(role, "access")
    try:
        with pytest.raises(StorageFailure):
            transport.request(uri, method=method, headers=headers)
        assert wire.calls == []
    finally:
        transport.close()
