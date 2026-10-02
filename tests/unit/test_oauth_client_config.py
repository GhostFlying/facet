"""OP05: only synthetic in-memory Desktop registration input, never OAuth."""

import json
from dataclasses import fields

import pytest
from test_credential_models import SENTINEL, Trap, assert_controlled

from facet.gmail.client_config import DesktopClientConfig, parse_desktop_client


def client():
    return {
        "installed": {
            "client_id": "synthetic-client",
            "client_secret": SENTINEL,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://accounts.google.com/o/oauth2/token",
            "redirect_uris": ["http://localhost"],
        }
    }


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize(
    "redirect",
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://127.3.4.5:1024/callback",
        "http://[::1]:65535/callback",
    ],
)
def test_official_shaped_legacy_modern_and_numeric_loopback(modern, redirect):
    document = client()
    value = document["installed"]
    if modern:
        value["auth_uri"] = "https://accounts.google.com/o/oauth2/v2/auth"
        value["token_uri"] = "https://oauth2.googleapis.com/token"
    value["redirect_uris"] = [redirect]
    value["project_id"] = "synthetic-project"
    value["auth_provider_x509_cert_url"] = "https://www.googleapis.com/oauth2/v1/certs"
    result = parse_desktop_client(json.dumps(document).encode())
    assert result.client_secret.value == SENTINEL
    assert tuple(f.name for f in fields(result)) == ("client_id", "client_secret")
    assert SENTINEL not in repr(result) + str(result)


@pytest.mark.parametrize(
    "redirect",
    [
        "http://localhost:1234",
        "http://example.invalid",
        "https://127.0.0.1",
        "http://127.0.0.1:",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:abc",
        "http://127.0.0.1?",
        "http://127.0.0.1#",
        "http://user@127.0.0.1",
        "http://%31%32%37.0.0.1",
        "http://[::1%lo]",
        "http://127.0.0.1/\\evil",
        "http://127.0.0.1/\n",
        "http://127.0.0.1/é",
    ],
)
def test_bad_registered_redirect_never_selects_callback(redirect):
    document = client()
    document["installed"]["redirect_uris"] = [redirect]
    assert_controlled(lambda: parse_desktop_client(json.dumps(document).encode()))


@pytest.mark.parametrize(
    "key,value",
    [
        ("auth_uri", "https://accounts.google.com/o/oauth2/auth?x"),
        ("auth_uri", "https://accounts.google.com.evil.invalid/o/oauth2/auth"),
        ("token_uri", "https://user@oauth2.googleapis.com/token"),
        ("token_uri", "https://oauth2.googleapis.com:443/token"),
        ("token_uri", "https://oauth2.googleapis.com/token/"),
        ("token_uri", "https://oauth2.googleapis.com/%74oken"),
        ("auth_provider_x509_cert_url", "https://evil.invalid"),
        ("project_id", "x\n"),
        ("unknown", SENTINEL),
        ("redirect_uris", []),
        ("redirect_uris", ["http://localhost"] * 2),
    ],
)
def test_finite_client_input_fields(key, value):
    document = client()
    document["installed"][key] = value
    assert_controlled(lambda: parse_desktop_client(json.dumps(document).encode()))


def test_web_extra_root_wrong_types_and_untrusted_object():
    value = client()["installed"]
    for document in (
        {"web": value},
        {"installed": value, "other": {}},
        {"installed": []},
    ):
        assert_controlled(
            lambda document=document: parse_desktop_client(
                json.dumps(document).encode()
            )
        )
    assert_controlled(lambda: parse_desktop_client(Trap()))
    assert_controlled(lambda: DesktopClientConfig(Trap(), Trap()))


def test_desktop_subclass_is_not_a_trusted_record():
    class Foreign(DesktopClientConfig):
        @property
        def client_id(self):
            raise AssertionError("descriptor must not be read")

    assert_controlled(
        lambda: DesktopClientConfig.__post_init__(object.__new__(Foreign))
    )
