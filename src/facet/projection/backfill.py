"""Fixed-window discovery producer and durable thread expansion scheduling."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from facet.contracts import (
    Count,
    EpochState,
    ErrorCode,
    Generation,
    JobKind,
    JobState,
    LocalId,
    PartitionProgress,
    PartitionState,
    PolicyVersion,
    Priority,
    Revision,
    RuleRef,
    Timestamp,
)
from facet.contracts.records import (
    AdmissionRefInitialBackfill,
    JobSubjectExpandThread,
    ThreadGenerationGuardTracked,
    ThreadGenerationGuardUntracked,
)
from facet.db.codecs import StorageFailure
from facet.db.keys import job_key
from facet.db.models import (
    EpochPartitionRow,
    RevisionGuard,
    SyncJobRow,
    ThreadAdmissionRow,
    TrackedThreadRow,
)
from facet.db.repositories import epochs, policy
from facet.db.repositories.base import _get


@dataclass(frozen=True, slots=True)
class DiscoveryDecision:
    """Result of the rule-based admission consumer for one discovery item."""

    admit: bool
    rule: RuleRef | None = None
    attention: ErrorCode | None = None

    def __post_init__(self):
        if (
            type(self.admit) is not bool
            or (self.admit and type(self.rule) is not RuleRef)
            or (not self.admit and self.rule is not None)
            or (self.admit and self.attention is not None)
            or (self.attention is not None and type(self.attention) is not ErrorCode)
        ):
            raise ValueError("invalid_input")


class AdmissionEvaluator(Protocol):
    """Typed seam for the metadata/rules admission consumer."""

    def evaluate(self, item, epoch) -> DiscoveryDecision: ...


def _local_id() -> LocalId:
    return LocalId(uuid4().hex)


def _now() -> Timestamp:
    return Timestamp(datetime.now(UTC))


class BackfillProducer:
    """Page source discovery and publish only durable expansion/message work."""

    def __init__(self, source, admission: AdmissionEvaluator):
        if not callable(getattr(admission, "evaluate", None)):
            raise ValueError("invalid_input")
        self._source = source
        self._admission = admission

    def preview(self, owner, projection_id, request):
        """Persist the guarded preview through PR33's operation journal."""
        from facet.db import command_store

        with owner.transaction() as uow:
            return command_store.preview_backfill(uow, projection_id, request)

    def start(self, owner, projection_id, request):
        """Fence H0 from the source profile before publishing the epoch."""
        from facet.db import command_store

        profile = self._source.profile()
        fence_recorded_at = _now()
        fenced = replace(
            request,
            fence_history_id=profile.history_id,
            fence_recorded_at=fence_recorded_at,
            accepted_at=(
                request.accepted_at
                if request.accepted_at.value >= fence_recorded_at.value
                else fence_recorded_at
            ),
        )
        with owner.transaction() as uow:
            return command_store.start_backfill(uow, projection_id, fenced)

    def discover(self, owner, projection_id, epoch_id: LocalId) -> int:
        with owner.transaction() as uow:
            epoch = _get(uow, projection_id, "epochs", (("epoch_id", epoch_id),))
            partition = _get(
                uow, projection_id, "epoch_partitions", (("epoch_id", epoch_id),)
            )
            if epoch is None or partition is None:
                raise ValueError("invalid_input")
            if partition.progress.state is PartitionState.NEEDS_ATTENTION:
                raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
            if partition.progress.state is PartitionState.COMPLETE:
                return partition.progress.observed_items.value
        query_planner = getattr(self._admission, "discovery_query", None)
        if callable(query_planner):
            query = query_planner(epoch)
            if query is None:
                return self._complete_selected_scope(
                    owner, projection_id, epoch_id, partition
                )
        else:
            query = None
        if query is not None and partition.progress.page_token is not None:
            # A token created by an older unfiltered scan is not valid for a
            # newly rule-selected query. Hold for explicit maintenance rather
            # than silently skipping or reusing provider pages.
            raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
        token = partition.progress.page_token
        observed = partition.progress.observed_items.value
        pages = 0
        while True:
            response = self._source.discover(
                window_start=epoch.window_start.value,
                window_end=epoch.window_end.value,
                page_token=token,
                **({"query": query} if query is not None else {}),
            )
            # Candidate metadata/authentication is provider work and must not
            # execute while the SQLite writer transaction is open.
            decisions = tuple(
                (item, self._admission.evaluate(item, epoch)) for item in response.items
            )
            now = _now()
            jobs = []
            with owner.transaction() as uow:
                current = _get(
                    uow,
                    projection_id,
                    "epoch_partitions",
                    (
                        ("epoch_id", epoch_id),
                        ("partition_key", partition.partition_key),
                    ),
                )
                if current is None:
                    raise ValueError("invalid_input")
                for item, decision in decisions:
                    if (
                        not isinstance(decision, DiscoveryDecision)
                        or not decision.admit
                    ):
                        if (
                            isinstance(decision, DiscoveryDecision)
                            and decision.attention is not None
                        ):
                            # The schema intentionally stores discovery
                            # attention as an aggregate partition fact.  It
                            # preserves restart visibility without copying a
                            # candidate address or provider payload into SQL.
                            next_progress = PartitionProgress(
                                current.progress.partition,
                                PartitionState.NEEDS_ATTENTION,
                                Count(current.progress.completed_pages.value + 1),
                                Count(
                                    current.progress.observed_items.value
                                    + len(response.items)
                                ),
                                response.next_page_token,
                                None,
                            )
                            epochs.advance_partition(
                                uow,
                                projection_id,
                                EpochPartitionRow(
                                    projection_id,
                                    epoch_id,
                                    current.partition_key,
                                    next_progress,
                                    Revision(current.revision.value + 1),
                                ),
                                (),
                                RevisionGuard(current.revision),
                            )
                            return observed + len(response.items)
                        continue
                    existing = _get(
                        uow,
                        projection_id,
                        "tracked_threads",
                        (("source_thread_id", item.thread_id),),
                    )
                    # A stopped generation is a durable user decision.  A
                    # later scan must not revive it merely because the same
                    # thread still matches the discovery window.
                    if existing is not None:
                        continue
                    generation = Generation(
                        1 if existing is None else existing.generation.value + 1
                    )
                    thread = TrackedThreadRow(
                        projection_id,
                        item.thread_id,
                        True,
                        generation,
                        now,
                        None,
                        None,
                        Revision(
                            1
                            if existing is None
                            else existing.admission_revision.value + 1
                        ),
                    )
                    admission = ThreadAdmissionRow(
                        projection_id,
                        item.thread_id,
                        thread.admission_revision,
                        generation,
                        now,
                        AdmissionRefInitialBackfill(
                            "initial_backfill",
                            epoch_id,
                            decision.rule,
                            PolicyVersion("auth-v1"),
                        ),
                    )
                    subject = JobSubjectExpandThread(
                        "expand_thread", item.thread_id, epoch_id, generation
                    )
                    job = SyncJobRow(
                        projection_id,
                        _local_id(),
                        JobKind.EXPAND_THREAD,
                        Count(1),
                        job_key(projection_id, subject),
                        Priority.BACKFILL,
                        JobState.QUEUED,
                        Revision(0),
                        now,
                        now,
                        None,
                        Count(0),
                        None,
                        epoch_id,
                        subject,
                    )
                    guard = (
                        ThreadGenerationGuardUntracked("untracked")
                        if existing is None
                        else ThreadGenerationGuardTracked(
                            "tracked", existing.generation
                        )
                    )
                    policy.admit_thread(
                        uow,
                        projection_id,
                        thread,
                        admission,
                        (job,),
                        guard,
                    )
                    jobs.append(job)
                next_progress = PartitionProgress(
                    partition.progress.partition,
                    PartitionState.COMPLETE
                    if response.next_page_token is None
                    else PartitionState.SCANNING,
                    Count(partition.progress.completed_pages.value + 1),
                    Count(
                        partition.progress.observed_items.value + len(response.items)
                    ),
                    response.next_page_token,
                    None,
                )
                receipt = epochs.advance_partition(
                    uow,
                    projection_id,
                    EpochPartitionRow(
                        projection_id,
                        epoch_id,
                        current.partition_key,
                        next_progress,
                        Revision(current.revision.value + 1),
                    ),
                    (),
                    RevisionGuard(current.revision),
                )
                partition = EpochPartitionRow(
                    projection_id,
                    epoch_id,
                    current.partition_key,
                    next_progress,
                    receipt.revision,
                )
            pages += 1
            observed += len(response.items)
            if response.next_page_token is None:
                break
            token = response.next_page_token
        return observed

    def _complete_selected_scope(self, owner, projection_id, epoch_id, known_partition):
        """Complete an empty sealed admission scope without mailbox claims."""

        with owner.transaction() as uow:
            epoch = _get(uow, projection_id, "epochs", (("epoch_id", epoch_id),))
            partition = _get(
                uow,
                projection_id,
                "epoch_partitions",
                (
                    ("epoch_id", epoch_id),
                    ("partition_key", known_partition.partition_key),
                ),
            )
            if epoch is None or partition is None:
                raise ValueError("invalid_input")
            if partition.progress.state is PartitionState.NEEDS_ATTENTION:
                raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
            if epoch.discovery_complete:
                if (
                    partition.progress.state is not PartitionState.COMPLETE
                    or partition.progress.page_token is not None
                ):
                    raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
                return 0
            if not epoch.discovery_complete:
                progress = partition.progress
                if progress.state is not PartitionState.COMPLETE or (
                    progress.page_token is not None
                ):
                    progress = replace(
                        progress,
                        state=PartitionState.COMPLETE,
                        page_token=None,
                    )
                    updated = replace(
                        partition,
                        progress=progress,
                        revision=Revision(partition.revision.value + 1),
                    )
                    epochs.advance_partition(
                        uow,
                        projection_id,
                        updated,
                        (),
                        RevisionGuard(partition.revision),
                    )
                    epoch = _get(
                        uow, projection_id, "epochs", (("epoch_id", epoch_id),)
                    )
                epochs.advance_epoch(
                    uow,
                    projection_id,
                    epoch_id,
                    EpochState.CATCHING_UP,
                    True,
                    Count(0),
                    RevisionGuard(epoch.revision),
                )
        return 0


DiscoveryProducer = BackfillProducer
