from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from facet.cli import bootstrap
from facet.config import ConfigError
from facet.contracts import ErrorCode, Role, Timestamp
from facet.db.codecs import StorageFailure
from facet.gmail.credential_models import (
    AccountAddress,
    ClientIdText,
    ProviderSecret,
    SecretText,
)
from facet.gmail.oauth import OAuthResult

REQUEST = "rq1_123e4567e89b42d3a456426614174000_123e4567e89b42d3a456426614174001"


def _client_document():
    return json.dumps(
        {
            "installed": {
                "client_id": "id",
                "client" + "_secret": "secret",
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
    )


class _TTY(io.StringIO):
    def isatty(self):
        return True


def _secret(role):
    return ProviderSecret(
        ClientIdText("client"),
        SecretText("client-secret"),
        SecretText(f"access-{role.value}"),
        SecretText(f"refresh-{role.value}"),
        Timestamp(datetime.now(UTC) + timedelta(hours=1)),
    )


def _install_fake_transport(monkeypatch):
    class Authorizer:
        def authorize(
            self,
            role,
            _client,
            scopes,
            *,
            port,
            bind_address="127.0.0.1",
            strict_setup=False,
            callback_timeout_seconds=300,
        ):
            assert port == 8080
            assert bind_address == "127.0.0.1"
            assert strict_setup is True
            assert callback_timeout_seconds == 900
            return OAuthResult(_secret(role), scopes)

    class Factory:
        def profile_account(self, role, _secret_value):
            return AccountAddress(
                "source@synthetic.example"
                if role is Role.SOURCE
                else "target@synthetic.example"
            )

    monkeypatch.setattr("facet.gmail.oauth.GoogleOAuthAuthorizer", Authorizer)
    monkeypatch.setattr(
        "facet.gmail.service_factory.GoogleGmailServiceFactory", Factory
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    ((None, 900), ("60", 60), ("1800", 1800), ("00060", 60)),
)
def test_setup_callback_timeout_accepts_unset_and_bounded_ascii_digits(
    monkeypatch, raw, expected
):
    if raw is None:
        monkeypatch.delenv("FACET_OAUTH_CALLBACK_TIMEOUT_SECONDS", raising=False)
    else:
        monkeypatch.setenv("FACET_OAUTH_CALLBACK_TIMEOUT_SECONDS", raw)
    assert bootstrap._setup_oauth_callback_timeout() == expected


@pytest.mark.parametrize(
    "raw",
    ("", " 60", "60 ", "+60", "1_800", "59", "1801", "-1", "0"),
)
def test_setup_callback_timeout_rejects_invalid_values(monkeypatch, raw):
    monkeypatch.setenv("FACET_OAUTH_CALLBACK_TIMEOUT_SECONDS", raw)
    with pytest.raises(ConfigError) as caught:
        bootstrap._setup_oauth_callback_timeout()
    assert caught.value.code is ErrorCode.INVALID_INPUT


def test_setup_callback_timeout_invalid_value_stops_before_authorizer_or_state(
    monkeypatch, tmp_path
):
    calls = []

    class Authorizer:
        def authorize(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("invalid timeout must stop before OAuth")

    monkeypatch.setattr("facet.gmail.oauth.GoogleOAuthAuthorizer", Authorizer)
    monkeypatch.setenv("FACET_OAUTH_CALLBACK_TIMEOUT_SECONDS", "")
    monkeypatch.setattr(bootstrap.sys, "stdin", _TTY("confirm\n"))
    monkeypatch.setattr(bootstrap.sys, "stdout", _TTY())
    monkeypatch.setattr(bootstrap.sys, "stderr", _TTY())
    client = tmp_path / "client.json"
    client.write_text(_client_document())
    client.chmod(0o600)
    tmp_path.chmod(0o700)
    options = bootstrap.build_parser().parse_args(
        [
            "setup",
            "--state-dir",
            str(tmp_path / "state"),
            "--oauth-client",
            str(client),
            "--request-id",
            REQUEST,
        ]
    )
    with pytest.raises(ConfigError) as caught:
        bootstrap._setup_command(options)
    assert caught.value.code is ErrorCode.INVALID_INPUT
    assert calls == []
    assert not (tmp_path / "state").exists()


def test_setup_binds_discovered_roles_through_production_owner(monkeypatch):
    import os

    anchor = Path(f"/run/user/{os.geteuid()}")
    if not anchor.is_dir() or anchor.stat().st_mode & 0o77:
        pytest.skip("no trusted runtime anchor")
    with TemporaryDirectory(prefix="facet-setup-", dir=anchor) as directory:
        _test_setup_binds(monkeypatch, Path(directory))


def _test_setup_binds(monkeypatch, tmp_path):
    _install_fake_transport(monkeypatch)
    stdin = _TTY("confirm\n")
    stdout = _TTY()
    stderr = _TTY()
    monkeypatch.setattr(bootstrap.sys, "stdin", stdin)
    monkeypatch.setattr(bootstrap.sys, "stdout", stdout)
    monkeypatch.setattr(bootstrap.sys, "stderr", stderr)
    options = bootstrap.build_parser().parse_args(
        [
            "setup",
            "--state-dir",
            str(tmp_path / "state"),
            "--oauth-client",
            str(tmp_path / "client.json"),
            "--request-id",
            REQUEST,
        ]
    )
    client = tmp_path / "client.json"
    client.write_text(_client_document())
    client.chmod(0o600)
    (tmp_path).chmod(0o700)
    data, warnings = bootstrap._setup_command(options)
    assert data == {"state_initialized": True, "binding_state": "verified"}
    assert warnings == ()
    assert (tmp_path / "state" / "config.yaml").is_file()
    assert "source@synthetic" in stderr.getvalue()


def test_setup_decline_does_not_create_state(monkeypatch, tmp_path):
    _install_fake_transport(monkeypatch)
    monkeypatch.setattr(bootstrap.sys, "stdin", _TTY("no\n"))
    monkeypatch.setattr(bootstrap.sys, "stdout", _TTY())
    monkeypatch.setattr(bootstrap.sys, "stderr", _TTY())
    client = tmp_path / "client.json"
    client.write_text(_client_document())
    client.chmod(0o600)
    (tmp_path).chmod(0o700)
    options = bootstrap.build_parser().parse_args(
        [
            "setup",
            "--state-dir",
            str(tmp_path / "state"),
            "--oauth-client",
            str(client),
            "--request-id",
            REQUEST,
        ]
    )
    with pytest.raises(ConfigError) as caught:
        bootstrap._setup_command(options)
    assert caught.value.code is ErrorCode.CONFIRMATION_REQUIRED
    assert not (tmp_path / "state").exists()


def test_setup_client_preflight_runs_before_authorizer(monkeypatch, tmp_path):
    calls = []

    class Authorizer:
        def authorize(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("OAuth must not start after client preflight failure")

    monkeypatch.setattr("facet.gmail.oauth.GoogleOAuthAuthorizer", Authorizer)
    monkeypatch.setattr(bootstrap.sys, "stdin", _TTY("confirm\n"))
    monkeypatch.setattr(bootstrap.sys, "stdout", _TTY())
    monkeypatch.setattr(bootstrap.sys, "stderr", _TTY())
    client = tmp_path / "client.json"
    client.write_text("not-json")
    client.chmod(0o600)
    tmp_path.chmod(0o700)
    options = bootstrap.build_parser().parse_args(
        [
            "setup",
            "--state-dir",
            str(tmp_path / "state"),
            "--oauth-client",
            str(client),
            "--request-id",
            REQUEST,
        ]
    )
    with pytest.raises(StorageFailure) as caught:
        bootstrap._setup_command(options)
    assert caught.value.code is ErrorCode.INVALID_INPUT
    assert calls == []
    assert not (tmp_path / "state").exists()


def test_setup_rechecks_root_before_each_authorizer_call(monkeypatch, tmp_path):
    from facet.gmail import oauth as oauth_module

    calls = []

    class Authorizer:
        def authorize(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("OAuth must not start for a newly-owned root")

    monkeypatch.setattr("facet.gmail.oauth.GoogleOAuthAuthorizer", Authorizer)
    original_reader = oauth_module.read_desktop_client
    client = tmp_path / "client.json"
    client.write_text(_client_document())
    client.chmod(0o600)
    tmp_path.chmod(0o700)
    state = tmp_path / "state"

    def reader(path):
        state.mkdir()
        state.chmod(0o700)
        return original_reader(path)

    monkeypatch.setattr("facet.gmail.oauth.read_desktop_client", reader)
    monkeypatch.setattr(bootstrap.sys, "stdin", _TTY("confirm\n"))
    monkeypatch.setattr(bootstrap.sys, "stdout", _TTY())
    monkeypatch.setattr(bootstrap.sys, "stderr", _TTY())
    options = bootstrap.build_parser().parse_args(
        [
            "setup",
            "--state-dir",
            str(state),
            "--oauth-client",
            str(client),
            "--request-id",
            REQUEST,
        ]
    )
    with pytest.raises(ConfigError) as caught:
        bootstrap._setup_command(options)
    assert caught.value.code is ErrorCode.REQUEST_CONFLICT
    assert calls == []


def test_setup_rejects_unapproved_bind_address_before_oauth(monkeypatch, tmp_path):
    calls = []

    class Authorizer:
        def authorize(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("OAuth must not start for an invalid bind")

    monkeypatch.setattr("facet.gmail.oauth.GoogleOAuthAuthorizer", Authorizer)
    monkeypatch.setattr(bootstrap.sys, "stdin", _TTY("confirm\n"))
    monkeypatch.setattr(bootstrap.sys, "stdout", _TTY())
    monkeypatch.setattr(bootstrap.sys, "stderr", _TTY())
    client = tmp_path / "client.json"
    client.write_text(_client_document())
    client.chmod(0o600)
    tmp_path.chmod(0o700)
    options = bootstrap.build_parser().parse_args(
        [
            "setup",
            "--state-dir",
            str(tmp_path / "state"),
            "--oauth-client",
            str(client),
            "--bind-address",
            "192.0.2.1",
            "--request-id",
            REQUEST,
        ]
    )
    with pytest.raises(ConfigError) as caught:
        bootstrap._setup_command(options)
    assert caught.value.code is ErrorCode.INVALID_INPUT
    assert calls == []
