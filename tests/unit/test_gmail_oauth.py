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
from facet.gmail.oauth import (
    GoogleOAuthAuthorizer,
    _valid_callback,
    read_desktop_client,
)


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


def test_read_desktop_client_rejects_symlinked_ancestor(tmp_path):
    os.chmod(tmp_path, 0o700)
    real = tmp_path / "real"
    real.mkdir()
    real.chmod(0o700)
    client = real / "client.json"
    client.write_text(json.dumps(_client()))
    client.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(StorageFailure) as caught:
        read_desktop_client(link / "client.json")
    assert caught.value.code is ErrorCode.SCOPE_REQUIRED


def test_read_desktop_client_uses_final_parent_for_host_like_ancestor(tmp_path):
    host_like = tmp_path / "data00" / "operator" / "facet"
    host_like.mkdir(parents=True)
    host_like.chmod(0o700)
    path = host_like / "client.json"
    path.write_text(json.dumps(_client()))
    path.chmod(0o600)
    assert read_desktop_client(path).client_id.value == "synthetic-client"


def test_container_secret_contract_allows_readable_non_private_parent(
    monkeypatch, tmp_path
):
    import facet.gmail.oauth as oauth_module

    parent = tmp_path / "secrets"
    parent.mkdir()
    parent.chmod(0o755)
    path = parent / "google-client.json"
    path.write_text(json.dumps(_client()))
    path.chmod(0o440)
    monkeypatch.setattr(oauth_module, "_CONTAINER_SECRET_PARENT", parent)
    assert read_desktop_client(path).client_id.value == "synthetic-client"
    path.chmod(0o460)
    with pytest.raises(StorageFailure) as caught:
        read_desktop_client(path)
    assert caught.value.code is ErrorCode.SCOPE_REQUIRED


def test_google_oauth_exchange_is_typed_and_uses_fixed_scopes(monkeypatch):
    from google_auth_oauthlib.flow import InstalledAppFlow

    from facet.gmail import oauth as oauth_module

    observed = {}

    class Credentials:
        token = "access-token"
        refresh_token = "refresh-token"
        expiry = datetime.now(UTC) + timedelta(hours=1)
        scopes = ("https://www.googleapis.com/auth/gmail.readonly",)

    class Flow:
        credentials = Credentials()

        def authorization_url(self, **kwargs):
            observed["authorization"] = kwargs
            return "https://accounts.example/authorize", "state-token"

        def fetch_token(self, **kwargs):
            observed["fetch"] = kwargs

    class Server:
        server_port = 8080
        timeout = None

        def handle_request(self):
            observed["server_timeout"] = self.timeout
            app_holder[
                "app"
            ].last_request_uri = (
                "http://localhost:8080/?code=code-token&state=state-token"
            )

        def server_close(self):
            observed["closed"] = True

    app_holder = {}

    def make_server(_host, _port, app, **_kwargs):
        app_holder["app"] = app
        return Server()

    def from_client_config(config, scopes):
        observed["config"] = config
        observed["scopes"] = scopes
        return Flow()

    monkeypatch.setattr(
        InstalledAppFlow, "from_client_config", staticmethod(from_client_config)
    )
    monkeypatch.setattr(oauth_module.wsgiref.simple_server, "make_server", make_server)
    client = DesktopClientConfig(ClientIdText("client"), SecretText("client-secret"))
    secret = GoogleOAuthAuthorizer().authorize(
        Role.SOURCE,
        client,
        ScopeSet(frozenset({ScopeName.GMAIL_READONLY})),
        port=8080,
    )
    assert secret.secret.access_token.value == "access-token"
    assert secret.secret.refresh_token.value == "refresh-token"
    assert secret.scopes.value == frozenset({ScopeName.GMAIL_READONLY})
    assert observed["scopes"] == ("https://www.googleapis.com/auth/gmail.readonly",)
    assert observed["authorization"]["prompt"] == "consent"
    assert observed["fetch"]["authorization_response"].startswith("https://")
    assert observed["server_timeout"] == 300
    assert observed["closed"] is True
    assert type(secret.secret.expires_at) is Timestamp


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


def test_strict_setup_requires_actual_granted_scope_evidence(monkeypatch):
    from google_auth_oauthlib.flow import InstalledAppFlow

    from facet.gmail import oauth as oauth_module

    observed = {}

    class Credentials:
        token = "access-token"
        refresh_token = "refresh-token"
        expiry = datetime.now(UTC) + timedelta(hours=1)
        scopes = ("https://www.googleapis.com/auth/gmail.readonly",)
        granted_scopes = None

    class Flow:
        credentials = Credentials()

        def authorization_url(self, **kwargs):
            observed["authorization"] = kwargs
            return "https://accounts.example/authorize", "state-token"

        def fetch_token(self, **kwargs):
            pass

    class Server:
        server_port = 8080

        def handle_request(self):
            app_holder[
                "app"
            ].last_request_uri = (
                "http://localhost:8080/?code=code-token&state=state-token"
            )

        def server_close(self):
            pass

    app_holder = {}

    def make_server(_host, _port, app, **_kwargs):
        app_holder["app"] = app
        return Server()

    monkeypatch.setattr(
        InstalledAppFlow, "from_client_config", staticmethod(lambda *_args: Flow())
    )
    monkeypatch.setattr(oauth_module.wsgiref.simple_server, "make_server", make_server)
    client = DesktopClientConfig(ClientIdText("client"), SecretText("client-secret"))
    with pytest.raises(StorageFailure) as caught:
        GoogleOAuthAuthorizer().authorize(
            Role.SOURCE,
            client,
            ScopeSet(frozenset({ScopeName.GMAIL_READONLY})),
            port=8080,
            strict_setup=True,
        )
    assert caught.value.code is ErrorCode.SCOPE_REQUIRED
    assert observed["authorization"]["include_granted_scopes"] == "false"


def test_strict_setup_accepts_space_delimited_granted_scopes(monkeypatch):
    from google_auth_oauthlib.flow import InstalledAppFlow

    from facet.gmail import oauth as oauth_module

    class Credentials:
        token = "access-token"
        refresh_token = "refresh-token"
        expiry = datetime.now(UTC) + timedelta(hours=1)
        granted_scopes = "https://www.googleapis.com/auth/gmail.readonly"

    class Flow:
        credentials = Credentials()

        def authorization_url(self, **_kwargs):
            return "https://accounts.example/authorize", "state-token"

        def fetch_token(self, **_kwargs):
            pass

    class Server:
        server_port = 8080

        def handle_request(self):
            app_holder[
                "app"
            ].last_request_uri = (
                "http://localhost:8080/?code=code-token&state=state-token"
            )

        def server_close(self):
            pass

    app_holder = {}

    def make_server(_host, _port, app, **_kwargs):
        app_holder["app"] = app
        return Server()

    monkeypatch.setattr(
        InstalledAppFlow, "from_client_config", staticmethod(lambda *_args: Flow())
    )
    monkeypatch.setattr(oauth_module.wsgiref.simple_server, "make_server", make_server)
    client = DesktopClientConfig(ClientIdText("client"), SecretText("client-secret"))
    result = GoogleOAuthAuthorizer().authorize(
        Role.SOURCE,
        client,
        ScopeSet(frozenset({ScopeName.GMAIL_READONLY})),
        port=8080,
        strict_setup=True,
    )
    assert result.scopes.value == frozenset({ScopeName.GMAIL_READONLY})


def test_callback_validation_requires_exact_loopback_state_and_result():
    assert _valid_callback(
        "http://localhost:8080/?code=code&state=state", "state", 8080
    )
    assert not _valid_callback(
        "http://127.0.0.1:8080/?code=code&state=state", "state", 8080
    )
    assert not _valid_callback(
        "http://localhost:8080/?code=code&state=other", "state", 8080
    )
    assert not _valid_callback(
        "http://localhost:8080/?code=one&code=two&state=state", "state", 8080
    )
