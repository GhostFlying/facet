"""Explicit private memory encoding, never a credential file reader or attestor."""

import json
import re
from datetime import datetime

from facet.contracts import LocalId, ProjectionId, Revision, Role, Timestamp

from .credential_models import (
    AccountAddress,
    ClientIdText,
    CredentialEnvelope,
    GrantEvidence,
    GrantEvidenceKind,
    ProviderSecret,
    ScopeName,
    ScopePolicy,
    ScopeSet,
    SecretText,
    _checked,
    _field,
    _require,
)

__all__ = ("encode_envelope", "decode_envelope")
_MAX_BYTES = 131072


def _reject(value):
    raise ValueError("invalid_input")


def _integer(text):
    _require(len(text.lstrip("-")) <= 19)
    value = int(text)
    _require(-(2**63) <= value <= 2**63 - 1)
    return value


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value)
        value[key] = item
    return value


def _json(raw):
    _require(type(raw) is bytes and len(raw) <= _MAX_BYTES)
    text = raw.decode("utf-8", errors="strict")
    _require(not text.startswith("\ufeff"))
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            _require(depth <= 8)
        elif char in "]}":
            depth -= 1
            _require(depth >= 0)
    return json.loads(
        text,
        object_pairs_hook=_pairs,
        parse_int=_integer,
        parse_float=_reject,
        parse_constant=_reject,
    )


def _object(value, keys):
    _require(type(value) is dict)
    _require(all(type(key) is str for key in value))
    _require(value.keys() == keys)
    return value


def _enum(value, kind):
    _require(type(value) is str)
    return kind(value)


def _time(value):
    _require(type(value) is str)
    _require(
        re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z",
            value,
        )
        is not None
    )
    return Timestamp(datetime.fromisoformat(value))


def _scopes(value):
    _require(type(value) is list and 1 <= len(value) <= 4)
    values = tuple(_enum(item, ScopeName) for item in value)
    _require(len(frozenset(values)) == len(values))
    return ScopeSet(frozenset(values))


def _decode(raw):
    value = _object(
        _json(raw),
        {
            "version",
            "projection_id",
            "state_instance_id",
            "role",
            "binding_revision",
            "credential_revision",
            "change_id",
            "account",
            "scope_policy",
            "scope_policy_revision",
            "grant",
            "profile_verified_at",
            "secret",
        },
    )
    grant = _object(
        value["grant"],
        {
            "kind",
            "granted",
            "requested",
            "observed_at",
            "parent_credential_revision",
        },
    )
    secret = _object(
        value["secret"],
        {
            "client_id",
            "client_secret",
            "access_token",
            "refresh_token",
            "expires_at",
        },
    )
    parent = grant["parent_credential_revision"]
    return CredentialEnvelope(
        version=value["version"],
        projection_id=ProjectionId(value["projection_id"]),
        state_instance_id=LocalId(value["state_instance_id"]),
        role=_enum(value["role"], Role),
        binding_revision=Revision(value["binding_revision"]),
        credential_revision=Revision(value["credential_revision"]),
        change_id=LocalId(value["change_id"]),
        account=AccountAddress(value["account"]),
        scope_policy=_enum(value["scope_policy"], ScopePolicy),
        scope_policy_revision=Revision(value["scope_policy_revision"]),
        grant=GrantEvidence(
            _enum(grant["kind"], GrantEvidenceKind),
            _scopes(grant["granted"]),
            _scopes(grant["requested"]),
            _time(grant["observed_at"]),
            None if parent is None else Revision(parent),
        ),
        profile_verified_at=_time(value["profile_verified_at"]),
        secret=ProviderSecret(
            ClientIdText(secret["client_id"]),
            SecretText(secret["client_secret"]),
            SecretText(secret["access_token"]),
            SecretText(secret["refresh_token"]),
            _time(secret["expires_at"]),
        ),
    )


def decode_envelope(raw: bytes) -> CredentialEnvelope:
    return _checked(lambda: _decode(raw))


def _stamp(value):
    return value.value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _encode(value):
    _field(value, CredentialEnvelope)
    grant, secret = value.grant, value.secret
    document = {
        "version": value.version,
        "projection_id": value.projection_id.value,
        "state_instance_id": value.state_instance_id.value,
        "role": value.role.value,
        "binding_revision": value.binding_revision.value,
        "credential_revision": value.credential_revision.value,
        "change_id": value.change_id.value,
        "account": value.account.value,
        "scope_policy": value.scope_policy.value,
        "scope_policy_revision": value.scope_policy_revision.value,
        "profile_verified_at": _stamp(value.profile_verified_at),
        "grant": {
            "kind": grant.kind.value,
            "granted": sorted(item.value for item in grant.granted.value),
            "requested": sorted(item.value for item in grant.requested.value),
            "observed_at": _stamp(grant.observed_at),
            "parent_credential_revision": None
            if grant.parent_credential_revision is None
            else grant.parent_credential_revision.value,
        },
        "secret": {
            "client_id": secret.client_id.value,
            "client_secret": secret.client_secret.value,
            "access_token": secret.access_token.value,
            "refresh_token": secret.refresh_token.value,
            "expires_at": _stamp(secret.expires_at),
        },
    }
    raw = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    _require(len(raw) <= _MAX_BYTES)
    return raw


def encode_envelope(value: CredentialEnvelope) -> bytes:
    return _checked(lambda: _encode(value))
