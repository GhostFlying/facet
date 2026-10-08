"""Closed reasons and bounded request-level refresh without insert replay."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from facet.cli.bootstrap import _provider_failure_private_data
from facet.contracts import ErrorCode, Revision, Role, Timestamp
from facet.gmail.credential_models import AccessSnapshot, SecretText
from facet.gmail.retry import (
    ProviderFailure,
    ProviderReason,
    ProviderStage,
    classify_http_status,
    provider_failure,
    provider_reason,
)
from facet.gmail.sync_transport import SyncHttp
from facet.runtime.foreground_runtime import _request_token_provider


@pytest.mark.parametrize(
    "reason,code",
    [
        ("domainPolicy", ErrorCode.SCOPE_REQUIRED),
        ("insufficientPermissions", ErrorCode.SCOPE_REQUIRED),
        ("dailyLimitExceeded", ErrorCode.TARGET_RATE_LIMITED),
        ("userRateLimitExceeded", ErrorCode.TARGET_RATE_LIMITED),
        ("storageQuotaExceeded", ErrorCode.TARGET_STORAGE_FULL),
        ("WIRE_ERROR_SENTINEL", ErrorCode.SCOPE_REQUIRED),
    ],
)
def test_reason_survives_normalization_and_rewrap_without_provider_text(reason, code):
    error = RuntimeError("WIRE_ERROR_SENTINEL")
    error.resp = SimpleNamespace(status=403)
    error.content = json.dumps(
        {"error": {"errors": [{"reason": reason}], "message": "WIRE_ERROR_SENTINEL"}}
    ).encode()
    failure = provider_failure(
        error, Role.TARGET, provider_stage=ProviderStage.TARGET_INSERT
    )
    assert failure.code is code
    expected = (
        ProviderReason.UNKNOWN
        if reason == "WIRE_ERROR_SENTINEL"
        else ProviderReason(reason)
    )
    assert failure.reason is expected
    assert failure.with_code(ErrorCode.INVALID_INPUT).reason is expected
    assert _provider_failure_private_data(failure)["reason"] == expected.value
    assert "WIRE_ERROR_SENTINEL" not in str(failure) + repr(failure) + str(
        _provider_failure_private_data(failure)
    )


@pytest.mark.parametrize(
    "payload",
    [b"WIRE_ERROR_SENTINEL", b"[]", b'{"reason":"WIRE_ERROR_SENTINEL"}', b"x" * 65537],
)
def test_unstructured_or_unknown_reason_is_closed(payload):
    assert provider_reason(payload) is ProviderReason.UNKNOWN
    assert (
        classify_http_status(403, Role.SOURCE, body=payload) is ErrorCode.SCOPE_REQUIRED
    )


def test_known_reason_among_unknown_entries():
    assert (
        provider_reason(
            {
                "error": {
                    "errors": [{"reason": "private"}, {"reason": "rateLimitExceeded"}]
                }
            }
        )
        is ProviderReason.RATE_LIMIT
    )


class Response:
    def __init__(self, status):
        self.status_code = status
        self.headers = {}
        self.content = b"{}"
        self.closed = False

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "method,override,expected",
    [("GET", None, 2), ("POST", "GET", 2), ("POST", None, 1)],
)
def test_read_401_replays_once_but_insert_never_replays(method, override, expected):
    calls, refreshes, responses = [], [], []

    def token(*, force):
        refreshes.append(force)
        return "new" if force else "old"

    http = SyncHttp(Role.TARGET, "old", token_provider=token)

    def request(*args, **kwargs):
        calls.append(kwargs["headers"]["Authorization"])
        response = Response(401)
        responses.append(response)
        return response

    http.session.request = request
    try:
        response, _ = http.request(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            method=method,
            headers={"x-http-method-override": override} if override else {},
        )
        assert response.status == 401
        assert len(calls) == expected and all(response.closed for response in responses)
        assert refreshes == ([False, True] if expected == 2 else [False])
    finally:
        http.close()


def test_role_snapshot_refreshes_at_threshold_without_reload_per_request(monkeypatch):
    now = datetime.now(UTC)
    snapshot = AccessSnapshot(
        Role.TARGET,
        Revision(1),
        Revision(1),
        Revision(1),
        SecretText("old"),
        Timestamp(now + timedelta(seconds=301)),
    )
    calls = []

    class Manager:
        def __init__(self, *args):
            pass

        def ensure_current(self, role, exchange, profile):
            calls.append(("threshold", role))
            return replace(
                snapshot,
                access_token=SecretText("new"),
                expires_at=Timestamp(now + timedelta(hours=1)),
            )

        def refresh(self, role, exchange, *, profile):
            calls.append(("reactive", role))
            return replace(
                snapshot,
                access_token=SecretText("forced"),
                expires_at=Timestamp(now + timedelta(hours=1)),
            )

    import facet.gmail.credentials as credentials
    import facet.runtime.foreground_runtime as runtime

    monkeypatch.setattr(runtime, "CredentialManager", Manager)
    monkeypatch.setattr(credentials, "_owner_now", lambda: Timestamp(now))
    token = _request_token_provider(
        SimpleNamespace(state_dir="synthetic"), object(), object(), snapshot
    )
    assert token() == "old" and token() == "old" and not calls
    now += timedelta(seconds=2)
    assert token() == "new" and token() == "new"
    assert calls == [("threshold", Role.TARGET)]
    assert token(force=True) == "forced"
    assert calls[-1] == ("reactive", Role.TARGET)


@pytest.mark.parametrize(
    "code,reason",
    [
        (ErrorCode.NETWORK_UNAVAILABLE, ProviderReason.MISSING),
        (ErrorCode.TARGET_AUTH_REQUIRED, ProviderReason.INVALID_GRANT),
    ],
)
def test_pre_http_refresh_failure_is_proven_not_dispatched(code, reason):
    def token(*, force):
        raise ProviderFailure(
            code, Role.TARGET, provider_stage=ProviderStage.TOKEN_REFRESH, reason=reason
        )

    http = SyncHttp(Role.TARGET, "old", token_provider=token)
    calls = []
    http.session.request = lambda *args, **kwargs: calls.append(args)
    try:
        with pytest.raises(ProviderFailure) as caught:
            http.request(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages", method="POST"
            )
        assert caught.value.request_dispatched is False
        assert caught.value.reason is reason and not calls
    finally:
        http.close()
