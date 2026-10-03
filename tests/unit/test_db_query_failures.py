"""DB-17: real SQLite failures while stepping rows must poison the owned UoW."""

from contextlib import suppress
from threading import Thread

import pytest
from test_db_repositories import admit, job, publish
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import ErrorCode, JobState, Revision
from facet.db.codecs import AuditKind, AuditObjectKind, StorageFailure
from facet.db.models import AuditEventRow
from facet.db.repositories import jobs
from facet.db.repositories.audit import append_audit
from facet.db.repositories.base import _query


def prior_mutations(state, uow):
    selected = job(100)
    jobs.enqueue(uow, P, selected)
    append_audit(
        uow,
        P,
        AuditEventRow(
            P,
            lid(90),
            AuditKind.JOB_STATE_CHANGED,
            AuditObjectKind.JOB,
            selected.job_id,
            None,
            None,
            Revision(0),
            Revision(0),
            JobState.QUEUED,
            JobState.QUEUED,
            None,
            NOW,
        ),
    )


def test_real_second_row_step_error_caught_inside_uow_rolls_back_jobs_and_audit(state):
    _, connection, session, _ = state
    publish(session)
    admit(session)
    called = []

    def fault(value):
        called.append(value)
        if value == 2:
            raise ValueError("SYNTHETIC_PRIVATE_FETCH_EXCEPTION")
        return value

    # A test-only direct function forces an actual SQLite step error after
    # execute produced its first row; no schema callback or production plugin.
    connection.create_function("test_only_fetch_fault", 1, fault)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        prior_mutations(state, uow)
        with pytest.raises(StorageFailure) as caught:
            _query(
                uow,
                "SELECT test_only_fetch_fault(v) FROM "
                "(SELECT 1 AS v UNION ALL SELECT 2)",
            )
        assert caught.value.code is ErrorCode.PERSISTENCE_FAILURE
        assert "SYNTHETIC_PRIVATE_FETCH_EXCEPTION" not in str(caught.value)
    assert called == [1, 2]
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE audit_id=?", (lid(90).value,)
    ).fetchone() == (0,)
    assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_bounded_query_consistency_failure_cannot_commit_prior_mutations(state):
    _, connection, session, _ = state
    publish(session)
    admit(session)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        prior_mutations(state, uow)
        with suppress(StorageFailure):
            _query(uow, "SELECT 1 UNION ALL SELECT 2", maximum=1)
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (0,)
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE audit_id=?", (lid(90).value,)
    ).fetchone() == (0,)


def test_legal_query_keeps_prior_mutations_and_foreign_thread_does_not_poison(state):
    _, connection, session, _ = state
    publish(session)
    admit(session)
    errors = []
    with session.transaction() as uow:
        prior_mutations(state, uow)

        def foreign_thread():
            try:
                _query(uow, "SELECT 1")
            except StorageFailure as error:
                errors.append(error.code)

        other = Thread(target=foreign_thread)
        other.start()
        other.join(timeout=2)
        assert not other.is_alive()
        assert errors == [ErrorCode.OWNER_UNAVAILABLE]
        assert not uow._failed
        assert _query(uow, "SELECT 1 UNION ALL SELECT 2", maximum=2) == ((1,), (2,))
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (1,)
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE audit_id=?", (lid(90).value,)
    ).fetchone() == (1,)
