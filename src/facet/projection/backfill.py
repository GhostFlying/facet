"""Fixed-window discovery producer and durable thread expansion scheduling."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import uuid4

from facet.contracts import (
    Count,
    EpochKind,
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
    ProjectionId,
    ProviderPageToken,
    Revision,
    RuleKind,
    RuleRef,
    Sha256Hex,
    Timestamp,
)
from facet.contracts.records import (
    AdmissionRefFutureRule,
    AdmissionRefInitialBackfill,
    JobSubjectExpandThread,
    PartitionRefSourceWindow,
    ThreadGenerationGuardTracked,
    ThreadGenerationGuardUntracked,
)
from facet.db.codecs import StorageFailure
from facet.db.keys import job_key, partition_key
from facet.db.models import (
    EpochPartitionRow,
    RevisionGuard,
    SyncJobRow,
    ThreadAdmissionRow,
    TrackedThreadRow,
)
from facet.db.repositories import epochs, policy
from facet.db.repositories.base import _get, _query
from facet.gmail.source import discovery_window
from facet.projection.rules import CanonicalSender


@dataclass(frozen=True, slots=True)
class DiscoveryDecision:
    """Result of the rule-based admission consumer for one discovery item."""

    admit: bool
    rule: RuleRef | None = None
    attention: ErrorCode | None = None
    sender: CanonicalSender | None = None

    def __post_init__(self):
        if (
            type(self.admit) is not bool
            or (self.admit and type(self.rule) is not RuleRef)
            or (not self.admit and self.rule is not None)
            or (self.admit and self.attention is not None)
            or (self.attention is not None and type(self.attention) is not ErrorCode)
            or type(self.sender) not in {CanonicalSender, type(None)}
            or (not self.admit and self.sender is not None)
        ):
            raise ValueError("invalid_input")


class AdmissionEvaluator(Protocol):
    """Typed seam for the metadata/rules admission consumer."""

    def evaluate(self, item, epoch) -> DiscoveryDecision: ...


def _local_id() -> LocalId:
    return LocalId(uuid4().hex)


def _now() -> Timestamp:
    return Timestamp(datetime.now(UTC))


def six_calendar_month_start(value: datetime) -> Timestamp:
    """Return the UTC first-of-month boundary six calendar months before value."""

    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError("invalid_input")
    value = value.astimezone(UTC)
    month = value.year * 12 + value.month - 1 - 6
    year, month_index = divmod(month, 12)
    return Timestamp(
        value.replace(
            year=year,
            month=month_index + 1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    )


def _scope_bytes(*values: object) -> bytes:
    encoded = []
    for value in values:
        if isinstance(value, datetime):
            raw = value.astimezone(UTC).isoformat().encode("utf-8")
        else:
            raw = str(value).encode("utf-8")
        encoded.append(len(raw).to_bytes(4, "big") + raw)
    return b"".join(encoded)


def rule_scope_digest(
    projection_id: ProjectionId,
    rule_id: LocalId,
    kind: RuleKind,
    normalized_value: str,
    revision: Revision,
    effective_at: Timestamp,
    policy_version: PolicyVersion,
    window_start: Timestamp,
    window_end: Timestamp,
    discovery_cutoff: Timestamp,
) -> Sha256Hex:
    """Identify one rule revision and its immutable historical scan scope."""

    if (
        type(projection_id) is not ProjectionId
        or type(rule_id) is not LocalId
        or type(kind) is not RuleKind
        or type(normalized_value) is not str
        or type(revision) is not Revision
        or type(effective_at) is not Timestamp
        or type(policy_version) is not PolicyVersion
        or type(window_start) is not Timestamp
        or type(window_end) is not Timestamp
        or type(discovery_cutoff) is not Timestamp
    ):
        raise ValueError("invalid_input")
    return Sha256Hex(
        sha256(
            _scope_bytes(
                "facet-rule-backfill-v1",
                projection_id.value,
                rule_id.value,
                kind.value,
                normalized_value,
                revision.value,
                effective_at.value,
                policy_version.value,
                window_start.value,
                window_end.value,
                discovery_cutoff.value,
            )
        ).hexdigest()
    )


def derived_rule_operation_id(scope: Sha256Hex, purpose: str) -> LocalId:
    """Derive a stable UUID-v4-shaped local key from one rule scope."""

    if type(scope) is not Sha256Hex or type(purpose) is not str or not purpose:
        raise ValueError("invalid_input")
    raw = list(sha256(_scope_bytes(scope.value, purpose)).hexdigest()[:32])
    raw[12] = "4"
    raw[16] = "8"
    return LocalId("".join(raw))


def _query_digest(query, epoch) -> str:
    window = discovery_window(
        epoch.window_start.value,
        epoch.window_end.value,
        precise=epoch.kind is EpochKind.HISTORY_GAP,
    )
    try:
        rendered = query.render(window)
    except ValueError:
        raise StorageFailure(ErrorCode.INVALID_INPUT) from None
    return sha256(rendered.encode("utf-8")).hexdigest()[:32]


def _encode_query_token(token, digest: str) -> ProviderPageToken | None:
    if token is None:
        return None
    return ProviderPageToken(f"facet-q1:{digest}:{token.value}")


def _decode_query_token(token, digest: str) -> ProviderPageToken | None:
    if token is None:
        return None
    prefix = f"facet-q1:{digest}:"
    if not token.value.startswith(prefix):
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
    raw = token.value[len(prefix) :]
    if not raw:
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
    return ProviderPageToken(raw)


def _current_blacklist_matches(uow, projection_id, projection, sender, now) -> bool:
    """Recheck current blacklist policy against one provider candidate."""

    rows = _query(
        uow,
        "SELECT rule_id,rule_revision FROM ruleset_members "
        "WHERE projection_id=? AND ruleset_revision=?",
        (projection_id.value, projection.ruleset_revision.value),
        maximum=1000,
    )
    for rule_id_value, revision_value in rows:
        identity = _get(
            uow,
            projection_id,
            "rules",
            (("rule_id", LocalId(rule_id_value)),),
        )
        revision = _get(
            uow,
            projection_id,
            "rule_revisions",
            (
                ("rule_id", LocalId(rule_id_value)),
                ("revision", Revision(revision_value)),
            ),
        )
        if identity is None or revision is None:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        if (
            identity.kind is RuleKind.BLACKLIST_SENDER
            and revision.enabled
            and revision.effective_at.value <= now.value
            and identity.normalized_value.value == sender.value
        ):
            return True
    return False


class BackfillProducer:
    """Page source discovery and publish only durable expansion/message work."""

    def __init__(self, source, admission: AdmissionEvaluator, *, progress=None):
        if not callable(getattr(admission, "evaluate", None)):
            raise ValueError("invalid_input")
        self._source = source
        self._admission = admission
        self._progress = progress

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
                uow,
                projection_id,
                "epoch_partitions",
                (
                    ("epoch_id", epoch_id),
                    (
                        "partition_key",
                        partition_key(
                            projection_id, PartitionRefSourceWindow("source_window")
                        ),
                    ),
                ),
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
            raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
        query_digest = None if query is None else _query_digest(query, epoch)
        token = (
            partition.progress.page_token
            if query_digest is None
            else _decode_query_token(partition.progress.page_token, query_digest)
        )
        observed = partition.progress.observed_items.value
        pages = 0
        while True:
            response = self._source.discover(
                window_start=epoch.window_start.value,
                window_end=epoch.window_end.value,
                page_token=token,
                **({"query": query} if query is not None else {}),
                **(
                    {"precise_window": True}
                    if epoch.kind is EpochKind.HISTORY_GAP
                    else {}
                ),
            )
            # Candidate metadata/authentication is provider work and must not
            # execute while the SQLite writer transaction is open.
            decisions = []
            for item in response.items:
                decisions.append((item, self._admission.evaluate(item, epoch)))
                if self._progress:
                    self._progress()
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
                                _encode_query_token(
                                    response.next_page_token, query_digest
                                )
                                if query_digest is not None
                                else response.next_page_token,
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
                    if epoch.kind in {
                        EpochKind.INITIAL_BACKFILL,
                        EpochKind.HISTORICAL_EXPANSION,
                        EpochKind.HISTORY_GAP,
                    }:
                        selected_rule_revision = _get(
                            uow,
                            projection_id,
                            "rule_revisions",
                            (
                                ("rule_id", decision.rule.rule_id),
                                ("revision", decision.rule.revision),
                            ),
                        )
                        if selected_rule_revision is None:
                            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
                        projection = _get(uow, projection_id, "projections", ())
                        if decision.sender is not None and _current_blacklist_matches(
                            uow, projection_id, projection, decision.sender, now
                        ):
                            continue
                        member = _get(
                            uow,
                            projection_id,
                            "ruleset_members",
                            (
                                ("ruleset_revision", projection.ruleset_revision),
                                ("rule_id", decision.rule.rule_id),
                            ),
                        )
                        identity = _get(
                            uow,
                            projection_id,
                            "rules",
                            (("rule_id", decision.rule.rule_id),),
                        )
                        current_rule = (
                            None
                            if identity is None
                            else _get(
                                uow,
                                projection_id,
                                "rule_revisions",
                                (
                                    ("rule_id", identity.rule_id),
                                    ("revision", identity.current_revision),
                                ),
                            )
                        )
                        if (
                            member is None
                            or member.rule_revision != decision.rule.revision
                            or current_rule is None
                            or not current_rule.enabled
                            or current_rule.revision != decision.rule.revision
                        ):
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
                    rule_revision = _get(
                        uow,
                        projection_id,
                        "rule_revisions",
                        (
                            ("rule_id", decision.rule.rule_id),
                            ("revision", decision.rule.revision),
                        ),
                    )
                    if rule_revision is None:
                        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
                    admission = ThreadAdmissionRow(
                        projection_id,
                        item.thread_id,
                        thread.admission_revision,
                        generation,
                        now,
                        AdmissionRefFutureRule(
                            "future_rule", decision.rule, rule_revision.policy_version
                        )
                        if epoch.kind is EpochKind.HISTORY_GAP
                        else AdmissionRefInitialBackfill(
                            "initial_backfill",
                            epoch_id,
                            decision.rule,
                            rule_revision.policy_version,
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
                    _encode_query_token(response.next_page_token, query_digest)
                    if query_digest is not None
                    else response.next_page_token,
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
            if self._progress:
                self._progress()
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
                if epoch.kind is EpochKind.HISTORY_GAP:
                    return 0
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
