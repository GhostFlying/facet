"""Real-file claimed/generation-bound expansion snapshots and item proofs."""

from dataclasses import replace

import pytest
from test_db_epochs import epoch
from test_db_repositories import (
    T,
    admit,
    attempt,
    claim,
    job,
    publish,
    ready_test_metadata,
    thread_rows,
    view,
)
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
    Count,
    EpochState,
    ErrorCode,
    Generation,
    InsertState,
    JobState,
    OutcomeCertainty,
    PartitionState,
    PolicyVersion,
    ProviderId,
    Revision,
    Sha256Hex,
    Visibility,
)
from facet.contracts.records import (
    EpochDecisionRefScheduledReconcile,
    JobSubjectExpandThread,
    JobSubjectProjectMessage,
    ThreadGenerationGuardTracked,
)
from facet.db.codecs import (
    AttributionKind,
    ExpansionItemKind,
    StorageFailure,
    ThreadStopReason,
)
from facet.db.keys import expansion_digest
from facet.db.models import (
    MappingHistoryRow,
    RevisionGuard,
    ThreadExpansionItemRow,
    ThreadExpansionRunRow,
)
from facet.db.repositories import epochs, expansion, jobs, policy
from facet.db.repositories.base import _insert


def setup(state):
    _, connection, session, info = state
    publish(session)
    tracked, _ = admit(session)
    value = replace(
        epoch(),
        decision=EpochDecisionRefScheduledReconcile("scheduled_reconcile", Revision(1)),
    )
    parent = replace(
        job(
            100,
            subject=JobSubjectExpandThread(
                "expand_thread", T, value.epoch_id, Generation(1)
            ),
        ),
        origin_epoch_id=value.epoch_id,
    )
    with session.transaction() as uow:
        epochs.start_epoch(uow, P, value, ())
        jobs.enqueue(uow, P, parent)
    ready_test_metadata(connection, session)
    acquired, _ = claim(session, info, parent)
    return value, parent, tracked, acquired


def run(parent, ids, n=200):
    return ThreadExpansionRunRow(
        P,
        lid(n),
        parent.job_id,
        T,
        parent.subject.epoch_id,
        parent.subject.generation,
        True,
        PartitionState.SCANNING,
        expansion_digest(ids),
        Count(len(set(ids))),
        NOW,
        None,
        Revision(0),
    )


def work(value, message, n):
    return replace(
        job(
            n,
            subject=JobSubjectProjectMessage(
                "project_message", message, T, value.generation
            ),
        ),
        origin_epoch_id=value.epoch_id,
    )


def item(value, message, child):
    return ThreadExpansionItemRow(
        P,
        value.run_id,
        message,
        ExpansionItemKind.PROJECT_JOB,
        child.job_id,
        None,
        None,
    )


def begin(session, value):
    with session.transaction() as uow:
        expansion.begin_expansion(uow, P, value, RevisionGuard(Revision(1)))


def ingest(session, value, items, children, *, revision=0):
    with session.transaction() as uow:
        expansion.ingest_expansion_items(
            uow, P, value.run_id, items, children, RevisionGuard(Revision(revision))
        )


def test_own_snapshot_finishes_then_only_own_claimed_job_can_complete(state):
    _, connection, session, _ = state
    _, parent, _, _ = setup(state)
    ids = (ProviderId("utf8-中"), ProviderId("utf8-a"), ProviderId("utf8-é"))
    value = run(parent, ids)
    begin(session, value)
    children = tuple(work(value, message, 300 + n) for n, message in enumerate(ids))
    ingest(
        session,
        value,
        tuple(
            item(value, message, child)
            for message, child in zip(ids, children, strict=True)
        ),
        children,
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        jobs.complete_noninsert_job(uow, P, parent.job_id, RevisionGuard(Revision(1)))
    with session.transaction() as uow:
        expansion.finish_expansion(
            uow, P, value.run_id, NOW, RevisionGuard(Revision(1))
        )
        jobs.complete_noninsert_job(uow, P, parent.job_id, RevisionGuard(Revision(1)))
    with view(state) as reader:
        assert reader.get_job(P, parent.job_id).state is JobState.COMPLETED
    assert connection.execute(
        "SELECT state,expected_messages FROM thread_expansion_runs"
    ).fetchone() == ("complete", 3)


def test_large_snapshot_chunks_and_bounded_digest_keyset(state):
    _, connection, session, _ = state
    _, parent, _, _ = setup(state)
    ids = tuple(ProviderId(f"msg-{n}") for n in range(601))
    value = run(parent, ids)
    begin(session, value)
    children = tuple(work(value, message, 1000 + n) for n, message in enumerate(ids))
    membership = tuple(
        item(value, message, child)
        for message, child in zip(ids, children, strict=True)
    )
    ingest(session, value, membership[:500], children[:500])
    with pytest.raises(StorageFailure), session.transaction() as uow:
        expansion.finish_expansion(
            uow, P, value.run_id, NOW, RevisionGuard(Revision(1))
        )
    ingest(session, value, membership[500:], children[500:], revision=1)
    with session.transaction() as uow:
        expansion.finish_expansion(
            uow, P, value.run_id, NOW, RevisionGuard(Revision(2))
        )
    assert connection.execute(
        "SELECT COUNT(*) FROM thread_expansion_items"
    ).fetchone() == (601,)


def test_identical_snapshot_resumes_old_allocation_and_changed_set_retains_old_work(
    state,
):
    _, connection, session, _ = state
    _, parent, _, _ = setup(state)
    message = ProviderId("first")
    value = run(parent, (message,))
    begin(session, value)
    child = work(value, message, 300)
    ingest(session, value, (item(value, message, child),), (child,))
    with session.transaction() as uow:
        receipt = expansion.begin_expansion(
            uow, P, replace(value, run_id=lid(201)), RevisionGuard(Revision(1))
        )
        assert receipt.object_id == value.run_id and receipt.disposition == "replayed"
    changed = run(parent, (message, ProviderId("new")), 202)
    begin(session, changed)
    assert connection.execute(
        "SELECT current FROM thread_expansion_runs ORDER BY run_id"
    ).fetchall() == [(0,), (1,)]
    assert connection.execute(
        "SELECT COUNT(*) FROM thread_expansion_items"
    ).fetchone() == (1,)
    with view(state) as reader:
        assert reader.get_job(P, child.job_id).state is JobState.QUEUED
    with pytest.raises(StorageFailure), session.transaction() as uow:
        expansion.finish_expansion(
            uow, P, value.run_id, NOW, RevisionGuard(Revision(1))
        )


def test_stable_child_job_replay_normalizes_allocation_without_duplicate_members(state):
    _, connection, session, _ = state
    _, parent, _, _ = setup(state)
    message = ProviderId("synthetic-message")
    value = run(parent, (message,))
    begin(session, value)
    child = work(value, message, 300)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, child)
    newly_allocated = replace(child, job_id=lid(301))
    ingest(session, value, (item(value, message, newly_allocated),), (newly_allocated,))
    ingest(
        session,
        value,
        (item(value, message, newly_allocated),),
        (newly_allocated,),
        revision=1,
    )
    assert connection.execute(
        "SELECT project_job_id FROM thread_expansion_items"
    ).fetchone() == (child.job_id.value,)
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (2,)


@pytest.mark.parametrize(
    "bad",
    [
        "digest",
        "overcount",
        "wrong_thread",
        "wrong_generation",
        "wrong_message",
        "extra_job",
        "stale",
        "oversize",
    ],
)
def test_snapshot_or_member_proof_failure_is_atomic(state, bad):
    _, connection, session, _ = state
    _, parent, _, _ = setup(state)
    message = ProviderId("synthetic-message")
    value = run(parent, () if bad == "overcount" else (message,))
    if bad == "digest":
        value = replace(value, snapshot_digest=Sha256Hex("f" * 64))
    begin(session, value)
    child = work(value, message, 300)
    if bad in {"wrong_thread", "wrong_generation", "wrong_message"}:
        updates = {
            "wrong_thread": {"source_thread_id": ProviderId("foreign")},
            "wrong_generation": {"generation": Generation(3)},
            "wrong_message": {"source_message_id": ProviderId("another-message")},
        }[bad]
        subject = replace(child.subject, **updates)
        from facet.db.keys import job_key

        child = replace(child, subject=subject, stable_key=job_key(P, subject))
    members, children = (item(value, message, child),), (child,)
    if bad == "extra_job":
        children += (work(value, ProviderId("unselected-message"), 301),)
    elif bad == "oversize":
        members = members * 501
    if bad == "digest":
        ingest(session, value, members, children)
        with pytest.raises(StorageFailure), session.transaction() as uow:
            expansion.finish_expansion(
                uow, P, value.run_id, NOW, RevisionGuard(Revision(1))
            )
        assert connection.execute(
            "SELECT state FROM thread_expansion_runs"
        ).fetchone() == ("scanning",)
    else:
        with pytest.raises(StorageFailure):
            ingest(
                session, value, members, children, revision=1 if bad == "stale" else 0
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM thread_expansion_items"
        ).fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (1,)


def test_stopped_and_retracked_generation_cannot_complete_old_run(state):
    _, connection, session, _ = state
    _, parent, tracked, _ = setup(state)
    value = run(parent, ())
    begin(session, value)
    with session.transaction() as uow:
        policy.stop_thread(
            uow, P, T, tracked.generation, NOW, ThreadStopReason.MANUAL_STOP
        )
    new_thread, admission = thread_rows(generation=3, admission_revision=2)
    with session.transaction() as uow:
        policy.admit_thread(
            uow,
            P,
            new_thread,
            admission,
            (),
            ThreadGenerationGuardTracked("tracked", Generation(2)),
        )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        expansion.finish_expansion(
            uow, P, value.run_id, NOW, RevisionGuard(Revision(0))
        )
    assert connection.execute("SELECT state FROM thread_expansion_runs").fetchone() == (
        "scanning",
    )


@pytest.mark.parametrize(
    "bad", ["unclaimed", "other_parent", "mismatched_epoch", "mismatched_generation"]
)
def test_run_requires_exact_current_claim_and_parent_identity(state, bad):
    _, connection, session, _ = state
    _, parent, _, _ = setup(state)
    value = run(parent, ())
    if bad == "unclaimed":
        with session.transaction() as uow:
            jobs.defer_job(
                uow,
                P,
                parent.job_id,
                "blocked",
                ErrorCode.NETWORK_UNAVAILABLE,
                None,
                RevisionGuard(Revision(1)),
            )
    elif bad == "other_parent":
        value = replace(value, job_id=lid(999))
    elif bad == "mismatched_epoch":
        value = replace(value, epoch_id=lid(999))
    else:
        value = replace(value, generation=Generation(3))
    with pytest.raises(StorageFailure):
        begin(session, value)
    assert connection.execute(
        "SELECT COUNT(*) FROM thread_expansion_runs"
    ).fetchone() == (0,)


@pytest.mark.parametrize(
    "case", ["verified", "missing", "source_mismatch", "unverified"]
)
def test_mapping_item_requires_exact_verified_attempt_history_relationship(state, case):
    _, connection, session, info = state
    _, parent, _, _ = setup(state)
    message = ProviderId("already-mapped")
    value = run(parent, (message,))
    begin(session, value)
    child = work(
        value,
        ProviderId("another-source") if case == "source_mismatch" else message,
        300,
    )
    child = replace(child, origin_epoch_id=None)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, child)
    acquired, _ = claim(session, info, child)
    prepared = attempt(child, acquired, 400, InsertState.PREPARED)
    verified = replace(
        prepared,
        state=InsertState.VERIFIED,
        certainty=OutcomeCertainty.INSERTED,
        dispatch_started_at=NOW,
        result_at=NOW,
        verified_at=NOW,
        semantic_digest=Sha256Hex("b" * 64),
        semantic_version=PolicyVersion("synthetic-mime-v1"),
        target_message_id=ProviderId("synthetic-target"),
        target_thread_id=ProviderId("synthetic-target-thread"),
        visibility=Visibility.NORMAL,
        attribution=AttributionKind.DIRECT_RESPONSE,
    )
    mapped = MappingHistoryRow(
        P,
        message,
        Revision(1),
        T,
        prepared.attempt_id,
        ProviderId("synthetic-target"),
        ProviderId("synthetic-target-thread"),
        NOW,
        None,
    )
    # Test-only already-validated M2 result allocation; verify_mapping's real
    # producer is another pending slice and no Gmail/fidelity proof is asserted.
    with session.transaction() as uow:
        _insert(
            uow, P, "insert_attempts", prepared if case == "unverified" else verified
        )
        if case != "missing":
            _insert(uow, P, "mapping_history", mapped)
    member = ThreadExpansionItemRow(
        P,
        value.run_id,
        message,
        ExpansionItemKind.VERIFIED_MAPPING,
        None,
        message,
        Revision(1),
    )
    if case == "verified":
        ingest(session, value, (member,), ())
        with session.transaction() as uow:
            expansion.finish_expansion(
                uow, P, value.run_id, NOW, RevisionGuard(Revision(1))
            )
        # Verified mapping references do not manufacture an epoch job. This
        # fixture's old project job was not itself selected by the snapshot.
        assert connection.execute(
            "SELECT COUNT(*) FROM epoch_jobs WHERE job_id=?", (child.job_id.value,)
        ).fetchone() == (0,)
    else:
        with pytest.raises(StorageFailure):
            ingest(session, value, (member,), ())
        assert connection.execute(
            "SELECT COUNT(*) FROM thread_expansion_items"
        ).fetchone() == (0,)


@pytest.mark.parametrize("origin", ["realtime", "other_epoch"])
@pytest.mark.parametrize("status", ["queued", "failed"])
def test_existing_items_only_child_joins_selected_epoch_without_changing_first_origin(
    state, origin, status
):
    _, connection, session, _ = state
    selected_epoch, parent, _, _ = setup(state)
    message = ProviderId("existing-selected-message")
    value = run(parent, (message,))
    begin(session, value)
    child = replace(work(value, message, 300), origin_epoch_id=None)
    if origin == "other_epoch":
        other = replace(
            epoch(501),
            decision=EpochDecisionRefScheduledReconcile(
                "scheduled_reconcile", Revision(1)
            ),
        )
        with session.transaction() as uow:
            epochs.start_epoch(uow, P, other, ())
        child = replace(child, origin_epoch_id=other.epoch_id)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, child)
        if status == "failed":
            # Synthetic prior scheduler outcome, not forced completion of work.
            uow._execute(
                "UPDATE sync_jobs SET state='failed' "
                "WHERE projection_id=? AND job_id=?",
                (P.value, child.job_id.value),
            )
    ingest(session, value, (item(value, message, child),), ())
    ingest(session, value, (item(value, message, child),), (), revision=1)
    with view(state) as reader:
        saved = reader.get_job(P, child.job_id)
        assert saved.origin_epoch_id == child.origin_epoch_id
        assert saved.job_id == child.job_id and saved.state.value == status
    assert connection.execute(
        "SELECT COUNT(*) FROM epoch_jobs WHERE epoch_id=? AND job_id=?",
        (value.epoch_id.value, child.job_id.value),
    ).fetchone() == (1,)
    with session.transaction() as uow:
        expansion.finish_expansion(
            uow, P, value.run_id, NOW, RevisionGuard(Revision(2))
        )
        jobs.complete_noninsert_job(uow, P, parent.job_id, RevisionGuard(Revision(1)))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        epochs.advance_epoch(
            uow,
            P,
            selected_epoch.epoch_id,
            EpochState.COMPLETED,
            True,
            Count(1),
            RevisionGuard(Revision(0)),
        )
    if status == "failed":
        with session.transaction() as uow:
            epochs.advance_epoch(
                uow,
                P,
                selected_epoch.epoch_id,
                EpochState.COMPLETED_WITH_ISSUES,
                True,
                Count(1),
                RevisionGuard(Revision(0)),
            )
    else:
        with pytest.raises(StorageFailure), session.transaction() as uow:
            epochs.advance_epoch(
                uow,
                P,
                selected_epoch.epoch_id,
                EpochState.COMPLETED_WITH_ISSUES,
                True,
                Count(1),
                RevisionGuard(Revision(0)),
            )
    # A separately opened read view proves the durable relation and unchanged
    # child's pending/failure, rather than relying on an enqueue receipt.
    with view(state) as reader:
        assert reader.get_job(P, child.job_id).state.value == status
        assert reader.get_epoch(P, selected_epoch.epoch_id).state is (
            EpochState.COMPLETED_WITH_ISSUES
            if status == "failed"
            else EpochState.PREPARED
        )


def test_later_bad_item_rolls_back_existing_child_epoch_join_and_all_membership(state):
    _, connection, session, _ = state
    _, parent, _, _ = setup(state)
    message = ProviderId("existing-selected-message")
    invalid = ProviderId("invalid-selected-message")
    value = run(parent, (message, invalid))
    begin(session, value)
    child = replace(work(value, message, 300), origin_epoch_id=None)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, child)
    missing = work(value, invalid, 301)
    with pytest.raises(StorageFailure):
        ingest(
            session,
            value,
            (item(value, message, child), item(value, invalid, missing)),
            (),
        )
    assert connection.execute(
        "SELECT COUNT(*) FROM epoch_jobs WHERE job_id=?", (child.job_id.value,)
    ).fetchone() == (0,)
    assert connection.execute(
        "SELECT COUNT(*) FROM thread_expansion_items"
    ).fetchone() == (0,)
    assert connection.execute(
        "SELECT revision FROM thread_expansion_runs"
    ).fetchone() == (0,)
    with view(state) as reader:
        assert reader.get_job(P, child.job_id).origin_epoch_id is None
        assert reader.get_job(P, missing.job_id) is None


def test_finish_revalidates_existing_child_membership_in_this_exact_epoch(state):
    _, connection, session, _ = state
    _, parent, _, _ = setup(state)
    message = ProviderId("existing-selected-message")
    value = run(parent, (message,))
    begin(session, value)
    child = replace(work(value, message, 300), origin_epoch_id=None)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, child)
        # The old items-only bug could persist exactly these facts. A closed
        # legacy fixture tests final proof validation without deleting immutable
        # epoch membership or altering trusted schema/trigger definitions.
        _insert(uow, P, "thread_expansion_items", item(value, message, child))
        uow._execute(
            "UPDATE thread_expansion_runs SET revision=1 "
            "WHERE projection_id=? AND run_id=?",
            (P.value, value.run_id.value),
        )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        expansion.finish_expansion(
            uow, P, value.run_id, NOW, RevisionGuard(Revision(1))
        )
    assert connection.execute("SELECT state FROM thread_expansion_runs").fetchone() == (
        "scanning",
    )
