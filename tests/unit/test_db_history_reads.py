"""Finite private History observations and real-file lost-response reconciliation."""

import sqlite3
from threading import Thread

import pytest
from test_db_events import event, resolution, setup
from test_db_history import page, start
from test_db_repositories import state as state
from test_db_repositories import view
from test_db_schema import P, lid

from facet.contracts import Count, ProjectionId, Revision
from facet.db.codecs import PollState, StorageFailure
from facet.db.connection import _attach_writer
from facet.db.models import RevisionGuard
from facet.db.repositories import events, history, reads


def test_lost_page_and_chunk_responses_reconcile_actual_saved_facts_after_reopen(state):
    path, _, session, info = state
    value = start(session)
    response = page(value, count=1)
    # The first acknowledgment is deliberately discarded, not guessed from +1.
    with session.transaction() as uow:
        history.begin_history_page(uow, P, response, RevisionGuard(value.revision))
    session.close()
    reopened = _attach_writer(sqlite3.connect(path, autocommit=True), info)
    try:
        with view(state) as reader:
            observed = reads.get_history_poll(reader, P, value.poll_id)
            saved_page = reads.get_history_page(reader, P, value.poll_id, Count(1))
            assert saved_page == response
            assert observed.state is PollState.READING
            assert observed.start_cursor == value.start_cursor
            assert observed.revision == Revision(1)
        changes = reopened._connection.total_changes
        with reopened.transaction() as uow:
            replay = history.begin_history_page(
                uow, P, response, RevisionGuard(observed.revision)
            )
        assert replay.disposition == "replayed"
        assert reopened._connection.total_changes == changes
        selected = event()
        work = resolution(selected)
        with reopened.transaction() as uow:
            events.ingest_history_chunk(
                uow,
                P,
                value.poll_id,
                response.ordinal,
                (selected,),
                (work,),
                RevisionGuard(replay.revision),
            )
        # Discard that chunk's receipt and close again. This uses the same
        # test-owned lineage; it is not M1-03's fresh-daemon publication gate.
        reopened.close()
        reopened = _attach_writer(sqlite3.connect(path, autocommit=True), info)
        with view(state) as reader:
            observed = reads.get_history_poll(reader, P, value.poll_id)
            assert (
                reads.get_history_page(reader, P, value.poll_id, Count(1)) == response
            )
            assert reads.get_event(reader, P, selected.event_id) == selected
            assert reads.get_job(reader, P, work.job_id) == work
            assert observed.revision == Revision(2)
        changes = reopened._connection.total_changes
        with reopened.transaction() as uow:
            replay = events.ingest_history_chunk(
                uow,
                P,
                value.poll_id,
                response.ordinal,
                (selected,),
                (work,),
                RevisionGuard(observed.revision),
            )
        assert replay.disposition == "replayed" and replay.revision == observed.revision
        assert reopened._connection.total_changes == changes
        with reopened.transaction() as uow:
            finished = history.finish_history_page(
                uow,
                P,
                value.poll_id,
                response.ordinal,
                response.metadata_digest,
                RevisionGuard(replay.revision),
            )
            history.finish_history_poll(
                uow,
                P,
                value.poll_id,
                response.response_history_id,
                RevisionGuard(finished.revision),
            )
        with view(state) as reader:
            assert (
                reads.get_history_poll(reader, P, value.poll_id).state
                is PollState.COMPLETED
            )
            assert reads.get_history_page(reader, P, value.poll_id, Count(1)).complete
            assert (
                reads.get_checkpoint(reader, P).cursor == response.response_history_id
            )
    finally:
        if not reopened._closed:
            reopened.close()


def test_history_reads_are_projection_scoped_missing_bounded_and_zero_write(state):
    _, connection, session, _ = state
    value = start(session)
    response = page(value)
    with session.transaction() as uow:
        history.begin_history_page(uow, P, response, RevisionGuard(value.revision))
    before = connection.total_changes
    with view(state) as reader:
        reader_changes = reader._connection.total_changes
        assert reads.get_history_poll(reader, P, value.poll_id).projection_id == P
        assert reads.get_history_page(reader, P, value.poll_id, Count(1)) == response
        assert reads.get_history_poll(reader, P, lid(9999)) is None
        assert reads.get_history_page(reader, P, value.poll_id, Count(2)) is None
        other = ProjectionId("foreign-projection")
        assert reads.get_history_poll(reader, other, value.poll_id) is None
        assert reads.get_history_page(reader, other, value.poll_id, Count(1)) is None
        assert reader._connection.total_changes == reader_changes
        assert not reader._connection.in_transaction
    assert connection.total_changes == before


@pytest.mark.parametrize("bad", ["view", "projection", "poll", "ordinal", "zero"])
def test_history_read_inputs_reject_before_foreign_value_access(state, bad):
    class Trap:
        @property
        def value(self):
            pytest.fail("untrusted value property was evaluated")

    with view(state) as reader:
        values = [reader, P, lid(1000), Count(1)]
        indices = {"view": 0, "projection": 1, "poll": 2, "ordinal": 3}
        if bad == "zero":
            values[3] = Count(0)
        else:
            values[indices[bad]] = Trap()
        with pytest.raises(StorageFailure):
            reads.get_history_page(*values)
        if bad not in {"ordinal", "zero"}:
            with pytest.raises(StorageFailure):
                reads.get_history_poll(*values[:3])


def test_history_reads_reject_writer_context_closed_view_and_foreign_thread(state):
    _, _, session, _ = state
    with session.transaction() as uow:
        with pytest.raises(StorageFailure):
            reads.get_history_poll(uow, P, lid(1000))
        with pytest.raises(StorageFailure):
            reads.get_history_page(uow, P, lid(1000), Count(1))
    failures = []
    with view(state) as reader:

        def attempt():
            for call in (
                lambda: reads.get_history_poll(reader, P, lid(1000)),
                lambda: reads.get_history_page(reader, P, lid(1000), Count(1)),
            ):
                try:
                    call()
                except StorageFailure:
                    failures.append(True)

        thread = Thread(target=attempt)
        thread.start()
        thread.join()
        assert failures == [True, True]
        assert reads.get_history_poll(reader, P, lid(1000)) is None
    with pytest.raises(StorageFailure):
        reads.get_history_poll(reader, P, lid(1000))
    with pytest.raises(StorageFailure):
        reads.get_history_page(reader, P, lid(1000), Count(1))


@pytest.mark.parametrize("operation", ["page", "chunk"])
def test_poll_revision_sql_failure_rolls_back_prior_page_or_chunk_writes(
    state, operation
):
    _, connection, session, _ = state
    if operation == "chunk":
        value, response = setup(session)
    else:
        value = start(session)
        response = page(value)
    with view(state) as reader:
        before = reads.get_history_poll(reader, P, value.poll_id)

    def refuse_update(action, table, column, database, trigger):
        if action == sqlite3.SQLITE_UPDATE and table == "history_polls":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(refuse_update)
    try:
        with pytest.raises(StorageFailure), session.transaction() as uow:
            if operation == "page":
                history.begin_history_page(
                    uow, P, response, RevisionGuard(before.revision)
                )
            else:
                selected = event()
                events.ingest_history_chunk(
                    uow,
                    P,
                    value.poll_id,
                    response.ordinal,
                    (selected,),
                    (resolution(selected),),
                    RevisionGuard(before.revision),
                )
    finally:
        connection.set_authorizer(None)
    with view(state) as reader:
        assert reads.get_history_poll(reader, P, value.poll_id) == before
        saved_page = reads.get_history_page(reader, P, value.poll_id, Count(1))
        assert saved_page == (response if operation == "chunk" else None)
        assert reads.get_event(reader, P, event().event_id) is None
        assert reads.get_job(reader, P, resolution(event()).job_id) is None
