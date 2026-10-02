"""SI02/03/05: actual fresh-run CAS, owned native faults and creator refusal."""

import importlib
import json
import os
import select
import signal
import sqlite3
import subprocess
import sys
from contextlib import suppress
from dataclasses import fields, replace
from pathlib import Path
from threading import Thread

import pytest
from integration.test_runtime_os_locks import tree
from test_command_bootstrap_storage import (
    SENTINEL,
    closed,
    expect_fixed,
    kernel_owner_status,
    logical,
    native_fault,
    opened,
    storage,
    writer_available,
)
from unit.test_db_schema import NOW, P, lid

from facet.contracts import ErrorCode
from facet.db import connection as adapters
from facet.db.command_records import LocalCommandKind, ShutdownPhase
from facet.db.connection import (
    _begin_owner_session_v2,
    _initialize_database_v2,
    _inspect_bootstrap_v2,
)
from facet.db.models import OwnerSessionInfo
from facet.runtime import locks, private_root


def new_owner(n=20):
    return OwnerSessionInfo(lid(n), lid(2), lid(3))


def begin(connection, *, owner=None, previous=None):
    return _begin_owner_session_v2(
        connection,
        owner=new_owner() if owner is None else owner,
        expected_previous_run=lid(1) if previous is None else previous,
        now=NOW,
    )


def inspect(connection):
    return _inspect_bootstrap_v2(
        connection,
        projection_id=P,
        namespace=lid(3),
        nonce=lid(4),
        prior_config_nonce=lid(5),
    )


def test_fresh_owner_changes_only_exact_two_columns_with_nonempty_business_facts(
    monkeypatch,
):
    # Reuse accepted genuine transaction/claim/intent producers, not forged
    # sessions or a dummy type participant. Their own source remains unchanged.
    monkeypatch.syspath_prepend(str(Path(__file__).parent / "unit"))
    intents = importlib.import_module("test_db_intents")
    with storage() as (_, path, connection, session, data, *_):
        actual = (path, connection, session, data["bootstrap"].owner)
        _, _, _, _, prepared = intents.setup(actual)
        intents.prepare(session, prepared)
        intents.dispatch(session, prepared)
        from facet.db.codecs import ThreadStopReason
        from facet.db.repositories import policy

        with session.transaction() as uow:
            policy.stop_thread(
                uow,
                P,
                prepared.source_thread_id,
                prepared.generation,
                NOW,
                ThreadStopReason.BLACKLIST,
            )
        connection.execute("UPDATE projections SET daemon_paused=1")
        connection.execute(
            "UPDATE projections SET restore_state='revalidation_required'"
        )
        from test_command_records import operation

        from facet.db.command_store import _OPERATION_COLUMNS, _scalar

        shutdown = replace(
            operation(),
            operation_id=lid(50),
            request_nonce=lid(51),
            command=LocalCommandKind.DAEMON_SHUTDOWN,
        )
        values = tuple(_scalar(getattr(shutdown, f.name)) for f in fields(shutdown))
        connection.execute(
            f"INSERT INTO operations({_OPERATION_COLUMNS}) "
            f"VALUES({','.join('?' for _ in values)})",
            values,
        )
        connection.execute(
            "INSERT INTO operation_controls VALUES(?,?,1,1,0,1)",
            (P.value, lid(50).value),
        )
        connection.execute(
            "UPDATE command_runtime SET control_revision=1,"
            "shutdown_phase=?,shutdown_operation_id=?,"
            "shutdown_owner_run_id=?",
            (ShutdownPhase.REQUESTED.value, lid(50).value, lid(1).value),
        )
        assert connection.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (1,)
        assert connection.execute("SELECT state FROM insert_attempts").fetchone() == (
            "dispatch_started",
        )
        before = logical(connection)
        assert before["tracked_threads"] and before["sync_jobs"]
        session.close()
        fresh = opened(path, configure=True)
        try:
            attached = begin(fresh)
            after = logical(fresh)
            for table, rows in before.items():
                if table == "projections":
                    assert after[table] == tuple(
                        (*row[:10], lid(20).value, *row[11:]) for row in rows
                    )
                elif table == "command_runtime":
                    assert after[table] == tuple(
                        (*row[:3], lid(20).value, *row[4:]) for row in rows
                    )
                else:
                    assert after[table] == rows
            assert attached._info == new_owner()
            assert inspect(fresh).current_operation.operation_id == lid(10)
            attached.close()
        finally:
            with suppress(sqlite3.Error):
                fresh.close()


@pytest.mark.parametrize(
    "variant",
    ["stale", "equal", "instance", "namespace", "mixed", "wrong_type", "wrong_now"],
)
def test_fresh_owner_lineage_refusals_are_before_begin_and_keep_original_owner(variant):
    with storage() as (_, _, connection, session, _, *_):
        owner, previous, now = new_owner(), lid(1), NOW
        code = ErrorCode.REQUEST_LINEAGE_MISMATCH
        if variant == "stale":
            previous = lid(80)
        elif variant == "equal":
            owner = new_owner(1)
        elif variant == "instance":
            owner = replace(owner, state_instance_id=lid(80))
        elif variant == "namespace":
            owner = replace(owner, request_namespace=lid(80))
        elif variant == "mixed":
            connection.execute(
                "UPDATE command_runtime SET owner_run_id=?", (lid(80).value,)
            )
        elif variant == "wrong_type":
            previous, code = object(), ErrorCode.INVALID_INPUT
        elif variant == "wrong_now":
            now, code = object(), ErrorCode.INVALID_INPUT
        before = logical(connection)
        trace = []
        connection.set_trace_callback(trace.append)
        expect_fixed(
            lambda: _begin_owner_session_v2(
                connection, owner=owner, expected_previous_run=previous, now=now
            ),
            code,
        )
        assert not any(sql.startswith("BEGIN") for sql in trace)
        assert logical(connection) == before and not connection.in_transaction
        session._check()


@pytest.mark.parametrize("entry", ["owner", "inspection"])
@pytest.mark.parametrize("error_type", [MemoryError, KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize(
    "prefix", ["BEGIN", "COMMIT", "SELECT state_instance_id,request_namespace,"]
)
def test_native_owner_and_inspection_ack_loss_requires_reopen(
    entry, prefix, error_type
):
    if entry == "inspection" and prefix.startswith("SELECT state_instance"):
        prefix = "SELECT p.state_instance_id,p.request_namespace,"
    with storage() as (_, path, connection, _, _, *_):
        before = logical(connection)
        with native_fault(connection, prefix, error_type=error_type) as observation:
            expect_fixed(
                lambda: begin(connection) if entry == "owner" else inspect(connection),
                ErrorCode.PERSISTENCE_FAILURE,
            )
        assert observation["hits"] == 1
        if prefix == "BEGIN":
            assert observation["active"] is True
        if prefix == "COMMIT":
            assert observation["active"] is False
            assert observation["sqls"].count("COMMIT") == 1
            assert "ROLLBACK" not in observation["sqls"]
        elif prefix.startswith("SELECT state_instance"):
            assert "ROLLBACK" not in observation["sqls"]
        else:
            assert observation["sqls"].count("ROLLBACK") == 1
        closed(connection)
        assert writer_available(path)
        fresh = opened(path, configure=True)
        try:
            result = inspect(fresh)
            published = entry == "owner" and prefix != "BEGIN"
            assert result.owner.owner_run_id == lid(20 if published else 1)
            after = logical(fresh)
            assert after["operations"] == before["operations"]
            assert after["operation_bootstrap"] == before["operation_bootstrap"]
        finally:
            fresh.close()


@pytest.mark.parametrize(
    "event,name", [("c_return", "execute"), ("c_call", "close"), ("c_return", "close")]
)
@pytest.mark.parametrize("error_type", [MemoryError, KeyboardInterrupt, SystemExit])
def test_real_rollback_and_close_uncertainty_one_attempt_no_false_session(
    event, name, error_type
):
    with storage(initialize=False) as (root, path, connection, _, data, *_):
        # Native authorizer denial after BEGIN is the independent failure that
        # enters cleanup. A second actual native acknowledgement/call fault
        # then proves rollback/close disposition, not a fake execute participant.
        def authorize(action, first, _second, _database, _trigger):
            if action == sqlite3.SQLITE_CREATE_TABLE and first == "command_runtime":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorize)
        with native_fault(
            connection, "ROLLBACK", event=event, name=name, error_type=error_type
        ) as observed:
            expect_fixed(
                lambda: _initialize_database_v2(connection, **data),
                ErrorCode.PERSISTENCE_FAILURE,
            )
        assert observed["hits"] == 1
        assert kernel_owner_status(root)
        if name == "execute" or event == "c_return":
            closed(connection)
        else:
            # Close-before-call remains physically open but idle after its
            # successful rollback. Production did not retry uncertain close;
            # the test observer explicitly retires its own native handle.
            assert not connection.in_transaction
            connection.close()
        assert writer_available(path)
        fresh = opened(path)
        try:
            assert logical(fresh) == {}
            assert fresh.execute("PRAGMA user_version").fetchone() == (0,)
        finally:
            fresh.close()


@pytest.mark.parametrize("error_type", [MemoryError, KeyboardInterrupt, SystemExit])
def test_rollback_native_call_denied_close_releases_real_transaction(
    monkeypatch, error_type
):
    with storage(initialize=False) as (_, path, connection, _, data, *_):
        original = adapters._command_code
        observed = {"fault": None}

        def arm_cleanup(error):
            # The native BEGIN-return fault disables Python profiling. Rearm
            # only the actual owned cleanup boundary, without replacing SQLite.
            observed["fault"] = native_fault(
                connection, "", event="c_call", error_type=error_type
            )
            observed["fault"].__enter__()
            return original(error)

        monkeypatch.setattr(adapters, "_command_code", arm_cleanup)
        with native_fault(
            connection, "BEGIN IMMEDIATE", error_type=error_type
        ) as began:
            expect_fixed(
                lambda: _initialize_database_v2(connection, **data),
                ErrorCode.PERSISTENCE_FAILURE,
            )
        observed["fault"].__exit__(None, None, None)
        assert began["active"] is True
        closed(connection)
        assert writer_available(path)


@pytest.mark.parametrize("operation", ["close", "transaction", "invalidate"])
def test_foreign_strong_thread_refusal_never_poison_or_close_genuine_session(operation):
    with storage() as (root, path, connection, session, _, *_):
        before = logical(connection)
        failures = []

        def foreign():
            try:
                if operation == "invalidate":
                    session._invalidate()
                else:
                    getattr(session, operation)()
            except Exception as error:
                failures.append(error)

        worker = Thread(target=foreign)
        worker.start()
        worker.join(timeout=15)
        assert not worker.is_alive() and len(failures) == 1
        assert failures[0].code is ErrorCode.OWNER_UNAVAILABLE
        session._check()
        assert logical(connection) == before and writer_available(path)
        assert kernel_owner_status(root)


def test_foreign_exit_does_not_retire_real_external_uow_or_claim_owner():
    with storage() as (_, path, connection, session, _, *_):
        uow = session.transaction()
        with uow:
            failures = []
            worker = Thread(target=lambda: _foreign_exit(uow, failures))
            worker.start()
            worker.join(timeout=15)
            assert not worker.is_alive()
            assert failures == [ErrorCode.OWNER_UNAVAILABLE]
            assert connection.in_transaction and session._uow is uow
            assert not writer_available(path)
        assert writer_available(path)
        assert not connection.in_transaction and session._uow is None


def _foreign_exit(uow, failures):
    try:
        uow.__exit__(None, None, None)
    except Exception as error:
        failures.append(error.code)


def test_real_fork_refuses_copied_session_without_parent_cleanup():
    with storage() as (_, _, connection, session, _, *_):
        read, write = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(read)
            try:
                session.close()
            except Exception as error:
                os.write(write, error.code.value.encode())
            finally:
                os.close(write)
                os._exit(0)
        os.close(write)
        try:
            assert select.select([read], [], [], 15)[0]
            assert os.read(read, 128) == b"owner_unavailable"
            assert os.waitpid(child, 0)[1] == 0
            child = None
            session._check()
            assert inspect(connection).owner == session._info
        finally:
            os.close(read)
            if child is not None:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)


CAS_CHILD = r"""
import sqlite3,sys
sys.path.insert(0,sys.argv[1])
from facet.contracts import LocalId,Timestamp
from facet.db.connection import _configure_writer,_begin_owner_session_v2
from facet.db.models import OwnerSessionInfo
from facet.runtime import locks,private_root
from datetime import UTC,datetime
root=private_root.open_existing_root(sys.argv[2])
with root,locks.acquire_owner(root) as owner:
    with locks.acquire_view(root,locks.LockMode.EXCLUSIVE,owner=owner):
        connection=sqlite3.connect(sys.argv[3],autocommit=True)
        _configure_writer(connection,creating=False)
        ids=[LocalId(value) for value in sys.argv[4:8]]
        session=_begin_owner_session_v2(connection,owner=OwnerSessionInfo(*ids[:3]),
            expected_previous_run=ids[3],now=Timestamp(datetime(2026,10,3,tzinfo=UTC)))
        print('published',flush=True)
        if sys.stdin.buffer.read(1)!=b'x': raise SystemExit(2)
        session.close()
print('closed',flush=True)
"""


@pytest.mark.parametrize("crash", [False, True])
def test_actual_two_process_kernel_owner_cas_and_crash_after_publication(crash):
    with storage() as (root, path, connection, session, _, owner, view):
        before = logical(connection)
        session.close()
        locks.release_lock(view)
        locks.release_lock(owner)
        child = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-c",
                CAS_CHILD,
                str(Path(__file__).parents[1] / "src"),
                str(root),
                str(path),
                lid(20).value,
                lid(2).value,
                lid(3).value,
                lid(1).value,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            assert select.select([child.stdout], [], [], 15)[0]
            assert child.stdout.readline() == b"published\n"
            assert kernel_owner_status(root)
            fresh = opened(path, configure=True)
            try:
                assert inspect(fresh).owner == new_owner()
                assert logical(fresh)["operations"] == before["operations"]
                expect_fixed(lambda: begin(fresh), ErrorCode.REQUEST_LINEAGE_MISMATCH)
            finally:
                fresh.close()
            if crash:
                child.kill()
            else:
                child.stdin.write(b"x")
                child.stdin.flush()
            output, errors = child.communicate(timeout=15)
            assert errors == b""
            assert child.returncode == (-signal.SIGKILL if crash else 0)
            assert output == (b"" if crash else b"closed\n")
            assert not kernel_owner_status(root)
            with (
                private_root.open_existing_root(str(root)) as new_root,
                locks.acquire_owner(new_root) as new_lock,
                locks.acquire_view(new_root, locks.LockMode.EXCLUSIVE, owner=new_lock),
            ):
                reopened = opened(path, configure=True)
                try:
                    final = begin(reopened, owner=new_owner(21), previous=lid(20))
                    assert final._info == new_owner(21)
                    assert inspect(reopened).current_operation.operation_id == lid(10)
                    final.close()
                finally:
                    with suppress(sqlite3.Error):
                        reopened.close()
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)


def test_snapshot_v2_barrier_keeps_destination_row_factory_and_native_settings(
    tmp_path,
):
    from facet.db.migration_backup import snapshot_database

    with storage() as (_, _, _, session, _, *_):
        destination = opened(tmp_path / "snapshot.db")

        def sentinel_factory(_cursor, _row):
            return SENTINEL

        destination.row_factory = sentinel_factory
        destination.set_authorizer(lambda *_args: sqlite3.SQLITE_DENY)
        before = tree(tmp_path)
        try:
            expect_fixed(
                lambda: snapshot_database(session, destination),
                ErrorCode.UNSUPPORTED_VERSION,
            )
            assert destination.row_factory is sentinel_factory
            assert tree(tmp_path) == before
        finally:
            destination.set_authorizer(None)
            destination.close()


READ_CHILD = r"""
import json,sys
sys.path[:0]=[sys.argv[1],sys.argv[2]]
try:
    import db_view_bootstrap as boot
    latch=boot._begin_read_bootstrap()
    facts=latch.probe_runtime()
    import db_view_adapter as fixed
    from facet.contracts import LocalId,ErrorCode
    from facet.db import read_views as views
    from facet.db.connection import _attach_view
    from facet.db.codecs import StorageFailure
    actual=fixed._runtime(facts)
    views._PROVIDER_TYPES=(fixed.FixedReadProvider,)
    views._QUALIFIED_RUNTIMES=(actual,)
    instance=LocalId(sys.argv[4])
    provider=fixed.FixedReadProvider(latch,sys.argv[3],instance=instance)
    provider.seal=views._issue_read_seal(provider,actual)
    lease=views._issue_read_lease(provider.seal,views.ViewMode.STOPPED_CLEAN)
    connection,permit=provider.open_bound(lease)
    statements=[]
    connection.set_trace_callback(statements.append)
    rejected=False
    try:
        raise ValueError('SYNTHETIC_READ_CALLER_PRIVATE_SENTINEL')
    except ValueError:
        try:
            reader=_attach_view(connection,instance,permit=permit)
        except StorageFailure as error:
            assert error.code is ErrorCode.UNSUPPORTED_VERSION
            assert error.__context__ is None and error.__cause__ is None
            rejected=True
    if rejected:
        assert not any(sql.startswith('PRAGMA query_only=') or
            sql.startswith('PRAGMA trusted_schema=') or
            sql.startswith('PRAGMA foreign_keys=') for sql in statements)
    else:
        assert connection.execute('PRAGMA query_only').fetchone()==(1,)
        reader.close()
    assert not provider.inventory and not provider.resources
    assert provider.events[-2:]==['retired','released']
    assert fixed._lock_available(sys.argv[3],'owner.lock')
    assert fixed._lock_available(sys.argv[3],'view.lock')
    print(json.dumps({'status':'refused' if rejected else 'attached',
        'retired':True,'kernel_released':True}))
except BaseException:
    print('{"status":"test_failed"}')
    raise SystemExit(1) from None
"""


@pytest.mark.parametrize("version", [1, 2])
def test_actual_fresh_read_provider_v1_positive_v2_preconfiguration_refusal(version):
    with storage(initialize=version == 2) as (
        root,
        path,
        connection,
        session,
        data,
        owner,
        view,
    ):
        if version == 1:
            session = adapters._initialize_database(
                connection,
                **{name: value for name, value in data.items() if name != "commands"},
            )
        session.close()
        assert not path.with_name(path.name + "-wal").exists()
        assert not path.with_name(path.name + "-shm").exists()
        # A separate closed-clean, owner-only synthetic fixture consumes the
        # retained actual test producer. This is not a shipping read issuer,
        # backup protocol or native-file opener/provenance implementation.
        read_root = root.parent / "closed-read-fixture"
        read_root.mkdir(mode=0o700)
        for name in ("owner.lock", "view.lock", "metadata.db"):
            descriptor = os.open(
                read_root / name, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600
            )
            try:
                if name == "metadata.db":
                    content = path.read_bytes()
                    assert len(content) < 16 * 1024 * 1024
                    assert os.write(descriptor, content) == len(content)
            finally:
                os.close(descriptor)
        before = tree(read_root)
        child = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-S",
                "-c",
                READ_CHILD,
                str(Path(__file__).parent / "unit"),
                str(Path(__file__).parents[1] / "src"),
                str(read_root),
                lid(2).value,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            output, errors = child.communicate(timeout=15)
            assert child.returncode == 0 and errors == b""
            assert len(output) <= 256
            assert json.loads(output) == {
                "status": "attached" if version == 1 else "refused",
                "retired": True,
                "kernel_released": True,
            }
            assert tree(read_root) == before
            locks.check_lock(owner)
            locks.check_lock(view)
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)


@pytest.mark.parametrize("version", [1, 2])
def test_actual_migration_scope_v1_noop_v2_refusal_before_begin_backup_or_step(
    version, monkeypatch
):
    monkeypatch.syspath_prepend(str(Path(__file__).parent / "unit"))
    fixture = importlib.import_module("test_db_migration_entry")
    from facet.db import migration_entry as engine

    with storage(initialize=version == 2) as (
        root,
        path,
        connection,
        session,
        data,
        owner,
        view,
    ):
        if version == 1:
            session = adapters._initialize_database(
                connection,
                **{name: value for name, value in data.items() if name != "commands"},
            )
        expected = fixture.context_files(connection)
        session.close()
        database = root / "database.db"
        path.rename(database)
        credentials = root / "credentials"
        credentials.mkdir(mode=0o700)
        for role in ("source", "target"):
            fixture.write_private(credentials / (role + ".lock"), b"")
        for name, content in expected.items():
            destination = (
                credentials if name in ("source.json", "target.json") else root
            )
            fixture.write_private(destination / name, content)
        locks.release_lock(view)
        locks.release_lock(owner)
        monkeypatch.setattr(engine, "_MIGRATION_PROVIDER_TYPES", (fixture.Scope,))
        with fixture.Scope(root) as scope:
            # The existing fixed test producer owns real owner/view and both
            # credentials. Actual private file/context checks back its supplied
            # native handle; no bool/type stand-in or production enrolment.
            scope.owner = new_owner(99)
            scope.file_identity = fixture.private_file(database)
            scope.expected_files = expected
            scope.connection = opened(database, configure=True)
            scope.held()
            trace = []
            scope.connection.set_trace_callback(trace.append)
            before = tree(root)
            if version == 1:
                result = engine.migrate_existing(
                    scope.connection, scope.owner, backup=None, provider=scope
                )
                assert result.disposition == "unchanged"
                assert result.to_version.value == 1
            else:
                expect_fixed(
                    lambda: engine.migrate_existing(
                        scope.connection, scope.owner, backup=None, provider=scope
                    ),
                    ErrorCode.UNSUPPORTED_VERSION,
                )
            assert not any(
                sql.startswith("BEGIN")
                or sql.startswith("CREATE")
                or sql.startswith("INSERT")
                for sql in trace
            )
            assert scope.bundle is scope.receipt is None
            assert not scope.connection.in_transaction
            assert tree(root) == before
            scope.held()


@pytest.mark.parametrize("entry", ["owner", "inspection"])
@pytest.mark.parametrize(
    "variant",
    ["busy", "trust", "query", "sync", "fk", "row_factory", "external_transaction"],
)
def test_real_v2_setting_and_external_transaction_refusal_before_owned_begin(
    entry, variant
):
    with storage() as (_, path, connection, session, _, *_):
        if variant == "row_factory":
            connection.row_factory = sqlite3.Row
        elif variant == "external_transaction":
            connection.execute("BEGIN IMMEDIATE")
        else:
            statement = {
                "busy": "PRAGMA busy_timeout=0",
                "trust": "PRAGMA trusted_schema=ON",
                "query": "PRAGMA query_only=ON",
                "sync": "PRAGMA synchronous=NORMAL",
                "fk": "PRAGMA foreign_keys=OFF",
            }[variant]
            connection.execute(statement)
        trace = []
        connection.set_trace_callback(trace.append)
        expect_fixed(
            lambda: begin(connection) if entry == "owner" else inspect(connection)
        )
        assert not any(
            sql.startswith("BEGIN")
            or sql.startswith("COMMIT")
            or sql.startswith("ROLLBACK")
            or sql.startswith("UPDATE")
            for sql in trace
        )
        assert connection.in_transaction is (variant == "external_transaction")
        session._check()
        assert writer_available(path) is (variant != "external_transaction")
        if variant == "external_transaction":
            connection.execute("ROLLBACK")


@pytest.mark.parametrize("entry", ["initialize", "owner", "inspection"])
def test_real_native_commit_denial_never_returns_result_and_reopen_is_truthful(entry):
    with storage(initialize=entry != "initialize") as (
        _,
        path,
        connection,
        _,
        data,
        *_,
    ):
        observed = []

        def authorize(action, first, _second, _database, _trigger):
            if action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT":
                observed.append(connection.in_transaction)
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorize)
        expect_fixed(
            lambda: (
                _initialize_database_v2(connection, **data)
                if entry == "initialize"
                else begin(connection)
                if entry == "owner"
                else inspect(connection)
            ),
            ErrorCode.PERSISTENCE_FAILURE,
        )
        assert observed == [True]
        closed(connection)
        assert writer_available(path)
        fresh = opened(path, configure=entry != "initialize")
        try:
            if entry == "initialize":
                assert logical(fresh) == {}
                assert fresh.execute("PRAGMA user_version").fetchone() == (0,)
            else:
                result = inspect(fresh)
                assert result.owner.owner_run_id == lid(1)
                assert result.current_operation.operation_id == lid(10)
                assert result.prior_operation.operation_id == lid(11)
        finally:
            fresh.close()
