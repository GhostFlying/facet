"""Private structural values, never OAuth/profile attestation or capabilities."""

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from facet.config import ConfigError, _mailbox
from facet.contracts import ErrorCode, LocalId, ProjectionId, Revision, Role, Timestamp

__all__ = (
    "SecretText",
    "ClientIdText",
    "AccountAddress",
    "ScopeName",
    "ScopeSet",
    "ScopePolicy",
    "GrantEvidenceKind",
    "GrantEvidence",
    "ProviderSecret",
    "RefreshResult",
    "CredentialEnvelope",
    "AccessSnapshot",
    "CredentialCodecError",
    "policy_scopes",
)


class CredentialCodecError(Exception):
    """Only a fixed code; no parser error, bytes or private record retained."""

    def __init__(self, code: ErrorCode = ErrorCode.INVALID_INPUT):
        if type(code) is not ErrorCode or code not in {
            ErrorCode.INVALID_INPUT,
            ErrorCode.UNSUPPORTED_VERSION,
        }:
            code = ErrorCode.INVALID_INPUT
        self.code = code
        super().__init__(code.value)


def _checked(call):
    code = ErrorCode.INVALID_INPUT
    try:
        return call()
    except CredentialCodecError as error:
        code = error.code
    except (
        ConfigError,
        ValueError,
        TypeError,
        AttributeError,
        UnicodeError,
        OverflowError,
        RecursionError,
    ):
        pass
    # Raising outside the handler avoids retaining the private parser context.
    raise CredentialCodecError(code)


def _require(condition):
    if not condition:
        raise ValueError("invalid_input")


class _PrivateValue:
    __slots__ = ()

    def __repr__(self):
        return "<private credential value>"

    __str__ = __repr__

    def __post_init__(self):
        _checked(lambda: _validate(self))


@dataclass(frozen=True, slots=True, repr=False)
class SecretText(_PrivateValue):
    value: str


@dataclass(frozen=True, slots=True, repr=False)
class ClientIdText(_PrivateValue):
    value: str


@dataclass(frozen=True, slots=True, repr=False)
class AccountAddress(_PrivateValue):
    value: str


class ScopeName(StrEnum):
    GMAIL_READONLY = "gmail_readonly"
    GMAIL_INSERT = "gmail_insert"
    GMAIL_MODIFY = "gmail_modify"
    GMAIL_LABELS = "gmail_labels"


class ScopePolicy(StrEnum):
    SOURCE_READONLY = "source_readonly"
    SOURCE_CONVENIENCE = "source_convenience"
    TARGET_DEFAULT = "target_default"
    TARGET_LABELS = "target_labels"


class GrantEvidenceKind(StrEnum):
    AUTHORIZATION_EXPLICIT = "authorization_explicit"
    AUTHORIZATION_OMITTED_EQUAL = "authorization_omitted_equal"
    REFRESH_EXPLICIT = "refresh_explicit"
    REFRESH_OMITTED_INHERITED = "refresh_omitted_inherited"


@dataclass(frozen=True, slots=True, repr=False)
class ScopeSet(_PrivateValue):
    value: frozenset[ScopeName]


@dataclass(frozen=True, slots=True, repr=False)
class GrantEvidence(_PrivateValue):
    kind: GrantEvidenceKind
    granted: ScopeSet
    requested: ScopeSet
    observed_at: Timestamp
    parent_credential_revision: Revision | None


@dataclass(frozen=True, slots=True, repr=False)
class ProviderSecret(_PrivateValue):
    client_id: ClientIdText
    client_secret: SecretText
    access_token: SecretText
    refresh_token: SecretText
    expires_at: Timestamp


@dataclass(frozen=True, slots=True, repr=False)
class RefreshResult(_PrivateValue):
    """Private refresh output with optional explicit scope evidence."""

    secret: ProviderSecret
    scopes: ScopeSet | None


@dataclass(frozen=True, slots=True, repr=False)
class CredentialEnvelope(_PrivateValue):
    version: int
    projection_id: ProjectionId
    state_instance_id: LocalId
    role: Role
    binding_revision: Revision
    credential_revision: Revision
    change_id: LocalId
    account: AccountAddress
    scope_policy: ScopePolicy
    scope_policy_revision: Revision
    grant: GrantEvidence
    profile_verified_at: Timestamp
    secret: ProviderSecret


@dataclass(frozen=True, slots=True, repr=False)
class AccessSnapshot(_PrivateValue):
    """Private immutable access token view for a verified role."""

    role: Role
    credential_revision: Revision
    binding_revision: Revision
    scope_policy_revision: Revision
    access_token: SecretText
    expires_at: Timestamp

    def __post_init__(self):
        _checked(lambda: _validate(self))

    def __repr__(self):
        return "<access snapshot>"

    __str__ = __repr__


_POLICIES = {
    ScopePolicy.SOURCE_READONLY: (Role.SOURCE, frozenset({ScopeName.GMAIL_READONLY})),
    ScopePolicy.SOURCE_CONVENIENCE: (Role.SOURCE, frozenset({ScopeName.GMAIL_MODIFY})),
    ScopePolicy.TARGET_DEFAULT: (
        Role.TARGET,
        frozenset({ScopeName.GMAIL_INSERT, ScopeName.GMAIL_READONLY}),
    ),
    ScopePolicy.TARGET_LABELS: (
        Role.TARGET,
        frozenset(
            {ScopeName.GMAIL_INSERT, ScopeName.GMAIL_READONLY, ScopeName.GMAIL_LABELS}
        ),
    ),
}


def policy_scopes(policy: ScopePolicy, role: Role) -> ScopeSet:
    def validated():
        _require(type(policy) is ScopePolicy and type(role) is Role)
        expected_role, values = _POLICIES[policy]
        _require(role is expected_role)
        return ScopeSet(values)

    return _checked(validated)


def _core(value, kind, *, positive=False):
    _require(type(value) is kind)
    raw = value.value
    if kind is Timestamp:
        _require(type(raw) is datetime and type(raw.tzinfo) is timezone)
        _require(raw.utcoffset() == timedelta(0))
    elif kind is Revision:
        _require(type(raw) is int and (1 if positive else 0) <= raw <= 2**63 - 1)
    else:
        _require(type(raw) is str)
        kind(raw)  # Revalidate exact payload with its single canonical owner.


def _field(value, kind):
    _require(type(value) is kind)
    _validate(value)


def _validate(value):
    kind = type(value)
    if kind in (SecretText, ClientIdText, AccountAddress):
        raw = value.value
        _require(type(raw) is str and bool(raw))
        bound = 16384 if kind is SecretText else 1024
        _require(len(raw.encode("utf-8")) <= bound)
        _require(not any(unicodedata.category(c) in {"Cc", "Cs"} for c in raw))
        if kind is ClientIdText:
            _require(raw.isascii() and not any(c.isspace() for c in raw))
        if kind is AccountAddress:
            # Exact str is checked before the shared internal validator.
            _mailbox(raw)
    elif kind is ScopeSet:
        _require(type(value.value) is frozenset and 1 <= len(value.value) <= 4)
        _require(all(type(item) is ScopeName for item in value.value))
    elif kind is GrantEvidence:
        _require(type(value.kind) is GrantEvidenceKind)
        _field(value.granted, ScopeSet)
        _field(value.requested, ScopeSet)
        _require(value.granted.value == value.requested.value)
        _core(value.observed_at, Timestamp)
        if value.kind in {
            GrantEvidenceKind.AUTHORIZATION_EXPLICIT,
            GrantEvidenceKind.AUTHORIZATION_OMITTED_EQUAL,
        }:
            _require(value.parent_credential_revision is None)
        else:
            _core(value.parent_credential_revision, Revision, positive=True)
    elif kind is ProviderSecret:
        _field(value.client_id, ClientIdText)
        for field in (value.client_secret, value.access_token, value.refresh_token):
            _field(field, SecretText)
        _core(value.expires_at, Timestamp)
    elif kind is RefreshResult:
        _field(value.secret, ProviderSecret)
        if value.scopes is not None:
            _field(value.scopes, ScopeSet)
    elif kind is CredentialEnvelope:
        _require(type(value.version) is int)
        if value.version != 1:
            raise CredentialCodecError(ErrorCode.UNSUPPORTED_VERSION)
        for field, field_type in (
            (value.projection_id, ProjectionId),
            (value.state_instance_id, LocalId),
            (value.change_id, LocalId),
            (value.profile_verified_at, Timestamp),
        ):
            _core(field, field_type)
        for revision in (
            value.binding_revision,
            value.credential_revision,
            value.scope_policy_revision,
        ):
            _core(revision, Revision, positive=True)
        _require(type(value.role) is Role and type(value.scope_policy) is ScopePolicy)
        _field(value.account, AccountAddress)
        _field(value.grant, GrantEvidence)
        _field(value.secret, ProviderSecret)
        _require(
            value.grant.granted.value
            == policy_scopes(value.scope_policy, value.role).value
        )
        parent = value.grant.parent_credential_revision
        if parent is not None:
            _require(parent.value == value.credential_revision.value - 1)
    elif kind is AccessSnapshot:
        _require(type(value.role) is Role)
        for revision in (
            value.credential_revision,
            value.binding_revision,
            value.scope_policy_revision,
        ):
            _core(revision, Revision, positive=True)
        _field(value.access_token, SecretText)
        _core(value.expires_at, Timestamp)
    else:
        _require(False)
