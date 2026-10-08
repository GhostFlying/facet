"""Synthetic end-to-end evidence for the readonly action effect consumer."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_db_actions import prepare_epoch, reopen
from test_db_events import event, resolution
from test_db_repositories import (
    T,
    admit,
    publish,
    ready_test_metadata,
)
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import ErrorCode, LabelChange, ProviderId, Role, Timestamp
from facet.db.codecs import ActionKind, PrivateAddress, StorageFailure, ThreadStopReason
from facet.db.keys import event_key
from facet.db.models import RevisionGuard
from facet.db.repositories import events, jobs, policy, reads
from facet.db.repositories.base import _insert
from facet.gmail.credentials import AccountAddress
from facet.gmail.retry import ProviderFailure
from facet.projection.action_consumer import ActionEffectConsumer
from facet.projection.actions import ActionMessageFact, PrivateActionLabelMap


class Source:
    def __init__(self, facts):
        self.facts = facts

    def get_thread_facts(self, source_thread_id):
        assert source_thread_id == T
        return self.facts


class FailingSource:
    def get_thread_facts(self, source_thread_id):
        raise StorageFailure(ErrorCode.SOURCE_AUTH_REQUIRED)


class ProviderFailingSource:
    def get_thread_facts(self, source_thread_id):
        raise ProviderFailure(ErrorCode.SOURCE_RATE_LIMITED, Role.SOURCE)


@pytest.fixture(autouse=True)
def ready_metadata(state):
    _, connection, session, _ = state
    ready_test_metadata(connection, session)


def _event(session, *, label, n=50, change=LabelChange.ADDED):
    row = event(n, thread=T, tag="label_changed", change=change)
    key = replace(row.event.key, label_id=label)
    row = replace(
        row,
        event_key=event_key(P, key),
        event=replace(row.event, key=key),
    )
    work = resolution(row, n=n + 1000)
    with session.transaction() as uow:
        _insert(uow, P, "source_events", row)
        jobs.enqueue(uow, P, work)
    return row


def _consumer(label_map, facts):
    return ActionEffectConsumer(
        label_map,
        Source(facts),
        (AccountAddress("source@example.com"),),
        "source@example.com",
    )


def test_add_sender_commits_rule_thread_action_and_resolve_job(state):
    _, connection, session, _ = state
    labels = PrivateActionLabelMap(
        ProviderId("add-sender"), ProviderId("add-domain"), ProviderId("blacklist")
    )
    row = _event(session, label=labels.add_sender_label_id)
    selected_epoch = prepare_epoch(session, n=1200)
    result = _consumer(
        labels,
        (
            ActionMessageFact(
                ProviderId("message-1"),
                T,
                PrivateAddress("bank@vendor.com"),
                NOW,
            ),
        ),
    ).process(session, P, row.event_id, epoch_id=selected_epoch.epoch_id)
    assert result.receipt is not None, result.attention
    with session.transaction() as uow:
        assert reads.get_event(uow, P, row.event_id).processing.value == "consumed"
        action = reads.get_action(uow, P, result.receipt.object_id)
        assert action.state.value == "executed"
        assert reads.get_thread(uow, P, T).active
        assert reads.get_job(uow, P, lid(1050)).state.value == "completed"
    assert connection.execute("SELECT COUNT(*) FROM action_commands").fetchone() == (1,)


def test_add_sender_accepts_partial_action_label_map(state):
    _, connection, session, _ = state
    labels = PrivateActionLabelMap(ProviderId("add-sender"), None, None)
    row = _event(session, label=labels.add_sender_label_id)
    selected_epoch = prepare_epoch(session, n=1201)
    result = _consumer(
        labels,
        (
            ActionMessageFact(
                ProviderId("message-partial"),
                T,
                PrivateAddress("bank@vendor.com"),
                NOW,
            ),
        ),
    ).process(session, P, row.event_id, epoch_id=selected_epoch.epoch_id)
    assert result.receipt is not None, result.attention
    with session.transaction() as uow:
        assert reads.get_event(uow, P, row.event_id).processing.value == "consumed"
        assert reads.get_thread(uow, P, T).active
    assert connection.execute("SELECT COUNT(*) FROM action_commands").fetchone() == (1,)


def test_partial_action_label_map_does_not_match_missing_category():
    labels = PrivateActionLabelMap(ProviderId("add-sender"), None, None)
    assert labels.kind(ProviderId("add-sender")) is ActionKind.ADD_SENDER
    assert labels.kind(ProviderId("domain")) is None


def test_blacklist_stops_selected_thread_without_expansion_job(state):
    _, _, session, _ = state
    publish(session)
    admit(session)
    labels = PrivateActionLabelMap(
        ProviderId("add-sender"), ProviderId("add-domain"), ProviderId("blacklist")
    )
    row = _event(session, label=labels.blacklist_label_id, n=60)
    result = _consumer(
        labels,
        (
            ActionMessageFact(
                ProviderId("message-2"),
                T,
                PrivateAddress("bank@vendor.com"),
                NOW,
            ),
        ),
    ).process(session, P, row.event_id)
    assert result.receipt is not None
    with session.transaction() as uow:
        thread = reads.get_thread(uow, P, T)
        assert thread is not None and not thread.active
        assert reads.get_event(uow, P, row.event_id).processing.value == "consumed"


def test_add_domain_uses_registrable_domain_and_selected_epoch(state):
    _, _, session, _ = state
    labels = PrivateActionLabelMap(
        ProviderId("add-sender"), ProviderId("add-domain"), ProviderId("blacklist")
    )
    row = _event(session, label=labels.add_domain_label_id, n=65)
    selected_epoch = prepare_epoch(session, n=1250)
    result = _consumer(
        labels,
        (
            ActionMessageFact(
                ProviderId("message-domain"),
                T,
                PrivateAddress("billing@sub.vendor.co.uk"),
                NOW,
            ),
        ),
    ).process(session, P, row.event_id, epoch_id=selected_epoch.epoch_id)
    assert result.receipt is not None
    assert session._connection.execute(
        "SELECT normalized_value FROM rules WHERE kind='allow_domain'"
    ).fetchone() == ("vendor.co.uk",)


def test_draft_only_facts_become_attention_without_action_or_rule(state):
    _, _, session, _ = state
    labels = PrivateActionLabelMap(
        ProviderId("add-sender"), ProviderId("add-domain"), ProviderId("blacklist")
    )
    row = _event(session, label=labels.add_sender_label_id, n=70)
    result = _consumer(
        labels,
        (
            ActionMessageFact(
                ProviderId("message-3"),
                T,
                PrivateAddress("bank@vendor.com"),
                NOW,
                True,
            ),
        ),
    ).process(session, P, row.event_id)
    assert result.receipt is None and result.attention is not None
    with session.transaction() as uow:
        assert (
            reads.get_event(uow, P, row.event_id).processing.value == "needs_attention"
        )
        assert reads.get_action(uow, P, lid(1070)) is None
        assert reads.get_job(uow, P, lid(1070)).state.value == "needs_attention"


def test_known_removed_label_completes_without_source_read(state):
    _, _, session, _ = state
    labels = PrivateActionLabelMap(
        ProviderId("add-sender"), ProviderId("add-domain"), ProviderId("blacklist")
    )
    row = _event(
        session,
        label=labels.add_sender_label_id,
        n=75,
        change=LabelChange.REMOVED,
    )
    result = _consumer(labels, ()).process(session, P, row.event_id)
    assert result.receipt is not None
    assert result.attention is None
    with session.transaction() as uow:
        assert reads.get_event(uow, P, row.event_id).processing.value == "consumed"
        assert reads.get_job(uow, P, lid(1075)).state.value == "completed"
    replay = _consumer(labels, ()).process(session, P, row.event_id)
    assert replay.attention is None
    assert replay.receipt.disposition == "replayed"


def test_unknown_removed_label_is_not_silently_consumed(state):
    _, _, session, _ = state
    labels = PrivateActionLabelMap(ProviderId("add-sender"), None, None)
    row = _event(
        session, label=ProviderId("retired-label"), n=175, change=LabelChange.REMOVED
    )
    result = _consumer(labels, ()).process(session, P, row.event_id)
    assert result.attention is not None
    with session.transaction() as uow:
        assert (
            reads.get_event(uow, P, row.event_id).processing.value == "needs_attention"
        )


def test_source_auth_failure_retains_resolve_job_for_retry(state):
    _, _, session, _ = state
    labels = PrivateActionLabelMap(
        ProviderId("add-sender"), ProviderId("add-domain"), ProviderId("blacklist")
    )
    row = _event(session, label=labels.add_sender_label_id, n=76)
    result = ActionEffectConsumer(
        labels,
        FailingSource(),
        (AccountAddress("source@example.com"),),
        "source@example.com",
    ).process(session, P, row.event_id)
    assert result.receipt is None and result.attention is ErrorCode.SOURCE_AUTH_REQUIRED
    with session.transaction() as uow:
        assert reads.get_event(uow, P, row.event_id).processing.value == "pending"
        retry = reads.get_job(uow, P, lid(1076))
        assert retry.state.value == "retry_wait"
        assert retry.next_attempt_at.value > datetime.now(UTC)


def test_provider_failure_retains_resolve_job_for_retry(state):
    _, _, session, _ = state
    labels = PrivateActionLabelMap(
        ProviderId("add-sender"), ProviderId("add-domain"), ProviderId("blacklist")
    )
    row = _event(session, label=labels.add_sender_label_id, n=77)
    result = ActionEffectConsumer(
        labels,
        ProviderFailingSource(),
        (AccountAddress("source@example.com"),),
        "source@example.com",
    ).process(session, P, row.event_id)
    assert result.receipt is None and result.attention is ErrorCode.SOURCE_RATE_LIMITED
    with session.transaction() as uow:
        assert reads.get_event(uow, P, row.event_id).processing.value == "pending"
        assert reads.get_job(uow, P, lid(1077)).state.value == "retry_wait"


@pytest.mark.parametrize("label", ["add-sender", "add-domain", "blacklist"])
@pytest.mark.parametrize("retry_after", [None, 120])
def test_provider_retry_deadline_survives_restart(
    state, monkeypatch, label, retry_after
):
    from facet.projection import action_consumer

    _, _, session, _ = state
    labels = PrivateActionLabelMap(
        ProviderId("add-sender"), ProviderId("add-domain"), ProviderId("blacklist")
    )
    row = _event(session, label=ProviderId(label), n=78)
    clock = [datetime.now(UTC)]
    monkeypatch.setattr(action_consumer, "_now", lambda: Timestamp(clock[0]))

    class RateLimitedSource:
        calls = 0

        def get_thread_facts(self, source_thread_id):
            assert source_thread_id == T
            self.calls += 1
            raise ProviderFailure(
                ErrorCode.SOURCE_RATE_LIMITED,
                Role.SOURCE,
                status=429,
                retry_after_seconds=retry_after,
            )

    source = RateLimitedSource()

    def consumer():
        return ActionEffectConsumer(
            labels,
            source,
            (AccountAddress("source@example.com"),),
            "source@example.com",
        )

    result = consumer().process(session, P, row.event_id)
    assert result.attention is ErrorCode.SOURCE_RATE_LIMITED
    deadline = clock[0] + timedelta(seconds=retry_after or 1)
    with session.transaction() as uow:
        job = reads.get_job(uow, P, lid(1078))
        pending_event = reads.get_event(uow, P, row.event_id)
    assert job.state.value == "retry_wait"
    assert job.next_attempt_at.value == deadline
    assert pending_event.processing.value == "pending"
    assert source.calls == 1
    clock[0] += timedelta(seconds=2)
    if retry_after is not None:
        with pytest.raises(StorageFailure) as caught:
            consumer().process(session, P, row.event_id)
        assert caught.value.code is ErrorCode.REQUEST_CONFLICT
        assert source.calls == 1
    with reopen(state) as (_, _, restarted, _):
        with restarted.transaction() as uow:
            restarted_job = reads.get_job(uow, P, lid(1078))
        assert restarted_job.next_attempt_at.value == deadline
        if retry_after is not None:
            with pytest.raises(StorageFailure) as caught:
                consumer().process(restarted, P, row.event_id)
            assert caught.value.code is ErrorCode.REQUEST_CONFLICT
            assert source.calls == 1
            clock[0] = deadline
        assert (
            consumer().process(restarted, P, row.event_id).attention
            is ErrorCode.SOURCE_RATE_LIMITED
        )
        assert source.calls == 2


def _alias_event(session, canonical, n):
    key = replace(canonical.event.key, source_message_id=ProviderId(f"alias-{n}"))
    row = replace(
        canonical,
        event_id=lid(n),
        event_key=event_key(P, key),
        event=replace(canonical.event, key=key),
    )
    with session.transaction() as uow:
        _insert(uow, P, "source_events", row)
        jobs.enqueue(uow, P, resolution(row, n=n + 1000))
    return row


def _business_snapshot(connection):
    tables = (
        "action_commands",
        "rules",
        "rule_revisions",
        "rulesets",
        "ruleset_members",
        "tracked_threads",
        "thread_admissions",
        "insert_attempts",
        "message_mappings",
    )
    return {
        table: connection.execute(f"SELECT * FROM {table}").fetchall()
        for table in tables
    }


@pytest.mark.parametrize("label", ["add-sender", "add-domain", "blacklist"])
def test_multiple_message_label_aliases_complete_without_repeating_effect(state, label):
    _, connection, session, _ = state
    if label == "blacklist":
        publish(session)
        admit(session)
    labels = PrivateActionLabelMap(
        ProviderId("add-sender"), ProviderId("add-domain"), ProviderId("blacklist")
    )
    canonical = _event(session, label=ProviderId(label), n=90)
    epoch = prepare_epoch(session, n=2290)
    consumer = _consumer(
        labels,
        (
            ActionMessageFact(
                ProviderId("canonical-message"),
                T,
                PrivateAddress("bank@vendor.com"),
                NOW,
            ),
        ),
    )
    assert (
        consumer.process(
            session, P, canonical.event_id, epoch_id=epoch.epoch_id
        ).attention
        is None
    )
    before = _business_snapshot(connection)
    expansion_count = connection.execute(
        "SELECT COUNT(*) FROM sync_jobs WHERE kind='expand_thread'"
    ).fetchone()
    no_source = ActionEffectConsumer(
        labels,
        FailingSource(),
        (AccountAddress("source@example.com"),),
        "source@example.com",
    )
    for n in (91, 92, 93):
        alias = _alias_event(session, canonical, n)
        result = no_source.process(session, P, alias.event_id, epoch_id=epoch.epoch_id)
        assert result.attention is None and result.receipt is not None
        with session.transaction() as uow:
            assert (
                reads.get_event(uow, P, alias.event_id).processing.value == "consumed"
            )
            assert reads.get_job(uow, P, lid(n + 1000)).state.value == "completed"
        assert no_source.process(session, P, alias.event_id).attention is None
    assert _business_snapshot(connection) == before
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM sync_jobs WHERE kind='expand_thread'"
        ).fetchone()
        == expansion_count
    )
    assert connection.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)


def test_alias_after_stop_and_restart_never_reactivates_thread(state):
    _, connection, session, _ = state
    labels = PrivateActionLabelMap(ProviderId("add-sender"), None, None)
    canonical = _event(session, label=labels.add_sender_label_id, n=94)
    epoch = prepare_epoch(session, n=2294)
    assert (
        _consumer(
            labels,
            (
                ActionMessageFact(
                    ProviderId("message"), T, PrivateAddress("bank@vendor.com"), NOW
                ),
            ),
        )
        .process(session, P, canonical.event_id, epoch_id=epoch.epoch_id)
        .attention
        is None
    )
    with session.transaction() as uow:
        thread = reads.get_thread(uow, P, T)
        policy.stop_thread(
            uow,
            P,
            T,
            thread.generation,
            Timestamp(datetime.now(UTC)),
            ThreadStopReason.MANUAL_STOP,
        )
    alias = _alias_event(session, canonical, 95)
    before = _business_snapshot(connection)
    with reopen(state) as (_, reopened, restarted, _):
        result = ActionEffectConsumer(
            labels,
            FailingSource(),
            (AccountAddress("source@example.com"),),
            "source@example.com",
        ).process(restarted, P, alias.event_id)
        assert result.attention is None
        assert _business_snapshot(reopened) == before


def test_alias_consumption_rolls_back_with_job_completion(state, monkeypatch):
    _, connection, session, _ = state
    labels = PrivateActionLabelMap(ProviderId("add-sender"), None, None)
    canonical = _event(session, label=labels.add_sender_label_id, n=96)
    epoch = prepare_epoch(session, n=2296)
    assert (
        _consumer(
            labels,
            (
                ActionMessageFact(
                    ProviderId("message"), T, PrivateAddress("bank@vendor.com"), NOW
                ),
            ),
        )
        .process(session, P, canonical.event_id, epoch_id=epoch.epoch_id)
        .attention
        is None
    )
    alias = _alias_event(session, canonical, 97)

    def fail_completion(*args):
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)

    monkeypatch.setattr(events, "complete_noninsert_job", fail_completion)
    with pytest.raises(StorageFailure):
        ActionEffectConsumer(
            labels,
            FailingSource(),
            (AccountAddress("source@example.com"),),
            "source@example.com",
        ).process(session, P, alias.event_id)
    with session.transaction() as uow:
        assert reads.get_event(uow, P, alias.event_id).processing.value == "pending"
        assert reads.get_job(uow, P, lid(1097)).state.value == "claimed"
    assert connection.execute("SELECT COUNT(*) FROM action_commands").fetchone() == (1,)


def _repairable_alias(state, *, reason=ErrorCode.REQUEST_CONFLICT, incomplete=False):
    _, _, session, _ = state
    labels = PrivateActionLabelMap(ProviderId("add-sender"), None, None)
    canonical = _event(session, label=labels.add_sender_label_id, n=104)
    epoch = prepare_epoch(session, n=2304)
    consumer = _consumer(
        labels,
        (
            ActionMessageFact(
                ProviderId("message"), T, PrivateAddress("bank@vendor.com"), NOW
            ),
        ),
    )
    if incomplete:

        def interrupted(*args, **kwargs):
            raise StorageFailure(ErrorCode.OWNER_BUSY)

        consumer._finalize = interrupted
        with pytest.raises(StorageFailure):
            consumer.process(session, P, canonical.event_id, epoch_id=epoch.epoch_id)
    else:
        assert (
            consumer.process(
                session, P, canonical.event_id, epoch_id=epoch.epoch_id
            ).attention
            is None
        )
    alias = _alias_event(session, canonical, 105)
    prepared = consumer._prepare(session, P, alias.event_id)
    consumer._attention(session, P, prepared, reason)
    with session.transaction() as uow:
        return (
            canonical,
            reads.get_event(uow, P, alias.event_id),
            reads.get_job(uow, P, lid(1105)),
            consumer,
        )


def test_explicit_alias_repair_completes_only_selected_pair_and_replays(state):
    _, connection, session, _ = state
    canonical, alias, job, consumer = _repairable_alias(state)
    old = _alias_event(session, canonical, 106)
    consumer._attention(
        session,
        P,
        consumer._prepare(session, P, old.event_id),
        ErrorCode.REQUEST_CONFLICT,
    )
    business = _business_snapshot(connection)
    with session.transaction() as uow:
        old_event = reads.get_event(uow, P, old.event_id)
        old_job = reads.get_job(uow, P, lid(1106))
        events.repair_executed_label_alias(
            uow,
            P,
            alias.event_id,
            RevisionGuard(alias.revision),
            RevisionGuard(job.revision),
        )
    with session.transaction() as uow:
        repaired_event = reads.get_event(uow, P, alias.event_id)
        repaired_job = reads.get_job(uow, P, job.job_id)
        assert (
            repaired_event.processing.value == "consumed"
            and repaired_event.error_code is None
        )
        assert (
            repaired_job.state.value == "completed"
            and repaired_job.last_error_code is None
        )
        assert reads.get_event(uow, P, old.event_id) == old_event
        assert reads.get_job(uow, P, old_job.job_id) == old_job
        assert (
            events.repair_executed_label_alias(
                uow,
                P,
                alias.event_id,
                RevisionGuard(repaired_event.revision),
                RevisionGuard(repaired_job.revision),
            ).disposition
            == "replayed"
        )
    assert _business_snapshot(connection) == business


@pytest.mark.parametrize(
    "fault", ["wrong_reason", "event_revision", "job_revision", "incomplete"]
)
def test_explicit_alias_repair_refuses_unsupported_state(state, fault):
    _, _, session, _ = state
    _, alias, job, _ = _repairable_alias(
        state,
        reason=ErrorCode.CONSISTENCY_FAILURE
        if fault == "wrong_reason"
        else ErrorCode.REQUEST_CONFLICT,
        incomplete=fault == "incomplete",
    )
    from facet.contracts import Revision

    event_revision = Revision(alias.revision.value + (fault == "event_revision"))
    job_revision = Revision(job.revision.value + (fault == "job_revision"))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        events.repair_executed_label_alias(
            uow,
            P,
            alias.event_id,
            RevisionGuard(event_revision),
            RevisionGuard(job_revision),
        )
    with session.transaction() as uow:
        assert reads.get_event(uow, P, alias.event_id) == alias
        assert reads.get_job(uow, P, job.job_id) == job


def test_explicit_alias_repair_rolls_back_both_updates(state, monkeypatch):
    _, _, session, _ = state
    _, alias, job, _ = _repairable_alias(state)
    from facet.db.transactions import UnitOfWork

    execute_sql = UnitOfWork._execute

    def fail_job_update(self, sql, parameters=()):
        if sql.startswith("UPDATE sync_jobs SET state='completed'"):
            raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)
        return execute_sql(self, sql, parameters)

    monkeypatch.setattr(UnitOfWork, "_execute", fail_job_update)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        events.repair_executed_label_alias(
            uow,
            P,
            alias.event_id,
            RevisionGuard(alias.revision),
            RevisionGuard(job.revision),
        )
    with session.transaction() as uow:
        assert reads.get_event(uow, P, alias.event_id) == alias
        assert reads.get_job(uow, P, job.job_id) == job


def test_alias_does_not_override_existing_attention(state):
    _, _, session, _ = state
    labels = PrivateActionLabelMap(ProviderId("add-sender"), None, None)
    canonical = _event(session, label=labels.add_sender_label_id, n=98)
    epoch = prepare_epoch(session, n=2298)
    assert (
        _consumer(
            labels,
            (
                ActionMessageFact(
                    ProviderId("message"), T, PrivateAddress("bank@vendor.com"), NOW
                ),
            ),
        )
        .process(session, P, canonical.event_id, epoch_id=epoch.epoch_id)
        .attention
        is None
    )
    alias = _alias_event(session, canonical, 99)
    from facet.db.codecs import EventProcessing

    with session.transaction() as uow:
        events.classify_event(
            uow,
            P,
            alias.event_id,
            EventProcessing.NEEDS_ATTENTION,
            ErrorCode.REQUEST_CONFLICT,
            (),
            RevisionGuard(alias.revision),
        )
    with pytest.raises(StorageFailure):
        ActionEffectConsumer(
            labels,
            FailingSource(),
            (AccountAddress("source@example.com"),),
            "source@example.com",
        ).process(session, P, alias.event_id)
    with session.transaction() as uow:
        assert (
            reads.get_event(uow, P, alias.event_id).processing.value
            == "needs_attention"
        )


def test_alias_waits_for_canonical_finalization_without_reading_source(
    state, monkeypatch
):
    _, connection, session, _ = state
    labels = PrivateActionLabelMap(ProviderId("add-sender"), None, None)
    canonical = _event(session, label=labels.add_sender_label_id, n=100)
    epoch = prepare_epoch(session, n=2300)
    consumer = _consumer(
        labels,
        (
            ActionMessageFact(
                ProviderId("message"), T, PrivateAddress("bank@vendor.com"), NOW
            ),
        ),
    )
    finalizer = consumer._finalize

    def interrupted(*args, **kwargs):
        raise StorageFailure(ErrorCode.OWNER_BUSY)

    monkeypatch.setattr(consumer, "_finalize", interrupted)
    with pytest.raises(StorageFailure):
        consumer.process(session, P, canonical.event_id, epoch_id=epoch.epoch_id)
    alias = _alias_event(session, canonical, 101)
    no_source = ActionEffectConsumer(
        labels,
        FailingSource(),
        (AccountAddress("source@example.com"),),
        "source@example.com",
    )
    with pytest.raises(StorageFailure) as caught:
        no_source.process(session, P, alias.event_id)
    assert caught.value.code is ErrorCode.OWNER_BUSY
    with session.transaction() as uow:
        assert reads.get_event(uow, P, alias.event_id).processing.value == "pending"
    monkeypatch.setattr(consumer, "_finalize", finalizer)
    assert (
        consumer.process(
            session, P, canonical.event_id, epoch_id=epoch.epoch_id
        ).attention
        is None
    )
    assert no_source.process(session, P, alias.event_id).attention is None
    assert connection.execute("SELECT COUNT(*) FROM action_commands").fetchone() == (1,)


@pytest.mark.parametrize("fault", ["history", "label", "thread", "removed"])
def test_repository_refuses_mismatched_alias_activation(state, fault):
    _, _, session, _ = state
    labels = PrivateActionLabelMap(ProviderId("add-sender"), None, None)
    canonical = _event(session, label=labels.add_sender_label_id, n=102)
    epoch = prepare_epoch(session, n=2302)
    assert (
        _consumer(
            labels,
            (
                ActionMessageFact(
                    ProviderId("message"), T, PrivateAddress("bank@vendor.com"), NOW
                ),
            ),
        )
        .process(session, P, canonical.event_id, epoch_id=epoch.epoch_id)
        .attention
        is None
    )
    key = replace(
        canonical.event.key, source_message_id=ProviderId("wrong-alias-message")
    )
    thread = T
    if fault == "history":
        key = replace(key, history_record_id=ProviderId("other-history"))
    elif fault == "label":
        key = replace(key, label_id=ProviderId("other-label"))
    elif fault == "thread":
        thread = ProviderId("other-thread")
    else:
        key = replace(key, change=LabelChange.REMOVED)
    alias = replace(
        canonical,
        event_id=lid(103),
        event_key=event_key(P, key),
        event=replace(canonical.event, key=key, source_thread_id=thread),
    )
    with session.transaction() as uow:
        _insert(uow, P, "source_events", alias)
        jobs.enqueue(uow, P, resolution(alias, n=1103))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        events.consume_executed_label_alias(
            uow, P, alias.event_id, RevisionGuard(alias.revision)
        )
    with session.transaction() as uow:
        assert reads.get_event(uow, P, alias.event_id).processing.value == "pending"
