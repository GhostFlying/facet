"""Owner-only credential/profile verification for the first Gmail consumer.

The manager intentionally stops at identity and scope verification. It does
not perform OAuth, refresh tokens, discover files, or expose a Gmail business
operation. A provider boundary is injected so offline tests exercise the same
verification path with synthetic profile facts.
"""

from __future__ import annotations

import hashlib
import os
import stat
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from facet.config import Config
from facet.contracts import (
    BindingState,
    ErrorCode,
    LocalId,
    ProjectionId,
    Revision,
    Role,
    Sha256Hex,
    SourceMode,
    Timestamp,
)
from facet.db.codecs import StorageFailure

from .credential_codec import decode_envelope, encode_envelope
from .credential_models import (
    AccessSnapshot,
    AccountAddress,
    CredentialEnvelope,
    GrantEvidence,
    GrantEvidenceKind,
    ProviderSecret,
    RefreshResult,
    ScopePolicy,
    ScopeSet,
    policy_scopes,
)

__all__ = (
    "ProfileEvidence",
    "ProfileReader",
    "CredentialMetadata",
    "VerifiedProfile",
    "VerifiedBindings",
    "AccessSnapshot",
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


class _AtomicWriteFailure(StorageFailure):
    """A private file-write failure carrying replace-boundary uncertainty."""

    __slots__ = ("replaced",)

    def __init__(self, code: ErrorCode, *, replaced: bool):
        self.replaced = replaced
        super().__init__(code)


@dataclass(slots=True)
class _RefreshFlight:
    owner_thread: int
    waiters: int = 0
    done: bool = False
    result: AccessSnapshot | None = None
    error: ErrorCode | None = None


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
            chunks = []
            remaining = 131073
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
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

    __slots__ = ("_state_dir", "_config", "_owner", "_flight_condition", "_flights")

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
        self._flight_condition = threading.Condition()
        self._flights = {}

    def _path(self, role: Role) -> Path:
        if type(role) is not Role:
            _fail(ErrorCode.INVALID_INPUT)
        name = "source.json" if role is Role.SOURCE else "target.json"
        return self._state_dir / "credentials" / name

    def _load_envelope(self, role: Role) -> CredentialEnvelope:
        self._check_private_root()
        from facet.db.repositories import credentials as repository

        with self._owner.session.transaction() as uow:
            unresolved = repository.get_open_change(
                uow, self._config.projection.id, role
            )
        if unresolved is not None:
            _fail(ErrorCode.MAINTENANCE_REQUIRED)
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

    def _check_private_root(self) -> Path:
        try:
            state = self._state_dir.stat(follow_symlinks=False)
            credentials = (self._state_dir / "credentials").stat(follow_symlinks=False)
        except OSError:
            _fail(ErrorCode.PERSISTENCE_FAILURE)
        if (
            not stat.S_ISDIR(state.st_mode)
            or state.st_uid != os.geteuid()
            or stat.S_IMODE(state.st_mode) & 0o77
            or not stat.S_ISDIR(credentials.st_mode)
            or credentials.st_uid != os.geteuid()
            or stat.S_IMODE(credentials.st_mode) & 0o77
        ):
            _fail(ErrorCode.SCOPE_REQUIRED)
        return self._state_dir / "credentials"

    def _snapshot_verified(
        self,
        role: Role,
        envelope: CredentialEnvelope,
        binding,
        observed: Timestamp,
    ) -> AccessSnapshot:
        if (
            binding is None
            or binding.state is not BindingState.VERIFIED
            or binding.credential_revision != envelope.credential_revision
        ):
            _fail(ErrorCode.BINDING_PENDING)
        if envelope.secret.expires_at.value <= observed.value:
            _fail(
                ErrorCode.SOURCE_AUTH_REQUIRED
                if role is Role.SOURCE
                else ErrorCode.TARGET_AUTH_REQUIRED
            )
        return AccessSnapshot(
            role,
            envelope.credential_revision,
            envelope.binding_revision,
            envelope.scope_policy_revision,
            envelope.secret.access_token,
            envelope.secret.expires_at,
        )

    def snapshot(self, role: Role) -> AccessSnapshot:
        """Return a verified-role access token without exposing refresh material."""

        if type(role) is not Role:
            _fail(ErrorCode.INVALID_INPUT)
        envelope = self._load_envelope(role)
        binding = self._owner.bindings()[role]
        return self._snapshot_verified(role, envelope, binding, _owner_now())

    def refresh(self, role: Role, exchange):
        """Single-flight one synthetic/provider-mediated refresh and publish it."""

        if type(role) is not Role or not callable(exchange):
            _fail(ErrorCode.INVALID_INPUT)
        with self._flight_condition:
            flight = self._flights.get(role)
            if flight is not None:
                if flight.owner_thread == threading.get_ident():
                    _fail(ErrorCode.REQUEST_CONFLICT)
                flight.waiters += 1
                while not flight.done:
                    self._flight_condition.wait()
                if flight.error is not None:
                    _fail(flight.error)
                if flight.result is None:
                    _fail(ErrorCode.CONSISTENCY_FAILURE)
                return flight.result
            flight = _RefreshFlight(threading.get_ident())
            self._flights[role] = flight
        try:
            result = self._refresh_once(role, exchange)
        except StorageFailure as error:
            self._finish_flight(role, flight, error=error.code)
            raise
        except BaseException:
            self._finish_flight(role, flight, error=ErrorCode.PERSISTENCE_FAILURE)
            raise
        self._finish_flight(role, flight, result=result)
        return result

    def _finish_flight(
        self,
        role: Role,
        flight: _RefreshFlight,
        *,
        result: AccessSnapshot | None = None,
        error: ErrorCode | None = None,
    ) -> None:
        with self._flight_condition:
            flight.result = result
            flight.error = error
            flight.done = True
            self._flights.pop(role, None)
            self._flight_condition.notify_all()

    def _refresh_once(self, role: Role, exchange) -> AccessSnapshot:
        old = self._load_envelope(role)
        binding = self._owner.bindings()[role]
        if (
            binding is None
            or binding.state is not BindingState.VERIFIED
            or binding.credential_revision != old.credential_revision
        ):
            _fail(ErrorCode.BINDING_PENDING)
        observed = _owner_now()
        new_revision = Revision(old.credential_revision.value + 1)
        change_id = LocalId(uuid4().hex)
        from facet.db.models import CredentialChangeRow
        from facet.db.repositories import credentials as repository

        requesting = CredentialChangeRow(
            self._config.projection.id,
            old.state_instance_id,
            change_id,
            role,
            "refresh",
            "requesting",
            old.credential_revision,
            new_revision,
            old.binding_revision,
            old.scope_policy_revision,
            None,
            None,
            None,
            old.scope_policy.value,
            None,
            None,
            None,
            None,
            old.profile_verified_at,
            old.secret.expires_at,
            observed,
            observed,
            None,
        )
        with self._owner.session.transaction() as uow:
            repository.begin_change(uow, self._config.projection.id, requesting)
        published = False
        try:
            try:
                refreshed = exchange(role, old.secret)
            except StorageFailure:
                raise
            except Exception:
                _fail(
                    ErrorCode.SOURCE_AUTH_REQUIRED
                    if role is Role.SOURCE
                    else ErrorCode.TARGET_AUTH_REQUIRED
                )
            explicit_scopes = None
            if type(refreshed) is RefreshResult:
                refreshed_secret = refreshed.secret
                explicit_scopes = refreshed.scopes
            elif type(refreshed) is ProviderSecret:
                refreshed_secret = refreshed
            else:
                _fail(ErrorCode.INVALID_INPUT)
            expected_scopes = policy_scopes(old.scope_policy, role)
            if explicit_scopes is not None and explicit_scopes != expected_scopes:
                _fail(ErrorCode.SCOPE_REQUIRED)
            if refreshed_secret.expires_at.value <= observed.value:
                _fail(
                    ErrorCode.SOURCE_AUTH_REQUIRED
                    if role is Role.SOURCE
                    else ErrorCode.TARGET_AUTH_REQUIRED
                )
            candidate = replace(
                old,
                credential_revision=new_revision,
                change_id=change_id,
                grant=GrantEvidence(
                    (
                        GrantEvidenceKind.REFRESH_EXPLICIT
                        if explicit_scopes is not None
                        else GrantEvidenceKind.REFRESH_OMITTED_INHERITED
                    ),
                    expected_scopes
                    if explicit_scopes is not None
                    else old.grant.granted,
                    expected_scopes
                    if explicit_scopes is not None
                    else old.grant.requested,
                    observed,
                    old.credential_revision,
                ),
                profile_verified_at=old.profile_verified_at,
                secret=refreshed_secret,
            )
            raw = encode_envelope(candidate)
            digest = Sha256Hex(hashlib.sha256(raw).hexdigest())
            validated = replace(
                requesting,
                phase="validated",
                envelope_digest=digest,
                grant_kind=candidate.grant.kind.value,
                granted_scopes=",".join(
                    sorted(scope.value for scope in candidate.grant.granted.value)
                ),
                grant_parent_revision=candidate.grant.parent_credential_revision,
                grant_observed_at=candidate.grant.observed_at,
                profile_verified_at=candidate.profile_verified_at,
                expires_at=candidate.secret.expires_at,
                updated_at=observed,
            )
            with self._owner.session.transaction() as uow:
                repository.mark_validated(uow, self._config.projection.id, validated)
            try:
                _atomic_write(self._path(role), raw)
            except _AtomicWriteFailure as error:
                published = error.replaced
                raise
            published = True
            with self._owner.session.transaction() as uow:
                repository.commit_change(uow, self._config.projection.id, validated)
            return self._snapshot_verified(
                role, candidate, self._owner.bindings()[role], observed
            )
        except StorageFailure as error:
            if published:
                self._attention(role, change_id, error.code)
            else:
                self._abandon(role, change_id, error.code)
            raise

    def _abandon(self, role: Role, change_id: LocalId, code: ErrorCode) -> None:
        from facet.db.repositories import credentials as repository

        try:
            with self._owner.session.transaction() as uow:
                repository.abandon_change(
                    uow, self._config.projection.id, role, change_id, code
                )
        except StorageFailure:
            # The original failure remains authoritative; an unavailable
            # owner/database is already a durable stop condition.
            return

    def _attention(self, role: Role, change_id: LocalId, code: ErrorCode) -> None:
        from facet.db.repositories import credentials as repository

        try:
            with self._owner.session.transaction() as uow:
                repository.mark_attention(
                    uow, self._config.projection.id, role, change_id, code
                )
        except StorageFailure:
            # Preserve the original commit uncertainty.  If the owner is
            # unavailable, the validated row itself remains the restart cue.
            return

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
    return _owner_now()


def _owner_now() -> Timestamp:
    return Timestamp(datetime.now(UTC))


def _atomic_write(path: Path, raw: bytes) -> None:
    if type(raw) is not bytes or not raw:
        _fail(ErrorCode.INVALID_INPUT)
    parent = path.parent
    replaced = False
    try:
        parent_info = parent.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != os.geteuid()
            or stat.S_IMODE(parent_info.st_mode) & 0o77
        ):
            _fail(ErrorCode.SCOPE_REQUIRED)
        try:
            target = path.lstat()
        except FileNotFoundError:
            target = None
        if target is not None and (
            not stat.S_ISREG(target.st_mode)
            or target.st_uid != os.geteuid()
            or stat.S_IMODE(target.st_mode) & 0o77
            or target.st_nlink != 1
        ):
            _fail(ErrorCode.SCOPE_REQUIRED)
        temp = parent / ("." + path.name + ".pending")
        descriptor = os.open(
            temp,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(descriptor, raw[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.replace(temp, path)
        except OSError:
            # A failed rename may have reached the filesystem before reporting
            # an error. Treat the boundary as uncertain and reconcile later.
            raise _AtomicWriteFailure(
                ErrorCode.PERSISTENCE_FAILURE, replaced=True
            ) from None
        replaced = True
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except _AtomicWriteFailure:
        raise
    except StorageFailure:
        raise
    except FileExistsError:
        raise _AtomicWriteFailure(
            ErrorCode.PERSISTENCE_FAILURE, replaced=replaced
        ) from None
    except OSError:
        raise _AtomicWriteFailure(
            ErrorCode.PERSISTENCE_FAILURE, replaced=replaced
        ) from None
