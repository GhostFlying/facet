"""Focused current-tag transaction/upgrade evidence; full CLI tested separately."""

from dataclasses import replace

import pytest
from test_db_actions import action_row, prepare_epoch
from test_db_repositories import T, ready_test_metadata
from test_db_repositories import state as state
from test_db_schema import NOW, P
from test_projection_action_consumer import _event

from facet.contracts import ErrorCode, LabelChange, ProviderId
from facet.db.codecs import (
    ActionKind,
    ActionState,
    EventProcessing,
    PrivateAddress,
    StorageFailure,
)
from facet.db.migrations.v0004 import STATEMENTS
from facet.db.repositories.base import _insert
from facet.gmail.source import MessageMetadata, ThreadMetadata
from facet.projection.actions import PrivateActionLabelMap
from facet.projection.current_actions import CurrentActionConsumer


class Source:
    def __init__(self, labels=(), *, sender="sender@vendor.com", draft=False):
        self.reads = 0
        self.metadata = ThreadMetadata(
            T,
            (
                MessageMetadata(
                    ProviderId("message-current"),
                    T,
                    tuple(labels) + (("DRAFT",) if draft else ()),
                    NOW.value,
                    (("From", sender),),
                ),
            ),
        )

    def thread_metadata(self, thread_id):
        assert thread_id == T
        self.reads += 1
        return self.metadata


@pytest.fixture(autouse=True)
def current_catalogue(state):
    _, connection, session, _ = state
    ready_test_metadata(connection, session)
    # Repository tests use an owned synthetic v1 UoW plus the exact new DDL.
    # Production version dispatch/migration is exercised by real CLI tests.
    with session.transaction() as uow:
        for statement in STATEMENTS:
            uow._execute(statement)


def consumer(source, labels):
    return CurrentActionConsumer(
        labels, source, (PrivateAddress("source@example.com"),), "source@example.com"
    )


def test_absent_unknown_removal_closes_without_sender_parsing(state):
    _, db, session, _ = state
    row = _event(session, label=ProviderId("deleted-label"), change=LabelChange.REMOVED)
    source = Source(sender="malformed@@sensitive.invalid")
    consumer(
        source, PrivateActionLabelMap(ProviderId("current-sender"), None, None)
    ).process(session, P, row.event_id)
    assert db.execute("SELECT processing,error_code FROM source_events").fetchone() == (
        "consumed",
        None,
    )
    assert db.execute("SELECT COUNT(*) FROM current_action_receipts").fetchone() == (0,)
    assert db.execute("SELECT COUNT(*) FROM rules").fetchone() == (0,)


def test_empty_label_catalogue_needs_no_thread_read(state):
    _, db, session, _ = state
    row = _event(session, label=ProviderId("deleted-label"))
    source = Source()
    consumer(source, None).process(session, P, row.event_id)
    assert source.reads == 0
    assert db.execute("SELECT state FROM sync_jobs").fetchone() == ("completed",)


def test_current_draft_only_tag_is_not_activation(state):
    _, db, session, _ = state
    row = _event(session, label=ProviderId("deleted-label"))
    source = Source(("current-sender",), draft=True, sender="bad@@invalid")
    consumer(
        source, PrivateActionLabelMap(ProviderId("current-sender"), None, None)
    ).process(session, P, row.event_id)
    assert db.execute("SELECT COUNT(*) FROM current_action_receipts").fetchone() == (0,)


def test_four_notifications_use_one_snapshot_and_one_activation(state):
    _, db, session, _ = state
    epoch = prepare_epoch(session)
    rows = [
        _event(session, label=ProviderId("deleted-label"), n=n) for n in range(50, 54)
    ]
    source = Source(("current-sender",))
    actor = consumer(
        source, PrivateActionLabelMap(ProviderId("current-sender"), None, None)
    )
    for row in rows:
        actor.process(session, P, row.event_id, epoch_id=epoch.epoch_id)
    assert source.reads == 1
    assert db.execute("SELECT COUNT(*) FROM current_action_receipts").fetchone() == (1,)
    assert db.execute(
        "SELECT COUNT(*) FROM sync_jobs WHERE kind='expand_thread'"
    ).fetchone() == (1,)


def test_notification_failure_rolls_back_effect_receipt_and_ack(state, monkeypatch):
    _, db, session, _ = state
    epoch = prepare_epoch(session)
    row = _event(session, label=ProviderId("deleted-label"))
    actor = consumer(
        Source(("current-sender",)),
        PrivateActionLabelMap(ProviderId("current-sender"), None, None),
    )

    def fail(*args):
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)

    monkeypatch.setattr(actor, "_complete_notification", fail)
    with pytest.raises(StorageFailure):
        actor.process(session, P, row.event_id, epoch_id=epoch.epoch_id)
    for table in (
        "rules",
        "tracked_threads",
        "current_action_receipts",
        "current_action_observations",
    ):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
    assert db.execute("SELECT processing FROM source_events").fetchone() == ("pending",)
    assert db.execute("SELECT state FROM sync_jobs").fetchone() == ("queued",)


def test_pending_legacy_identity_does_not_collide_with_current_category(state):
    _, db, session, _ = state
    epoch = prepare_epoch(session)
    row = _event(session, label=ProviderId("current-label"))
    legacy = replace(
        action_row(source=replace(row, processing=EventProcessing.RESOLVED)),
        kind=ActionKind.ADD_SENDER,
    )
    with session.transaction() as uow:
        _insert(uow, P, "action_commands", legacy)
    actor = consumer(
        Source(("current-label",)),
        PrivateActionLabelMap(None, ProviderId("current-label"), None),
    )
    actor.process(session, P, row.event_id, epoch_id=epoch.epoch_id)
    assert db.execute("SELECT kind,state FROM action_commands").fetchone() == (
        "add_sender",
        "pending",
    )
    assert db.execute("SELECT action_kind FROM current_action_receipts").fetchone() == (
        "add_domain",
    )


@pytest.mark.parametrize("matching", [True, False])
def test_upgrade_seeds_only_matching_executed_legacy_label(state, matching):
    _, db, session, _ = state
    epoch = prepare_epoch(session)
    old = _event(session, label=ProviderId("old-label"), n=60)
    legacy = replace(
        action_row(source=replace(old, processing=EventProcessing.RESOLVED)),
        state=ActionState.EXECUTED,
        executed_at=NOW,
    )
    with session.transaction() as uow:
        _insert(uow, P, "action_commands", legacy)
    row = _event(session, label=ProviderId("obsolete-trigger"), n=61)
    identifier = ProviderId("old-label" if matching else "recreated-label")
    actor = consumer(
        Source((identifier.value,)), PrivateActionLabelMap(identifier, None, None)
    )
    actor.process(session, P, row.event_id, epoch_id=epoch.epoch_id)
    assert db.execute("SELECT COUNT(*) FROM current_action_receipts").fetchone() == (
        0 if matching else 1,
    )
    assert db.execute("SELECT state FROM action_commands").fetchone() == ("executed",)
