"""Generation-bound fetched ID snapshots; no raw cache or source fetch here."""

import hashlib
import struct
from dataclasses import replace

from facet.contracts import (
    ClaimPhase,
    JobKind,
    JobState,
    PartitionState,
    ProviderId,
    Timestamp,
)

from ..codecs import ExpansionItemKind, next_revision, timestamp_to_sql
from ..keys import _frame
from ..models import SyncJobRow, ThreadExpansionItemRow, WriteReceipt
from .base import (
    _batch,
    _conflict,
    _get,
    _guard,
    _insert,
    _mutating,
    _query,
    _require_row,
)
from .jobs import _join_epoch, _thread_guard, enqueue


def _parent(uow, projection_id, job_id):
    parent = _get(uow, projection_id, "sync_jobs", (("job_id", job_id),))
    claim = _get(uow, projection_id, "job_claims", (("job_id", job_id),))
    if (
        parent is None
        or parent.kind is not JobKind.EXPAND_THREAD
        or parent.state is not JobState.CLAIMED
        or claim is None
        or claim.claim.owner_run_id != uow._session._info.owner_run_id
        or claim.claim.job_revision != parent.revision
        or claim.claim.phase is not ClaimPhase.PREPARING
        or claim.claim.thread_generation != parent.subject.generation
    ):
        _conflict()
    _thread_guard(uow, projection_id, parent)
    return parent, claim.claim


def _identity(parent, run):
    subject = parent.subject
    if (run.source_thread_id, run.epoch_id, run.generation) != (
        subject.source_thread_id,
        subject.epoch_id,
        subject.generation,
    ):
        _conflict()


def _run(uow, projection_id, run_id, guard):
    run = _get(uow, projection_id, "thread_expansion_runs", (("run_id", run_id),))
    if run is None or not run.current or run.state is not PartitionState.SCANNING:
        _conflict()
    _guard(run.revision, guard)
    parent, _ = _parent(uow, projection_id, run.job_id)
    _identity(parent, run)
    return run


def _project_reference(uow, projection_id, run, item):
    job = _get(uow, projection_id, "sync_jobs", (("job_id", item.project_job_id),))
    if (
        job is None
        or job.kind is not JobKind.PROJECT_MESSAGE
        or job.subject.source_message_id != item.source_message_id
        or job.subject.source_thread_id != run.source_thread_id
        or job.subject.generation != run.generation
    ):
        _conflict()
    return job


def _item_reference(uow, projection_id, run, item):
    if item.kind is ExpansionItemKind.PROJECT_JOB:
        job = _project_reference(uow, projection_id, run, item)
        if (
            _get(
                uow,
                projection_id,
                "epoch_jobs",
                (("epoch_id", run.epoch_id), ("job_id", job.job_id)),
            )
            is None
        ):
            _conflict()
    else:
        mapping = _get(
            uow,
            projection_id,
            "mapping_history",
            (
                ("source_message_id", item.mapped_source_message_id),
                ("mapping_revision", item.mapping_revision),
            ),
        )
        if (
            mapping is None
            or mapping.source_message_id != item.source_message_id
            or mapping.source_thread_id != run.source_thread_id
        ):
            _conflict()
        attempt = _get(
            uow, projection_id, "insert_attempts", (("attempt_id", mapping.attempt_id),)
        )
        if (
            attempt is None
            or attempt.state.value != "verified"
            or (
                attempt.source_message_id,
                attempt.source_thread_id,
                attempt.target_message_id,
                attempt.target_thread_id,
                attempt.verified_at,
            )
            != (
                mapping.source_message_id,
                mapping.source_thread_id,
                mapping.target_message_id,
                mapping.target_thread_id,
                mapping.verified_at,
            )
        ):
            _conflict()


@_mutating
def begin_expansion(uow, projection_id, run, guard):
    _require_row(projection_id, "thread_expansion_runs", run)
    parent, claim = _parent(uow, projection_id, run.job_id)
    _guard(parent.revision, guard)
    _identity(parent, run)
    if (
        not run.current
        or run.state is not PartitionState.SCANNING
        or run.revision.value != 0
        or run.completed_at is not None
        or run.started_at.value < claim.acquired_at.value
    ):
        _conflict()
    old_rows = _query(
        uow,
        "SELECT run_id FROM thread_expansion_runs WHERE projection_id=? "
        "AND job_id=? AND current=1",
        (projection_id.value, parent.job_id.value),
        maximum=1,
    )
    if old_rows:
        from facet.contracts import LocalId

        old = _get(
            uow,
            projection_id,
            "thread_expansion_runs",
            (("run_id", LocalId(old_rows[0][0])),),
        )
        _identity(parent, old)
        if (old.snapshot_digest, old.expected_messages) == (
            run.snapshot_digest,
            run.expected_messages,
        ):
            return WriteReceipt("replayed", old.run_id, old.revision)
        uow._execute(
            "UPDATE thread_expansion_runs SET current=0 "
            "WHERE projection_id=? AND run_id=? AND current=1",
            (projection_id.value, old.run_id.value),
        )
    _insert(uow, projection_id, "thread_expansion_runs", run)
    return WriteReceipt("created", run.run_id, run.revision)


@_mutating
def ingest_expansion_items(uow, projection_id, run_id, items, jobs, guard):
    _batch(items, ThreadExpansionItemRow)
    _batch(jobs, SyncJobRow)
    run = _run(uow, projection_id, run_id, guard)
    selected = set()
    for item in items:
        _require_row(projection_id, "thread_expansion_items", item)
        if item.run_id != run_id:
            _conflict()
        if item.kind is ExpansionItemKind.PROJECT_JOB:
            selected.add((item.source_message_id, item.project_job_id))
    aliases = {}
    for job in jobs:
        _require_row(projection_id, "sync_jobs", job)
        if (
            job.kind is not JobKind.PROJECT_MESSAGE
            or (job.subject.source_message_id, job.job_id) not in selected
            or job.subject.source_thread_id != run.source_thread_id
            or job.subject.generation != run.generation
            or job.origin_epoch_id != run.epoch_id
        ):
            _conflict()
        # Stable-key replay retains the first local allocation. Only an exact
        # semantic enqueue receipt can resolve a supplied allocation to that ID.
        _thread_guard(uow, projection_id, job)
        aliases[job.job_id] = enqueue(uow, projection_id, job).object_id
    for item in items:
        if item.project_job_id in aliases:
            item = replace(item, project_job_id=aliases[item.project_job_id])
        if item.kind is ExpansionItemKind.PROJECT_JOB:
            child = _project_reference(uow, projection_id, run, item)
            # Existing realtime/another-epoch work retains its first origin and
            # allocation, but this selected snapshot must also wait for it.
            _thread_guard(uow, projection_id, child)
            _join_epoch(uow, projection_id, run.epoch_id, child.job_id)
        _item_reference(uow, projection_id, run, item)
        old = _get(
            uow,
            projection_id,
            "thread_expansion_items",
            (
                ("run_id", run_id),
                ("source_message_id", item.source_message_id),
            ),
        )
        if old is not None:
            if old != item:
                _conflict()
        else:
            _insert(uow, projection_id, "thread_expansion_items", item)
    count = _query(
        uow,
        "SELECT COUNT(*) FROM thread_expansion_items "
        "WHERE projection_id=? AND run_id=?",
        (projection_id.value, run_id.value),
        maximum=1,
    )[0][0]
    if count > run.expected_messages.value:
        _conflict()
    revision = next_revision(run.revision)
    uow._execute(
        "UPDATE thread_expansion_runs SET revision=? "
        "WHERE projection_id=? AND run_id=? AND revision=?",
        (revision.value, projection_id.value, run_id.value, run.revision.value),
    )
    return WriteReceipt("updated", run_id, revision)


@_mutating
def finish_expansion(uow, projection_id, run_id, completed_at, guard):
    if type(completed_at) is not Timestamp:
        _conflict()
    run = _run(uow, projection_id, run_id, guard)
    if completed_at.value < run.started_at.value:
        _conflict()
    # Check the full set in bounded keyset chunks. UTF-8 byte order is SQLite
    # BINARY order for these validated text IDs. No entire-thread allocation.
    digest = hashlib.sha256(_frame(("expansion-snapshot-v1",)))
    after, count = "", 0
    while True:
        rows = _query(
            uow,
            "SELECT source_message_id,kind,project_job_id,mapped_source_message_id,"
            "mapping_revision FROM thread_expansion_items WHERE projection_id=? "
            "AND run_id=? AND source_message_id COLLATE BINARY>? "
            "ORDER BY source_message_id COLLATE BINARY LIMIT 500",
            (projection_id.value, run_id.value, after),
            maximum=500,
        )
        if not rows:
            break
        from facet.contracts import LocalId, Revision

        for message, kind, project_id, mapped, revision in rows:
            source_id = ProviderId(message)
            item = ThreadExpansionItemRow(
                projection_id,
                run_id,
                source_id,
                ExpansionItemKind(kind),
                None if project_id is None else LocalId(project_id),
                None if mapped is None else ProviderId(mapped),
                None if revision is None else Revision(revision),
            )
            _item_reference(uow, projection_id, run, item)
            raw = source_id.value.encode("utf-8")
            digest.update(struct.pack(">I", len(raw)))
            digest.update(raw)
            count += 1
        after = rows[-1][0]
    if (
        count != run.expected_messages.value
        or digest.hexdigest() != run.snapshot_digest.value
    ):
        _conflict()
    revision = next_revision(run.revision)
    uow._execute(
        "UPDATE thread_expansion_runs SET state='complete',completed_at=?,"
        "revision=? WHERE projection_id=? AND run_id=? AND revision=?",
        (
            timestamp_to_sql(completed_at),
            revision.value,
            projection_id.value,
            run_id.value,
            run.revision.value,
        ),
    )
    return WriteReceipt("updated", run_id, revision)
