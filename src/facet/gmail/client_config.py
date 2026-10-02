"""Pure Desktop input-format parser; no URLs or capabilities in its result."""

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from .credential_codec import _json
from .credential_models import ClientIdText, SecretText, _checked, _field, _require

__all__ = ("DesktopClientConfig", "parse_desktop_client")


@dataclass(frozen=True, slots=True, repr=False)
class DesktopClientConfig:
    client_id: ClientIdText
    client_secret: SecretText

    def __post_init__(self):
        def validated():
            _require(type(self) is DesktopClientConfig)
            _field(self.client_id, ClientIdText)
            _field(self.client_secret, SecretText)

        _checked(validated)

    def __repr__(self):
        return "<private desktop client>"

    __str__ = __repr__


def _redirect(value):
    _require(type(value) is str and len(value.encode("utf-8")) <= 2048)
    _require(
        value.isascii()
        and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
    )
    _require(not any(c in value for c in "\\?#@"))
    if value == "http://localhost":
        return
    parts = urlsplit(value)
    _require(parts.scheme == "http" and value.startswith("http://"))
    _require(parts.hostname is not None and "%" not in parts.netloc)
    _require(ipaddress.ip_address(parts.hostname).is_loopback)
    _require(not parts.path or parts.path.startswith("/"))
    # urlsplit accepts an empty port; the closed grammar does not.
    authority = parts.netloc
    suffix = (
        authority[authority.index("]") + 1 :]
        if authority.startswith("[")
        else authority[len(parts.hostname) :]
    )
    _require(
        not suffix
        or (
            suffix.startswith(":")
            and suffix[1:].isascii()
            and suffix[1:].isdigit()
            and 1 <= int(suffix[1:]) <= 65535
        )
    )


def _parse(raw):
    document = _json(raw)
    _require(type(document) is dict and document.keys() == {"installed"})
    value = document["installed"]
    required = {"client_id", "client_secret", "auth_uri", "token_uri", "redirect_uris"}
    _require(
        type(value) is dict
        and required
        <= value.keys()
        <= required | {"project_id", "auth_provider_x509_cert_url"}
    )
    for key, allowed in (
        (
            "auth_uri",
            {
                "https://accounts.google.com/o/oauth2/auth",
                "https://accounts.google.com/o/oauth2/v2/auth",
            },
        ),
        (
            "token_uri",
            {
                "https://accounts.google.com/o/oauth2/token",
                "https://oauth2.googleapis.com/token",
            },
        ),
    ):
        _require(type(value[key]) is str and value[key] in allowed)
    if "project_id" in value:
        project = value["project_id"]
        _require(
            type(project) is str
            and project.isascii()
            and len(project) <= 256
            and not any(ord(c) < 32 or ord(c) == 127 for c in project)
        )
    if "auth_provider_x509_cert_url" in value:
        cert = value["auth_provider_x509_cert_url"]
        _require(
            type(cert) is str and cert == "https://www.googleapis.com/oauth2/v1/certs"
        )
    redirects = value["redirect_uris"]
    _require(type(redirects) is list and 1 <= len(redirects) <= 16)
    for entry in redirects:
        _redirect(entry)
    _require(len(set(redirects)) == len(redirects))
    return DesktopClientConfig(
        ClientIdText(value["client_id"]), SecretText(value["client_secret"])
    )


def parse_desktop_client(raw: bytes) -> DesktopClientConfig:
    return _checked(lambda: _parse(raw))
