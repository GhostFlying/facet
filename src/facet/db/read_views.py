"""Private read admission bridge, not an opener or production view provider.

Both compiled inventories are deliberately empty. A future reviewed M1-03
producer supplies genuine bootstrap/runtime/OS ownership; metadata and opaque
class names never stand in for that lifecycle. Tests use an isolated producer,
not a shipped plug-in or an environment/config registration switch.
"""

import os
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from threading import current_thread
from types import FunctionType

from facet.contracts import ErrorCode, LocalId, Sha256Hex

from .codecs import StorageFailure, invalid, sqlite_failure


class ViewMode(StrEnum):
    STOPPED_CLEAN = "stopped_clean"
    LIVE_WAL = "live_wal"


@dataclass(frozen=True, slots=True, repr=False)
class FileIdentity:
    device: int
    inode: int
    uid: int
    mode: int

    def __post_init__(self):
        if any(
            type(v) is not int or v < 0
            for v in (self.device, self.inode, self.uid, self.mode)
        ):
            invalid()

    def __repr__(self):
        return "FileIdentity()"


@dataclass(frozen=True, slots=True, repr=False)
class ReadRuntimeIdentity:
    python_version: tuple[int, int, int]
    sqlite_version: tuple[int, int, int]
    sqlite_source_id: str
    compile_options_digest: Sha256Hex
    architecture: str
    platform: str
    vfs: str

    def __post_init__(self):
        for version in (self.python_version, self.sqlite_version):
            if (
                type(version) is not tuple
                or len(version) != 3
                or any(type(v) is not int or v < 0 for v in version)
            ):
                invalid()
        source = self.sqlite_source_id
        if (
            type(source) is not str
            or not source
            or len(source) > 256
            or any(ord(c) < 32 or ord(c) > 126 for c in source)
            or type(self.compile_options_digest) is not Sha256Hex
            or type(self.architecture) is not str
            or self.architecture not in {"x86_64", "aarch64"}
            or type(self.platform) is not str
            or self.platform != "linux"
            or type(self.vfs) is not str
            or self.vfs != "unix"
        ):
            invalid()

    def __repr__(self):
        return "ReadRuntimeIdentity()"


class _Opaque:
    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        invalid()

    def __setattr__(self, name, value):
        invalid()

    def __reduce_ex__(self, protocol):
        invalid()

    def __repr__(self):
        return type(self).__name__ + "()"


class ReadProcessSeal(_Opaque):
    __slots__ = (
        "provider",
        "runtime",
        "creator_pid",
        "creator_thread",
        "invalidated",
        "leases",
        "permits",
    )


class ReadViewLease(_Opaque):
    __slots__ = (
        "seal",
        "mode",
        "db_identity",
        "wal_identity",
        "shm_identity",
        "creator_pid",
        "creator_thread",
        "active",
    )

    def check(self):
        _check_lease(self)

    def close(self):
        _release_lease(self)


class ReadViewPermit(_Opaque):
    __slots__ = (
        "connection",
        "expected_instance",
        "lease",
        "seal",
        "creator_pid",
        "creator_thread",
        "phase",
    )


_PROVIDER_TYPES: tuple[type, ...] = ()
_QUALIFIED_RUNTIMES: tuple[ReadRuntimeIdentity, ...] = ()
_REGISTRY_PID = os.getpid()
_SEALS: set[ReadProcessSeal] = set()
_LEASES: set[ReadViewLease] = set()
_PERMITS: set[ReadViewPermit] = set()
_ISSUED_PIDS: set[int] = set()


def _unavailable():
    raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)


def _allocate(cls, **values):
    result = object.__new__(cls)
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


def _creator(obj):
    if (
        os.getpid() != _REGISTRY_PID
        or obj.creator_pid != os.getpid()
        or obj.creator_thread is not current_thread()
    ):
        _unavailable()


def _provider_type(provider):
    if not any(type(provider) is cls for cls in _PROVIDER_TYPES):
        _unavailable()
    return type(provider)


def _call(provider, name, *args):
    cls = _provider_type(provider)
    method = vars(cls).get(name)
    if type(method) is not FunctionType:
        _unavailable()
    try:
        result = method(provider, *args)
        if name != "_acquire_lease" and result is not None:
            invalid()
        return result
    except StorageFailure as error:
        # A registered producer still must not leak exception context or a
        # subclass's arbitrary provider payload through the database boundary.
        code = (
            error.code
            if type(error) is StorageFailure
            else ErrorCode.CONSISTENCY_FAILURE
        )
        raise StorageFailure(code) from None
    except Exception:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None


def _check_seal(seal):
    if type(seal) is not ReadProcessSeal or seal not in _SEALS:
        _unavailable()
    _creator(seal)
    if seal.invalidated:
        _unavailable()
    _provider_type(seal.provider)


def _invalidate(seal):
    object.__setattr__(seal, "invalidated", True)


def _issue_read_seal(provider: object, runtime: ReadRuntimeIdentity) -> ReadProcessSeal:
    if type(runtime) is not ReadRuntimeIdentity:
        invalid()
    _provider_type(provider)
    if os.getpid() != _REGISTRY_PID or os.getpid() in _ISSUED_PIDS:
        _unavailable()
    if not any(
        type(r) is ReadRuntimeIdentity and r == runtime for r in _QUALIFIED_RUNTIMES
    ):
        raise StorageFailure(ErrorCode.UNSUPPORTED_VERSION)
    _call(provider, "_check_bootstrap", runtime)
    # This provider's latch was consumed. Even allocation failure must not give
    # the process another final-seal attempt.
    _ISSUED_PIDS.add(os.getpid())
    seal = _allocate(
        ReadProcessSeal,
        provider=provider,
        runtime=runtime,
        creator_pid=os.getpid(),
        creator_thread=current_thread(),
        invalidated=False,
        leases=set(),
        permits=set(),
    )
    _SEALS.add(seal)
    return seal


def _issue_read_lease(seal: ReadProcessSeal, mode: ViewMode) -> ReadViewLease:
    _check_seal(seal)
    if type(mode) is not ViewMode:
        invalid()
    lease = _allocate(
        ReadViewLease,
        seal=seal,
        mode=mode,
        db_identity=None,
        wal_identity=None,
        shm_identity=None,
        creator_pid=os.getpid(),
        creator_thread=current_thread(),
        active=False,
    )
    acquired = False
    try:
        identities = _call(seal.provider, "_acquire_lease", lease, mode)
        acquired = True
        if (
            type(identities) is not tuple
            or len(identities) != 3
            or type(identities[0]) is not FileIdentity
            or mode is ViewMode.STOPPED_CLEAN
            and any(v is not None for v in identities[1:])
            or mode is ViewMode.LIVE_WAL
            and any(type(v) is not FileIdentity for v in identities[1:])
        ):
            invalid()
        for name, value in zip(
            ("db_identity", "wal_identity", "shm_identity"), identities, strict=True
        ):
            object.__setattr__(lease, name, value)
        object.__setattr__(lease, "active", True)
        seal.leases.add(lease)
        _LEASES.add(lease)
        return lease
    except StorageFailure:
        _invalidate(seal)
        if acquired:
            _call(seal.provider, "_release_lease", lease)
        # Before a successful return, partial acquisition cleanup is the fixed
        # provider's obligation; do not release somebody else's descriptors.
        raise


def _check_lease(lease):
    if type(lease) is not ReadViewLease or lease not in _LEASES:
        _unavailable()
    _creator(lease)
    _check_seal(lease.seal)
    if not lease.active or lease not in lease.seal.leases:
        _unavailable()
    try:
        _call(lease.seal.provider, "_check_lease", lease)
    except StorageFailure:
        _invalidate(lease.seal)
        raise


def _bind_read_view(
    connection: sqlite3.Connection,
    expected_instance: LocalId,
    lease: ReadViewLease,
    seal: ReadProcessSeal,
) -> ReadViewPermit:
    if (
        type(connection) is not sqlite3.Connection
        or type(expected_instance) is not LocalId
    ):
        invalid()
    _check_seal(seal)
    _check_lease(lease)
    if lease.seal is not seal or any(p.lease is lease for p in seal.permits):
        _unavailable()
    # Rejection before claim does not adopt this caller's connection ownership.
    _call(seal.provider, "_claim_connection", connection, lease)
    try:
        permit = _allocate(
            ReadViewPermit,
            connection=connection,
            expected_instance=expected_instance,
            lease=lease,
            seal=seal,
            creator_pid=os.getpid(),
            creator_thread=current_thread(),
            phase="bound",
        )
        seal.permits.add(permit)
        _PERMITS.add(permit)
        return permit
    except Exception:
        _invalidate(seal)
        try:
            connection.close()
            _call(seal.provider, "_closed_connection", connection, lease)
            _release_lease(lease)
        except (sqlite3.Error, StorageFailure):
            pass
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None


def _validate_permit(permit):
    if type(permit) is not ReadViewPermit or permit not in _PERMITS:
        _unavailable()
    _creator(permit)
    if permit not in permit.seal.permits or permit.phase not in {"bound", "attached"}:
        _unavailable()
    _check_lease(permit.lease)


def _consume_permit(permit, connection, expected_instance):
    _validate_permit(permit)
    if (
        permit.phase != "bound"
        or permit.connection is not connection
        or type(expected_instance) is not LocalId
        or permit.expected_instance != expected_instance
    ):
        _unavailable()
    object.__setattr__(permit, "phase", "attached")


def _check_permit(permit):
    _validate_permit(permit)
    if permit.phase != "attached":
        _unavailable()


def _release_lease(lease):
    if type(lease) is not ReadViewLease or lease not in _LEASES:
        _unavailable()
    _creator(lease)
    if not lease.active or any(p.lease is lease for p in lease.seal.permits):
        _unavailable()
    try:
        _call(lease.seal.provider, "_release_lease", lease)
    except StorageFailure:
        _invalidate(lease.seal)
        raise
    object.__setattr__(lease, "active", False)
    lease.seal.leases.remove(lease)
    _LEASES.remove(lease)


def _close_permit(permit):
    # Cleanup may follow a failed OS check. Never require a still-healthy lease
    # to close the connection we actually own; do require its enrolled creator.
    if type(permit) is not ReadViewPermit or permit not in _PERMITS:
        _unavailable()
    _creator(permit)
    try:
        permit.connection.close()
        _call(
            permit.seal.provider, "_closed_connection", permit.connection, permit.lease
        )
    except (sqlite3.Error, StorageFailure) as error:
        _invalidate(permit.seal)
        if isinstance(error, sqlite3.Error):
            raise sqlite_failure(error) from None
        raise
    object.__setattr__(permit, "phase", "closed")
    permit.seal.permits.remove(permit)
    _PERMITS.remove(permit)
    _release_lease(permit.lease)
