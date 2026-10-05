"""Small production state owner built on the shipped v2 storage initializer.

This module owns the narrow lifetime needed by the first projection consumer:
the private state directory, the existing owner lock, and one initialized
SQLite writer session. It does not implement a daemon, IPC, or a second
runtime protocol.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import stat
from contextlib import contextmanager, suppress
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
from facet.db.codecs import PrivateAddress, StorageFailure, timestamp_to_sql
from facet.db.command_records import (
    BootstrapCommand,
    BootstrapOperationSeed,
    FreshCommandBootstrap,
    RequestId,
)
from facet.db.connection import (
    WriterSession,
    _begin_owner_session_v2,
    _configure_writer,
    _initialize_database_v2,
    _inspect_bootstrap_v2,
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


def _backup_write(path: Path, content: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _backup_fsync(path: Path, *, directory: bool = False) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | os.O_NOFOLLOW
        | os.O_CLOEXEC
        | (os.O_DIRECTORY if directory else 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _request_parts(request_id: str | None) -> tuple[LocalId, LocalId]:
    if request_id is None:
        return _new_id(), _new_id()
    try:
        parsed = RequestId(request_id)
        _, namespace, nonce = parsed.value.split("_")
        return LocalId(namespace), LocalId(nonce)
    except (TypeError, ValueError):
        _invalid(ErrorCode.INVALID_INPUT)


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
        cls,
        state_dir: str | os.PathLike[str],
        config: Config,
        config_bytes: bytes,
        request_id: str | None = None,
    ) -> StateOwner:
        if type(config) is not Config or type(config_bytes) is not bytes:
            _invalid()
        request_namespace, bootstrap_nonce = _request_parts(request_id)
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
            info = OwnerSessionInfo(_new_id(), _new_id(), request_namespace)
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
    @contextmanager
    def inspect_initialization(
        cls,
        state_dir: str | os.PathLike[str],
        projection_id: ProjectionId,
        request_id: str,
    ):
        """Inspect a stopped bootstrap journal while holding the owner lock."""
        if type(projection_id) is not ProjectionId:
            _invalid()
        request_namespace, nonce = _request_parts(request_id)
        state = Path(state_dir)
        _check_directory(state, create=False)
        runtime = state / "runtime-locks"
        credentials = state / "credentials"
        _check_directory(runtime, create=False)
        _check_directory(credentials, create=False)
        database = state / "facet.db"
        _check_file(database)
        root = lease = connection = None
        try:
            root = private_root.open_existing_root(str(runtime))
            lease = locks.acquire_owner(root)
            connection = _open_database(database, create=False)
            _configure_writer(connection, creating=False)
            try:
                inspection = _inspect_bootstrap_v2(
                    connection,
                    projection_id=projection_id,
                    namespace=request_namespace,
                    nonce=nonce,
                    prior_config_nonce=None,
                )
            except StorageFailure as error:
                if error.code is ErrorCode.REQUEST_LINEAGE_MISMATCH:
                    _invalid(ErrorCode.REQUEST_CONFLICT)
                raise
            # Keep the same owner lease through digest validation and config
            # publication, including incomplete-init replay.
            yield inspection
        finally:
            if connection is not None:
                with suppress(BaseException):
                    connection.close()
            if lease is not None:
                with suppress(BaseException):
                    locks.release_lock(lease)
            if root is not None:
                with suppress(BaseException):
                    private_root.close_root(root)

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

    def verify_config_artifact(self, config_bytes: bytes) -> None:
        """Verify the locked state's canonical bootstrap artifact digest."""
        if type(config_bytes) is not bytes:
            _invalid()
        digest = hashlib.sha256(config_bytes).hexdigest()
        try:
            rows = self._connection.execute(
                "SELECT b.config_artifact_digest "
                "FROM operation_bootstrap b "
                "JOIN operations o ON o.projection_id=b.projection_id "
                "AND o.operation_id=b.operation_id "
                "WHERE b.projection_id=? AND o.command=? "
                "AND o.state=? LIMIT 2",
                (
                    self._config.projection.id.value,
                    BootstrapCommand.FACET_INIT.value,
                    "completed",
                ),
            ).fetchall()
        except sqlite3.Error:
            _invalid(ErrorCode.DATABASE_UNAVAILABLE)
        if len(rows) != 1:
            _invalid(ErrorCode.MAINTENANCE_REQUIRED)
        if rows[0][0] != digest:
            _invalid(ErrorCode.REQUEST_CONFLICT)

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

    def ensure_action_label_schema(
        self, request_id: LocalId, config_bytes: bytes
    ) -> None:
        """Upgrade an owned v2 database to the closed v3 label catalogue."""
        from facet.db.migrations import (
            _FRESH_V2_MANIFEST,
            _FRESH_V3_MANIFEST,
            FRESH_V3_CHECKSUMS,
            FRESH_V3_REGISTRY,
            FRESH_V3_REGISTRY_DIGEST,
        )
        from facet.db.schema import _inspect_manifest

        if type(request_id) is not LocalId or type(config_bytes) is not bytes:
            _invalid(ErrorCode.INVALID_INPUT)
        self.session._check()
        self.session._check_lineage()
        self.verify_config_artifact(config_bytes)
        connection = self._connection
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 3:
            _inspect_manifest(connection, _FRESH_V3_MANIFEST)
            return
        if version != 2:
            _invalid(ErrorCode.MAINTENANCE_REQUIRED)
        _inspect_manifest(connection, _FRESH_V2_MANIFEST)
        backup_root = self._state_dir / "backups"
        bundle = backup_root / f"action-label-v3-{request_id.value}"
        temporary = backup_root / f".action-label-v3-{request_id.value}.tmp"
        created_temporary = False
        try:
            if not backup_root.exists():
                backup_root.mkdir(mode=0o700)
            _check_directory(backup_root, create=False)
            if bundle.exists() or temporary.exists():
                _invalid(ErrorCode.REQUEST_CONFLICT)
            temporary.mkdir(mode=0o700)
            created_temporary = True
            _backup_write(temporary / "config.yaml", config_bytes)
            _check_directory(self._state_dir / "credentials", create=False)
            for name in ("source.json", "target.json"):
                source = self._state_dir / "credentials" / name
                role = "source" if name == "source.json" else "target"
                if not source.exists() and not source.is_symlink():
                    revision = connection.execute(
                        "SELECT credential_revision FROM bindings "
                        "WHERE projection_id=? AND role=?",
                        (self.projection_id.value, role),
                    ).fetchone()
                    if revision != (0,):
                        _invalid(ErrorCode.MAINTENANCE_REQUIRED)
                    continue
                _check_file(source)
                descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                try:
                    before = os.fstat(descriptor)
                    if before != source.lstat() or before.st_size > 1048576:
                        _invalid(ErrorCode.SCOPE_REQUIRED)
                    with os.fdopen(descriptor, "rb", closefd=False) as stream:
                        content = stream.read(1048577)
                    if len(content) > 1048576 or os.fstat(descriptor) != before:
                        _invalid(ErrorCode.SCOPE_REQUIRED)
                finally:
                    os.close(descriptor)
                _backup_write(temporary / name, content)
            _backup_write(temporary / "facet.db", b"")
            snapshot = sqlite3.connect(temporary / "facet.db", autocommit=True)
            try:
                connection.backup(snapshot)
                _inspect_manifest(snapshot, _FRESH_V2_MANIFEST)
            finally:
                snapshot.close()
            _backup_fsync(temporary / "facet.db")
            _backup_fsync(temporary, directory=True)
            os.replace(temporary, bundle)
            created_temporary = False
            _backup_fsync(backup_root, directory=True)
        except BaseException:
            if created_temporary:
                shutil.rmtree(temporary)
            raise
        commit_attempted = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            _inspect_manifest(connection, _FRESH_V2_MANIFEST)
            for statement in FRESH_V3_REGISTRY[-1][2]:
                connection.execute(statement)
            created = connection.execute(
                "SELECT created_at FROM schema_metadata WHERE singleton=1"
            ).fetchone()[0]
            connection.execute("DELETE FROM schema_metadata WHERE singleton=1")
            connection.execute(
                "INSERT INTO schema_metadata VALUES(1,3,?,?)",
                (FRESH_V3_REGISTRY_DIGEST, created),
            )
            connection.execute(
                "INSERT INTO schema_migrations VALUES(3,?,?,?)",
                ("v0003", FRESH_V3_CHECKSUMS[-1], timestamp_to_sql(_timestamp())),
            )
            connection.execute("PRAGMA user_version=3")
            _inspect_manifest(connection, _FRESH_V3_MANIFEST)
            commit_attempted = True
            connection.execute("COMMIT")
        except BaseException:
            if not commit_attempted and connection.in_transaction:
                connection.execute("ROLLBACK")
            if commit_attempted:
                self.session._invalidate()
            raise

    def bindings(self):
        from facet.db.repositories import reads

        with self.session.transaction() as uow:
            return {
                role: reads.get_binding(uow, self.projection_id, role) for role in Role
            }

    def publish_verified_bindings(self, verified: VerifiedBindings):
        if self._closed:
            _invalid(ErrorCode.OWNER_UNAVAILABLE)
        from facet.gmail.credentials import VerifiedBindings

        if type(verified) is not VerifiedBindings:
            _invalid(ErrorCode.INVALID_INPUT)
        from facet.db.repositories.bindings import verify_bindings

        with self.session.transaction() as uow:
            return verify_bindings(uow, self.projection_id, verified)

    def publish_verified_profile(self, profile):
        """Publish one role's verified profile without marking readiness early."""

        from facet.gmail.credentials import VerifiedProfile

        if type(profile) is not VerifiedProfile:
            _invalid(ErrorCode.INVALID_INPUT)
        from facet.db.repositories.bindings import verify_profile

        with self.session.transaction() as uow:
            return verify_profile(uow, self.projection_id, profile)

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
