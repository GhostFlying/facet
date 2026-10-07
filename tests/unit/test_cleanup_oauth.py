import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from google_auth_oauthlib.flow import InstalledAppFlow

from facet.contracts import ErrorCode
from facet.db.codecs import StorageFailure
from facet.gmail import cleanup_oauth
from facet.gmail.client_config import DesktopClientConfig
from facet.gmail.credential_models import ClientIdText, SecretText


@pytest.fixture
def flow(monkeypatch):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    terminal = Terminal()
    seen = {"terminal": terminal}
    credentials = SimpleNamespace(
        token="CLEANUP_ACCESS_SENTINEL",
        refresh_token="CLEANUP_REFRESH_SENTINEL",
        expiry=datetime.now(UTC) + timedelta(hours=1),
        granted_scopes=[cleanup_oauth.FULL_MAIL_SCOPE],
    )

    class Flow:
        def __init__(self):
            self.credentials = credentials

        def authorization_url(self, **kwargs):
            seen["authorization"] = kwargs
            return "https://accounts.google.com/o/oauth2/v2/auth?synthetic=1", "state"

        def fetch_token(self, **kwargs):
            seen["fetch"] = kwargs

    class Server:
        server_port = 18082

        def handle_request(self):
            seen["app"].last_request_uri = seen.get(
                "callback", "http://localhost:18082/?state=state&code=synthetic"
            )

        def server_close(self):
            seen["closed"] = True

    def make_server(host, port, application, **kwargs):
        seen["host"] = host
        seen["app"] = application
        return Server()

    def from_client_config(config, scopes):
        seen["scopes"] = scopes
        return Flow()

    monkeypatch.setattr(InstalledAppFlow, "from_client_config", from_client_config)
    monkeypatch.setattr(cleanup_oauth.wsgiref.simple_server, "make_server", make_server)
    monkeypatch.setattr(
        cleanup_oauth,
        "sys",
        SimpleNamespace(
            stdin=SimpleNamespace(isatty=lambda: True),
            stderr=terminal,
        ),
    )
    return credentials, seen


def authorize():
    return cleanup_oauth.authorize_cleanup(
        DesktopClientConfig(ClientIdText("client"), SecretText("client-secret")),
        port=18082,
        callback_timeout_seconds=900,
    )


def test_temporary_exact_scope_online_without_credential_persistence(flow, tmp_path):
    credentials, seen = flow
    access = authorize()
    assert access.token.value == credentials.token
    assert seen["scopes"] == [cleanup_oauth.FULL_MAIL_SCOPE]
    assert seen["authorization"] == {
        "access_type": "online",
        "prompt": "consent",
        "include_granted_scopes": "false",
    }
    assert seen["host"] == "127.0.0.1"
    assert seen["fetch"]["timeout"] == 30
    assert seen["closed"]
    output = seen["terminal"].getvalue()
    assert "accounts.google.com" in output
    assert "CLEANUP_ACCESS_SENTINEL" not in output + repr(access)
    assert "CLEANUP_REFRESH_SENTINEL" not in output + repr(access)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "granted",
    [
        None,
        [],
        ["https://www.googleapis.com/auth/gmail.insert"],
        [cleanup_oauth.FULL_MAIL_SCOPE, "extra"],
    ],
)
def test_actual_scope_evidence_required(flow, granted):
    credentials, _ = flow
    credentials.granted_scopes = granted
    credentials.scopes = [cleanup_oauth.FULL_MAIL_SCOPE]
    with pytest.raises(StorageFailure) as caught:
        authorize()
    assert caught.value.code is ErrorCode.SCOPE_REQUIRED


@pytest.mark.parametrize(
    "callback",
    [
        "http://localhost:18082/?state=other&code=x",
        "http://localhost:18082/?state=state&code=x&code=y",
    ],
)
def test_wrong_callback_no_token_exchange(flow, callback):
    _, seen = flow
    seen["callback"] = callback
    with pytest.raises(StorageFailure):
        authorize()
    assert "fetch" not in seen
    assert seen["closed"]


def test_expired_access_denied(flow):
    credentials, _ = flow
    credentials.expiry = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(StorageFailure):
        authorize()


def test_non_tty_no_oauth(flow, monkeypatch):
    _, seen = flow
    monkeypatch.setattr(cleanup_oauth.sys.stdin, "isatty", lambda: False)
    with pytest.raises(StorageFailure) as caught:
        authorize()
    assert caught.value.code is ErrorCode.CONFIRMATION_REQUIRED
    assert set(seen) == {"terminal"}
    assert seen["terminal"].getvalue() == ""
