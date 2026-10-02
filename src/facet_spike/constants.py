"""Constants shared by the Gmail spike."""

from __future__ import annotations

SOURCE_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)
TARGET_SCOPES = (
    "https://www.googleapis.com/auth/gmail.insert",
    "https://www.googleapis.com/auth/gmail.readonly",
)

ROLE_SCOPES = {
    "source": SOURCE_SCOPES,
    "target": TARGET_SCOPES,
}

DEFAULT_RUNTIME_DIR = ".facet-spike"
DEFAULT_OAUTH_PORT = 8765
