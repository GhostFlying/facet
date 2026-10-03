"""File-backed restart/replay evidence for the action effect boundary."""

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))

import pytest
from test_db_actions import prepare_epoch, reopen
from test_db_events import event, resolution
from test_db_repositories import T, ready_test_metadata
from test_db_repositories import state as state
from test_db_schema import NOW, P

from facet.contracts import LabelChange, ProviderId
from facet.db.codecs import PrivateAddress
from facet.db.keys import event_key
from facet.db.repositories import jobs, reads
from facet.db.repositories.base import _insert
from facet.gmail.credentials import AccountAddress
from facet.projection.action_consumer import ActionEffectConsumer
from facet.projection.actions import ActionMessageFact, PrivateActionLabelMap


class CountingSource:
    def __init__(self):
        self.calls = 0

    def get_thread_facts(self, source_thread_id):
        self.calls += 1
        assert source_thread_id == T
        return (
            ActionMessageFact(
                ProviderId("message-restart"),
                T,
                PrivateAddress("bank@vendor.com"),
                NOW,
            ),
        )


@pytest.fixture(autouse=True)
def ready_metadata(state):
    _, connection, session, _ = state
    ready_test_metadata(connection, session)


def test_action_effect_reopens_and_replays_without_refetching_source(state):
    path, _, session, _ = state
    labels = PrivateActionLabelMap(
        ProviderId("add-sender"), ProviderId("add-domain"), ProviderId("blacklist")
    )
    row = event(80, thread=T, tag="label_changed", change=LabelChange.ADDED)
    key = replace(row.event.key, label_id=labels.add_sender_label_id)
    row = replace(
        row,
        event_key=event_key(P, key),
        event=replace(row.event, key=key),
    )
    with session.transaction() as uow:
        _insert(uow, P, "source_events", row)
        jobs.enqueue(uow, P, resolution(row, n=1080))
    epoch = prepare_epoch(session, n=1300)
    source = CountingSource()
    consumer = ActionEffectConsumer(
        labels,
        source,
        (AccountAddress("source@example.com"),),
        "source@example.com",
    )
    first = consumer.process(session, P, row.event_id, epoch_id=epoch.epoch_id)
    assert first.receipt is not None and source.calls == 1
    with reopen(state) as (_, _, reopened, _):
        second = consumer.process(reopened, P, row.event_id, epoch_id=epoch.epoch_id)
        assert second.receipt is not None and source.calls == 1
        with reopened.transaction() as uow:
            assert reads.get_event(uow, P, row.event_id).processing.value == "consumed"
            assert reads.get_job(uow, P, first.receipt.object_id) is None
    assert path.exists()
