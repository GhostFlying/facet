"""Offline tests for the manager-owned Google refresh boundary."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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
        self.granted_scopes = None

    def refresh(self, request):
        del request
        if self.mode not in {"success", "omitted"}:
            from google.auth.exceptions import RefreshError

            error = RefreshError("synthetic provider payload")
            error.response = SimpleNamespace(status=self.mode)
            if self.mode == "invalid_grant":
                error.content = b'{"error":"invalid_grant"}'
            raise error
        self.token = "new-access"
        self.expiry = datetime.now(UTC) + timedelta(hours=1)
        if self.mode != "omitted":
            self.granted_scopes = ("https://www.googleapis.com/auth/gmail.readonly",)
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


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        ("invalid_grant", ErrorCode.SOURCE_AUTH_REQUIRED),
        (401, ErrorCode.SOURCE_AUTH_REQUIRED),
        (403, ErrorCode.SOURCE_AUTH_REQUIRED),
        (429, ErrorCode.SOURCE_RATE_LIMITED),
        (500, ErrorCode.NETWORK_UNAVAILABLE),
    ),
)
def test_refresh_maps_provider_failures_without_raw_payload(mode, expected):
    _Credentials.mode = mode
    with pytest.raises(StorageFailure) as caught:
        refresh_google(Role.SOURCE, _secret(), SCOPES)
    assert caught.value.code is expected
    assert "synthetic provider payload" not in repr(caught.value)


def test_refresh_rejects_malformed_provider_result(monkeypatch):
    _Credentials.mode = "success"

    def malformed(self, request):
        del self, request

    monkeypatch.setattr(_Credentials, "refresh", malformed)
    with pytest.raises(StorageFailure) as caught:
        refresh_google(Role.TARGET, _secret(), SCOPES)
    assert caught.value.code is ErrorCode.INVALID_INPUT
