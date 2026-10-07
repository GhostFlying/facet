"""Offline tests for the manager-owned Google refresh boundary."""

from datetime import UTC, datetime, timedelta

import pytest

from facet.contracts import ErrorCode, Role, Timestamp
from facet.db.codecs import StorageFailure
from facet.gmail.credential_models import (
    ClientIdText,
    ProviderSecret,
    ScopeName,
    ScopeSet,
    SecretText,
)
from facet.gmail.refresh_exchange import refresh_google
from facet.gmail.retry import ProviderFailure, ProviderStage

SCOPES = ScopeSet(frozenset({ScopeName.GMAIL_READONLY}))


def _secret():
    return ProviderSecret(
        ClientIdText("synthetic-client"),
        SecretText("synthetic-client-secret"),
        SecretText("old-access"),
        SecretText("synthetic-refresh"),
        Timestamp(datetime(2040, 1, 1, tzinfo=UTC)),
    )


class _Credentials:
    mode = "success"

    def __init__(self, **kwargs):
        self.token = None
        self.refresh_token = kwargs["refresh_token"]
        self.expiry = None
        self.scopes = kwargs["scopes"]
        self.granted_scopes = None

    def refresh(self, request):
        if self.mode == "timeout":
            request("https://synthetic.invalid/token", timeout=999)
            return
        if self.mode == "transport":
            from google.auth.exceptions import TransportError

            raise TransportError("synthetic transport failure")
        if self.mode not in {"success", "omitted"}:
            from google.auth.exceptions import RefreshError

            if self.mode == "invalid_grant":
                response_data = {"error": "invalid_grant"}
            elif self.mode == "retryable":
                response_data = {"error": "temporarily_unavailable"}
            elif self.mode == 429:
                response_data = {"error": "rate_limit_exceeded", "code": 429}
            elif isinstance(self.mode, int) and self.mode >= 500:
                response_data = {"error": "backendError", "code": self.mode}
            else:
                response_data = {
                    "error": self.mode
                    if isinstance(self.mode, str)
                    else "unauthorized_client",
                    "code": self.mode,
                }
            error = RefreshError(
                "synthetic provider payload",
                response_data,
                retryable=self.mode == "retryable",
            )
            raise error
        self.token = "new-access"
        self.expiry = datetime.now(UTC) + timedelta(hours=1)
        if self.mode != "omitted":
            self.granted_scopes = self.scopes
        else:
            self.refresh_token = None


@pytest.fixture(autouse=True)
def fake_google_credentials(monkeypatch):
    from google.oauth2 import credentials

    monkeypatch.setattr(credentials, "Credentials", _Credentials)


def test_refresh_returns_new_secret_and_explicit_scopes(monkeypatch):
    _Credentials.mode = "success"
    result = refresh_google(Role.SOURCE, _secret(), SCOPES)
    assert result.secret.access_token.value == "new-access"
    assert result.secret.refresh_token.value == "synthetic-refresh"
    assert result.scopes == SCOPES


def test_refresh_inherits_omitted_refresh_token_and_scopes():
    _Credentials.mode = "omitted"
    result = refresh_google(Role.SOURCE, _secret(), SCOPES)
    assert result.secret.refresh_token.value == "synthetic-refresh"
    assert result.scopes is None


def test_target_refresh_preserves_target_policy_scope_evidence():
    _Credentials.mode = "success"
    target_scopes = ScopeSet(
        frozenset({ScopeName.GMAIL_READONLY, ScopeName.GMAIL_INSERT})
    )
    result = refresh_google(Role.TARGET, _secret(), target_scopes)
    assert result.scopes == target_scopes


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        ("invalid_grant", ErrorCode.SOURCE_AUTH_REQUIRED),
        ("invalid_scope", ErrorCode.SCOPE_REQUIRED),
        (401, ErrorCode.SOURCE_AUTH_REQUIRED),
        (403, ErrorCode.SOURCE_AUTH_REQUIRED),
        (429, ErrorCode.SOURCE_RATE_LIMITED),
        (500, ErrorCode.NETWORK_UNAVAILABLE),
        ("retryable", ErrorCode.NETWORK_UNAVAILABLE),
        ("transport", ErrorCode.NETWORK_UNAVAILABLE),
    ),
)
def test_refresh_maps_provider_failures_without_raw_payload(mode, expected):
    _Credentials.mode = mode
    with pytest.raises(ProviderFailure) as caught:
        refresh_google(Role.SOURCE, _secret(), SCOPES)
    assert caught.value.code is expected
    assert caught.value.provider_stage is ProviderStage.TOKEN_REFRESH
    assert caught.value.timeout_seconds == 30
    assert caught.value.attempt == 1
    assert caught.value.observed_at is not None
    assert "synthetic provider payload" not in repr(caught.value)


def test_refresh_forces_fixed_timeout_at_request_call(monkeypatch):
    calls = []

    class _Request:
        def __call__(self, _url, **kwargs):
            calls.append(kwargs)
            raise TimeoutError("synthetic token endpoint timeout")

    import google.auth.transport.requests

    monkeypatch.setattr(google.auth.transport.requests, "Request", _Request)
    _Credentials.mode = "timeout"
    with pytest.raises(ProviderFailure) as caught:
        refresh_google(Role.SOURCE, _secret(), SCOPES)
    assert calls == [{"timeout": 30}]
    assert caught.value.code is ErrorCode.NETWORK_UNAVAILABLE
    assert caught.value.provider_stage is ProviderStage.TOKEN_REFRESH
    assert caught.value.timeout_seconds == 30
    assert "synthetic token endpoint timeout" not in repr(caught.value)


def test_refresh_rejects_malformed_provider_result(monkeypatch):
    _Credentials.mode = "success"

    def malformed(self, request):
        del self, request

    monkeypatch.setattr(_Credentials, "refresh", malformed)
    with pytest.raises(StorageFailure) as caught:
        refresh_google(Role.TARGET, _secret(), SCOPES)
    assert caught.value.code is ErrorCode.INVALID_INPUT
