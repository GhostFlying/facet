"""Current tags authorize actions; History is only a durable dirty-thread hint."""

from facet.contracts import (
    Count,
    ErrorCode,
    Generation,
    JobKind,
    JobState,
    Priority,
    ProviderId,
    ProviderPageToken,
    Revision,
    RuleKind,
    RuleOrigin,
)
from facet.contracts.records import (
    AdmissionRefFutureRule,
    JobSubjectExpandThread,
    SourceEventKeyLabelChanged,
    ThreadGenerationGuardUntracked,
)
from facet.db.codecs import (
    ActionKind,
    EventProcessing,
    StorageFailure,
    ThreadStopReason,
    timestamp_to_sql,
)
from facet.db.keys import job_key
from facet.db.models import (
    RevisionGuard,
    RuleRevisionRow,
    RuleRow,
    RulesetMemberRow,
    RulesetRow,
    SyncJobRow,
    ThreadAdmissionRow,
    TrackedThreadRow,
    WriteReceipt,
)
from facet.db.repositories import actions, events, jobs, policy, reads
from facet.db.repositories.base import _get
from facet.gmail.source import SourceAdapter
from facet.projection.action_consumer import (
    ActionEffectResult,
    _epoch_is_authorized,
    _new_id,
    _now,
    _resolve_job,
    _rule_kind,
)
from facet.projection.actions import _own
from facet.projection.rules import (
    RuleInputError,
    learn_domain,
    load_rule_policy,
    normalize_rule,
)


def label_ids(labels):
    return {
        ActionKind.ADD_SENDER: None if labels is None else labels.add_sender_label_id,
        ActionKind.ADD_DOMAIN: None if labels is None else labels.add_domain_label_id,
        ActionKind.BLACKLIST: None if labels is None else labels.blacklist_label_id,
    }


def _presence(metadata, labels):
    if labels is None:
        return {kind: False for kind in ActionKind}
    available = {
        label
        for message in metadata.messages
        if "DRAFT" not in message.labels
        for label in message.labels
    }
    return {
        kind: identifier is not None and identifier.value in available
        for kind, identifier in label_ids(labels).items()
    }


def initialize_baseline(owner, labels):
    """Select fixed baseline IDs before fresh H0; upgrades keep pending actions."""
    projection = owner.projection_id
    with owner.session.transaction() as uow:
        upgraded = (
            uow._execute(
                "SELECT 1 FROM epochs WHERE projection_id=? LIMIT 1",
                (projection.value,),
            ).fetchone()
            is not None
        )
        for kind, identifier in label_ids(labels).items():
            uow._execute(
                "INSERT OR IGNORE INTO current_action_baselines VALUES(?,?,?,NULL,?)",
                (
                    projection.value,
                    kind.value,
                    None if identifier is None else identifier.value,
                    int(upgraded or identifier is None),
                ),
            )


def finish_baseline(owner, source, labels):
    """Resumable zero-effect initial observations, only after durable initial H0."""
    projection = owner.projection_id
    with owner.session.transaction() as uow:
        if not uow._execute(
            "SELECT 1 FROM epochs WHERE projection_id=? LIMIT 1", (projection.value,)
        ).fetchone():
            return
        pending = uow._execute(
            "SELECT action_kind,label_id,page_token FROM current_action_baselines "
            "WHERE projection_id=? AND complete=0",
            (projection.value,),
        ).fetchall()
    for kind_value, identifier, token in pending:
        kind = ActionKind(kind_value)
        for _ in range(1000):
            threads, next_token = source.action_label_threads(
                ProviderId(identifier),
                None if token is None else ProviderPageToken(token),
            )
            snapshots = [
                (thread, _presence(source.thread_metadata(thread), labels))
                for thread in threads
            ]
            with owner.session.transaction() as uow:
                for thread, present in snapshots:
                    # Only this baseline's category is acknowledged. Other labels
                    # are scanned against their independently fixed initial IDs.
                    uow._execute(
                        "INSERT OR IGNORE INTO current_action_observations "
                        "VALUES(?,?,?,?,?,0,NULL,?)",
                        (
                            projection.value,
                            thread.value,
                            kind.value,
                            identifier,
                            int(present[kind]),
                            timestamp_to_sql(_now()),
                        ),
                    )
                uow._execute(
                    "UPDATE current_action_baselines SET page_token=?,complete=? "
                    "WHERE projection_id=? AND action_kind=?",
                    (
                        None if next_token is None else next_token.value,
                        int(next_token is None),
                        projection.value,
                        kind.value,
                    ),
                )
            if next_token is None:
                break
            token = next_token.value
        else:
            raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)


class CurrentActionConsumer:
    """One current snapshot per dirty thread; receipts replace event replay."""

    def __init__(self, labels, source, own_addresses, source_primary):
        self._labels = labels
        self._source = source
        self._own_addresses = own_addresses
        self._source_primary = source_primary
        self._snapshots = {}

    def begin_cycle(self):
        self._snapshots.clear()

    def _snapshot(self, thread_id):
        if thread_id not in self._snapshots:
            metadata = self._source.thread_metadata(thread_id)
            if (
                metadata.thread_id != thread_id
                or any(message.thread_id != thread_id for message in metadata.messages)
                or len({message.message_id for message in metadata.messages})
                != len(metadata.messages)
            ):
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            self._snapshots[thread_id] = metadata
        return self._snapshots[thread_id]

    def process(self, owner, projection_id, event_id, *, epoch_id=None):
        with owner.transaction() as uow:
            event = reads.get_event(uow, projection_id, event_id)
            if event is None:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            job = _resolve_job(uow, projection_id, event)
            if job is None:
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            if event.processing is EventProcessing.CONSUMED:
                return ActionEffectResult(
                    receipt=WriteReceipt("replayed", job.job_id, job.revision)
                )
        if event.event.source_thread_id is None:
            message = self._source.message_metadata(event.event.key.source_message_id)
            if message.message_id != event.event.key.source_message_id:
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            with owner.transaction() as uow:
                events.enrich_event(
                    uow,
                    projection_id,
                    event_id,
                    message.thread_id,
                    RevisionGuard(event.revision),
                )
            return self.process(owner, projection_id, event_id, epoch_id=epoch_id)
        thread_id = event.event.source_thread_id
        # An authoritative empty global label catalogue proves no category can
        # be present; it does not claim the thread or its messages are absent.
        metadata = None if self._labels is None else self._snapshot(thread_id)
        present = _presence(metadata, self._labels)
        identifiers = label_ids(self._labels)
        now = _now(event.event.observed_at)
        with owner.transaction() as uow:
            current = reads.get_event(uow, projection_id, event_id)
            if current != event or _resolve_job(uow, projection_id, event) != job:
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            if event.processing not in {
                EventProcessing.PENDING,
                EventProcessing.RESOLVED,
                EventProcessing.NEEDS_ATTENTION,
            }:
                raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
            if (
                event.processing is EventProcessing.NEEDS_ATTENTION
                and event.error_code
                not in {
                    ErrorCode.REQUEST_CONFLICT,
                    ErrorCode.OWNER_UNAVAILABLE,
                    ErrorCode.INVALID_INPUT,
                }
            ):
                raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
            # Decide presence first; irrelevant malformed From values are never
            # parsed when no current action needs a sender.
            newly_present = []
            for kind, identifier in identifiers.items():
                previous = uow._execute(
                    "SELECT label_id,present,activation_sequence,activation_id "
                    "FROM current_action_observations WHERE projection_id=? "
                    "AND source_thread_id=? AND action_kind=?",
                    (projection_id.value, thread_id.value, kind.value),
                ).fetchone()
                if previous is None and identifier is not None:
                    legacy = uow._execute(
                        "SELECT 1 FROM action_commands WHERE projection_id=? "
                        "AND source_thread_id=? AND kind=? AND label_id=? "
                        "AND state='executed' LIMIT 1",
                        (
                            projection_id.value,
                            thread_id.value,
                            kind.value,
                            identifier.value,
                        ),
                    ).fetchone()
                    if legacy:
                        previous = (identifier.value, 1, 0, None)
                sequence = 0 if previous is None else previous[2]
                activation = None if previous is None else previous[3]
                same_present = (
                    previous is not None
                    and previous[1]
                    and identifier is not None
                    and previous[0] == identifier.value
                )
                if present[kind] and not same_present:
                    newly_present.append((kind, identifier, sequence + 1))
                else:
                    self._ack(
                        uow,
                        projection_id,
                        thread_id,
                        kind,
                        identifier,
                        present[kind],
                        sequence,
                        activation,
                        now,
                    )
            normalized, sender = self._normalized(metadata, newly_present, present)
            # BlackList is resolved before any add can admit or enqueue.
            for kind, identifier, sequence in sorted(
                newly_present, key=lambda item: item[0] is not ActionKind.BLACKLIST
            ):
                rule = normalized.get(kind)
                activation = _new_id()
                ref = (
                    None
                    if rule is None
                    else self._publish(uow, projection_id, rule, now)
                )
                thread = _get(
                    uow,
                    projection_id,
                    "tracked_threads",
                    (("source_thread_id", thread_id),),
                )
                if rule is not None:
                    if kind is ActionKind.BLACKLIST:
                        if thread is not None and thread.active:
                            policy.stop_thread(
                                uow,
                                projection_id,
                                thread_id,
                                thread.generation,
                                now,
                                ThreadStopReason.BLACKLIST,
                            )
                    elif (
                        not present[ActionKind.BLACKLIST]
                        and thread is None
                        and not self._blacklisted(uow, projection_id, sender)
                    ):
                        _epoch_is_authorized(uow, projection_id, epoch_id)
                        thread = TrackedThreadRow(
                            projection_id,
                            thread_id,
                            True,
                            Generation(1),
                            now,
                            None,
                            None,
                            Revision(1),
                        )
                        admission = ThreadAdmissionRow(
                            projection_id,
                            thread_id,
                            Revision(1),
                            Generation(1),
                            now,
                            AdmissionRefFutureRule(
                                "future_rule", ref, load_rule_policy().version
                            ),
                        )
                        policy.admit_thread(
                            uow,
                            projection_id,
                            thread,
                            admission,
                            (),
                            ThreadGenerationGuardUntracked("untracked"),
                        )
                        subject = JobSubjectExpandThread(
                            "expand_thread", thread_id, epoch_id, Generation(1)
                        )
                        jobs.enqueue(
                            uow,
                            projection_id,
                            SyncJobRow(
                                projection_id,
                                _new_id(),
                                JobKind.EXPAND_THREAD,
                                Count(1),
                                job_key(projection_id, subject),
                                Priority.REALTIME,
                                JobState.QUEUED,
                                Revision(0),
                                now,
                                now,
                                None,
                                Count(0),
                                None,
                                epoch_id,
                                subject,
                            ),
                        )
                thread = _get(
                    uow,
                    projection_id,
                    "tracked_threads",
                    (("source_thread_id", thread_id),),
                )
                uow._execute(
                    "INSERT INTO current_action_receipts "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        projection_id.value,
                        activation.value,
                        thread_id.value,
                        kind.value,
                        identifier.value,
                        sequence,
                        event_id.value,
                        timestamp_to_sql(now),
                        None if ref is None else ref.rule_id.value,
                        None if ref is None else ref.revision.value,
                        None if thread is None else thread.generation.value,
                        None if thread is None else thread.admission_revision.value,
                        "suppressed" if rule is None else "applied",
                    ),
                )
                self._ack(
                    uow,
                    projection_id,
                    thread_id,
                    kind,
                    identifier,
                    True,
                    sequence,
                    activation.value,
                    now,
                )
            if isinstance(event.event.key, SourceEventKeyLabelChanged):
                self._complete_notification(uow, projection_id, event, job, now)
            return ActionEffectResult(
                receipt=WriteReceipt("updated", job.job_id, job.revision)
            )

    @staticmethod
    def _ack(
        uow, projection, thread, kind, identifier, present, sequence, activation, now
    ):
        uow._execute(
            "INSERT INTO current_action_observations VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(projection_id,source_thread_id,action_kind) DO UPDATE SET "
            "label_id=excluded.label_id,present=excluded.present,"
            "activation_sequence=excluded.activation_sequence,activation_id=excluded.activation_id,"
            "observed_at=excluded.observed_at",
            (
                projection.value,
                thread.value,
                kind.value,
                None if identifier is None else identifier.value,
                int(present),
                sequence,
                activation,
                timestamp_to_sql(now),
            ),
        )

    def _normalized(self, metadata, newly_present, present):
        needed = [
            kind
            for kind, _, _ in newly_present
            if kind is ActionKind.BLACKLIST or not present[ActionKind.BLACKLIST]
        ]
        if not needed:
            return {}, None
        facts = SourceAdapter.action_facts(metadata)
        external = [
            fact
            for fact in facts
            if not fact.is_draft and not _own(fact.sender, self._own_addresses)
        ]
        if not external:
            raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
        sender = max(
            external,
            key=lambda fact: (fact.observed_at.value, fact.source_message_id.value),
        ).sender
        result = {}
        for kind in needed:
            try:
                if kind is ActionKind.ADD_DOMAIN:
                    learned = learn_domain(
                        sender.value,
                        source_primary=self._source_primary,
                        own=tuple(address.value for address in self._own_addresses),
                    )
                    if learned.domain is None:
                        raise RuleInputError()
                    result[kind] = normalize_rule(
                        _rule_kind(kind), learned.domain.value
                    )
                else:
                    result[kind] = normalize_rule(_rule_kind(kind), sender.value)
            except (RuleInputError, ValueError):
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT) from None
        return result, normalize_rule(RuleKind.BLACKLIST_SENDER, sender.value)

    @staticmethod
    def _blacklisted(uow, projection, sender):
        rule = actions._find_rule(
            uow, projection, RuleKind.BLACKLIST_SENDER, sender.storage_value.value
        )
        if rule is None:
            return False
        state = reads.get_projection(uow, projection)
        member = _get(
            uow,
            projection,
            "ruleset_members",
            (("ruleset_revision", state.ruleset_revision), ("rule_id", rule.rule_id)),
        )
        if member is None:
            return False
        revision = _get(
            uow,
            projection,
            "rule_revisions",
            (("rule_id", rule.rule_id), ("revision", member.rule_revision)),
        )
        return revision is not None and revision.enabled

    @staticmethod
    def _publish(uow, projection, normalized, now):
        from facet.contracts import RuleRef

        existing = actions._find_rule(
            uow, projection, normalized.kind, normalized.storage_value.value
        )
        state = reads.get_projection(uow, projection)
        members = actions._ruleset_members(uow, projection, state.ruleset_revision)
        if existing is not None:
            member = next(
                (item for item in members if item.rule_id == existing.rule_id), None
            )
            version = (
                None
                if member is None
                else _get(
                    uow,
                    projection,
                    "rule_revisions",
                    (("rule_id", member.rule_id), ("revision", member.rule_revision)),
                )
            )
            if version is not None and version.enabled:
                return RuleRef(existing.rule_id, version.revision)
        rule_id = _new_id() if existing is None else existing.rule_id
        revision = Revision(
            1 if existing is None else existing.current_revision.value + 1
        )
        snapshot = RulesetRow(
            projection, Revision(state.ruleset_revision.value + 1), now, True
        )
        policy.publish_rules(
            uow,
            projection,
            (
                RuleRow(
                    projection,
                    rule_id,
                    normalized.kind,
                    normalized.storage_value,
                    revision,
                ),
            ),
            (
                RuleRevisionRow(
                    projection,
                    rule_id,
                    revision,
                    True,
                    now,
                    RuleOrigin.ACTION_LABEL,
                    load_rule_policy().version,
                ),
            ),
            snapshot,
            tuple(
                RulesetMemberRow(
                    projection, snapshot.revision, item.rule_id, item.rule_revision
                )
                for item in members
                if item.rule_id != rule_id
            )
            + (RulesetMemberRow(projection, snapshot.revision, rule_id, revision),),
            RevisionGuard(state.ruleset_revision),
        )
        return RuleRef(rule_id, revision)

    @staticmethod
    def _complete_notification(uow, projection, event, job, now):
        if job.state not in {
            JobState.QUEUED,
            JobState.RETRY_WAIT,
            JobState.NEEDS_ATTENTION,
        }:
            raise StorageFailure(ErrorCode.OWNER_BUSY)
        uow._execute(
            "UPDATE source_events SET processing='consumed',error_code=NULL,"
            "revision=revision+1 "
            "WHERE projection_id=? AND event_id=? AND revision=?",
            (projection.value, event.event_id.value, event.revision.value),
        )
        uow._execute(
            "UPDATE sync_jobs SET state='completed',last_error_code=NULL,"
            "next_attempt_at=NULL,updated_at=?,revision=revision+1 "
            "WHERE projection_id=? AND job_id=? AND revision=?",
            (
                timestamp_to_sql(now),
                projection.value,
                job.job_id.value,
                job.revision.value,
            ),
        )
