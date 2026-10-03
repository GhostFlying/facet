"""Small production state owner built on the shipped v2 storage initializer.

This module owns the narrow lifetime needed by the first projection consumer:
the private state directory, the existing owner lock, and one initialized
SQLite writer session. It does not implement a daemon, IPC, or a second
runtime protocol.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from facet.config import Config
from facet.contracts import (
    BindingState,
    Count,
    ErrorCode,
    LocalId,
    ProjectionId,
    RestoreState,
    Revision,
    Role,
    Sha256Hex,
    Timestamp,
)
from facet.db.codecs import PrivateAddress, StorageFailure
from facet.db.command_records import (
    BootstrapCommand,
    BootstrapOperationSeed,
    FreshCommandBootstrap,
)
from facet.db.connection import (
    WriterSession,
    _begin_owner_session_v2,
    _configure_writer,
    _initialize_database_v2,
)
from facet.db.models import (
    BindingRow,
    BootstrapInitContext,
    OwnerSessionInfo,
    ProjectionRow,
    RulesetRow,
)
from facet.runtime import locks, private_root

if TYPE_CHECKING:
    from facet.gmail.credentials import VerifiedBindings

__all__ = ("StateOwner",)


def _invalid(code: ErrorCode = ErrorCode.INVALID_INPUT) -> None:
    raise StorageFailure(code)


def _new_id() -> LocalId:
    return LocalId(uuid4().hex)


def _timestamp() -> Timestamp:
    return Timestamp(datetime.now(UTC))


def _check_directory(path: Path, *, create: bool) -> None:
    try:
        if create:
            path.mkdir(mode=0o700)
        info = path.stat(follow_symlinks=False)
    except (FileExistsError, OSError):
        _invalid(ErrorCode.MAINTENANCE_REQUIRED)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o77
    ):
        _invalid(ErrorCode.SCOPE_REQUIRED)


def _check_file(path: Path) -> None:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        _invalid(ErrorCode.MAINTENANCE_REQUIRED)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o77
        or info.st_nlink != 1
    ):
        _invalid(ErrorCode.SCOPE_REQUIRED)


def _open_database(path: Path, *, create: bool) -> sqlite3.Connection:
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        _invalid(ErrorCode.MAINTENANCE_REQUIRED)
    except OSError:
        _invalid(ErrorCode.PERSISTENCE_FAILURE)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o77
            or info.st_nlink != 1
        ):
            _invalid(ErrorCode.SCOPE_REQUIRED)
    finally:
        os.close(descriptor)
    try:
        return sqlite3.connect(path, autocommit=True)
    except sqlite3.Error:
        _invalid(ErrorCode.PERSISTENCE_FAILURE)


def _seed(
    owner: OwnerSessionInfo,
    config_bytes: bytes,
    now: Timestamp,
    bootstrap_nonce: LocalId,
) -> FreshCommandBootstrap:
    digest = Sha256Hex(hashlib.sha256(config_bytes).hexdigest())
    seed = BootstrapOperationSeed(
        _new_id(),
        owner.request_namespace,
        bootstrap_nonce,
        BootstrapCommand.FACET_INIT,
        1,
        digest,
        digest,
        digest,
        now,
        now,
        Revision(0),
        Revision(0),
        True,
        False,
    )
    return FreshCommandBootstrap(seed, None)


class StateOwner:
    """One initialized production writer and its private ownership lease."""

    __slots__ = (
        "_state_dir",
        "_database_path",
        "_runtime_path",
        "_root",
        "_owner_lease",
        "_connection",
        "_session",
        "_config",
        "_info",
        "_closed",
    )

    def __init__(
        self,
        state_dir: Path,
        database_path: Path,
        runtime_path: Path,
        root,
        owner_lease,
        connection: sqlite3.Connection,
        session: WriterSession,
        config: Config,
        info: OwnerSessionInfo,
    ) -> None:
        self._state_dir = state_dir
        self._database_path = database_path
        self._runtime_path = runtime_path
        self._root = root
        self._owner_lease = owner_lease
        self._connection = connection
        self._session = session
        self._config = config
        self._info = info
        self._closed = False

    @classmethod
    def create(
        cls, state_dir: str | os.PathLike[str], config: Config, config_bytes: bytes
    ) -> StateOwner:
        if type(config) is not Config or type(config_bytes) is not bytes:
            _invalid()
        state = Path(state_dir)
        _check_directory(state, create=True)
        runtime = state / "runtime-locks"
        credentials = state / "credentials"
        _check_directory(credentials, create=True)
        _check_directory(runtime, create=True)
        root = owner_lease = connection = None
        try:
            root = private_root.create_lock_root(str(runtime))
            owner_lease = locks.acquire_owner(root)
            database = state / "facet.db"
            connection = _open_database(database, create=True)
            now = _timestamp()
            info = OwnerSessionInfo(_new_id(), _new_id(), _new_id())
            projection = ProjectionRow(
                config.projection.id,
                Count(1),
                info.state_instance_id,
                info.request_namespace,
                Revision(0),
                Revision(0),
                config.projection.source_mode,
                BindingState.VERIFICATION_PENDING,
                RestoreState.NORMAL,
                True,
                info.owner_run_id,
                now,
            )
            bindings = tuple(
                BindingRow(
                    config.projection.id,
                    role,
                    PrivateAddress(
                        config.projection.source_email
                        if role is Role.SOURCE
                        else config.projection.target_email
                    ),
                    None,
                    Revision(0),
                    Revision(1),
                    BindingState.VERIFICATION_PENDING,
                    None,
                )
                for role in Role
            )
            bootstrap_nonce = _new_id()
            session = _initialize_database_v2(
                connection,
                bootstrap=BootstrapInitContext(info, bootstrap_nonce),
                initial_projection=projection,
                source_binding=bindings[0],
                target_binding=bindings[1],
                initial_ruleset=RulesetRow(
                    config.projection.id, Revision(0), now, True
                ),
                commands=_seed(info, config_bytes, now, bootstrap_nonce),
            )
            return cls(
                state,
                database,
                runtime,
                root,
                owner_lease,
                connection,
                session,
                config,
                info,
            )
        except BaseException:
            if connection is not None:
                with suppress(BaseException):
                    connection.close()
            if owner_lease is not None:
                with suppress(BaseException):
                    locks.release_lock(owner_lease)
            if root is not None:
                with suppress(BaseException):
                    private_root.close_root(root)
            raise

    @classmethod
    def open(cls, state_dir: str | os.PathLike[str], config: Config) -> StateOwner:
        if type(config) is not Config:
            _invalid()
        state = Path(state_dir)
        _check_directory(state, create=False)
        runtime = state / "runtime-locks"
        credentials = state / "credentials"
        _check_directory(runtime, create=False)
        _check_directory(credentials, create=False)
        database = state / "facet.db"
        _check_file(database)
        root = owner_lease = connection = None
        try:
            root = private_root.open_existing_root(str(runtime))
            owner_lease = locks.acquire_owner(root)
            connection = _open_database(database, create=False)
            _configure_writer(connection, creating=False)
            try:
                row = connection.execute(
                    "SELECT projection_id,state_instance_id,request_namespace,"
                    "last_owner_run_id FROM projections LIMIT 2"
                ).fetchall()
            except sqlite3.Error:
                _invalid(ErrorCode.DATABASE_UNAVAILABLE)
            if (
                len(row) != 1
                or row[0][0] != config.projection.id.value
                or row[0][3] is None
            ):
                _invalid(ErrorCode.MAINTENANCE_REQUIRED)
            try:
                bindings = connection.execute(
                    "SELECT role,declared_address FROM bindings "
                    "WHERE projection_id=? ORDER BY role",
                    (config.projection.id.value,),
                ).fetchall()
            except sqlite3.Error:
                _invalid(ErrorCode.DATABASE_UNAVAILABLE)
            expected_bindings = [
                (Role.SOURCE.value, config.projection.source_email),
                (Role.TARGET.value, config.projection.target_email),
            ]
            if bindings != expected_bindings:
                _invalid(ErrorCode.BINDING_MISMATCH)
            info = OwnerSessionInfo(_new_id(), LocalId(row[0][1]), LocalId(row[0][2]))
            session = _begin_owner_session_v2(
                connection,
                owner=info,
                expected_previous_run=LocalId(row[0][3]),
                now=_timestamp(),
            )
            return cls(
                state,
                database,
                runtime,
                root,
                owner_lease,
                connection,
                session,
                config,
                info,
            )
        except BaseException:
            if connection is not None:
                with suppress(BaseException):
                    connection.close()
            if owner_lease is not None:
                with suppress(BaseException):
                    locks.release_lock(owner_lease)
            if root is not None:
                with suppress(BaseException):
                    private_root.close_root(root)
            raise

    @property
    def state_dir(self) -> Path:
        return self._state_dir

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def projection_id(self) -> ProjectionId:
        return self._config.projection.id

    @property
    def owner_info(self) -> OwnerSessionInfo:
        return self._info

    @property
    def config(self) -> Config:
        return self._config

    @property
    def session(self) -> WriterSession:
        if self._closed:
            _invalid(ErrorCode.OWNER_UNAVAILABLE)
        return self._session

    def bindings(self):
        from facet.db.repositories import reads

        with self.session.transaction() as uow:
            return {
                role: reads.get_binding(uow, self.projection_id, role) for role in Role
            }

    def publish_verified_bindings(self, verified: VerifiedBindings):
        if self._closed:
            _invalid(ErrorCode.OWNER_UNAVAILABLE)
        from facet.db.repositories.bindings import verify_bindings

        with self.session.transaction() as uow:
            return verify_bindings(uow, self.projection_id, verified)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._session.close()
        finally:
            try:
                locks.release_lock(self._owner_lease)
            finally:
                private_root.close_root(self._root)

    def __enter__(self) -> StateOwner:
        if self._closed:
            _invalid(ErrorCode.OWNER_UNAVAILABLE)
        return self

    def __exit__(self, exception_type, exception, traceback) -> bool:
        self.close()
        return False
