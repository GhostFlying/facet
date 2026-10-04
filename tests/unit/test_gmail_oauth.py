import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from facet.contracts import ErrorCode, Role, Timestamp
from facet.db.codecs import StorageFailure
from facet.gmail.client_config import DesktopClientConfig
from facet.gmail.credential_models import (
    ClientIdText,
    ScopeName,
    ScopeSet,
    SecretText,
)
from facet.gmail.oauth import GoogleOAuthAuthorizer, read_desktop_client


def _client():
    return {
        "installed": {
            "client_id": "synthetic-client",
            "client" + "_secret": "synthetic-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def test_read_desktop_client_requires_owner_only_file(tmp_path):
    os.chmod(tmp_path, 0o700)
    path = tmp_path / "client.json"
    path.write_text(json.dumps(_client()))
    path.chmod(0o600)
    result = read_desktop_client(path)
    assert result.client_id.value == "synthetic-client"
    path.chmod(0o644)
    with pytest.raises(StorageFailure) as caught:
        read_desktop_client(path)
    assert caught.value.code is ErrorCode.SCOPE_REQUIRED


def test_google_oauth_exchange_is_typed_and_uses_fixed_scopes(monkeypatch):
    from google_auth_oauthlib.flow import InstalledAppFlow

    observed = {}

    class Credentials:
        token = "access-token"
        refresh_token = "refresh-token"
        expiry = datetime.now(UTC) + timedelta(hours=1)

    class Flow:
        def run_local_server(self, **kwargs):
            observed["run"] = kwargs
            return Credentials()

    def from_client_config(config, scopes):
        observed["config"] = config
        observed["scopes"] = scopes
        return Flow()

    monkeypatch.setattr(
        InstalledAppFlow, "from_client_config", staticmethod(from_client_config)
    )
    client = DesktopClientConfig(ClientIdText("client"), SecretText("client-secret"))
    secret = GoogleOAuthAuthorizer().authorize(
        Role.SOURCE,
        client,
        ScopeSet(frozenset({ScopeName.GMAIL_READONLY})),
        port=8080,
    )
    assert secret.access_token.value == "access-token"
    assert secret.refresh_token.value == "refresh-token"
    assert observed["scopes"] == ("https://www.googleapis.com/auth/gmail.readonly",)
    assert observed["run"]["open_browser"] is True
    assert observed["run"]["bind_addr"] == "127.0.0.1"
    assert type(secret.expires_at) is Timestamp


def test_google_oauth_rejects_unbounded_loopback_port():
    client = DesktopClientConfig(ClientIdText("client"), SecretText("client-secret"))
    with pytest.raises(StorageFailure) as caught:
        GoogleOAuthAuthorizer().authorize(
            Role.SOURCE,
            client,
            ScopeSet(frozenset({ScopeName.GMAIL_READONLY})),
            port=80,
        )
    assert caught.value.code is ErrorCode.INVALID_INPUT
