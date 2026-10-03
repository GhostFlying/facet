"""DB-18: real SIGKILL at SQL boundaries, not power loss or runtime lock proof.

Each child and database is test-owned. Reopen uses the same synthetic owner
lineage only to inspect library facts; production new-owner publication/claim
reconstruction remains M1-03's separate integration gate.
"""

import os
import select
import signal
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fakes.network import deny_network
from fakes.privacy import inspect_files, inspect_sqlite, markers
from test_db_intents import dispatch, prepare, setup
from test_db_repositories import view
from test_db_schema import P, create_state, lid

from facet.contracts import ErrorCode, InsertState, Revision
from facet.db.codecs import StorageFailure
from facet.db.connection import _attach_writer
from facet.db.models import RevisionGuard
from facet.db.repositories import intents, jobs


def _boundary(name):
    print(name, flush=True)
    # Blocking is only a test rendezvous. The parent kills this exact child PID.
    sys.stdin.readline()
    raise AssertionError("expected test-owned SIGKILL")


def _worker(mode, path):
    with deny_network():
        if mode == "initialize_open":

            class BeforeInitializationCommit(sqlite3.Connection):
                def execute(self, sql, parameters=()):
                    if sql == "COMMIT":
                        _boundary(mode)
                    return super().execute(sql, parameters)

            create_state(path, factory=BeforeInitializationCommit)
            raise AssertionError("initialization boundary was not reached")
        connection, session, info = create_state(path)
        state = path, connection, session, info
        _, _, _, _, row = setup(state)
        if mode == "prepare_open":
            with session.transaction() as uow:
                intents.prepare_attempt(uow, P, row, RevisionGuard(Revision(1)))
                _boundary(mode)
        prepare(session, row)
        if mode == "prepared":
            assert not connection.in_transaction
            _boundary(mode)
        if mode == "dispatch_open":
            with session.transaction() as uow:
                intents.mark_dispatch(
                    uow,
                    P,
                    row.attempt_id,
                    row.claim_id,
                    row.prepared_at,
                    RevisionGuard(Revision(0)),
                )
                _boundary(mode)
        dispatch(session, row)
        assert not connection.in_transaction
        _boundary(mode)


def _kill_at(mode, path):
    repo = Path(__file__).resolve().parents[2]
    # Explicit synthetic test helper/import paths; no mailbox credentials.
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.pathsep.join((str(repo / "src"), str(repo / "tests"))),
    }
    worker = subprocess.Popen(
        [sys.executable, __file__, mode, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        assert select.select([worker.stdout], [], [], 8)[0]
        line = worker.stdout.readline().strip()
        if line != mode:
            stdout, stderr = worker.communicate(timeout=3)
            pytest.fail(f"test worker did not reach named boundary: {stdout} {stderr}")
        worker.kill()
        stdout, stderr = worker.communicate(timeout=5)
        assert worker.returncode == -signal.SIGKILL
        assert not stdout and not stderr
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.communicate(timeout=5)


@pytest.mark.parametrize(
    "mode,state_name,phase,revision",
    [
        ("prepare_open", None, "preparing", None),
        ("prepared", InsertState.PREPARED, "preparing", 0),
        ("dispatch_open", InsertState.PREPARED, "preparing", 0),
        ("dispatched", InsertState.DISPATCH_STARTED, "dispatching", 1),
    ],
)
def test_sigkill_insert_boundaries_keep_old_or_complete_factual_group(
    tmp_path, mode, state_name, phase, revision
):
    path = tmp_path / "metadata.db"
    _kill_at(mode, path)
    from test_db_schema import bootstrap_rows

    info, _, _, _ = bootstrap_rows()
    connection = sqlite3.connect(path, autocommit=True)
    session = _attach_writer(connection, info)
    state = path, connection, session, info
    try:
        with view(state) as reader:
            row = reader.get_attempt(P, lid(200))
            original = reader.get_job(P, lid(100))
            assert original.state.value == "claimed" and original.revision.value == 1
            if state_name is None:
                assert row is None
            else:
                assert row.state is state_name and row.revision == Revision(revision)
                assert row.target_message_id is None and row.result_at is None
                assert reader.counts(P, None).confirmed_mappings.value == 0
        assert connection.execute(
            "SELECT phase FROM job_claims WHERE job_id=?", (lid(100).value,)
        ).fetchone() == (phase,)
        if mode == "dispatched":
            # An uncertain marker cannot be turned into an ordinary insert retry.
            with pytest.raises(StorageFailure), session.transaction() as uow:
                jobs.defer_job(
                    uow,
                    P,
                    original.job_id,
                    "retry_wait",
                    ErrorCode.NETWORK_UNAVAILABLE,
                    row.prepared_at,
                    RevisionGuard(original.revision),
                )
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        inspect_sqlite(connection, markers())
        inspect_files(tmp_path, list(tmp_path.iterdir()), markers())
    finally:
        session.close()


def test_sigkill_initial_schema_commit_does_not_fabricate_an_empty_recovery(
    tmp_path,
):
    path = tmp_path / "metadata.db"
    _kill_at("initialize_open", path)
    from test_db_schema import bootstrap_rows

    info, _, _, _ = bootstrap_rows()
    connection = sqlite3.connect(path, autocommit=True)
    # SQLite rolls uncommitted DDL/identity rows back. Ordinary attach refuses,
    # and cannot recreate state without the real matching bootstrap journal.
    assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []
    assert connection.execute("PRAGMA user_version").fetchone() == (0,)
    with pytest.raises(StorageFailure):
        _attach_writer(connection, info)
    assert path.exists()


if __name__ == "__main__":
    _worker(sys.argv[1], Path(sys.argv[2]))
