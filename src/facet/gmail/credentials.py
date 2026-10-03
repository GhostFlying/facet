"""Owner-only credential/profile verification for the first Gmail consumer.

The manager intentionally stops at identity and scope verification. It does
not perform OAuth, refresh tokens, discover files, or expose a Gmail business
operation. A provider boundary is injected so offline tests exercise the same
verification path with synthetic profile facts.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from facet.config import Config
from facet.contracts import (
    BindingState,
    ErrorCode,
    LocalId,
    ProjectionId,
    Revision,
    Role,
    SourceMode,
    Timestamp,
)
from facet.db.codecs import StorageFailure

from .credential_codec import decode_envelope
from .credential_models import (
    AccountAddress,
    CredentialEnvelope,
    GrantEvidence,
    ProviderSecret,
    ScopePolicy,
    ScopeSet,
)

__all__ = (
    "ProfileEvidence",
    "ProfileReader",
    "CredentialMetadata",
    "VerifiedProfile",
    "VerifiedBindings",
    "CredentialManager",
)


def _fail(code: ErrorCode) -> None:
    raise StorageFailure(code)


@dataclass(frozen=True, slots=True, repr=False)
class ProfileEvidence:
    """Minimal provider profile result; no provider response is retained."""

    account: AccountAddress
    scopes: ScopeSet

    def __post_init__(self) -> None:
        account_ok = type(self.account) is AccountAddress
        scopes_ok = type(self.scopes) is ScopeSet
        if not account_ok or not scopes_ok:
            _fail(ErrorCode.INVALID_INPUT)

    def __repr__(self) -> str:
        return "<profile evidence>"

    __str__ = __repr__


class ProfileReader(Protocol):
    def get_profile(self, role: Role, secret: ProviderSecret) -> ProfileEvidence:
        """Read only the provider profile using the manager-owned secret."""


@dataclass(frozen=True, slots=True, repr=False)
class CredentialMetadata:
    """Credential identity and grant metadata without provider secrets."""

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

    def __post_init__(self) -> None:
        if (
            type(self.version) is not int
            or type(self.projection_id) is not ProjectionId
            or type(self.state_instance_id) is not LocalId
            or type(self.role) is not Role
            or type(self.binding_revision) is not Revision
            or type(self.credential_revision) is not Revision
            or type(self.change_id) is not LocalId
            or type(self.account) is not AccountAddress
            or type(self.scope_policy) is not ScopePolicy
            or type(self.scope_policy_revision) is not Revision
            or type(self.grant) is not GrantEvidence
            or type(self.profile_verified_at) is not Timestamp
        ):
            _fail(ErrorCode.INVALID_INPUT)

    def __repr__(self) -> str:
        return "<credential metadata>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedProfile:
    projection_id: ProjectionId
    role: Role
    account: AccountAddress
    scopes: ScopeSet
    binding_revision: Revision
    credential_revision: Revision
    verified_at: Timestamp

    def __post_init__(self) -> None:
        values = (
            self.projection_id,
            self.role,
            self.account,
            self.scopes,
            self.binding_revision,
            self.credential_revision,
            self.verified_at,
        )
        if type(self.projection_id) is not ProjectionId or type(self.role) is not Role:
            _fail(ErrorCode.INVALID_INPUT)
        account_ok = type(self.account) is AccountAddress
        scopes_ok = type(self.scopes) is ScopeSet
        if not account_ok or not scopes_ok:
            _fail(ErrorCode.INVALID_INPUT)
        if any(type(value) is not Revision for value in values[4:6]) or any(
            value.value < 1 for value in values[4:6]
        ):
            _fail(ErrorCode.INVALID_INPUT)
        if type(self.verified_at) is not Timestamp:
            _fail(ErrorCode.INVALID_INPUT)

    def __repr__(self) -> str:
        return "<verified profile>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedBindings:
    projection_id: ProjectionId
    profiles: tuple[VerifiedProfile, VerifiedProfile]

    def __post_init__(self) -> None:
        if (
            type(self.projection_id) is not ProjectionId
            or type(self.profiles) is not tuple
            or len(self.profiles) != 2
            or any(type(profile) is not VerifiedProfile for profile in self.profiles)
            or {profile.role for profile in self.profiles} != {Role.SOURCE, Role.TARGET}
            or any(
                profile.projection_id != self.projection_id for profile in self.profiles
            )
        ):
            _fail(ErrorCode.INVALID_INPUT)
        source_account = self.profiles[0].account.value.casefold()
        target_account = self.profiles[1].account.value.casefold()
        if source_account == target_account:
            _fail(ErrorCode.BINDING_MISMATCH)

    def __repr__(self) -> str:
        return "<verified bindings>"

    __str__ = __repr__


def _expected_policy(config: Config, role: Role) -> ScopePolicy:
    if role is Role.SOURCE:
        return (
            ScopePolicy.SOURCE_READONLY
            if config.projection.source_mode is SourceMode.READONLY
            else ScopePolicy.SOURCE_CONVENIENCE
        )
    return ScopePolicy.TARGET_DEFAULT


def _read_credential(path: Path, role: Role) -> CredentialEnvelope:
    try:
        parent = path.parent
        parent_info = parent.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != os.geteuid()
            or parent_info.st_mode & 0o77
        ):
            _fail(ErrorCode.SCOPE_REQUIRED)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o77
                or info.st_nlink != 1
                or info.st_size > 131072
            ):
                _fail(ErrorCode.SCOPE_REQUIRED)
            raw = os.read(descriptor, 131073)
        finally:
            os.close(descriptor)
    except FileNotFoundError:
        _fail(
            ErrorCode.SOURCE_AUTH_REQUIRED
            if role is Role.SOURCE
            else ErrorCode.TARGET_AUTH_REQUIRED
        )
    except StorageFailure:
        raise
    except OSError:
        _fail(ErrorCode.PERSISTENCE_FAILURE)
    if len(raw) > 131072:
        _fail(ErrorCode.SCOPE_REQUIRED)
    try:
        return decode_envelope(raw)
    except Exception as error:
        # CredentialCodecError carries only its closed code. Avoid retaining
        # parser/provider details in a production-facing exception.
        code = getattr(error, "code", ErrorCode.INVALID_INPUT)
        if type(code) is not ErrorCode:
            code = ErrorCode.INVALID_INPUT
        _fail(code)


class CredentialManager:
    """Load, verify and publish two fixed-role credential bindings."""

    __slots__ = ("_state_dir", "_config", "_owner")

    def __init__(
        self, state_dir: str | os.PathLike[str], config: Config, owner
    ) -> None:
        if type(config) is not Config:
            _fail(ErrorCode.INVALID_INPUT)
        if not hasattr(owner, "owner_info") or not hasattr(owner, "bindings"):
            _fail(ErrorCode.INVALID_INPUT)
        self._state_dir = Path(state_dir)
        self._config = config
        self._owner = owner

    def _path(self, role: Role) -> Path:
        if type(role) is not Role:
            _fail(ErrorCode.INVALID_INPUT)
        name = "source.json" if role is Role.SOURCE else "target.json"
        return self._state_dir / "credentials" / name

    def _load_envelope(self, role: Role) -> CredentialEnvelope:
        envelope = _read_credential(self._path(role), role)
        owner = self._owner.owner_info
        if (
            envelope.projection_id != self._config.projection.id
            or envelope.state_instance_id != owner.state_instance_id
            or envelope.role is not role
            or envelope.binding_revision.value < 1
            or envelope.credential_revision.value < 1
            or envelope.scope_policy is not _expected_policy(self._config, role)
        ):
            _fail(ErrorCode.BINDING_MISMATCH)
        binding = self._owner.bindings()[role]
        account = envelope.account.value.casefold()
        declared = binding.declared_address.value.casefold() if binding else None
        if (
            binding is None
            or envelope.binding_revision != binding.binding_revision
            or account != declared
        ):
            _fail(ErrorCode.BINDING_MISMATCH)
        expected_credential_revision = binding.credential_revision.value + (
            1 if binding.state is BindingState.VERIFICATION_PENDING else 0
        )
        if envelope.credential_revision.value != expected_credential_revision:
            _fail(ErrorCode.BINDING_MISMATCH)
        return envelope

    def load(self, role: Role) -> CredentialMetadata:
        """Read credential identity and grant metadata without secrets."""

        envelope = self._load_envelope(role)
        return CredentialMetadata(
            envelope.version,
            envelope.projection_id,
            envelope.state_instance_id,
            envelope.role,
            envelope.binding_revision,
            envelope.credential_revision,
            envelope.change_id,
            envelope.account,
            envelope.scope_policy,
            envelope.scope_policy_revision,
            envelope.grant,
            envelope.profile_verified_at,
        )

    def verify(self, reader: ProfileReader) -> VerifiedBindings:
        if not hasattr(reader, "get_profile"):
            _fail(ErrorCode.INVALID_INPUT)
        profiles = []
        for role in (Role.SOURCE, Role.TARGET):
            envelope = self._load_envelope(role)
            try:
                evidence = reader.get_profile(role, envelope.secret)
            except StorageFailure:
                raise
            except Exception:
                _fail(
                    ErrorCode.SOURCE_AUTH_REQUIRED
                    if role is Role.SOURCE
                    else ErrorCode.TARGET_AUTH_REQUIRED
                )
            if type(evidence) is not ProfileEvidence:
                _fail(ErrorCode.INVALID_INPUT)
            expected_scopes = envelope.grant.granted
            if evidence.scopes != expected_scopes:
                _fail(ErrorCode.SCOPE_REQUIRED)
            configured = (
                self._config.projection.source_email
                if role is Role.SOURCE
                else self._config.projection.target_email
            )
            if evidence.account.value.casefold() != configured.casefold():
                _fail(ErrorCode.BINDING_MISMATCH)
            profiles.append(
                VerifiedProfile(
                    self._config.projection.id,
                    role,
                    evidence.account,
                    evidence.scopes,
                    envelope.binding_revision,
                    envelope.credential_revision,
                    evidence_verified_at(evidence),
                )
            )
        return VerifiedBindings(self._config.projection.id, tuple(profiles))

    def verify_and_publish(self, reader: ProfileReader) -> VerifiedBindings:
        verified = self.verify(reader)
        self._owner.publish_verified_bindings(verified)
        return verified


def evidence_verified_at(evidence: ProfileEvidence) -> Timestamp:
    """Use a bounded UTC observation time without adding provider metadata."""

    del evidence
    from datetime import UTC, datetime

    return Timestamp(datetime.now(UTC))
