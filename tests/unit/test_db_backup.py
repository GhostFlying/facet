"""DB-19 partial: real WAL snapshot API, failure preservation, no full bundle."""

import os
import select
import sqlite3
import subprocess
import time
from threading import Thread

import pytest
from fakes.privacy import (
    MarkerKind,
    Profile,
    assert_private_boundary,
    inspect_files,
    inspect_sqlite,
    markers,
)
from test_db_intents import dispatch, prepare, setup
from test_db_repositories import job, publish, view
from test_db_repositories import state as state
from test_db_schema import P, create_state, lid

from facet.contracts import ErrorCode
from facet.db.codecs import SchemaVersion, StorageFailure
from facet.db.connection import _attach_writer
from facet.db.migration_backup import snapshot_database
from facet.db.repositories import jobs


def destination(tmp_path, *, name="snapshot.db"):
    path = tmp_path / name
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(descriptor)
    return path, sqlite3.connect(path, autocommit=True)


def test_snapshot_reads_committed_wal_and_reopens_exact_facts(state, tmp_path):
    path, connection, session, info = state
    original, _, _, _, prepared = setup(state)
    prepare(session, prepared)
    dispatched = dispatch(session, prepared)
    assert path.with_name(path.name + "-wal").stat().st_size > 0
    copied_path, copied = destination(tmp_path)
    changes = connection.total_changes
    receipt = snapshot_database(session, copied)
    assert receipt.schema_version == SchemaVersion(1)
    assert receipt.state_instance_id == info.state_instance_id
    assert receipt.request_namespace == info.request_namespace
    assert receipt.integrity_ok is True and connection.total_changes == changes
    assert copied.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert copied.execute("PRAGMA foreign_key_check").fetchall() == []
    copied.close()
    reopened = sqlite3.connect(copied_path, autocommit=True)
    copied_session = _attach_writer(reopened, info)
    copied_state = copied_path, reopened, copied_session, info
    with view(copied_state) as reader:
        attempt = reader.get_attempt(P, prepared.attempt_id)
        assert attempt.state.value == "dispatch_started"
        assert attempt.revision == dispatched.revision
        assert reader.get_job(P, original.job_id).state.value == "claimed"
    copied_session.close()
    with view(state) as reader:
        assert reader.get_attempt(P, prepared.attempt_id) == attempt


@pytest.mark.parametrize("existing", ["unrelated", "facet", "transaction"])
def test_snapshot_never_overwrites_existing_or_active_destination(
    state, tmp_path, existing
):
    _, source, session, _ = state
    path, copied = destination(tmp_path)
    if existing == "unrelated":
        copied.execute("CREATE TABLE private_marker(value TEXT)")
        copied.execute("INSERT INTO private_marker VALUES('synthetic-preserved')")
    elif existing == "facet":
        snapshot_database(session, copied)
    else:
        copied.execute("BEGIN")
    before = copied.execute(
        "SELECT type,name,sql FROM sqlite_schema ORDER BY type,name"
    ).fetchall()
    changes = source.total_changes
    with pytest.raises(StorageFailure):
        snapshot_database(session, copied)
    assert (
        copied.execute(
            "SELECT type,name,sql FROM sqlite_schema ORDER BY type,name"
        ).fetchall()
        == before
    )
    assert source.total_changes == changes
    if existing == "unrelated":
        assert copied.execute("SELECT value FROM private_marker").fetchall() == [
            ("synthetic-preserved",)
        ]
    if copied.in_transaction:
        copied.execute("ROLLBACK")
    copied.close()
    assert path.exists()


def test_snapshot_rejects_source_transaction_without_making_destination(
    state, tmp_path
):
    _, _, session, _ = state
    publish(session)
    _, copied = destination(tmp_path)
    with session.transaction() as uow:
        with pytest.raises(StorageFailure):
            snapshot_database(session, copied)
        assert uow._active
    assert copied.execute("SELECT name FROM sqlite_schema").fetchall() == []
    copied.close()


@pytest.mark.parametrize("bad", ["closed", "wrong_thread", "foreign", "reader"])
def test_snapshot_requires_current_actual_writer_session(state, tmp_path, bad):
    _, _, session, _ = state
    _, copied = destination(tmp_path)
    errors = []
    if bad == "closed":
        session.close()
        with pytest.raises(StorageFailure):
            snapshot_database(session, copied)
    elif bad == "wrong_thread":

        def run():
            try:
                snapshot_database(session, copied)
            except StorageFailure as error:
                errors.append(error.code)

        worker = Thread(target=run)
        worker.start()
        worker.join(3)
        assert not worker.is_alive() and errors == [ErrorCode.OWNER_UNAVAILABLE]
    elif bad == "reader":
        with view(state) as reader:
            assert reader.call("snapshot_reject_read_source", P) == {
                "actual_child_assertions": True
            }
    else:

        class Foreign:
            @property
            def _connection(self):
                raise AssertionError("must not access an arbitrary object")

        with pytest.raises(StorageFailure):
            snapshot_database(Foreign(), copied)
    assert copied.execute("SELECT name FROM sqlite_schema").fetchall() == []
    copied.close()


@pytest.mark.parametrize(
    "failure", ["read_only", "read_only_uri", "authorizer", "same_source", "alias"]
)
def test_snapshot_failure_returns_no_receipt_and_preserves_source(
    state, tmp_path, failure
):
    source_path, connection, session, _ = state
    publish(session)
    path, copied = destination(tmp_path)
    if failure == "read_only":
        copied.execute("PRAGMA query_only=ON")
    elif failure == "read_only_uri":
        copied.close()
        copied = sqlite3.connect(f"file:{path}?mode=ro", uri=True, autocommit=True)
    elif failure == "authorizer":
        copied.set_authorizer(lambda *args: sqlite3.SQLITE_DENY)
    elif failure == "alias":
        copied.close()
        copied = sqlite3.connect(source_path, autocommit=True)
    else:
        copied.close()
        copied = connection
    changes = connection.total_changes
    with pytest.raises(StorageFailure) as error:
        snapshot_database(session, copied)
    assert str(error.value) in {code.value for code in ErrorCode}
    assert connection.total_changes == changes
    if copied is not connection:
        copied.set_authorizer(None)
        copied.close()
    with view(state) as reader:
        assert reader.get_projection(P).ruleset_revision.value == 1


def test_changed_source_owner_cannot_get_a_snapshot_receipt(state, tmp_path):
    _, connection, session, _ = state
    _, copied = destination(tmp_path)
    # Violating external writer is a test-only closed lineage failure fixture.
    connection.execute(
        "UPDATE projections SET last_owner_run_id=? WHERE projection_id=?",
        (lid(999).value, P.value),
    )
    with pytest.raises(StorageFailure) as error:
        snapshot_database(session, copied)
    assert error.value.code is ErrorCode.REQUEST_LINEAGE_MISMATCH
    assert copied.execute("SELECT name FROM sqlite_schema").fetchall() == []
    copied.close()


def test_snapshot_does_not_contain_an_uncommitted_job(state, tmp_path):
    _, connection, session, _ = state
    publish(session)
    _, copied = destination(tmp_path)
    # Actual failed write boundary rather than copying only the main file.
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.enqueue(uow, P, job(123))
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)
    snapshot_database(session, copied)
    assert copied.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)
    copied.close()


def test_backup_busy_is_bounded_and_preserves_pristine_destination(state, tmp_path):
    _, _, session, _ = state
    path, copied = destination(tmp_path)
    # A violating competitor holds the supplied destination's RESERVED lock.
    # Real backup_step must fail, not internally sleep/retry without a bound.
    import sys

    script = (
        "import sqlite3,sys\n"
        "c=sqlite3.connect(sys.argv[1],autocommit=True)\n"
        "c.execute('BEGIN IMMEDIATE')\n"
        "print('locked',flush=True)\n"
        "sys.stdin.readline()\n"
        "c.execute('ROLLBACK')\n"
        "c.close()\n"
    )
    worker = subprocess.Popen(
        [sys.executable, "-c", script, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([worker.stdout], [], [], 3)[0]
        assert worker.stdout.readline().strip() == "locked"
        started = time.monotonic()
        with pytest.raises(StorageFailure) as error:
            snapshot_database(session, copied)
        assert time.monotonic() - started < 2
        assert error.value.code is ErrorCode.DATABASE_UNAVAILABLE
        assert copied.execute("PRAGMA busy_timeout").fetchone() == (5000,)
        assert copied.execute("SELECT name FROM sqlite_schema").fetchall() == []
    finally:
        try:
            worker.communicate("release\n", timeout=3)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.communicate(timeout=3)
            raise AssertionError("test-owned lock child failed to stop") from None
        assert worker.returncode == 0
        copied.close()


def test_main_file_copy_is_not_a_wal_snapshot(state, tmp_path):
    path, _, session, info = state
    publish(session)
    copied_path = tmp_path / "wrong-main-only.db"
    copied_path.write_bytes(path.read_bytes())
    os.chmod(copied_path, 0o600)
    copied = sqlite3.connect(copied_path, autocommit=True)
    # Valid current committed data exists only in WAL. A main-only copy cannot
    # provide the exact database identity/catalogue and is not repaired empty.
    with pytest.raises(StorageFailure):
        _attach_writer(copied, info)
    assert copied_path.exists()


def test_snapshot_cells_active_files_and_failure_outputs_have_no_private_content(
    tmp_path, capsys, caplog
):
    sentinels = markers()
    forbidden = next(m.value for m in sentinels if m.kind is MarkerKind.CONTENT)

    class FailingBackup(sqlite3.Connection):
        fail = False

        def backup(self, target, **kwargs):
            if self.fail:
                raise sqlite3.OperationalError(forbidden)
            return super().backup(target, **kwargs)

    connection, session, _ = create_state(
        tmp_path / "metadata.db", factory=FailingBackup
    )
    path, copied = destination(tmp_path)
    try:
        publish(session)
        connection.fail = True
        with pytest.raises(StorageFailure) as error:
            snapshot_database(session, copied)
        assert error.value.code is ErrorCode.PERSISTENCE_FAILURE
        assert_private_boundary(str(error.value), sentinels, Profile.LOG)
        assert_private_boundary(repr(error.value), sentinels, Profile.LOG)
        assert copied.execute("SELECT name FROM sqlite_schema").fetchall() == []
        connection.fail = False
        snapshot_database(session, copied)
        inspect_sqlite(connection, sentinels)
        inspect_sqlite(copied, sentinels)
        inspect_files(tmp_path, list(tmp_path.iterdir()), sentinels)
        # The failure marker was never bound to SQL or copied then deleted.
        captured = capsys.readouterr()
        assert_private_boundary(captured.out, sentinels, Profile.LOG)
        assert_private_boundary(captured.err, sentinels, Profile.LOG)
        assert_private_boundary(caplog.text, sentinels, Profile.LOG)
        copied.close()
        reopened = sqlite3.connect(path, autocommit=True)
        inspect_sqlite(reopened, sentinels)
        reopened.close()
    finally:
        copied.close()
        session.close()
