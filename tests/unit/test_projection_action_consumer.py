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
from facet.db.codecs import ActionKind, PrivateAddress, StorageFailure
from facet.db.keys import event_key
from facet.db.repositories import jobs, reads
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


def test_removed_label_becomes_attention_without_source_read(state):
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
    assert result.receipt is None
    assert result.attention is not None
    with session.transaction() as uow:
        assert (
            reads.get_event(uow, P, row.event_id).processing.value == "needs_attention"
        )
        assert reads.get_job(uow, P, lid(1075)).state.value == "needs_attention"


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
