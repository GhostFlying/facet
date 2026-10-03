"""SI01/02/04: supplied native WAL storage, never a production file issuer."""

import os
import sqlite3
import subprocess
import sys
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import replace

import pytest
from integration.test_runtime_os_locks import tree, trusted_sandbox
from unit.test_db_schema import NOW, P, bootstrap_rows, lid

from facet.contracts import ErrorCode, Revision, Sha256Hex
from facet.db.codecs import StorageFailure
from facet.db.command_records import (
    BootstrapCommand,
    BootstrapOperationSeed,
    FreshCommandBootstrap,
)
from facet.db.connection import (
    _configure_writer,
    _initialize_database_v2,
    _inspect_bootstrap_v2,
)
from facet.db.migrations import FRESH_V2_REGISTRY
from facet.db.models import BootstrapInitContext
from facet.runtime import locks, private_root

SENTINEL = "SYNTHETIC_COMMAND_PRIVATE_ERROR_SENTINEL"
DIGEST = Sha256Hex("a" * 64)


def command_seed(*, prior=False):
    return BootstrapOperationSeed(
        lid(11 if prior else 10),
        lid(3),
        lid(5 if prior else 4),
        BootstrapCommand.CONFIG_INIT if prior else BootstrapCommand.FACET_INIT,
        1,
        DIGEST,
        Sha256Hex("b" * 64),
        Sha256Hex("c" * 64),
        NOW,
        NOW,
        Revision(0),
        Revision(0),
        True,
        False,
    )


def inputs(*, prior=True):
    owner, projection, bindings, ruleset = bootstrap_rows()
    return {
        "bootstrap": BootstrapInitContext(owner, lid(4)),
        "initial_projection": projection,
        "source_binding": bindings[0],
        "target_binding": bindings[1],
        "initial_ruleset": ruleset,
        "commands": FreshCommandBootstrap(
            command_seed(), command_seed(prior=True) if prior else None
        ),
    }


def opened(path, *, configure=False, shared=False):
    connection = sqlite3.connect(path, autocommit=True, check_same_thread=not shared)
    if configure:
        _configure_writer(connection, creating=False)
    return connection


@contextmanager
def storage(*, initialize=True, prior=True):
    # Owned resources are real kernel holders throughout each storage scenario.
    # The supplied connection is test data, not native-file or issuer authority.
    with trusted_sandbox() as sandbox, ExitStack() as stack:
        root_path = sandbox / "state"
        root = private_root.create_lock_root(str(root_path))
        stack.callback(private_root.close_root, root)
        owner_lock = locks.acquire_owner(root)
        stack.callback(locks.release_lock, owner_lock)
        view_lock = locks.acquire_view(root, locks.LockMode.EXCLUSIVE, owner=owner_lock)
        stack.callback(locks.release_lock, view_lock)
        path = root_path / "metadata.db"
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(descriptor)
        connection = opened(path)
        stack.callback(safe_close, connection)
        data = inputs(prior=prior)
        session = _initialize_database_v2(connection, **data) if initialize else None
        yield root_path, path, connection, session, data, owner_lock, view_lock


def safe_close(connection):
    with suppress(sqlite3.Error):
        connection.close()


def closed(connection):
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def expect_fixed(function, code=None):
    # Also exercise the caller-already-excepting privacy boundary.
    try:
        raise ValueError(SENTINEL)
    except ValueError:
        with pytest.raises(StorageFailure) as caught:
            function()
    error = caught.value
    if code is not None:
        assert error.code is code
    assert error.__context__ is None and error.__cause__ is None
    assert str(error) == error.code.value
    assert SENTINEL not in repr(error)
    return error.code


def logical(connection):
    tables = connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
    ).fetchall()
    return {
        table: tuple(connection.execute(f'SELECT * FROM "{table}"').fetchall())
        for (table,) in tables
    }


def writer_available(path):
    # A fresh actual native connection is the paired SQLite contention oracle.
    contender = sqlite3.connect(
        path.as_uri() + "?mode=rw", uri=True, autocommit=True, timeout=0
    )
    try:
        try:
            contender.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            assert error.sqlite_errorcode == sqlite3.SQLITE_BUSY
            return False
        contender.execute("ROLLBACK")
        return True
    finally:
        contender.close()


@contextmanager
def native_fault(
    connection,
    prefix,
    *,
    event="c_return",
    name="execute",
    occurrence=1,
    error_type=MemoryError,
):
    """One actual native call/return fault, never an execute replacement."""
    seen = {
        "sql": "",
        "sqls": [],
        "hits": 0,
        "matches": 0,
        "active": None,
        "closed": None,
    }

    def trace(sql):
        seen["sql"] = sql
        seen["sqls"].append(sql)

    connection.set_trace_callback(trace)

    def profile(_frame, phase, call):
        if (
            phase == event
            and getattr(call, "__self__", None) is connection
            and getattr(call, "__name__", None) == name
            and (name == "close" or seen["sql"].startswith(prefix))
        ):
            seen["matches"] += 1
            if seen["matches"] != occurrence:
                return
            seen["hits"] += 1
            if name != "close":
                seen["active"] = connection.in_transaction
            raise error_type(SENTINEL)

    sys.setprofile(profile)
    try:
        yield seen
    finally:
        sys.setprofile(None)
        with suppress(sqlite3.Error):
            connection.set_trace_callback(None)


@pytest.mark.parametrize("prior", [False, True])
def test_atomic_native_v2_receipts_and_original_keys(prior):
    with storage(initialize=False, prior=prior) as (_, _, connection, _, data, *held):
        trace = []
        connection.set_trace_callback(trace.append)
        session = _initialize_database_v2(connection, **data)
        assert sum(sql == "BEGIN IMMEDIATE" for sql in trace) == 1
        assert sum(sql == "COMMIT" for sql in trace) == 1
        assert not connection.in_transaction
        assert len(logical(connection)) == 39
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT daemon_paused,binding_state FROM projections"
        ).fetchone() == (1, "verification_pending")
        assert connection.execute(
            "SELECT binding_guard,control_revision,owner_run_id,shutdown_phase "
            "FROM command_runtime"
        ).fetchone() == (1, 0, lid(1).value, "idle")
        inspection = _inspect_bootstrap_v2(
            connection,
            projection_id=P,
            namespace=lid(3),
            nonce=lid(4),
            prior_config_nonce=lid(5) if prior else None,
        )
        assert inspection.current_operation.operation_id == lid(10)
        assert inspection.current_payload.initialized_schema_version.value == 2
        assert inspection.owner == data["bootstrap"].owner
        if prior:
            assert inspection.prior_operation.operation_id == lid(11)
            assert inspection.prior_payload.initialized_schema_version is None
        else:
            assert inspection.prior_operation is inspection.prior_payload is None
        for lease in held:
            locks.check_lock(lease)
        session.close()


@pytest.mark.parametrize(
    "prefix,committed",
    [
        ("BEGIN IMMEDIATE", False),
        ("CREATE TABLE command_runtime", False),
        ("INSERT INTO operation_bootstrap", False),
        ("PRAGMA user_version=2", False),
        ("COMMIT", True),
        ("SELECT state_instance_id,request_namespace,last_owner_run_id", True),
    ],
)
@pytest.mark.parametrize("error_type", [MemoryError, KeyboardInterrupt, SystemExit])
def test_real_native_ack_loss_pristine_or_committed_never_false_success(
    prefix, committed, error_type
):
    with storage(initialize=False) as (_, path, connection, _, data, *held):
        with native_fault(connection, prefix, error_type=error_type) as observation:
            expect_fixed(
                lambda: _initialize_database_v2(connection, **data),
                ErrorCode.PERSISTENCE_FAILURE,
            )
        assert observation["hits"] == 1
        if prefix == "BEGIN IMMEDIATE":
            assert observation["active"] is True
        if prefix == "COMMIT":
            assert observation["active"] is False
        assert observation["sqls"].count("BEGIN IMMEDIATE") == 1
        if committed:
            assert observation["sqls"].count("COMMIT") == 1
            assert "ROLLBACK" not in observation["sqls"]
        else:
            assert observation["sqls"].count("ROLLBACK") == 1
        closed(connection)
        assert writer_available(path)
        reopened = opened(path, configure=committed)
        try:
            if committed:
                result = _inspect_bootstrap_v2(
                    reopened,
                    projection_id=P,
                    namespace=lid(3),
                    nonce=lid(4),
                    prior_config_nonce=lid(5),
                )
                assert result.current_operation.operation_id == lid(10)
                assert result.prior_operation.operation_id == lid(11)
                assert len(logical(reopened)) == 39
            else:
                assert reopened.execute("PRAGMA user_version").fetchone() == (0,)
                assert logical(reopened) == {}
                session = _initialize_database_v2(reopened, **data)
                assert session._info == data["bootstrap"].owner
        finally:
            reopened.close()
        for lease in held:
            locks.check_lock(lease)


@pytest.mark.parametrize(
    "field,value",
    [
        ("commands", object()),
        ("bootstrap", object()),
        ("initial_projection", object()),
        ("source_binding", object()),
        ("target_binding", object()),
        ("initial_ruleset", object()),
    ],
)
def test_wrong_actual_input_types_refuse_before_any_sql_or_effect(field, value):
    with storage(initialize=False) as (root, _, connection, _, data, *_):
        before = tree(root)
        trace = []
        connection.set_trace_callback(trace.append)
        data[field] = value
        expect_fixed(
            lambda: _initialize_database_v2(connection, **data), ErrorCode.INVALID_INPUT
        )
        assert trace == [] and tree(root) == before
        assert connection.execute("SELECT 1").fetchone() == (1,)


@pytest.mark.parametrize(
    "field,change",
    [
        ("initial_projection", {"daemon_paused": False}),
        ("initial_projection", {"config_revision": Revision(1)}),
        ("initial_projection", {"last_owner_run_id": lid(90)}),
        ("source_binding", {"credential_revision": Revision(1)}),
        ("target_binding", {"binding_revision": Revision(2)}),
        ("bootstrap", {"bootstrap_nonce": lid(90)}),
    ],
)
def test_initial_lineage_and_pending_guards_precede_writes(field, change):
    with storage(initialize=False) as (root, _, connection, _, data, *_):
        before = tree(root)
        trace = []
        connection.set_trace_callback(trace.append)
        data[field] = replace(data[field], **change)
        expect_fixed(
            lambda: _initialize_database_v2(connection, **data), ErrorCode.INVALID_INPUT
        )
        assert trace == [] and tree(root) == before


def test_pristine_denial_and_external_transaction_are_not_owned_cleanup():
    with storage(initialize=False) as (_, path, connection, _, data, *_):
        connection.execute("CREATE TABLE unrelated(value INTEGER)")
        expect_fixed(
            lambda: _initialize_database_v2(connection, **data),
            ErrorCode.MAINTENANCE_REQUIRED,
        )
        assert logical(connection) == {"unrelated": ()}
        connection.execute("BEGIN IMMEDIATE")
        expect_fixed(
            lambda: _initialize_database_v2(connection, **data), ErrorCode.INVALID_INPUT
        )
        assert connection.in_transaction and not writer_available(path)
        connection.execute("ROLLBACK")
        assert writer_available(path)


@pytest.mark.parametrize("missing", [False, True])
def test_bounded_lookup_has_no_creation_or_lineage_publication(missing):
    with storage() as (_, _, connection, _, _, *_):
        before = logical(connection)
        result = _inspect_bootstrap_v2(
            connection,
            projection_id=P,
            namespace=lid(3),
            nonce=lid(99) if missing else lid(4),
            prior_config_nonce=None,
        )
        assert (result.current_operation is None) is missing
        assert result.prior_operation is result.prior_payload is None
        assert logical(connection) == before and not connection.in_transaction


@pytest.mark.parametrize("error_type", [MemoryError, KeyboardInterrupt, SystemExit])
def test_native_contender_detects_ack_loss_without_cleanup_negative(error_type):
    with storage(initialize=False) as (_, path, connection, _, _, *_):
        with (
            native_fault(
                connection, "BEGIN IMMEDIATE", error_type=error_type
            ) as observation,
            pytest.raises(error_type),
        ):
            connection.execute("BEGIN IMMEDIATE")
        assert observation["active"] is True and connection.in_transaction
        assert not writer_available(path)
        connection.execute("ROLLBACK")
        assert writer_available(path)


def kernel_owner_status(root):
    code = (
        "import fcntl,os,sys; fd=os.open(sys.argv[1],os.O_RDONLY); "
        "busy=False\ntry: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
        "except BlockingIOError: busy=True\nfinally: os.close(fd)\n"
        "print('busy' if busy else 'free')"
    )
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", code, str(root / "locks" / "owner.lock")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        output, errors = child.communicate(timeout=15)
        assert child.returncode == 0 and errors == b""
        assert output in {b"busy\n", b"free\n"}
        return output == b"busy\n"
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)


def test_real_os_owner_survives_storage_failure_until_explicit_release():
    with storage(initialize=False) as (root, _, connection, _, data, owner, _):
        assert kernel_owner_status(root)
        with native_fault(connection, "BEGIN IMMEDIATE"):
            expect_fixed(lambda: _initialize_database_v2(connection, **data))
        assert kernel_owner_status(root)
        locks.check_lock(owner)


@pytest.mark.parametrize(
    "statement",
    [statement for _, _, statements in FRESH_V2_REGISTRY for statement in statements],
    ids=lambda statement: "_".join(statement.split()[:4]),
)
def test_every_native_compiled_ddl_return_fault_rolls_back_exact_catalogue(statement):
    with storage(initialize=False) as (_, path, connection, _, data, *_):
        with native_fault(connection, statement) as observed:
            expect_fixed(
                lambda: _initialize_database_v2(connection, **data),
                ErrorCode.PERSISTENCE_FAILURE,
            )
        assert observed["hits"] == 1 and observed["active"] is True
        closed(connection)
        assert writer_available(path)
        reopened = opened(path)
        try:
            assert logical(reopened) == {}
            assert reopened.execute("PRAGMA user_version").fetchone() == (0,)
        finally:
            reopened.close()


@pytest.mark.parametrize(
    "prefix,occurrence",
    [
        ("INSERT INTO schema_metadata", 1),
        ("INSERT INTO schema_migrations", 1),
        ("INSERT INTO schema_migrations", 2),
        ("INSERT INTO projections", 1),
        ("INSERT INTO rulesets", 1),
        ("INSERT INTO binding_revisions", 1),
        ("INSERT INTO binding_revisions", 2),
        ("INSERT INTO bindings", 1),
        ("INSERT INTO bindings", 2),
        ("INSERT INTO history_checkpoints", 1),
        ("INSERT INTO command_runtime", 1),
        ("INSERT INTO operations", 1),
        ("INSERT INTO operations", 2),
        ("INSERT INTO operation_bootstrap", 1),
        ("INSERT INTO operation_bootstrap", 2),
        ("PRAGMA application_id=", 1),
        ("PRAGMA user_version=2", 1),
    ],
)
def test_each_initial_row_and_version_native_return_fault_keeps_pristine_state(
    prefix, occurrence
):
    with storage(initialize=False) as (_, path, connection, _, data, *_):
        with native_fault(connection, prefix, occurrence=occurrence) as observed:
            expect_fixed(
                lambda: _initialize_database_v2(connection, **data),
                ErrorCode.PERSISTENCE_FAILURE,
            )
        assert observed["hits"] == 1 and observed["matches"] == occurrence
        closed(connection)
        assert writer_available(path)
        fresh = opened(path)
        try:
            assert logical(fresh) == {}
            assert fresh.execute("PRAGMA user_version").fetchone() == (0,)
        finally:
            fresh.close()
