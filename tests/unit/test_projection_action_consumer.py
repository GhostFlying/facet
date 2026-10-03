"""Synthetic end-to-end evidence for the readonly action effect consumer."""

from dataclasses import replace

import pytest
from test_db_actions import prepare_epoch
from test_db_events import event, resolution
from test_db_repositories import (
    T,
    admit,
    publish,
    ready_test_metadata,
)
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import LabelChange, ProviderId
from facet.db.codecs import PrivateAddress
from facet.db.keys import event_key
from facet.db.repositories import jobs, reads
from facet.db.repositories.base import _insert
from facet.gmail.credentials import AccountAddress
from facet.projection.action_consumer import ActionEffectConsumer
from facet.projection.actions import ActionMessageFact, PrivateActionLabelMap


class Source:
    def __init__(self, facts):
        self.facts = facts

    def get_thread_facts(self, source_thread_id):
        assert source_thread_id == T
        return self.facts


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
            reads.get_event(uow, P, row.event_id).processing.value
            == "needs_attention"
        )
        assert reads.get_job(uow, P, lid(1075)).state.value == "needs_attention"
