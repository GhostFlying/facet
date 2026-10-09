"""Resumable source scans followed by H1 catchup; no target-copy implementation."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from facet.contracts import (
    Count,
    EpochKind,
    EpochState,
    ErrorCode,
    JobKind,
    JobState,
    LocalId,
    PartitionProgress,
    PartitionState,
    Priority,
    ProviderId,
    Revision,
    Timestamp,
)
from facet.contracts.records import (
    EpochDecisionRefScheduledReconcile,
    JobSubjectExpandThread,
    PartitionRefSourceThread,
    PartitionRefSourceWindow,
)
from facet.db.codecs import (
    MIN_TIMESTAMP,
    PollOrigin,
    PollState,
    StorageFailure,
    timestamp_from_sql,
    timestamp_to_sql,
)
from facet.db.keys import job_key, partition_key
from facet.db.models import (
    EpochPartitionRow,
    EpochRow,
    HistoryPollRow,
    RevisionGuard,
    SyncJobRow,
)
from facet.db.repositories import epochs, history, reads
from facet.db.repositories.base import _decode, _get, _query
from facet.db.repositories.serialization import COLUMNS
from facet.projection.backfill import BackfillProducer


def _id():
    return LocalId(uuid4().hex)


def _now():
    return Timestamp(datetime.now(UTC))


class GapRecovery:
    """Reuse durable recovery scope, source expansion and History repositories."""

    def __init__(
        self, owner, source, worker, admission_loader, admission, *, progress=None
    ):
        self.owner, self.source, self.worker = owner, source, worker
        self.projection = owner.projection_id
        self.loader, self.admission = admission_loader, admission
        self.progress = progress

    def _partition(self, epoch_id, ref):
        return EpochPartitionRow(
            self.projection,
            epoch_id,
            partition_key(self.projection, ref),
            PartitionProgress(
                ref, PartitionState.NOT_STARTED, Count(0), Count(0), None, None
            ),
            Revision(0),
        )

    def prepare(self):
        """H1 is already durable; never fabricate a downtime start or new fence."""
        with self.owner.session.transaction() as uow:
            gap = epochs._latest_unresolved_gap(uow, self.projection)
            if gap is None:
                return None
            if gap.reliable_coverage_at is None:
                raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
            rows = _query(
                uow,
                "SELECT "
                + ",".join(COLUMNS["epochs"])
                + " FROM epochs WHERE projection_id=? AND gap_id=? "
                "AND kind='history_gap' LIMIT 1",
                (self.projection.value, gap.gap_id.value),
                maximum=1,
            )
            if rows:
                epoch = _decode(uow, self.projection, "epochs", rows[0])
                if epoch.state in {EpochState.PAUSED, EpochState.NEEDS_ATTENTION}:
                    raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
                return epoch
            projection = reads.get_projection(uow, self.projection)
            start = timestamp_from_sql(
                max(
                    MIN_TIMESTAMP,
                    timestamp_to_sql(gap.reliable_coverage_at) - 300_000_000,
                )
            )
            epoch = EpochRow(
                self.projection,
                _id(),
                EpochKind.HISTORY_GAP,
                EpochState.PREPARED,
                Revision(0),
                _now(),
                start,
                gap.h1_recorded_at,
                None,
                EpochDecisionRefScheduledReconcile(
                    "scheduled_reconcile", projection.ruleset_revision
                ),
                gap.gap_id,
                Count(300_000_000),
                gap.h1,
                gap.h1_recorded_at,
                None,
                False,
                None,
            )
            epochs.start_epoch(
                uow,
                self.projection,
                epoch,
                (
                    self._partition(
                        epoch.epoch_id, PartitionRefSourceWindow("source_window")
                    ),
                ),
            )
            return epoch

    def _active_partitions(self, epoch):
        """Page all active selectors; no hard cap on the required thread set."""
        after = ""
        while True:
            with self.owner.session.transaction() as uow:
                identifiers = _query(
                    uow,
                    "SELECT source_thread_id FROM tracked_threads "
                    "WHERE projection_id=? AND active=1 AND source_thread_id>? "
                    "ORDER BY source_thread_id LIMIT 500",
                    (self.projection.value, after),
                    maximum=500,
                )
                if not identifiers:
                    return
                current = _get(
                    uow, self.projection, "epochs", (("epoch_id", epoch.epoch_id),)
                )
                parts = tuple(
                    self._partition(
                        epoch.epoch_id,
                        PartitionRefSourceThread(
                            "source_thread", ProviderId(identifier)
                        ),
                    )
                    for (identifier,) in identifiers
                )
                epochs.extend_partitions(
                    uow,
                    self.projection,
                    epoch.epoch_id,
                    parts,
                    RevisionGuard(current.revision),
                )
                after = identifiers[-1][0]

    def _scan_threads(self, epoch, max_jobs):
        after = b""
        while True:
            with self.owner.session.transaction() as uow:
                rows = _query(
                    uow,
                    "SELECT "
                    + ",".join(COLUMNS["epoch_partitions"])
                    + " FROM epoch_partitions WHERE projection_id=? AND epoch_id=? "
                    "AND tag='source_thread' AND state<>'complete' AND partition_key>? "
                    "ORDER BY partition_key LIMIT 500",
                    (self.projection.value, epoch.epoch_id.value, after),
                    maximum=500,
                )
                for values in rows:
                    part = _decode(uow, self.projection, "epoch_partitions", values)
                    thread = reads.get_thread(
                        uow, self.projection, part.progress.partition.source_thread_id
                    )
                    progress = part.progress
                    if thread is None or not thread.active:
                        state, work = PartitionState.COMPLETE, ()
                    else:
                        subject = JobSubjectExpandThread(
                            "expand_thread",
                            thread.source_thread_id,
                            epoch.epoch_id,
                            thread.generation,
                        )
                        now = _now()
                        job = SyncJobRow(
                            self.projection,
                            _id(),
                            JobKind.EXPAND_THREAD,
                            Count(1),
                            job_key(self.projection, subject),
                            Priority.BACKFILL,
                            JobState.QUEUED,
                            Revision(0),
                            now,
                            now,
                            None,
                            Count(0),
                            None,
                            epoch.epoch_id,
                            subject,
                        )
                        existing = _get(
                            uow,
                            self.projection,
                            "sync_jobs",
                            (("stable_key", job.stable_key),),
                        )
                        if existing is not None:
                            state = (
                                PartitionState.COMPLETE
                                if existing.state
                                in {JobState.COMPLETED, JobState.SOURCE_MISSING}
                                else PartitionState.SCANNING
                            )
                            work = ()
                        else:
                            state, work = PartitionState.SCANNING, (job,)
                    epochs.advance_partition(
                        uow,
                        self.projection,
                        replace(
                            part,
                            progress=replace(progress, state=state),
                            revision=Revision(part.revision.value + 1),
                        ),
                        work,
                        RevisionGuard(part.revision),
                    )
                if not rows:
                    break
                after = rows[-1][2]
        if max_jobs:
            self.worker.expand_epoch(epoch.epoch_id, max_jobs=max_jobs)

    def scan(self, epoch, *, max_jobs):
        """Persist all source work before a recovery-origin History poll exists."""
        if epoch.discovery_complete:
            return True
        from facet.sync import SourceCandidateAdmission

        selected = self.loader(epoch) if self.loader is not None else self.admission
        if selected is None:
            raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
        BackfillProducer(
            self.source,
            SourceCandidateAdmission(self.source, selected),
            progress=self.progress,
        ).discover(self.owner.session, self.projection, epoch.epoch_id)
        self._active_partitions(epoch)
        self._scan_threads(epoch, max_jobs)
        # Refresh progress after expansion, without another provider request.
        self._scan_threads(epoch, 0)
        with self.owner.session.transaction() as uow:
            if _query(
                uow,
                "SELECT 1 FROM epoch_partitions WHERE projection_id=? "
                "AND epoch_id=? AND state<>'complete' LIMIT 1",
                (self.projection.value, epoch.epoch_id.value),
                maximum=1,
            ):
                return False
            current = _get(
                uow, self.projection, "epochs", (("epoch_id", epoch.epoch_id),)
            )
            epochs.advance_epoch(
                uow,
                self.projection,
                epoch.epoch_id,
                EpochState.CATCHING_UP,
                True,
                None,
                RevisionGuard(current.revision),
            )
        return True

    def catchup(self, epoch, producer):
        with self.owner.session.transaction() as uow:
            checkpoint = reads.get_checkpoint(uow, self.projection)
            if checkpoint.active_poll_id is None:
                poll = HistoryPollRow(
                    self.projection,
                    _id(),
                    PollOrigin.RECOVERY_EPOCH,
                    epoch.epoch_id,
                    epoch.fence_history_id,
                    checkpoint.revision,
                    _now(),
                    PollState.READING,
                    Count(0),
                    None,
                    None,
                    None,
                    Revision(0),
                )
                history.begin_history_poll(
                    uow, self.projection, poll, RevisionGuard(checkpoint.revision)
                )
            else:
                poll = _get(
                    uow,
                    self.projection,
                    "history_polls",
                    (("poll_id", checkpoint.active_poll_id),),
                )
                if (
                    poll.origin_epoch_id != epoch.epoch_id
                    or poll.origin is not PollOrigin.RECOVERY_EPOCH
                ):
                    raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        before = poll.completed_pages.value
        producer.consume(self.owner.session, self.projection, poll)
        with self.owner.session.transaction() as uow:
            result = _get(
                uow, self.projection, "history_polls", (("poll_id", poll.poll_id),)
            )
        return result.completed_pages.value - before

    def warnings(self):
        with self.owner.session.transaction() as uow:
            seen = _query(
                uow,
                "SELECT 1 FROM history_gaps WHERE projection_id=? LIMIT 1",
                (self.projection.value,),
                maximum=1,
            )
        return ("expired_action_events_not_reconstructable",) if seen else ()
