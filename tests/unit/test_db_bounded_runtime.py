"""DB-27/28: bounded file-SQL behavior, not runtime/process-owner acceptance."""

import os
import select
import socket
import subprocess
import sys
from pathlib import Path
from time import monotonic

import pytest
from fakes.network import NetworkDenied, deny_network
from test_db_repositories import admit, job, publish, view
from test_db_repositories import state as state
from test_db_results import known, ready, record
from test_db_schema import P

from facet.contracts import ErrorCode
from facet.db.codecs import PageLimit, StorageFailure
from facet.db.repositories import jobs
from facet.db.repositories.serialization import COLUMNS


@pytest.mark.parametrize(
    "table,time_column,id_column,index",
    [
        ("sync_jobs", "created_at", "job_id", "jobs_inspection"),
        ("insert_attempts", "prepared_at", "attempt_id", "attempts_inspection"),
        ("source_events", "observed_at", "event_id", "events_inspection"),
        ("audit_events", "observed_at", "audit_id", "audit_recent"),
    ],
)
def test_registered_keyset_queries_use_bounded_index_without_offset_or_temp_sort(
    state, table, time_column, id_column, index
):
    # The inventory is test-owned fixed tuples, not runtime/operator SQL input.
    sql = (
        "EXPLAIN QUERY PLAN SELECT "
        + ",".join(COLUMNS[table])
        + f" FROM {table} WHERE projection_id=? "
        + f"AND ({time_column},{id_column})>(?,?) "
        + f"ORDER BY {time_column},{id_column} LIMIT ?"
    )
    details = tuple(
        row[3] for row in state[1].execute(sql, (P.value, 0, "0" * 32, 501)).fetchall()
    )
    assert any("SEARCH" in detail and index in detail for detail in details)
    assert not any("USE TEMP B-TREE" in detail for detail in details)


def test_501_jobs_are_keyset_paginated_without_long_lived_read_transaction(state):
    publish(state[2])
    admit(state[2])
    expected = tuple(job(n) for n in range(1000, 1501))
    with state[2].transaction() as uow:
        for row in expected:
            jobs.enqueue(uow, P, row)
    with view(state) as reader:
        first = reader.list_jobs(P, PageLimit(500), None)
        assert len(first.items) == 500 and first.next_key is not None
        second = reader.list_jobs(P, PageLimit(500), first.next_key)
        assert len(second.items) == 1 and second.next_key is None
        assert first.items + second.items == expected
        assert reader.call("keyset_501", P) == {"actual_child_assertions": True}


def test_real_other_process_sqlite_writer_busy_is_bounded_and_retains_old_work(state):
    path, connection, session, _ = state
    publish(session)
    admit(session)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, job(100))
    # This child owns only its own SQLite transaction. It is not evidence of
    # M1-03's absent OS writer-lock/provider or a permission to run two daemons.
    script = (
        "import sqlite3,sys\n"
        "from fakes.network import deny_network\n"
        "with deny_network():\n"
        " c=sqlite3.connect(sys.argv[1],autocommit=True)\n"
        " c.execute('BEGIN IMMEDIATE')\n"
        " print('locked',flush=True)\n"
        " sys.stdin.readline()\n"
        " c.execute('ROLLBACK')\n"
        " c.close()\n"
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHONNOUSERSITE": "1",
    }
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        assert select.select([child.stdout], [], [], 3)[0]
        assert child.stdout.readline().strip() == "locked"
        assert connection.execute("PRAGMA busy_timeout").fetchone() == (5000,)
        started = monotonic()
        with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
            jobs.enqueue(uow, P, job(101))
        assert caught.value.code is ErrorCode.DATABASE_UNAVAILABLE
        assert monotonic() - started < 10
        assert not connection.in_transaction and session._uow is None
    finally:
        if child.poll() is None:
            child.stdin.write("release\n")
            child.stdin.flush()
        try:
            child.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate(timeout=3)
    assert child.returncode == 0
    with view(state) as reader:
        assert reader.get_job(P, job(100).job_id) == job(100)
        assert reader.get_job(P, job(101).job_id) is None
    with session.transaction() as uow:
        jobs.enqueue(uow, P, job(101))
    assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_actual_claim_prepare_dispatch_and_result_complete_without_network_wait(state):
    with deny_network():
        with pytest.raises(NetworkDenied):
            socket.create_connection(("example.invalid", 443), timeout=0.1)
        original, _, _, attempt = ready(state)
        record(state, known(attempt))
        with view(state) as reader:
            assert reader.get_job(P, original.job_id).state.value == "claimed"
            assert (
                reader.get_attempt(P, attempt.attempt_id).state.value
                == "known_inserted"
            )
    assert not state[1].in_transaction
