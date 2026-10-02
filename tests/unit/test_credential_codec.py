"""OP03/04/06: private bounded JSON grammar, no input-error retention."""

import json
from dataclasses import replace

import pytest
from test_credential_models import SENTINEL, Trap, assert_controlled, envelope

from facet.contracts import ErrorCode
from facet.gmail.credential_codec import decode_envelope, encode_envelope
from facet.gmail.credential_models import SecretText


def test_exact_canonical_roundtrip_has_only_explicit_memory_secret():
    value = envelope()
    raw = encode_envelope(value)
    assert SENTINEL.encode() in raw
    assert decode_envelope(raw) == value
    assert encode_envelope(decode_envelope(raw)) == raw
    assert (
        raw
        == json.dumps(
            json.loads(raw), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    )
    assert b".123456Z" in raw and not raw.endswith(b"\n")


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{}",
        b"[]",
        b"null",
        b"NaN",
        b"Infinity",
        b"1e3",
        b"1.0",
        b"\xef\xbb\xbf{}",
        b"\xff",
        b"{}{}",
        b'{"x":1,"x":2}',
        b"[" * 9 + b"0" + b"]" * 9,
        b"9" * 10000,
        b" " * 131073,
        b'{"secret":"SYNTHETIC_PRIVATE_CREDENTIAL",}',
    ],
)
def test_malformed_json_does_not_retain_private_parser_context(raw):
    assert_controlled(lambda: decode_envelope(raw))


@pytest.mark.parametrize("section", [None, "grant", "secret"])
@pytest.mark.parametrize("mutation", ["extra", "missing", "duplicate"])
def test_every_nested_object_exact_keys(section, mutation):
    value = json.loads(encode_envelope(envelope()))
    target = value if section is None else value[section]
    key = next(iter(target))
    if mutation == "extra":
        target["private_unknown"] = SENTINEL
    elif mutation == "missing":
        del target[key]
    raw = json.dumps(value).encode()
    if mutation == "duplicate":
        text = json.dumps(key).encode() + b":"
        raw = raw.replace(text, text + b'"SYNTHETIC_PRIVATE_CREDENTIAL",' + text, 1)
    assert_controlled(lambda: decode_envelope(raw))


@pytest.mark.parametrize(
    "key,value",
    [
        ("version", True),
        ("binding_revision", -1),
        ("credential_revision", 2**63),
        ("scope_policy_revision", 1.0),
        ("role", "unknown"),
        ("profile_verified_at", "2026-10-02T01:02:03+00:00"),
        ("profile_verified_at", "2026-02-30T01:02:03Z"),
        ("profile_verified_at", "2026-10-02T01:02:60Z"),
        ("profile_verified_at", "2026-10-02T01:02:03.1234567Z"),
    ],
)
def test_bad_envelope_scalar(key, value):
    document = json.loads(encode_envelope(envelope()))
    document[key] = value
    assert_controlled(lambda: decode_envelope(json.dumps(document).encode()))


def test_unsupported_version_code_and_timestamp_canonicalization():
    document = json.loads(encode_envelope(envelope()))
    document["version"] = 99
    assert (
        assert_controlled(lambda: decode_envelope(json.dumps(document).encode())).code
        is ErrorCode.UNSUPPORTED_VERSION
    )
    document["version"] = 1
    document["profile_verified_at"] = "2026-10-02T01:02:03Z"
    raw = json.dumps(document).encode()
    assert b"2026-10-02T01:02:03.000000Z" in encode_envelope(decode_envelope(raw))


@pytest.mark.parametrize(
    "scopes", [["gmail_insert", "gmail_insert"], ["evil"], [], None]
)
def test_scope_duplicate_unknown_or_wrong_shape(scopes):
    document = json.loads(encode_envelope(envelope()))
    document["grant"]["granted"] = scopes
    assert_controlled(lambda: decode_envelope(json.dumps(document).encode()))


def test_escaped_brackets_and_byte_limit_do_not_make_false_depth():
    value = envelope()
    value = replace(
        value, secret=replace(value.secret, access_token=SecretText('["\\]' * 1000))
    )
    raw = encode_envelope(value)
    assert decode_envelope(raw) == value
    padded = raw + b" " * (131072 - len(raw))
    assert decode_envelope(padded) == value
    assert_controlled(lambda: decode_envelope(padded + b" "))


def test_wrong_types_and_bytes_subclasses_never_invoke_hooks():
    class BadBytes(bytes):
        def decode(self, *args, **kwargs):
            raise AssertionError("decode hook called")

    for value in (Trap(), BadBytes(b"{}"), bytearray(b"{}"), "{}"):
        assert_controlled(lambda value=value: decode_envelope(value))
        assert_controlled(lambda value=value: encode_envelope(value))


def test_internal_lexical_depth_guard_has_exact_boundary_positive_control():
    # The finite envelope schema has no depth-8 branch. Exercise the shared
    # private lexer separately, without calling this generic tree an envelope.
    from facet.gmail.credential_codec import _json

    raw = b"[" * 8 + b"0" + b"]" * 8
    value = _json(raw)
    for _ in range(8):
        assert type(value) is list and len(value) == 1
        value = value[0]
    assert value == 0
    with pytest.raises(ValueError, match="invalid_input"):
        _json(b"[" + raw + b"]")
