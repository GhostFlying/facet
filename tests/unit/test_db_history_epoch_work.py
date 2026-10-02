"""Required History work must belong to its actual initial/recovery epoch."""

from contextlib import suppress
from dataclasses import replace

import pytest
from test_db_epochs import epoch, failed_poll_and_gap, recovery_epoch, seed_scan
from test_db_events import event, resolution
from test_db_history import initial_epoch, page, poll, start
from test_db_repositories import state as state
from test_db_repositories import view
from test_db_schema import P, lid

from facet.contracts import Count, EpochState, ErrorCode, Revision
from facet.db.codecs import PollOrigin, StorageFailure
from facet.db.models import HistoryPageEventRow, RevisionGuard
from facet.db.repositories import epochs, events, history, jobs, reads
from facet.db.repositories.base import _insert


def selected_poll(session, origin):
    # Closed synthetic authorization/scan fixtures, not runtime approval or
    # actual Gmail/H0/H1 discovery evidence.
    if origin == "initial":
        selected = initial_epoch(session)
        value = poll(
            origin=PollOrigin.INITIAL_EPOCH,
            origin_epoch_id=selected.epoch_id,
            cursor=selected.fence_history_id,
        )
    else:
        gap = failed_poll_and_gap(session)
        with session.transaction() as uow:
            epochs.record_gap(uow, P, gap)
        selected = recovery_epoch(gap, 950)
        seed_scan(session, selected)
        value = poll(
            origin=PollOrigin.RECOVERY_EPOCH,
            origin_epoch_id=selected.epoch_id,
            cursor=gap.h1,
            checkpoint_revision=1,
        )
    with session.transaction() as uow:
        history.begin_history_poll(
            uow, P, value, RevisionGuard(value.start_checkpoint_revision)
        )
    return selected, value


def prior_work(session, origin):
    row = event()
    work = resolution(row)
    if origin == "other_epoch":
        other = epoch(800)
        with session.transaction() as uow:
            epochs.start_epoch(uow, P, other, ())
        work = replace(work, origin_epoch_id=other.epoch_id)
    with session.transaction() as uow:
        _insert(uow, P, "source_events", row)
        jobs.enqueue(uow, P, work)
    return row, work


@pytest.mark.parametrize("origin", ["initial", "recovery"])
@pytest.mark.parametrize("first_origin", ["realtime", "other_epoch"])
@pytest.mark.parametrize("status", ["queued", "failed"])
def test_existing_resolution_needs_current_epoch_join_and_retains_first_identity(
    state, origin, first_origin, status
):
    _, connection, session, _ = state
    row, old_work = prior_work(session, first_origin)
    if status == "failed":
        with session.transaction() as uow:
            jobs.defer_job(
                uow,
                P,
                old_work.job_id,
                "failed",
                ErrorCode.CONSISTENCY_FAILURE,
                None,
                RevisionGuard(old_work.revision),
            )
    with view(state) as reader:
        original_work = reads.get_job(reader, P, old_work.job_id)
    selected, value = selected_poll(session, origin)
    response = page(value, count=1)
    with session.transaction() as uow:
        begun = history.begin_history_page(
            uow, P, response, RevisionGuard(value.revision)
        )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        events.ingest_history_chunk(
            uow,
            P,
            value.poll_id,
            response.ordinal,
            (row,),
            (),
            RevisionGuard(begun.revision),
        )
    with view(state) as reader:
        assert (
            reads.get_history_poll(reader, P, value.poll_id).revision == begun.revision
        )
        assert reads.get_job(reader, P, old_work.job_id) == original_work
    assert connection.execute(
        "SELECT COUNT(*) FROM history_page_events"
    ).fetchone() == (0,)
    current_work = replace(old_work, job_id=lid(700), origin_epoch_id=selected.epoch_id)
    with session.transaction() as uow:
        ingested = events.ingest_history_chunk(
            uow,
            P,
            value.poll_id,
            response.ordinal,
            (row,),
            (current_work,),
            RevisionGuard(begun.revision),
        )
    assert ingested.revision == Revision(2)
    before = connection.total_changes
    with session.transaction() as uow:
        replay = events.ingest_history_chunk(
            uow,
            P,
            value.poll_id,
            response.ordinal,
            (row,),
            (current_work,),
            RevisionGuard(ingested.revision),
        )
    assert replay.disposition == "replayed" and replay.revision == ingested.revision
    assert connection.total_changes == before
    with view(state) as reader:
        assert reads.get_job(reader, P, old_work.job_id) == original_work
        assert reads.get_job(reader, P, current_work.job_id) is None
    assert connection.execute(
        "SELECT COUNT(*) FROM epoch_jobs WHERE epoch_id=? AND job_id=?",
        (selected.epoch_id.value, old_work.job_id.value),
    ).fetchone() == (1,)
    with session.transaction() as uow:
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
    # Catch-up completion records durable work; it does not complete queued
    # resolution or bypass the epoch's separate work-completion gate.
    with view(state) as reader:
        guard = reads.get_epoch(reader, P, selected.epoch_id).revision
    total = selected.known_message_total if selected.discovery_complete else Count(1)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_epoch(
            uow,
            P,
            selected.epoch_id,
            EpochState.COMPLETED,
            True,
            total,
            RevisionGuard(guard),
        )
    with view(state) as reader:
        assert reads.get_job(reader, P, old_work.job_id).state.value == status
        assert (
            reads.get_epoch(reader, P, selected.epoch_id).state
            is not EpochState.COMPLETED
        )
    if status == "failed":
        with session.transaction() as uow:
            epochs.advance_epoch(
                uow,
                P,
                selected.epoch_id,
                EpochState.COMPLETED_WITH_ISSUES,
                True,
                total,
                RevisionGuard(guard),
            )
        with view(state) as reader:
            assert (
                reads.get_epoch(reader, P, selected.epoch_id).state
                is EpochState.COMPLETED_WITH_ISSUES
            )
            assert reads.get_job(reader, P, old_work.job_id) == original_work


@pytest.mark.parametrize("origin", ["initial", "recovery"])
@pytest.mark.parametrize("stage", ["page", "poll"])
def test_finish_revalidates_legacy_page_required_work_in_exact_epoch(
    state, origin, stage
):
    _, _, session, _ = state
    row, _ = prior_work(session, "realtime")
    _, value = selected_poll(session, origin)
    response = page(value, count=1)
    with session.transaction() as uow:
        history.begin_history_page(uow, P, response, RevisionGuard(value.revision))
        # Exact closed old-bug fixture: a page member whose resolve job exists
        # but was never joined to this origin epoch. No trigger/DDL weakening,
        # no deletion of immutable epoch_jobs or provider-response oracle.
        _insert(
            uow,
            P,
            "history_page_events",
            HistoryPageEventRow(P, value.poll_id, response.ordinal, row.event_id),
        )
        if stage == "poll":
            uow._execute(
                "UPDATE history_pages SET complete=1 "
                "WHERE projection_id=? AND poll_id=?",
                (P.value, value.poll_id.value),
            )
            uow._execute(
                "UPDATE history_polls SET completed_pages=1,revision=3 "
                "WHERE projection_id=? AND poll_id=?",
                (P.value, value.poll_id.value),
            )
    with view(state) as reader:
        before = reads.get_history_poll(reader, P, value.poll_id)
        checkpoint = reads.get_checkpoint(reader, P)
        saved_page = reads.get_history_page(reader, P, value.poll_id, response.ordinal)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        if stage == "page":
            history.finish_history_page(
                uow,
                P,
                value.poll_id,
                response.ordinal,
                response.metadata_digest,
                RevisionGuard(before.revision),
            )
        else:
            history.finish_history_poll(
                uow,
                P,
                value.poll_id,
                response.response_history_id,
                RevisionGuard(before.revision),
            )
    with view(state) as reader:
        assert reads.get_history_poll(reader, P, value.poll_id) == before
        assert reads.get_checkpoint(reader, P) == checkpoint
        assert (
            reads.get_history_page(reader, P, value.poll_id, response.ordinal)
            == saved_page
        )


def test_checkpoint_poll_does_not_invent_or_require_an_epoch_for_prior_work(state):
    _, connection, session, _ = state
    row, old_work = prior_work(session, "realtime")
    value = start(session)
    response = page(value, count=1)
    with session.transaction() as uow:
        begun = history.begin_history_page(
            uow, P, response, RevisionGuard(value.revision)
        )
        ingested = events.ingest_history_chunk(
            uow,
            P,
            value.poll_id,
            response.ordinal,
            (row,),
            (),
            RevisionGuard(begun.revision),
        )
        assert ingested.revision == Revision(2)
        finished = history.finish_history_page(
            uow,
            P,
            value.poll_id,
            response.ordinal,
            response.metadata_digest,
            RevisionGuard(ingested.revision),
        )
        history.finish_history_poll(
            uow,
            P,
            value.poll_id,
            response.response_history_id,
            RevisionGuard(finished.revision),
        )
    assert connection.execute("SELECT COUNT(*) FROM epoch_jobs").fetchone() == (0,)
    with view(state) as reader:
        assert reads.get_job(reader, P, old_work.job_id).origin_epoch_id is None


@pytest.mark.parametrize("origin", ["initial", "recovery"])
def test_caught_missing_epoch_work_undoes_prior_chunk_join_membership_and_revision(
    state, origin
):
    _, connection, session, _ = state
    first, old_work = prior_work(session, "realtime")
    second = event(2)
    second_work = resolution(second)
    with session.transaction() as uow:
        _insert(uow, P, "source_events", second)
        jobs.enqueue(uow, P, second_work)
    selected, value = selected_poll(session, origin)
    response = page(value, count=2)
    with session.transaction() as uow:
        begun = history.begin_history_page(
            uow, P, response, RevisionGuard(value.revision)
        )
    joined_work = replace(old_work, origin_epoch_id=selected.epoch_id)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        accepted = events.ingest_history_chunk(
            uow,
            P,
            value.poll_id,
            response.ordinal,
            (first,),
            (joined_work,),
            RevisionGuard(begun.revision),
        )
        with suppress(StorageFailure):
            events.ingest_history_chunk(
                uow,
                P,
                value.poll_id,
                response.ordinal,
                (second,),
                (),
                RevisionGuard(accepted.revision),
            )
    with view(state) as reader:
        assert (
            reads.get_history_poll(reader, P, value.poll_id).revision == begun.revision
        )
        assert reads.get_job(reader, P, old_work.job_id) == old_work
        assert reads.get_job(reader, P, second_work.job_id) == second_work
    assert connection.execute(
        "SELECT COUNT(*) FROM history_page_events"
    ).fetchone() == (0,)
    assert connection.execute(
        "SELECT COUNT(*) FROM epoch_jobs WHERE epoch_id=?", (selected.epoch_id.value,)
    ).fetchone() == (0,)
