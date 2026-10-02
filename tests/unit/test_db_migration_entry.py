"""MG01–09: real private files, complete test bundle and native SQLite faults.

The static participant below is test-only. It neither registers a shipping
provider nor claims the pending production stopped-preflight/M6 bundle gate.
"""

import fcntl
import hashlib
import json
import os
import select
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack, contextmanager
from dataclasses import fields, replace
from pathlib import Path

import pytest
from test_db_mappings import inserted, verify
from test_db_schema import create_state, lid

from facet.contracts import ErrorCode, Revision, Sha256Hex
from facet.db import migration_entry as engine
from facet.db.codecs import SchemaVersion, StorageFailure
from facet.db.migrations import _CURRENT_MANIFEST, _ExistingStep, _SchemaManifest, v0001
from facet.db.models import (
    DatabaseSnapshotInfo,
    MigrationBackupReceipt,
    MigrationResult,
    MigrationState,
    OwnerSessionInfo,
)
from facet.runtime import locks, private_root

SQL = (
    "CREATE INDEX migration_rule_effective_test ON "
    "rule_revisions(projection_id,effective_at)"
)
STEP_HASH = hashlib.sha256(SQL.encode()).hexdigest()
SOURCE_LEDGER = (
    (9001, "v9001", hashlib.sha256("\n".join(v0001.STATEMENTS).encode()).hexdigest()),
)
TARGET_LEDGER = (*SOURCE_LEDGER, (9002, "v9002", STEP_HASH))


def manifest(version, catalogue, ledger):
    digest = hashlib.sha256(
        "\n".join(f"{v}:{n}:{h}" for v, n, h in ledger).encode("ascii")
    ).hexdigest()
    return _SchemaManifest(SchemaVersion(version), catalogue, ledger, Sha256Hex(digest))


SOURCE = manifest(9001, _CURRENT_MANIFEST.catalogue, SOURCE_LEDGER)
TARGET = manifest(
    9002,
    (*SOURCE.catalogue, ("index", "migration_rule_effective_test", SQL)),
    TARGET_LEDGER,
)
STEP = _ExistingStep(SOURCE, TARGET, (SQL,), Sha256Hex(STEP_HASH))
FILES = ("database.db", "config.json", "bindings.json", "source.json", "target.json")
SENTINEL = "SYNTHETIC_PRIVATE_MIGRATION_SENTINEL"
INSPECTION_FILE_LIMIT = 16 * 1024 * 1024
INSPECTION_TREE_LIMIT = 64 * 1024 * 1024
INSPECTION_SECONDS = 8
INSPECTION_CHUNK = 64 * 1024


def fail(code=ErrorCode.CONSISTENCY_FAILURE):
    try:
        raise StorageFailure(code) from None
    except StorageFailure as error:
        error.__cause__ = None
        error.__context__ = None
        raise


def private_file(path):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        fail()
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode)


def private_directory(path):
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        fail()
    return (info.st_dev, info.st_ino)


def write_private(path, data):
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def sync_directory(path):
    descriptor = os.open(
        path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def context_files(connection):
    projection = connection.execute(
        "SELECT projection_id,state_instance_id,request_namespace,config_revision "
        "FROM projections"
    ).fetchone()
    rows = connection.execute(
        "SELECT role,declared_address,verified_address,credential_revision,"
        "binding_revision FROM bindings ORDER BY role"
    ).fetchall()
    assert len(rows) == 2 and [row[0] for row in rows] == ["source", "target"]
    accounts = [row[2] or row[1] for row in rows]
    assert accounts[0] != accounts[1]
    config = dict(
        zip(
            ("projection", "instance", "namespace", "revision"), projection, strict=True
        )
    )
    bindings = {
        role: {
            "account": verified or declared,
            "credential_revision": cred,
            "binding_revision": binding,
        }
        for role, declared, verified, cred, binding in rows
    }
    result = {"config.json": encoded(config), "bindings.json": encoded(bindings)}
    for role in ("source", "target"):
        result[role + ".json"] = encoded(
            {
                "role": role,
                **bindings[role],
                "fixture_token": "synthetic-" + role + "-token",
            }
        )
    return result


def logical(connection):
    tables = tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
        )
    )
    assert len(tables) == 32
    return {
        name: tuple(
            sorted(connection.execute(f'SELECT * FROM "{name}"').fetchall(), key=repr)
        )
        for name in tables
    }


def tree(path):
    result = {}
    for entry in (path, *sorted(path.rglob("*"))):
        info = entry.lstat()
        result[str(entry.relative_to(path))] = (
            info.st_dev,
            info.st_ino,
            info.st_uid,
            info.st_mode,
            info.st_nlink,
            info.st_size,
            info.st_mtime_ns,
            entry.read_bytes() if stat.S_ISREG(info.st_mode) else None,
        )
    return result


def inspection_deadline(deadline):
    if time.monotonic() >= deadline:
        fail(ErrorCode.MAINTENANCE_REQUIRED)


def physical(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
    )


def read_bounded(path, info, deadline):
    inspection_deadline(deadline)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        assert physical(os.fstat(descriptor)) == physical(info)
        result = bytearray()
        while len(result) < info.st_size:
            inspection_deadline(deadline)
            chunk = os.read(
                descriptor, min(INSPECTION_CHUNK, info.st_size - len(result))
            )
            if not chunk:
                fail()
            result.extend(chunk)
        inspection_deadline(deadline)
        if os.read(descriptor, 1):
            fail()
        assert physical(os.fstat(descriptor)) == physical(info)
        assert physical(path.lstat()) == physical(info)
        return bytes(result)
    finally:
        os.close(descriptor)


def bounded_tree(path, deadline):
    # Admit the whole existing tree BEFORE allocating any file-byte oracle.
    inventory = [(path, path.lstat())]
    size = inventory[0][1].st_size if stat.S_ISREG(inventory[0][1].st_mode) else 0
    for entry in path.rglob("*"):
        inspection_deadline(deadline)
        info = entry.lstat()
        inventory.append((entry, info))
        if stat.S_ISREG(info.st_mode):
            size += info.st_size
        if size > INSPECTION_TREE_LIMIT:
            fail(ErrorCode.MAINTENANCE_REQUIRED)
    if size > INSPECTION_TREE_LIMIT:
        fail(ErrorCode.MAINTENANCE_REQUIRED)
    result = {}
    for entry, info in inventory:
        inspection_deadline(deadline)
        result[str(entry.relative_to(path))] = (
            *physical(info),
            read_bounded(entry, info, deadline) if stat.S_ISREG(info.st_mode) else None,
        )
    return result


@contextmanager
def inspection(scope):
    """Owned TEST recognition copy, never a bundle or native provenance issuer."""
    if type(scope) is not Scope:
        fail(ErrorCode.INVALID_INPUT)
    scope.held()
    deadline = time.monotonic() + INSPECTION_SECONDS
    path = scope.root_path / "database.db"
    private_file(path)
    if path.stat().st_size < 100:
        fail(ErrorCode.MAINTENANCE_REQUIRED)
    wal, shm = Path(str(path) + "-wal"), Path(str(path) + "-shm")
    if wal.exists() != shm.exists():
        fail(ErrorCode.MAINTENANCE_REQUIRED)
    sources = (path, wal) if wal.exists() else (path,)
    if wal.exists():
        private_file(wal)
        private_file(shm)
    for source in sources:
        private_file(source)
        if source.stat().st_size > INSPECTION_FILE_LIMIT:
            fail(ErrorCode.MAINTENANCE_REQUIRED)
    before = bounded_tree(scope.root_path.parent, deadline)
    with ExitStack() as outputs:
        connection = None
        scratch = None
        try:
            if wal.exists():
                scratch = outputs.enter_context(sandbox())
                assert scratch != scope.root_path.parent
                assert not scratch.is_relative_to(scope.root_path.parent)
                private_directory(scratch)
                for source in sources:
                    scope.held()
                    info = source.lstat()
                    private_file(source)
                    if info.st_size > INSPECTION_FILE_LIMIT:
                        fail(ErrorCode.MAINTENANCE_REQUIRED)
                    data = read_bounded(source, info, deadline)
                    scope.held()
                    destination = scratch / source.name
                    write_private(destination, data)
                    assert private_file(destination)[:2] != private_file(source)[:2]
                    inspection_deadline(deadline)
                inspected = scratch / "database.db"
                suffix = "?mode=ro"
            else:
                inspected = path
                suffix = "?mode=ro&immutable=1"
            scope.held()
            inspection_deadline(deadline)
            connection = sqlite3.connect(
                inspected.as_uri() + suffix,
                uri=True,
                autocommit=True,
                timeout=1,
            )
            connection.set_progress_handler(
                lambda: int(time.monotonic() >= deadline), 1000
            )
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            yield connection
        finally:
            try:
                if connection is not None:
                    connection.close()
            finally:
                try:
                    if scratch is not None:
                        private_directory(scratch)
                        for output in scratch.iterdir():
                            private_file(output)
                finally:
                    outputs.close()
                    scope.held()
                    after = bounded_tree(scope.root_path.parent, deadline)
                    if after != before:
                        fail()


@contextmanager
def sandbox():
    def trusted(path):
        for entry in (path, *path.parents):
            info = entry.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in (0, os.geteuid())
                or stat.S_IMODE(info.st_mode) & 0o7022
            ):
                return False
        return True

    anchor = next(
        (
            p
            for p in (Path.cwd(), Path(f"/run/user/{os.geteuid()}"))
            if p.exists() and trusted(p)
        ),
        None,
    )
    assert anchor is not None, "no_verified_trusted_test_anchor"
    with tempfile.TemporaryDirectory(
        prefix="facet-migration-test-", dir=anchor
    ) as directory:
        yield Path(directory)


def make_fixture(parent, *, version=9001, seed=True):
    root = parent / "state"
    with private_root.create_lock_root(str(root)):
        pass
    credentials = root / "credentials"
    credentials.mkdir(mode=0o700)
    for role in ("source", "target"):
        write_private(credentials / (role + ".lock"), b"")
    path = root / "database.db"
    seed_path = path if version == 1 else parent / "typed-seed.db"
    connection, session, owner = create_state(seed_path)
    if seed:
        state = (seed_path, connection, session, owner)
        _, _, _, attempt = inserted(state)
        verify(state, attempt)
        assert all(
            connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] > 0
            for name in ("rules", "sync_jobs", "insert_attempts", "message_mappings")
        )
    files = context_files(connection)
    seeded_rows = logical(connection)
    session.close()
    if version == 9001:
        write_private(path, b"")
        connection = sqlite3.connect(path, autocommit=True, cached_statements=0)
        try:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("BEGIN IMMEDIATE")
            for sql in v0001.STATEMENTS:
                if not sql.startswith("CREATE TRIGGER "):
                    connection.execute(sql)
            expected = dict(seeded_rows)
            expected["schema_metadata"] = (
                (
                    1,
                    9001,
                    SOURCE.registry_digest.value,
                    seeded_rows["schema_metadata"][0][3],
                ),
            )
            expected["schema_migrations"] = (
                (*SOURCE_LEDGER[0], seeded_rows["schema_migrations"][0][3]),
            )
            # Fixed fixture order, with immutable mapping history before its
            # immediate live-mapping FK. Original declared deferred pointer
            # cycles remain enforced by native SQLite at COMMIT, not disabled.
            order = [table.name for table in v0001.TABLES]
            order.remove("mapping_history")
            order.insert(order.index("message_mappings"), "mapping_history")
            for name in order:
                for row in expected[name]:
                    marks = ",".join("?" for _ in row)
                    assert (
                        connection.execute(
                            f'INSERT INTO "{name}" VALUES({marks})', row
                        ).rowcount
                        == 1
                    )
            for sql in v0001.STATEMENTS:
                if sql.startswith("CREATE TRIGGER "):
                    connection.execute(sql)
            connection.execute(f"PRAGMA application_id={v0001.APPLICATION_ID}")
            connection.execute("PRAGMA user_version=9001")
            assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
            engine._state(connection, SOURCE)
            assert logical(connection) == expected
            connection.execute("COMMIT")
        finally:
            connection.close()
    else:
        assert version == 1
    for name, data in files.items():
        write_private(
            credentials / name
            if name in ("source.json", "target.json")
            else root / name,
            data,
        )
    sync_directory(credentials)
    sync_directory(root)
    return root


class HeldRole:
    """Fixed fixture credential mutex, not a Facet request-key lease/provider."""

    def __init__(self, path):
        self.path = path
        self.pid, self.thread = os.getpid(), threading.current_thread()
        self.identity = private_file(path)
        self.descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            assert os.fstat(self.descriptor).st_size == 0
            fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.descriptor)
            raise
        self.phase = "held"

    def check(self):
        if (
            os.getpid() != self.pid
            or threading.current_thread() is not self.thread
            or self.phase != "held"
        ):
            fail(ErrorCode.OWNER_UNAVAILABLE)
        info = os.fstat(self.descriptor)
        if (
            (info.st_dev, info.st_ino, info.st_uid, info.st_mode) != self.identity
            or private_file(self.path) != self.identity
            or info.st_size != 0
        ):
            fail(ErrorCode.OWNER_UNAVAILABLE)

    def close(self):
        if os.getpid() != self.pid or threading.current_thread() is not self.thread:
            fail(ErrorCode.OWNER_UNAVAILABLE)
        if self.phase == "held":
            self.phase = "closed"
            os.close(self.descriptor)


class Scope:
    """Static actual fixture producer: continuous kernel/role freeze + full files."""

    def __init__(self, root):
        self.root_path = Path(root)
        self.pid, self.thread = os.getpid(), threading.current_thread()
        self.connection = None
        self.receipt = None
        self.bundle = None
        self.stack = ExitStack()
        self.phase = "new"

    def __enter__(self):
        try:
            self.root = self.stack.enter_context(
                private_root.open_existing_root(str(self.root_path))
            )
            self.owner_lock = self.stack.enter_context(locks.acquire_owner(self.root))
            self.view = self.stack.enter_context(
                locks.acquire_view(
                    self.root, locks.LockMode.EXCLUSIVE, owner=self.owner_lock
                )
            )
            self.credential_identity = private_directory(self.root_path / "credentials")
            self.roles = []
            for role in ("source", "target"):
                held = HeldRole(self.root_path / "credentials" / (role + ".lock"))
                self.stack.callback(held.close)
                self.roles.append(held)
            self.phase = "held"
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *args):
        try:
            if self.connection is not None:
                self.connection.close()
        finally:
            self.phase = "closed"
            self.stack.close()

    def held(self):
        if (
            os.getpid() != self.pid
            or threading.current_thread() is not self.thread
            or self.phase != "held"
        ):
            fail(ErrorCode.OWNER_UNAVAILABLE)
        try:
            private_root.check_root(self.root)
            locks.check_lock(self.owner_lock)
            locks.check_lock(self.view)
            if (
                private_directory(self.root_path / "credentials")
                != self.credential_identity
            ):
                fail(ErrorCode.OWNER_UNAVAILABLE)
            for participant in self.roles:
                participant.check()
        except private_root.LockFailure:
            fail(ErrorCode.OWNER_UNAVAILABLE)

    def preflight(self):
        self.held()
        path = self.root_path / "database.db"
        identity = private_file(path)
        try:
            with inspection(self) as connection:
                selected, _ = engine._manifest(connection)
                state = engine._state(connection, selected)
                expected = context_files(connection)
                for name, data in expected.items():
                    participant = (
                        self.root_path / "credentials" / name
                        if name in ("source.json", "target.json")
                        else self.root_path / name
                    )
                    private_file(participant)
                    if participant.read_bytes() != data:
                        fail()
                if private_file(path) != identity:
                    fail()
                return state, selected, expected
        except sqlite3.Error:
            fail(ErrorCode.MAINTENANCE_REQUIRED)

    def publish(self, state, selected, expected):
        self.held()
        parent = self.root_path / "backups"
        parent.mkdir(mode=0o700)
        stage = parent / "staging"
        stage.mkdir(mode=0o700)
        path = self.root_path / "database.db"
        suffix = (
            "?mode=ro" if Path(str(path) + "-wal").exists() else "?mode=ro&immutable=1"
        )
        source = sqlite3.connect(path.as_uri() + suffix, uri=True, autocommit=True)
        destination = None
        try:
            write_private(stage / "database.db", b"")
            destination = sqlite3.connect(stage / "database.db", autocommit=True)
            source.backup(destination)
            destination.execute("PRAGMA foreign_keys=ON")
            destination.execute("PRAGMA trusted_schema=OFF")
            assert engine._state(destination, selected) == state
        finally:
            if destination is not None:
                destination.close()
            source.close()
        for name, data in expected.items():
            write_private(stage / name, data)
        inventory = {
            name: hashlib.sha256((stage / name).read_bytes()).hexdigest()
            for name in FILES
        }
        payload = encoded({"bundle": lid(80).value, "files": inventory})
        write_private(stage / "manifest.json", payload)
        for name in FILES:
            private_file(stage / name)
            descriptor = os.open(
                stage / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
            )
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        sync_directory(stage)
        published = parent / "complete"
        os.rename(stage, published)
        sync_directory(parent)
        self.bundle = published
        self.bundle_identity = private_directory(published)
        self.receipt = MigrationBackupReceipt(
            lid(80),
            Sha256Hex(hashlib.sha256(payload).hexdigest()),
            state.state_instance_id,
            state.request_namespace,
            state.schema_version,
            state.config_revision,
            state.source_credential_revision,
            state.target_credential_revision,
        )

    def open(self):
        state, selected, expected = self.preflight()
        if state.schema_version == SOURCE.version:
            self.publish(state, selected, expected)
        self.owner = OwnerSessionInfo(
            lid(99), state.state_instance_id, state.request_namespace
        )
        self.file_identity = private_file(self.root_path / "database.db")
        self.expected_files = expected
        self.connection = sqlite3.connect(
            (self.root_path / "database.db").as_uri() + "?mode=rw",
            uri=True,
            autocommit=True,
            cached_statements=0,
        )
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA trusted_schema=OFF")
        self._check_migration_connection(self.connection, self.owner)
        return self.connection

    def _check_migration_connection(self, connection, owner):
        self.held()
        if (
            connection is not self.connection
            or owner != self.owner
            or private_file(self.root_path / "database.db") != self.file_identity
        ):
            fail(ErrorCode.OWNER_UNAVAILABLE)
        for name, data in self.expected_files.items():
            path = (
                self.root_path / "credentials" / name
                if name in ("source.json", "target.json")
                else self.root_path / name
            )
            private_file(path)
            if path.read_bytes() != data:
                fail()

    def _validate_migration_backup(self, connection, receipt, state):
        self._check_migration_connection(connection, self.owner)
        if (
            self.bundle is None
            or receipt != self.receipt
            or private_directory(self.bundle) != self.bundle_identity
        ):
            fail()
        if {p.name for p in self.bundle.iterdir()} != {*FILES, "manifest.json"}:
            fail()
        for name in (*FILES, "manifest.json"):
            private_file(self.bundle / name)
        payload = (self.bundle / "manifest.json").read_bytes()
        if hashlib.sha256(payload).hexdigest() != receipt.manifest_digest.value:
            fail()
        actual = json.loads(payload)
        expected = {
            name: hashlib.sha256((self.bundle / name).read_bytes()).hexdigest()
            for name in FILES
        }
        if actual != {"bundle": receipt.bundle_id.value, "files": expected}:
            fail()
        for name, data in self.expected_files.items():
            if (self.bundle / name).read_bytes() != data:
                fail()
        backup = sqlite3.connect(
            (self.bundle / "database.db").as_uri() + "?mode=ro&immutable=1",
            uri=True,
            autocommit=True,
        )
        try:
            backup.execute("PRAGMA foreign_keys=ON")
            backup.execute("PRAGMA trusted_schema=OFF")
            if (
                engine._state(backup, SOURCE) != state
                or context_files(backup) != self.expected_files
            ):
                fail()
        finally:
            backup.close()


@pytest.fixture
def fixture(monkeypatch, deny_external_network):
    monkeypatch.setattr(engine, "_MIGRATION_PROVIDER_TYPES", (Scope,))
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", TARGET)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", (STEP,))
    with sandbox() as parent:
        yield parent


def run(scope, *, receipt=None):
    return engine.migrate_existing(
        scope.connection,
        scope.owner,
        backup=scope.receipt if receipt is None else receipt,
        provider=scope,
    )


def refused(operation, code=None):
    with pytest.raises(StorageFailure) as captured:
        operation()
    error = captured.value
    if code is not None:
        assert error.code is code
    assert error.__context__ is None and error.__cause__ is None
    assert SENTINEL not in str(error) + repr(error) + repr(error.args)
    return error


def reopened(root, expected):
    with Scope(root) as scope:
        state, selected, _ = scope.preflight()
        assert selected == expected and state.schema_version == expected.version
        path = root / "database.db"
        suffix = (
            "?mode=ro" if Path(str(path) + "-wal").exists() else "?mode=ro&immutable=1"
        )
        connection = sqlite3.connect(path.as_uri() + suffix, uri=True, autocommit=True)
        try:
            return logical(connection)
        finally:
            connection.close()


def test_mg03_complete_bundle_preserves_actual_32_tables_and_prior_owner(fixture):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        prior = engine._state(connection, SOURCE)
        assert prior.last_owner_run_id != scope.owner.owner_run_id
        assert scope.bundle.exists() and scope.receipt is not None
        result = run(scope)
        assert result == MigrationResult(
            "migrated",
            SOURCE.version,
            TARGET.version,
            prior.state_instance_id,
            prior.request_namespace,
        )
        assert engine._state(connection, TARGET) == replace(
            prior, schema_version=TARGET.version
        )
        assert connection.execute(
            "SELECT name FROM sqlite_schema WHERE name='migration_rule_effective_test'"
        ).fetchone() == ("migration_rule_effective_test",)
        after = logical(connection)
        for name in before.keys() - {"schema_metadata", "schema_migrations"}:
            assert after[name] == before[name]
        assert after["schema_migrations"][0] == before["schema_migrations"][0]
        assert len(after["schema_migrations"]) == 2
    assert reopened(root, TARGET) == after


def test_mg01_current_real_ownership_is_unchanged_without_backup(fixture, monkeypatch):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    with Scope(root) as scope:
        connection = scope.open()
        rows = logical(connection)
        before = tree(root), rows, connection.total_changes
        sql = []
        connection.set_trace_callback(sql.append)
        result = run(scope)
        assert (
            result.disposition == "unchanged"
            and result.from_version == result.to_version == SchemaVersion(1)
        )
        assert not any(
            query.startswith(
                ("BEGIN", "UPDATE", "INSERT", "DELETE", "CREATE", "COMMIT", "ROLLBACK")
            )
            for query in sql
        )
        assert (tree(root), logical(connection), connection.total_changes) == before
        assert scope.receipt is None and not (root / "backups").exists()


@pytest.mark.parametrize("provider", [None, object()])
def test_mg01_unregistered_receipt_never_authorizes_sql(fixture, monkeypatch, provider):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    with Scope(root) as scope:
        connection = scope.open()
        observed = engine._state(connection, _CURRENT_MANIFEST)
        receipt = MigrationBackupReceipt(
            lid(80),
            Sha256Hex("a" * 64),
            observed.state_instance_id,
            observed.request_namespace,
            observed.schema_version,
            observed.config_revision,
            observed.source_credential_revision,
            observed.target_credential_revision,
        )
        sql = []
        connection.set_trace_callback(sql.append)
        refused(
            lambda: engine.migrate_existing(
                connection, scope.owner, backup=receipt, provider=provider
            ),
            ErrorCode.MAINTENANCE_REQUIRED,
        )
        assert sql == [] and not connection.in_transaction
        assert engine._state(connection, _CURRENT_MANIFEST) == observed


def test_mg01_unused_optional_receipt_is_never_validated_or_claimed(
    fixture, monkeypatch
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    with Scope(root) as scope:
        connection = scope.open()
        observed = engine._state(connection, _CURRENT_MANIFEST)
        unused = MigrationBackupReceipt(
            lid(81),
            Sha256Hex("f" * 64),
            lid(82),
            lid(83),
            SchemaVersion(50),
            Revision(50),
            Revision(50),
            Revision(50),
        )
        result = engine.migrate_existing(
            connection, scope.owner, backup=unused, provider=scope
        )
        assert result.disposition == "unchanged"
        assert engine._state(connection, _CURRENT_MANIFEST) == observed
        assert scope.receipt is None and not (root / "backups").exists()


@pytest.mark.parametrize("bad", ["connection", "owner", "snapshot", "integer"])
def test_mg09_wrong_exact_inputs_refuse_before_sql(fixture, monkeypatch, bad):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    with Scope(root) as scope:
        connection = scope.open()
        observed = engine._state(connection, _CURRENT_MANIFEST)
        supplied, owner, receipt = connection, scope.owner, None
        if bad == "connection":
            supplied = object()
        elif bad == "owner":
            owner = object()
        elif bad == "snapshot":
            receipt = DatabaseSnapshotInfo(
                observed.schema_version,
                observed.state_instance_id,
                observed.request_namespace,
                True,
            )
        else:
            receipt = 1
        sql = []
        connection.set_trace_callback(sql.append)
        try:
            raise RuntimeError(SENTINEL)
        except RuntimeError:
            refused(
                lambda: engine.migrate_existing(
                    supplied, owner, backup=receipt, provider=scope
                ),
                ErrorCode.INVALID_INPUT,
            )
        assert sql == []
        scope.held()
        assert engine._state(connection, _CURRENT_MANIFEST) == observed


@pytest.mark.parametrize(
    "case",
    [
        "missing_root",
        "missing_db",
        "zero",
        "empty",
        "partial",
        "unknown",
        "future",
        "foreign_application",
        "extra_view",
        "missing_index",
    ],
)
def test_mg02_unknown_preflight_has_zero_create_replace_or_repair(
    fixture, monkeypatch, case
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    path = root / "database.db"
    if case == "missing_root":
        root = fixture / "absent"
    elif case == "missing_db":
        path.unlink()
    elif case == "zero":
        with path.open("wb"):
            pass
    elif case == "empty":
        path.unlink()
        write_private(path, b"")
        native = sqlite3.connect(path, autocommit=True)
        native.execute("PRAGMA user_version=0")
        native.close()
    else:
        native = sqlite3.connect(path, autocommit=True)
        statements = {
            "partial": "DROP TABLE schema_metadata",
            "unknown": "PRAGMA user_version=0",
            "future": "PRAGMA user_version=2",
            "foreign_application": "PRAGMA application_id=1",
            "extra_view": "CREATE VIEW migration_unknown AS SELECT 1",
            "missing_index": "DROP INDEX audit_recent",
        }
        native.execute(statements[case])
        native.close()
    before = tree(fixture)
    opened = []
    connect = sqlite3.connect

    def observed_connect(*args, **kwargs):
        opened.append((args, kwargs))
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", observed_connect)
    with (
        pytest.raises((StorageFailure, private_root.LockFailure, OSError)),
        Scope(root) as scope,
    ):
        scope.open()
    assert tree(fixture) == before
    assert all("mode=ro&immutable=1" in str(args[0]) for args, _ in opened)
    assert not any(
        str(entry).endswith(("-wal", "-shm")) for entry in fixture.rglob("*")
    )


def stopped_wal(root, case):
    """Fixed known-fixture construction under real freeze, never preflight."""
    with Scope(root) as scope:
        scope.preflight()
        path = root / "database.db"
        native = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, autocommit=True)
        try:
            native.execute("PRAGMA foreign_keys=ON")
            native.execute("PRAGMA trusted_schema=OFF")
            native.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
            statements = {
                "unknown": "PRAGMA user_version=0",
                "future": "PRAGMA user_version=2",
                "foreign_application": "PRAGMA application_id=1",
                "extra_view": "CREATE VIEW migration_unknown AS SELECT 1",
                "missing_index": "DROP INDEX audit_recent",
                "namespace": "UPDATE projections SET "
                f"request_namespace='{lid(501).value}'",
                "config": "UPDATE projections SET config_revision=config_revision+1",
                "prior_owner": "UPDATE projections SET "
                f"last_owner_run_id='{lid(502).value}'",
            }
            if case == "wrong_digest":
                old = native.execute("SELECT * FROM schema_metadata").fetchone()
                native.execute("BEGIN IMMEDIATE")
                native.execute("DELETE FROM schema_metadata")
                native.execute(
                    "INSERT INTO schema_metadata VALUES(?,?,?,?)",
                    (old[0], old[1], "0" * 64, old[3]),
                )
                native.execute("COMMIT")
            elif case == "extra_ledger":
                created = native.execute("SELECT * FROM schema_migrations").fetchone()[
                    3
                ]
                native.execute(
                    "INSERT INTO schema_migrations VALUES(?,?,?,?)",
                    (2, "v0002", "0" * 64, created),
                )
            else:
                native.execute(statements[case])
        finally:
            native.close()
    assert Path(str(path) + "-wal").stat().st_size > 32
    assert Path(str(path) + "-shm").stat().st_size > 0


@pytest.mark.parametrize(
    "case",
    [
        "unknown",
        "future",
        "foreign_application",
        "extra_view",
        "missing_index",
        "wrong_digest",
        "extra_ledger",
        "namespace",
        "config",
    ],
)
def test_mg02_actual_committed_wal_refusal_never_opens_original_sqlite(
    fixture, monkeypatch, case
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    stopped_wal(root, case)
    before = bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS)
    opened = []
    connect = sqlite3.connect

    def observed_connect(*args, **kwargs):
        opened.append((args, kwargs))
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", observed_connect)
    with Scope(root) as scope:
        refused(
            scope.open,
            ErrorCode.UNSUPPORTED_VERSION if case == "future" else None,
        )
        assert scope.connection is None and scope.bundle is None
        scope.held()
        assert kernel_owner(root) == "owner_busy"
        assert bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS) == before
    assert opened and all(
        "?mode=ro" in args[0]
        and "immutable" not in args[0]
        and (root / "database.db").as_uri() not in args[0]
        for args, _ in opened
    )
    assert not (root / "backups").exists()
    # All inspected paths belong to disposed, independently owned output.
    assert all(
        not Path(args[0].split("?")[0].removeprefix("file://")).exists()
        for args, _ in opened
    )
    assert bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS) == before


def test_mg02_original_readonly_shm_detector_pairs_actual_future_wal(
    fixture, monkeypatch
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    stopped_wal(root, "future")
    with Scope(root) as scope:
        before = bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS)
        main = root / "database.db"
        assert int.from_bytes(main.read_bytes()[60:64], "big") == 1
        native = sqlite3.connect(main.as_uri() + "?mode=ro", uri=True, autocommit=True)
        try:
            assert native.execute("PRAGMA user_version").fetchone() == (2,)
            assert native.execute(
                "SELECT version,name,checksum FROM schema_migrations"
            ).fetchall() == list(_CURRENT_MANIFEST.ledger)
            refused(lambda: engine._manifest(native), ErrorCode.UNSUPPORTED_VERSION)
        finally:
            native.close()
        after = bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS)
        assert set(before) == set(after)
        assert [name for name in before if before[name] != after[name]] == [
            "state/database.db-shm"
        ]
        assert before["state/database.db-shm"][-1] != after["state/database.db-shm"][-1]
        # The corrected branch now inspects that same actual committed future
        # without any further original-file change or writer/bundle authority.
        refused(scope.open, ErrorCode.UNSUPPORTED_VERSION)
        assert bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS) == after
        assert scope.connection is None and scope.bundle is None
        assert kernel_owner(root) == "owner_busy"


def test_mg01_real_current_wal_truth_then_noop_has_no_sql_writes(fixture, monkeypatch):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    stopped_wal(root, "prior_owner")
    before = bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS)
    with Scope(root) as scope:
        state, selected, _ = scope.preflight()
        assert selected == _CURRENT_MANIFEST
        assert state.last_owner_run_id == lid(502)
        assert bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS) == before
        connection = scope.open()
        sql = []
        connection.set_trace_callback(sql.append)
        rows, changes = logical(connection), connection.total_changes
        result = run(scope)
        assert result.disposition == "unchanged"
        assert connection.total_changes == changes and logical(connection) == rows
        assert not any(
            statement.startswith(("BEGIN", "COMMIT", "INSERT", "UPDATE", "DELETE"))
            for statement in sql
        )
        assert scope.bundle is None and scope.receipt is None
        assert kernel_owner(root) == "owner_busy"
    assert not (root / "backups").exists()


def test_mg03_genuine_predecessor_wal_full_bundle_before_writer(fixture, monkeypatch):
    root = make_fixture(fixture)
    stopped_wal(root, "prior_owner")
    before = bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS)
    calls = []
    connect = sqlite3.connect

    def observed_connect(*args, **kwargs):
        path = str(args[0])
        calls.append(path)
        if path == (root / "database.db").as_uri() + "?mode=rw":
            assert (root / "backups" / "complete" / "manifest.json").is_file()
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", observed_connect)
    with Scope(root) as scope:
        state, selected, _ = scope.preflight()
        assert selected == SOURCE and state.last_owner_run_id == lid(502)
        assert bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS) == before
        connection = scope.open()
        scope._validate_migration_backup(connection, scope.receipt, state)
        old = logical(connection)
        result = run(scope)
        assert result.disposition == "migrated"
        assert (
            engine._state(connection, TARGET).last_owner_run_id
            == state.last_owner_run_id
        )
    actual = reopened(root, TARGET)
    for name in old.keys() - {"schema_metadata", "schema_migrations"}:
        assert actual[name] == old[name]
    assert actual["schema_migrations"][0] == old["schema_migrations"][0]
    assert any(path.endswith("?mode=rw") for path in calls)


def test_mg08_target_wal_truth_reopens_noop_without_new_bundle(fixture):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
        assert run(scope).disposition == "migrated"
        expected = logical(connection)
    assert int.from_bytes((root / "database.db").read_bytes()[60:64], "big") == 9001
    before = bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS)
    with Scope(root) as scope:
        state, selected, _ = scope.preflight()
        assert selected == TARGET and state.schema_version.value == 9002
        assert bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS) == before
        connection = scope.open()
        sql = []
        connection.set_trace_callback(sql.append)
        assert run(scope).disposition == "unchanged"
        assert logical(connection) == expected
        assert not any(statement.startswith("BEGIN") for statement in sql)
        assert scope.receipt is None and scope.bundle is None


@pytest.mark.parametrize("fault", ["authorizer", "deadline"])
def test_mg02_native_inspection_faults_cleanup_and_keep_original_freeze(
    fixture, monkeypatch, fault
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    stopped_wal(root, "prior_owner")
    before = bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS)
    observed = []
    connect = sqlite3.connect

    def observed_connect(*args, **kwargs):
        observed.append(args[0])
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", observed_connect)
    with Scope(root) as scope:
        begun = time.monotonic()

        def actual_fault():
            with inspection(scope) as native:
                if fault == "authorizer":
                    native.set_authorizer(lambda *_: sqlite3.SQLITE_DENY)
                    with pytest.raises(sqlite3.DatabaseError) as captured:
                        engine._manifest(native)
                    assert captured.value.sqlite_errorcode == sqlite3.SQLITE_AUTH
                    native.set_authorizer(None)
                else:
                    with pytest.raises(sqlite3.OperationalError) as captured:
                        native.execute(
                            "WITH RECURSIVE spin(n) AS(VALUES(0) UNION ALL "
                            "SELECT n+1 FROM spin WHERE n<1000000000) "
                            "SELECT sum(n) FROM spin"
                        ).fetchone()
                    assert captured.value.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT
                    assert time.monotonic() - begun >= INSPECTION_SECONDS

        if fault == "deadline":
            refused(actual_fault, ErrorCode.MAINTENANCE_REQUIRED)
        else:
            actual_fault()
        scope.held()
        assert kernel_owner(root) == "owner_busy"
        for held in scope.roles:
            descriptor = os.open(held.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(descriptor)
        assert bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS) == before
        assert all(
            not Path(path.split("?")[0].removeprefix("file://")).exists()
            for path in observed
        )


@pytest.mark.parametrize("bad", ["missing_wal", "missing_shm", "mode", "alias"])
def test_mg02_wal_file_guards_refuse_before_native_inspection(
    fixture, monkeypatch, bad
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    stopped_wal(root, "prior_owner")
    path = root / "database.db"
    wal, shm = Path(str(path) + "-wal"), Path(str(path) + "-shm")
    if bad == "missing_wal":
        wal.unlink()
    elif bad == "missing_shm":
        shm.unlink()
    elif bad == "mode":
        wal.chmod(0o640)
    else:
        original = fixture / "owned-alias.db"
        path.rename(original)
        path.symlink_to(original)
    before = bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS)

    def unexpected(*args, **kwargs):
        raise AssertionError("unknown_wal_native_open")

    monkeypatch.setattr(sqlite3, "connect", unexpected)
    with Scope(root) as scope:
        refused(scope.open)
        assert scope.connection is None and scope.bundle is None
        scope.held()
    assert bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS) == before


@pytest.mark.parametrize("source", ["database.db", "database.db-wal"])
def test_mg02_per_file_admission_precedes_copy_allocation(fixture, monkeypatch, source):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    stopped_wal(root, "prior_owner")
    with (root / source).open("r+b") as stream:
        stream.truncate(INSPECTION_FILE_LIMIT + 1)
    before = bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS)

    def unexpected(*args, **kwargs):
        raise AssertionError("oversized_source_read_or_native_open")

    with Scope(root) as scope, monkeypatch.context() as denied:
        denied.setattr(os, "read", unexpected)
        denied.setattr(sqlite3, "connect", unexpected)
        refused(scope.open, ErrorCode.MAINTENANCE_REQUIRED)
    assert bounded_tree(fixture, time.monotonic() + INSPECTION_SECONDS) == before


def test_mg02_whole_tree_admission_precedes_byte_oracle_allocation(
    fixture, monkeypatch
):
    root = make_fixture(fixture)
    for number in range(4):
        path = fixture / f"bounded-sparse-{number}.db"
        write_private(path, b"")
        with path.open("r+b") as stream:
            stream.truncate(INSPECTION_FILE_LIMIT)
    # Oversized trees are not captured into an oversized oracle. Record every
    # physical fact and prove no descriptor read/SQLite open was attempted.
    before = {
        str(path.relative_to(fixture)): physical(path.lstat())
        for path in (fixture, *fixture.rglob("*"))
    }

    def unexpected(*args, **kwargs):
        raise AssertionError("oversized_tree_byte_read_or_native_open")

    with Scope(root) as scope, monkeypatch.context() as denied:
        denied.setattr(os, "read", unexpected)
        denied.setattr(sqlite3, "connect", unexpected)
        refused(scope.open, ErrorCode.MAINTENANCE_REQUIRED)
    assert {
        str(path.relative_to(fixture)): physical(path.lstat())
        for path in (fixture, *fixture.rglob("*"))
    } == before


def kernel_owner(root):
    child = Path(__file__).parents[1] / "integration" / "runtime_lock_child.py"
    result = subprocess.run(
        [sys.executable, "-B", str(child), "try_owner", str(root)],
        capture_output=True,
        timeout=8,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0 and result.stderr == b""
    return result.stdout.decode().strip()


def test_mg05_real_foreign_thread_refuses_without_poisoning_creator(
    fixture, monkeypatch
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        sql, outcomes = [], []
        connection.set_trace_callback(sql.append)

        def foreign():
            try:
                engine.migrate_existing(
                    connection, scope.owner, backup=None, provider=scope
                )
            except StorageFailure as error:
                outcomes.append((error.code, error.__context__, error.__cause__))
            except BaseException:
                outcomes.append("unexpected")
            else:
                outcomes.append("accepted")

        participant = threading.Thread(target=foreign)
        participant.start()
        participant.join(timeout=8)
        assert not participant.is_alive()
        assert outcomes == [(ErrorCode.OWNER_UNAVAILABLE, None, None)]
        assert sql == []
        scope.held()
        assert kernel_owner(root) == "owner_busy"
        for held in scope.roles:
            fd = os.open(held.path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
        assert run(scope).disposition == "unchanged"
        assert logical(connection) == before
    assert kernel_owner(root) == "held"


def test_mg05_real_fork_copy_cannot_use_enrollment_or_release_parent(
    fixture, monkeypatch
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        observed = []
        connection.set_trace_callback(observed.append)
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read_fd)
            code = 1
            try:
                refused(lambda: run(scope), ErrorCode.OWNER_UNAVAILABLE)
                assert observed == []
                os.write(write_fd, b"refused")
                code = 0
            except BaseException:
                os.write(write_fd, b"error")
            finally:
                os.close(write_fd)
            os._exit(code)
        os.close(write_fd)
        reaped = False
        try:
            ready, _, _ = select.select([read_fd], [], [], 8)
            assert ready and os.read(read_fd, 64) == b"refused"
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                actual, status = os.waitpid(pid, os.WNOHANG)
                if actual == pid:
                    reaped = True
                    assert os.waitstatus_to_exitcode(status) == 0
                    break
                time.sleep(0.01)
            assert reaped, "owned_fork_reap_timeout"
        finally:
            os.close(read_fd)
            if not reaped:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
        scope.held()
        assert kernel_owner(root) == "owner_busy"
        assert run(scope).disposition == "unchanged"
        assert logical(connection) == before
    assert kernel_owner(root) == "held"


@pytest.mark.parametrize("lost", ["source", "target", "connection"])
def test_mg05_lost_real_role_or_wrong_enrollment_refuses_before_sql(
    fixture, monkeypatch, lost
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        sql = []
        connection.set_trace_callback(sql.append)
        supplied = connection
        extra = None
        try:
            if lost == "connection":
                extra = sqlite3.connect(
                    (root / "database.db").as_uri() + "?mode=rw",
                    uri=True,
                    autocommit=True,
                )
                supplied = extra
            else:
                scope.roles[0 if lost == "source" else 1].close()
            refused(
                lambda: engine.migrate_existing(
                    supplied, scope.owner, backup=None, provider=scope
                ),
                ErrorCode.OWNER_UNAVAILABLE,
            )
            assert sql == []
            assert kernel_owner(root) == "owner_busy"
            assert logical(connection) == before
        finally:
            if extra is not None:
                extra.close()
    assert kernel_owner(root) == "held"


@pytest.mark.parametrize(
    "field,value",
    [
        ("manifest_digest", Sha256Hex("f" * 64)),
        ("bundle_id", lid(81)),
        ("state_instance_id", lid(82)),
        ("request_namespace", lid(83)),
        ("schema_version", SchemaVersion(1)),
        ("config_revision", Revision(50)),
        ("source_credential_revision", Revision(50)),
        ("target_credential_revision", Revision(50)),
    ],
)
def test_mg04_each_bare_receipt_field_is_not_bundle_authority(fixture, field, value):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        sql = []
        connection.set_trace_callback(sql.append)
        refused(lambda: run(scope, receipt=replace(scope.receipt, **{field: value})))
        assert "BEGIN IMMEDIATE" not in sql and logical(connection) == before


@pytest.mark.parametrize(
    "name",
    [
        "source.json",
        "target.json",
        "config.json",
        "bindings.json",
        "manifest.json",
        "database.db",
    ],
)
def test_mg04_incomplete_published_bundle_refuses_before_begin(fixture, name):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        (scope.bundle / name).unlink()
        sql = []
        connection.set_trace_callback(sql.append)
        refused(lambda: run(scope))
        assert "BEGIN IMMEDIATE" not in sql and logical(connection) == before


@pytest.mark.parametrize("selected", ["source", "target"])
def test_mg06_real_immutable_guards_remain_enabled_with_row_times(fixture, selected):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        if selected == "target":
            assert run(scope).disposition == "migrated"
        current = logical(connection)
        assert current["schema_metadata"][0][3] == before["schema_metadata"][0][3]
        assert current["schema_migrations"][0] == before["schema_migrations"][0]
        for query in (
            "UPDATE schema_metadata SET schema_version=9003",
            "UPDATE schema_migrations SET applied_at=0 WHERE version=9001",
            "DELETE FROM schema_migrations WHERE version=9001",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(query)
            assert logical(connection) == current
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def sql_cut(connection, cut, *, deny_rollback=False):
    """Deny one actual native permission, observing its preceding real effects."""
    captured = []
    version_written = []
    commit_requested = []

    def trace(sql):
        if sql == "PRAGMA user_version=9002":
            version_written.append(sql)

    def control(action, first, second, database, source):
        if action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT":
            commit_requested.append(first)
        if (
            action == sqlite3.SQLITE_TRANSACTION
            and first == "ROLLBACK"
            and deny_rollback
        ):
            return sqlite3.SQLITE_DENY
        hit = (
            (
                cut == "after_ddl"
                and action == sqlite3.SQLITE_READ
                and first == "schema_metadata"
                and second == "created_at"
            )
            or (
                cut == "after_delete"
                and action == sqlite3.SQLITE_INSERT
                and first == "schema_metadata"
            )
            or (
                cut == "after_insert"
                and action == sqlite3.SQLITE_INSERT
                and first == "schema_migrations"
            )
            or (
                cut == "after_ledger"
                and action == sqlite3.SQLITE_PRAGMA
                and first == "user_version"
                and second is not None
            )
            or (
                cut == "after_version"
                and version_written
                and action == sqlite3.SQLITE_READ
                and first == "sqlite_master"
            )
            or (
                cut == "before_commit"
                and version_written
                and action == sqlite3.SQLITE_READ
                and first == "bindings"
                and second == "credential_revision"
            )
            or (
                cut == "commit"
                and action == sqlite3.SQLITE_TRANSACTION
                and first == "COMMIT"
            )
            or (
                cut == "final"
                and commit_requested
                and not connection.in_transaction
                and action == sqlite3.SQLITE_READ
                and first == "sqlite_master"
            )
        )
        if hit and not captured:
            # Reentrant read-only observation on the same genuine connection,
            # not a fabricated transaction/version flag. Restore the control so
            # native ROLLBACK refusal remains a distinct uncertainty case.
            connection.set_authorizer(None)
            try:
                captured.append(
                    (
                        connection.in_transaction,
                        connection.execute("PRAGMA user_version").fetchone()[0],
                        logical(connection),
                        connection.execute(
                            "SELECT name FROM sqlite_schema WHERE "
                            "name='migration_rule_effective_test'"
                        ).fetchall(),
                    )
                )
            finally:
                connection.set_authorizer(control)
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_trace_callback(trace)
    connection.set_authorizer(control)
    return captured


@pytest.mark.parametrize(
    "cut",
    [
        "after_ddl",
        "after_delete",
        "after_insert",
        "after_ledger",
        "after_version",
        "before_commit",
    ],
)
def test_mg06_every_native_cut_rolls_back_all_32_rows_and_reopens(fixture, cut):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        captured = sql_cut(connection, cut)
        refused(lambda: run(scope), ErrorCode.PERSISTENCE_FAILURE)
        connection.set_authorizer(None)
        connection.set_trace_callback(None)
        assert len(captured) == 1
        transaction, version, observed, index = captured[0]
        assert transaction is True and index == [("migration_rule_effective_test",)]
        if cut == "after_delete":
            assert observed["schema_metadata"] == ()
        elif cut in {"after_insert", "after_ledger", "after_version", "before_commit"}:
            assert observed["schema_metadata"][0][1:3] == (
                9002,
                TARGET.registry_digest.value,
            )
            assert observed["schema_metadata"][0][3] == before["schema_metadata"][0][3]
        if cut in {"after_ledger", "after_version", "before_commit"}:
            assert len(observed["schema_migrations"]) == 2
        else:
            assert observed["schema_migrations"] == before["schema_migrations"]
        assert version == (9002 if cut in {"after_version", "before_commit"} else 9001)
        assert not connection.in_transaction
        assert logical(connection) == before
        assert engine._state(connection, SOURCE).schema_version == SOURCE.version
        scope.held()
    assert reopened(root, SOURCE) == before


@pytest.mark.parametrize("cut,rollback", [("commit", False), ("after_delete", True)])
def test_mg08_native_commit_or_rollback_refusal_invalidates_once_and_reopens(
    fixture, cut, rollback
):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        captured = sql_cut(connection, cut, deny_rollback=rollback)
        closed = []
        previous = sys.getprofile()

        def profile(frame, event, operation):
            if (
                event == "c_call"
                and getattr(operation, "__self__", None) is connection
                and getattr(operation, "__name__", None) == "close"
            ):
                closed.append(operation)

        sys.setprofile(profile)
        try:
            refused(lambda: run(scope), ErrorCode.PERSISTENCE_FAILURE)
        finally:
            sys.setprofile(previous)
        assert len(closed) == 1
        assert len(captured) == 1
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
        scope.held()
        assert kernel_owner(root) == "owner_busy"
    assert reopened(root, SOURCE) == before


def test_mg08_actual_postcommit_inspection_refusal_reopens_target_as_noop(fixture):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        captured = sql_cut(connection, "final")
        refused(lambda: run(scope), ErrorCode.PERSISTENCE_FAILURE)
        assert len(captured) == 1
        transaction, version, actual, index = captured[0]
        assert transaction is False and version == 9002
        assert index == [("migration_rule_effective_test",)]
        for name in before.keys() - {"schema_metadata", "schema_migrations"}:
            assert actual[name] == before[name]
        assert actual["schema_metadata"][0][3] == before["schema_metadata"][0][3]
        assert actual["schema_migrations"][0] == before["schema_migrations"][0]
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
        assert kernel_owner(root) == "owner_busy"
    assert reopened(root, TARGET) == actual
    bundles = tree(root / "backups")
    with Scope(root) as scope:
        connection = scope.open()
        sql = []
        connection.set_trace_callback(sql.append)
        assert run(scope).disposition == "unchanged"
        assert not any(
            query.startswith(
                ("BEGIN", "CREATE", "INSERT", "DELETE", "UPDATE", "COMMIT")
            )
            for query in sql
        )
        assert scope.receipt is None and tree(root / "backups") == bundles
        assert logical(connection) == actual


def test_mg06_real_deferred_fk_invalid_target_rolls_back_not_discard_rows(fixture):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        original = before["rules"][0]
        # Fixed TEMP fault adds a native deferred current-revision FK violation
        # after publication, without changing the main catalogue.
        connection.execute(
            "CREATE TEMP TRIGGER migration_fk_fault AFTER INSERT ON "
            "main.schema_metadata BEGIN INSERT INTO rules "
            "SELECT projection_id,"
            f"'{lid(500).value}',kind,'foreign-key-fault@example.invalid',"
            "current_revision "
            f"FROM rules WHERE rule_id='{original[1]}'; END"
        )
        observed, version_written = [], []

        def trace(sql):
            if sql == "PRAGMA user_version=9002":
                version_written.append(sql)

        def observe(action, first, second, database, source):
            if (
                version_written
                and not observed
                and action == sqlite3.SQLITE_READ
                and first == "sqlite_master"
            ):
                connection.set_authorizer(None)
                try:
                    observed.append(
                        (
                            connection.execute("PRAGMA foreign_keys").fetchone(),
                            connection.execute("PRAGMA foreign_key_check").fetchall(),
                            logical(connection),
                        )
                    )
                finally:
                    connection.set_authorizer(observe)
            return sqlite3.SQLITE_OK

        connection.set_trace_callback(trace)
        connection.set_authorizer(observe)
        refused(lambda: run(scope), ErrorCode.CONSISTENCY_FAILURE)
        connection.set_authorizer(None)
        assert len(observed) == 1 and observed[0][0] == (1,)
        assert any(row[0] == "rules" for row in observed[0][1])
        assert len(observed[0][2]["rules"]) == len(before["rules"]) + 1
        assert not connection.in_transaction and logical(connection) == before
    assert reopened(root, SOURCE) == before


@pytest.mark.parametrize(
    "drift", ["config", "source_revision", "target_revision", "prior_owner"]
)
def test_mg05_actual_sql_state_drift_invalidates_original_backup_before_begin(
    fixture, drift
):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        if drift == "config":
            connection.execute(
                "UPDATE projections SET config_revision=config_revision+1"
            )
        elif drift == "prior_owner":
            connection.execute(
                "UPDATE projections SET last_owner_run_id=?", (lid(501).value,)
            )
        else:
            role = "source" if drift == "source_revision" else "target"
            connection.execute(
                "UPDATE bindings SET credential_revision=credential_revision+1 "
                "WHERE role=?",
                (role,),
            )
        changed = logical(connection)
        sql = []
        connection.set_trace_callback(sql.append)
        refused(lambda: run(scope), ErrorCode.CONSISTENCY_FAILURE)
        assert "BEGIN IMMEDIATE" not in sql
        assert logical(connection) == changed and connection.execute(
            "PRAGMA user_version"
        ).fetchone() == (9001,)
    # Deliberately drifted config/credentials no longer match the frozen private
    # context, so physical state is inspected under actual locks without granting
    # a new provider enrollment or fixing those files.
    with Scope(root) as scope:
        connection = sqlite3.connect(
            (root / "database.db").as_uri() + "?mode=ro&immutable=1",
            uri=True,
            autocommit=True,
        )
        try:
            assert logical(connection) == changed
            engine._state(connection, SOURCE)
        finally:
            connection.close()


@pytest.mark.parametrize(
    "participant",
    [
        "source.json",
        "target.json",
        "config.json",
        "bindings.json",
        "manifest.json",
        "database.db",
    ],
)
def test_mg04_actual_completed_bundle_tampering_is_not_authorized_by_receipt(
    fixture, participant
):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        path = scope.bundle / participant
        if participant == "database.db":
            with path.open("r+b") as stream:
                stream.seek(0)
                stream.write(b"SYNTHETIC_CORRUPT_BACKUP")
        else:
            data = json.loads(path.read_bytes())
            if participant == "manifest.json":
                data["bundle"] = lid(502).value
            elif participant == "config.json":
                data["instance"] = lid(502).value
            elif participant == "bindings.json":
                data["source"]["account"] = "wrong@example.invalid"
            else:
                data["account"] = "wrong@example.invalid"
                data["credential_revision"] += 1
            with path.open("wb") as stream:
                stream.write(encoded(data))
        sql = []
        connection.set_trace_callback(sql.append)
        refused(lambda: run(scope), ErrorCode.CONSISTENCY_FAILURE)
        assert "BEGIN IMMEDIATE" not in sql and logical(connection) == before


def test_mg09_registered_class_or_provider_exception_is_never_authority(
    fixture, monkeypatch, caplog, capsys
):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        sql = []
        connection.set_trace_callback(sql.append)
        forged = object.__new__(Scope)
        refused(
            lambda: engine.migrate_existing(
                connection, scope.owner, backup=scope.receipt, provider=forged
            ),
            ErrorCode.CONSISTENCY_FAILURE,
        )
        assert sql == []

        class BrokenProvider:
            def _check_migration_connection(self, supplied, owner):
                scope._check_migration_connection(supplied, owner)
                raise RuntimeError(SENTINEL + str(root) + lid(1).value + SQL)

            def _validate_migration_backup(self, supplied, receipt, state):
                fail()

        monkeypatch.setattr(engine, "_MIGRATION_PROVIDER_TYPES", (BrokenProvider,))
        try:
            raise RuntimeError(SENTINEL)
        except RuntimeError:
            refused(
                lambda: engine.migrate_existing(
                    connection,
                    scope.owner,
                    backup=scope.receipt,
                    provider=BrokenProvider(),
                ),
                ErrorCode.CONSISTENCY_FAILURE,
            )
        assert sql == [] and logical(connection) == before
        assert caplog.records == []
        output = capsys.readouterr()
        assert output.out == output.err == ""
        assert SENTINEL.encode() not in repr(tree(root)).encode()


def test_mg05_actual_drift_after_valid_bundle_before_begin_is_reinspected(
    fixture, monkeypatch
):
    root = make_fixture(fixture)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)

        class DriftingProvider:
            def _check_migration_connection(self, supplied, owner):
                scope._check_migration_connection(supplied, owner)

            def _validate_migration_backup(self, supplied, receipt, state):
                scope._validate_migration_backup(supplied, receipt, state)
                supplied.execute(
                    "UPDATE projections SET config_revision=config_revision+1"
                )

        monkeypatch.setattr(engine, "_MIGRATION_PROVIDER_TYPES", (DriftingProvider,))
        sql = []
        connection.set_trace_callback(sql.append)
        refused(
            lambda: engine.migrate_existing(
                connection,
                scope.owner,
                backup=scope.receipt,
                provider=DriftingProvider(),
            ),
            ErrorCode.CONSISTENCY_FAILURE,
        )
        assert sql.count("BEGIN IMMEDIATE") == sql.count("ROLLBACK") == 1
        assert "COMMIT" not in sql
        assert connection.execute("PRAGMA user_version").fetchone() == (9001,)
        assert (
            connection.execute(
                "SELECT name FROM sqlite_schema WHERE "
                "name='migration_rule_effective_test'"
            ).fetchall()
            == []
        )
        after = logical(connection)
        for name in before.keys() - {"projections"}:
            assert after[name] == before[name]
        assert connection.execute(
            "SELECT config_revision FROM projections"
        ).fetchone() == (scope.receipt.config_revision.value + 1,)
        scope.held()


@pytest.mark.parametrize(
    "condition",
    ["transaction", "row_factory", "text_factory", "query_only", "autocommit"],
)
def test_mg01_supplied_native_connection_conditions_never_adopt_external_uow(
    fixture, monkeypatch, condition
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        if condition == "transaction":
            connection.execute("BEGIN IMMEDIATE")
        elif condition == "row_factory":
            connection.row_factory = sqlite3.Row
        elif condition == "text_factory":
            connection.text_factory = bytes
        elif condition == "query_only":
            connection.execute("PRAGMA query_only=ON")
        else:
            connection.autocommit = False
        sql = []
        connection.set_trace_callback(sql.append)
        refused(lambda: run(scope))
        assert not any(
            query.startswith(
                ("BEGIN", "COMMIT", "ROLLBACK", "CREATE", "UPDATE", "INSERT", "DELETE")
            )
            for query in sql
        )
        if condition in {"transaction", "autocommit"}:
            assert connection.in_transaction
        connection.set_trace_callback(None)
        connection.row_factory = None
        connection.text_factory = str
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        connection.autocommit = True
        connection.execute("PRAGMA query_only=OFF")
        assert logical(connection) == before
        assert run(scope).disposition == "unchanged"


@pytest.mark.parametrize("lost", ["view", "source_inode", "target_inode"])
def test_mg05_released_view_or_replaced_real_role_lock_refuses_without_cleanup_poison(
    fixture, monkeypatch, lost
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", _CURRENT_MANIFEST)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", ())
    root = make_fixture(fixture, version=1)
    with Scope(root) as scope:
        connection = scope.open()
        before = logical(connection)
        if lost == "view":
            for held in reversed(scope.roles):
                held.close()
            locks.release_lock(scope.view)
        else:
            held = scope.roles[0 if lost == "source_inode" else 1]
            original = held.path.with_suffix(".held-original")
            held.path.rename(original)
            write_private(held.path, b"")
            descriptor = os.open(original, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(descriptor)
        sql = []
        connection.set_trace_callback(sql.append)
        refused(lambda: run(scope), ErrorCode.OWNER_UNAVAILABLE)
        assert sql == []
        locks.check_lock(scope.owner_lock)
        assert kernel_owner(root) == "owner_busy"
        assert logical(connection) == before
    assert kernel_owner(root) == "held"


@pytest.mark.parametrize(
    "disposition,old,new,valid",
    [
        ("unchanged", 1, 1, True),
        ("unchanged", 1, 2, False),
        ("migrated", 1, 2, True),
        ("migrated", 2, 1, False),
        ("migrated", 1, 1, False),
        ("other", 1, 2, False),
    ],
)
def test_mg09_exact_result_values_are_private(disposition, old, new, valid):
    args = (disposition, SchemaVersion(old), SchemaVersion(new), lid(1), lid(2))
    if valid:
        result = MigrationResult(*args)
        assert lid(1).value not in repr(result) and lid(2).value not in str(result)
    else:
        with pytest.raises(StorageFailure):
            MigrationResult(*args)
    assert (
        len(fields(MigrationState)) == 8
        and len(fields(MigrationResult)) == 5
        and len(fields(MigrationBackupReceipt)) == 8
    )
