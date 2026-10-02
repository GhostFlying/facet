"""OAuth helpers for the supported Desktop loopback flow."""

from __future__ import annotations

import json
import stat
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from facet_spike.constants import ROLE_SCOPES
from facet_spike.errors import SpikeError
from facet_spike.files import write_private_json
from facet_spike.runtime import RuntimePaths


def _check_private_file(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise SpikeError(
            f"{path} is readable by group or other users; run chmod 600 first"
        )


def authorize(
    paths: RuntimePaths,
    role: str,
    *,
    port: int,
    open_browser: bool,
) -> Credentials:
    if role not in ROLE_SCOPES:
        raise SpikeError(f"unknown OAuth role: {role}")
    if not paths.client_secret.exists():
        raise SpikeError(f"missing Desktop OAuth client JSON: {paths.client_secret}")
    _check_private_file(paths.client_secret)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(paths.client_secret),
        scopes=ROLE_SCOPES[role],
    )
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=port,
        open_browser=open_browser,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message=(
            "Open this URL in a browser after arranging the loopback port "
            "forward if this command runs remotely:\n{url}"
        ),
        success_message=(
            "Facet Gmail spike authorization completed. You may close this tab."
        ),
    )
    save_credentials(paths, role, credentials)
    return credentials


def load_credentials(paths: RuntimePaths, role: str) -> Credentials:
    if role not in ROLE_SCOPES:
        raise SpikeError(f"unknown OAuth role: {role}")
    token_path = paths.token(role)
    if not token_path.exists():
        raise SpikeError(f"{role} is not authorized; run: facet-spike auth {role}")
    _check_private_file(token_path)
    credentials = Credentials.from_authorized_user_file(
        str(token_path),
        scopes=ROLE_SCOPES[role],
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        save_credentials(paths, role, credentials)
    if not credentials.valid:
        raise SpikeError(f"{role} credentials are invalid; authorize that role again")
    if not credentials.has_scopes(ROLE_SCOPES[role]):
        raise SpikeError(
            f"{role} token does not contain all required scopes; authorize again"
        )
    return credentials


def save_credentials(
    paths: RuntimePaths,
    role: str,
    credentials: Credentials,
) -> None:
    payload = json.loads(credentials.to_json())
    write_private_json(paths.token(role), payload)
