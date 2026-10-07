"""Ephemeral full-mail consent, exclusively for explicit target cleanup.

No credentials from this adapter are persisted or accepted by sync.
"""

from __future__ import annotations

import sys
import wsgiref.simple_server
from dataclasses import dataclass
from datetime import UTC, datetime

from facet.contracts import ErrorCode
from facet.db.codecs import StorageFailure

from .client_config import DesktopClientConfig
from .credential_models import SecretText
from .oauth import _RedirectApp, _SilentRequestHandler, _valid_callback

FULL_MAIL_SCOPE = "https://mail.google.com/"


@dataclass(frozen=True, slots=True, repr=False)
class CleanupAccess:
    token: SecretText
    expires_at: datetime


def authorize_cleanup(client: DesktopClientConfig, *, port, callback_timeout_seconds):
    if (
        type(client) is not DesktopClientConfig
        or type(port) is not int
        or not 1024 <= port <= 65535
        or type(callback_timeout_seconds) is not int
        or not 60 <= callback_timeout_seconds <= 1800
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise StorageFailure(ErrorCode.CONFIRMATION_REQUIRED)
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": client.client_id.value,
                    "client_secret": client.client_secret.value,
                    "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            },
            [FULL_MAIL_SCOPE],
        )
        application = _RedirectApp()
        server = wsgiref.simple_server.make_server(
            "127.0.0.1", port, application, handler_class=_SilentRequestHandler
        )
        try:
            flow.redirect_uri = f"http://localhost:{server.server_port}/"
            url, state = flow.authorization_url(
                access_type="online", prompt="consent", include_granted_scopes="false"
            )
            print(
                "Temporary target-cleanup consent (full Gmail access): " + url,
                file=sys.stderr,
            )
            server.timeout = callback_timeout_seconds
            server.handle_request()
            if application.last_request_uri is None or not _valid_callback(
                application.last_request_uri, state, server.server_port
            ):
                raise StorageFailure(ErrorCode.TARGET_AUTH_REQUIRED)
            flow.fetch_token(
                authorization_response=application.last_request_uri.replace(
                    "http", "https", 1
                ),
                timeout=30,
            )
            credentials = flow.credentials
        finally:
            server.server_close()
        granted = getattr(credentials, "granted_scopes", None)
        if isinstance(granted, str):
            granted = granted.split()
        if not isinstance(granted, (list, tuple, set)) or set(granted) != {
            FULL_MAIL_SCOPE
        }:
            raise StorageFailure(ErrorCode.SCOPE_REQUIRED)
        expiry = getattr(credentials, "expiry", None)
        token = getattr(credentials, "token", None)
        if not isinstance(expiry, datetime) or type(token) is not str or not token:
            raise StorageFailure(ErrorCode.TARGET_AUTH_REQUIRED)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= datetime.now(UTC):
            raise StorageFailure(ErrorCode.TARGET_AUTH_REQUIRED)
        return CleanupAccess(SecretText(token), expiry)
    except StorageFailure:
        raise
    except Exception:
        raise StorageFailure(ErrorCode.TARGET_AUTH_REQUIRED) from None
