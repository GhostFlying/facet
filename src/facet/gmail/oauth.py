"""Private Google Desktop OAuth exchange for the production CLI."""

from __future__ import annotations

import errno
import os
import stat
import sys
import wsgiref.simple_server
import wsgiref.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from facet.contracts import ErrorCode, Role, Timestamp
from facet.db.codecs import StorageFailure

from .client_config import DesktopClientConfig, parse_desktop_client
from .credential_models import (
    ClientIdText,
    ProviderSecret,
    ScopeName,
    ScopeSet,
    SecretText,
)

__all__ = (
    "OAuthAuthorizer",
    "OAuthResult",
    "GoogleOAuthAuthorizer",
    "read_desktop_client",
)


def _fail(code: ErrorCode) -> None:
    raise StorageFailure(code)


def _scope_values(scopes: ScopeSet) -> tuple[str, ...]:
    names = {
        ScopeName.GMAIL_READONLY: "https://www.googleapis.com/auth/gmail.readonly",
        ScopeName.GMAIL_INSERT: "https://www.googleapis.com/auth/gmail.insert",
        ScopeName.GMAIL_MODIFY: "https://www.googleapis.com/auth/gmail.modify",
        ScopeName.GMAIL_LABELS: "https://www.googleapis.com/auth/gmail.labels",
    }
    try:
        return tuple(sorted(names[name] for name in scopes.value))
    except (KeyError, AttributeError, TypeError):
        _fail(ErrorCode.INVALID_INPUT)


_SCOPE_NAMES = {
    "https://www.googleapis.com/auth/gmail.readonly": ScopeName.GMAIL_READONLY,
    "https://www.googleapis.com/auth/gmail.insert": ScopeName.GMAIL_INSERT,
    "https://www.googleapis.com/auth/gmail.modify": ScopeName.GMAIL_MODIFY,
    "https://www.googleapis.com/auth/gmail.labels": ScopeName.GMAIL_LABELS,
}


class OAuthResult:
    __slots__ = ("secret", "scopes")

    def __init__(self, secret: ProviderSecret, scopes: ScopeSet):
        if type(secret) is not ProviderSecret or type(scopes) is not ScopeSet:
            _fail(ErrorCode.INVALID_INPUT)
        self.secret = secret
        self.scopes = scopes

    def __repr__(self):
        return "<oauth result>"

    __str__ = __repr__


_CONTAINER_SECRET_PARENT = Path("/run/secrets")


def _read_private(path: Path, *, container_secret: bool = False) -> bytes:
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail(ErrorCode.SCOPE_REQUIRED)
    directory = None
    try:
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for component in path.parts[1:-1]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=directory,
            )
            os.close(directory)
            directory = child
        parent = os.fstat(directory)
        parent_is_private = (
            stat.S_ISDIR(parent.st_mode)
            and parent.st_uid == os.geteuid()
            and stat.S_IMODE(parent.st_mode) & 0o77 == 0
        )
        parent_is_container_secret = (
            container_secret
            and path.parent == _CONTAINER_SECRET_PARENT
            and stat.S_ISDIR(parent.st_mode)
            and stat.S_IMODE(parent.st_mode) & 0o022 == 0
        )
        if not parent_is_private and not parent_is_container_secret:
            _fail(ErrorCode.SCOPE_REQUIRED)
        descriptor = os.open(
            path.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory
        )
        try:
            info = os.fstat(descriptor)
            file_is_private = (
                stat.S_ISREG(info.st_mode)
                and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) & 0o77 == 0
            )
            file_is_container_secret = (
                container_secret
                and path.parent == _CONTAINER_SECRET_PARENT
                and stat.S_ISREG(info.st_mode)
                and stat.S_IMODE(info.st_mode) & 0o022 == 0
            )
            if (
                (not file_is_private and not file_is_container_secret)
                or info.st_nlink != 1
                or info.st_size > 32768
            ):
                _fail(ErrorCode.SCOPE_REQUIRED)
            raw = os.read(descriptor, 32769)
        finally:
            os.close(descriptor)
            os.close(directory)
            directory = None
    except FileNotFoundError:
        _fail(ErrorCode.SOURCE_AUTH_REQUIRED)
    except StorageFailure:
        raise
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            _fail(ErrorCode.SCOPE_REQUIRED)
        _fail(ErrorCode.PERSISTENCE_FAILURE)
    finally:
        if directory is not None:
            os.close(directory)
    if len(raw) > 32768:
        _fail(ErrorCode.SCOPE_REQUIRED)
    return raw


def read_desktop_client(path: str | os.PathLike[str]) -> DesktopClientConfig:
    """Read and validate a private installed-app client file."""

    if not isinstance(path, (str, os.PathLike)):
        _fail(ErrorCode.INVALID_INPUT)
    try:
        candidate = Path(path)
        return parse_desktop_client(
            _read_private(
                candidate,
                container_secret=candidate.parent == _CONTAINER_SECRET_PARENT,
            )
        )
    except StorageFailure:
        raise
    except Exception:
        _fail(ErrorCode.INVALID_INPUT)


class OAuthAuthorizer(Protocol):
    def authorize(
        self,
        role: Role,
        client: DesktopClientConfig,
        scopes: ScopeSet,
        *,
        port: int,
        bind_address: str = "127.0.0.1",
        strict_setup: bool = False,
        callback_timeout_seconds: int = 300,
    ) -> OAuthResult:
        """Exchange one explicit role's loopback consent for private secrets."""


class GoogleOAuthAuthorizer:
    """Run one Google installed-app loopback flow without persisting tokens."""

    def authorize(
        self,
        role: Role,
        client: DesktopClientConfig,
        scopes: ScopeSet,
        *,
        port: int,
        bind_address: str = "127.0.0.1",
        strict_setup: bool = False,
        callback_timeout_seconds: int = 300,
    ) -> OAuthResult:
        if (
            type(role) is not Role
            or type(client) is not DesktopClientConfig
            or type(scopes) is not ScopeSet
            or type(port) is not int
            or not 1024 <= port <= 65535
            or bind_address not in {"127.0.0.1", "0.0.0.0"}
            or type(strict_setup) is not bool
            or type(callback_timeout_seconds) is not int
            or not 60 <= callback_timeout_seconds <= 1800
        ):
            _fail(ErrorCode.INVALID_INPUT)
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow

            config = {
                "installed": {
                    "client_id": client.client_id.value,
                    "client_secret": client.client_secret.value,
                    "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
            flow = InstalledAppFlow.from_client_config(config, _scope_values(scopes))
            wsgi_app = _RedirectApp()
            server = wsgiref.simple_server.make_server(
                bind_address,
                port,
                wsgi_app,
                handler_class=_SilentRequestHandler,
            )
            try:
                flow.redirect_uri = f"http://localhost:{server.server_port}/"
                auth_url, expected_state = flow.authorization_url(
                    access_type="offline",
                    prompt="consent",
                    include_granted_scopes="false" if strict_setup else "true",
                )
                print(
                    "Open this authorization URL in the controlling browser: "
                    + auth_url,
                    file=sys.stderr,
                )
                server.timeout = callback_timeout_seconds
                server.handle_request()
                if wsgi_app.last_request_uri is None or not _valid_callback(
                    wsgi_app.last_request_uri,
                    expected_state,
                    server.server_port,
                ):
                    _fail(
                        ErrorCode.SOURCE_AUTH_REQUIRED
                        if role is Role.SOURCE
                        else ErrorCode.TARGET_AUTH_REQUIRED
                    )
                flow.fetch_token(
                    authorization_response=wsgi_app.last_request_uri.replace(
                        "http", "https", 1
                    )
                )
                credentials = flow.credentials
            finally:
                server.server_close()
            expiry = getattr(credentials, "expiry", None)
            token = getattr(credentials, "token", None)
            refresh = getattr(credentials, "refresh_token", None)
            if not isinstance(token, str) or not token or not isinstance(refresh, str):
                _fail(
                    ErrorCode.SOURCE_AUTH_REQUIRED
                    if role is Role.SOURCE
                    else ErrorCode.TARGET_AUTH_REQUIRED
                )
            if not isinstance(expiry, datetime):
                _fail(ErrorCode.INVALID_INPUT)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if strict_setup:
                # Requested scopes are not evidence of what Google granted. The
                # token response's granted_scopes field is the only acceptable
                # first-run evidence; absent evidence fails closed.
                granted = getattr(credentials, "granted_scopes", None)
                if isinstance(granted, str):
                    granted = tuple(granted.split())
            else:
                granted = getattr(credentials, "scopes", None)
                if granted is None:
                    granted = getattr(credentials, "granted_scopes", None)
            if not isinstance(granted, (tuple, list, set)):
                _fail(ErrorCode.SCOPE_REQUIRED)
            try:
                scope_set = ScopeSet(
                    frozenset(_SCOPE_NAMES[value] for value in granted)
                )
            except (KeyError, TypeError, ValueError):
                _fail(ErrorCode.SCOPE_REQUIRED)
            return OAuthResult(
                ProviderSecret(
                    ClientIdText(client.client_id.value),
                    SecretText(client.client_secret.value),
                    SecretText(token),
                    SecretText(refresh),
                    Timestamp(expiry.astimezone(UTC)),
                ),
                scope_set,
            )
        except StorageFailure:
            raise
        except Exception:
            _fail(
                ErrorCode.SOURCE_AUTH_REQUIRED
                if role is Role.SOURCE
                else ErrorCode.TARGET_AUTH_REQUIRED
            )


class _SilentRequestHandler(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _RedirectApp:
    def __init__(self):
        self.last_request_uri = None

    def __call__(self, environ, start_response):
        if environ.get("REQUEST_METHOD") == "GET":
            self.last_request_uri = wsgiref.util.request_uri(environ)
        start_response("200 OK", [("Content-type", "text/plain; charset=utf-8")])
        return [b"Authorization completed. You may close this tab."]


def _valid_callback(uri, expected_state, port):
    if not isinstance(uri, str) or not isinstance(expected_state, str):
        return False
    parsed = urlsplit(uri)
    if (
        parsed.scheme != "http"
        or parsed.netloc != f"localhost:{port}"
        or parsed.path != "/"
        or parsed.fragment
    ):
        return False
    query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=False)
    states = query.get("state", ())
    codes = query.get("code", ())
    errors = query.get("error", ())
    if len(states) != 1 or states[0] != expected_state:
        return False
    return (len(codes) == 1 and not errors) or (len(errors) == 1 and not codes)
