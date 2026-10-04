"""Private Google Desktop OAuth exchange for the production CLI."""

from __future__ import annotations

import contextlib
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

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


def _read_private(path: Path) -> bytes:
    try:
        parent = path.parent.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) & 0o77
        ):
            _fail(ErrorCode.SCOPE_REQUIRED)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o77
                or info.st_nlink != 1
                or info.st_size > 32768
            ):
                _fail(ErrorCode.SCOPE_REQUIRED)
            raw = os.read(descriptor, 32769)
        finally:
            os.close(descriptor)
    except FileNotFoundError:
        _fail(ErrorCode.SOURCE_AUTH_REQUIRED)
    except StorageFailure:
        raise
    except OSError:
        _fail(ErrorCode.PERSISTENCE_FAILURE)
    if len(raw) > 32768:
        _fail(ErrorCode.SCOPE_REQUIRED)
    return raw


def read_desktop_client(path: str | os.PathLike[str]) -> DesktopClientConfig:
    """Read and validate a private installed-app client file."""

    if not isinstance(path, (str, os.PathLike)):
        _fail(ErrorCode.INVALID_INPUT)
    try:
        return parse_desktop_client(_read_private(Path(path)))
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
    ) -> ProviderSecret:
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
    ) -> ProviderSecret:
        if (
            type(role) is not Role
            or type(client) is not DesktopClientConfig
            or type(scopes) is not ScopeSet
            or type(port) is not int
            or not 1024 <= port <= 65535
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
            # google-auth-oauthlib prints its prompt itself. Redirect that
            # private URL-bearing output to stderr so JSON stdout stays clean.
            with contextlib.redirect_stdout(sys.stderr):
                credentials = flow.run_local_server(
                    host="localhost",
                    bind_addr="127.0.0.1",
                    port=port,
                    open_browser=True,
                    authorization_prompt_message=(
                        "Open this authorization URL in the controlling browser: {url}"
                    ),
                )
        except StorageFailure:
            raise
        except Exception:
            _fail(
                ErrorCode.SOURCE_AUTH_REQUIRED
                if role is Role.SOURCE
                else ErrorCode.TARGET_AUTH_REQUIRED
            )
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
        return ProviderSecret(
            ClientIdText(client.client_id.value),
            SecretText(client.client_secret.value),
            SecretText(token),
            SecretText(refresh),
            Timestamp(expiry.astimezone(UTC)),
        )
