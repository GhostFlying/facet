"""Real adapter eligibility through durable History and guarded legacy repair."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from test_history_admission import HistorySource, _runner
from test_projection_worker import _ready_owner, _trusted_parent
from test_sync import _Target

from facet.contracts import ErrorCode, LocalId, ProviderId, Role
from facet.db.codecs import PrivateAddress
from facet.db.keys import event_key
from facet.db.repositories.base import _get, _insert
from facet.gmail.retry import ProviderFailure
from facet.gmail.source import SourceAdapter


@pytest.fixture
def state(monkeypatch, gmail_controller):
    with TemporaryDirectory(dir=_trusted_parent()) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch, seed=False)
        owner.ensure_current_action_schema(LocalId(uuid4().hex), b"synthetic-config")
        source = HistorySource(owner)
        adapter = SourceAdapter(
            gmail_controller.service("source"),
            source_account=PrivateAddress(owner.config.projection.source_email),
        )
        source.history_candidate = adapter.history_candidate
        source.candidate = adapter.candidate
        target = _Target(source.raw_bytes)
        try:
            yield owner, source, target, gmail_controller
        finally:
            owner.close()


def metadata(state, labels=(), *, headers=None):
    state[3].script(
        "source",
        "messages.get",
        {"userId": "me", "id": "m-new", "format": "metadata"},
        {
            "id": "m-new",
            "threadId": "thread-1",
            "labelIds": list(labels),
            "internalDate": "1791244800000",
            "payload": {
                "headers": headers
                if headers is not None
                else [{"name": "From", "value": "PRIVATE_BAD@@FROM"}]
            },
        },
    )


@pytest.mark.parametrize("label", ["SPAM", "TRASH", "DRAFT"])
def test_history_ineligible_malformed_from_is_consumed_without_projection(state, label):
    owner, source, target, _ = state
    metadata(state, (label,))
    result = _runner(owner, source, target).run_once()
    assert result.attention == 0
    assert target.inserted == 0
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM tracked_threads"
    ).fetchone() == (0,)
    assert owner._connection.execute(
        "SELECT processing,error_code FROM source_events"
    ).fetchone() == ("consumed", None)
    assert owner._connection.execute(
        "SELECT state,last_error_code FROM sync_jobs"
    ).fetchone() == ("completed", None)


def seed_legacy(state):
    owner, source, target, _ = state
    metadata(state)
    assert _runner(owner, source, target).run_once().attention == 1
    assert owner._connection.execute(
        "SELECT last_error_code FROM sync_jobs"
    ).fetchone() == ("invalid_input",)
    with owner.session.transaction() as uow:
        uow._execute("UPDATE source_events SET error_code='request_conflict'")
        uow._execute("UPDATE sync_jobs SET last_error_code='request_conflict'")
    source.arrivals = False
    return _runner(owner, source, target)


def test_legacy_exclusion_is_audited_idempotent_and_preserves_cursor(state):
    owner, source, target, _ = state
    runner = seed_legacy(state)
    cursor = owner._connection.execute("SELECT * FROM history_checkpoints").fetchall()
    metadata(state, ("SPAM",))
    assert runner._converge_completed_events(100) == 1
    assert runner._converge_completed_events(100) == 0
    assert target.inserted == 0
    assert (
        owner._connection.execute("SELECT * FROM history_checkpoints").fetchall()
        == cursor
    )
    assert owner._connection.execute(
        "SELECT processing,error_code FROM source_events"
    ).fetchone() == ("consumed", None)
    assert owner._connection.execute(
        "SELECT before_state,after_state,error_code FROM audit_events "
        "WHERE error_code='request_conflict'"
    ).fetchall() == [("needs_attention", "completed", "request_conflict")]
    for path in Path(owner.state_dir).glob("facet.db*"):
        assert b"PRIVATE_BAD@@FROM" not in path.read_bytes()


@pytest.mark.parametrize("change", ["revision", "action_receipt"])
def test_legacy_repair_rechecks_state_after_source_read(state, change):
    owner, source, _, _ = state
    runner = seed_legacy(state)
    original = source.history_candidate

    def changed(item):
        assert not owner._connection.in_transaction
        result = original(item)
        with owner.session.transaction() as uow:
            if change == "revision":
                uow._execute("UPDATE sync_jobs SET revision=revision+1")
            else:
                event_id = uow._execute(
                    "SELECT event_id FROM source_events"
                ).fetchone()[0]
                uow._execute(
                    "INSERT INTO current_action_receipts "
                    "VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,'suppressed')",
                    (
                        owner.projection_id.value,
                        uuid4().hex,
                        "thread-1",
                        "add_sender",
                        "synthetic-label",
                        1,
                        event_id,
                        int(datetime.now(UTC).timestamp() * 1e6),
                    ),
                )
        return result

    source.history_candidate = changed
    metadata(state, ("SPAM",))
    assert runner._converge_completed_events(100) == 0
    assert owner._connection.execute(
        "SELECT state,last_error_code FROM sync_jobs"
    ).fetchone() == ("needs_attention", "request_conflict")


@pytest.mark.parametrize("case", ["eligible", "malformed", "network", "404"])
def test_legacy_repair_requires_positive_exclusion(state, case):
    owner, source, _, _ = state
    runner = seed_legacy(state)
    if case in {"network", "404"}:

        def fail(item):
            raise ProviderFailure(
                ErrorCode.NETWORK_UNAVAILABLE,
                Role.SOURCE,
                status=404 if case == "404" else None,
            )

        source.history_candidate = fail
    else:
        metadata(
            state,
            headers=[{"name": "From", "value": "synthetic@example.com"}]
            if case == "eligible"
            else None,
        )
    assert runner._converge_completed_events(100) == 0
    assert owner._connection.execute("SELECT state FROM sync_jobs").fetchone() == (
        "needs_attention",
    )


@pytest.mark.parametrize("relationship", ["event", "thread"])
def test_prior_action_receipt_prevents_even_metadata_recheck(state, relationship):
    owner, _, _, _ = state
    runner = seed_legacy(state)
    with owner.session.transaction() as uow:
        event_id = uow._execute("SELECT event_id FROM source_events").fetchone()[0]
        if relationship == "thread":
            old = _get(
                uow,
                owner.projection_id,
                "source_events",
                (("event_id", LocalId(event_id)),),
            )
            key = replace(
                old.event.key, history_record_id=ProviderId("different-record")
            )
            other = replace(
                old,
                event_id=LocalId(uuid4().hex),
                event_key=event_key(owner.projection_id, key),
                event=replace(old.event, key=key),
            )
            _insert(uow, owner.projection_id, "source_events", other)
            event_id = other.event_id.value
        uow._execute(
            "INSERT INTO current_action_receipts "
            "VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,'suppressed')",
            (
                owner.projection_id.value,
                uuid4().hex,
                "thread-1" if relationship == "thread" else "different-thread",
                "add_sender",
                "synthetic-label",
                1,
                event_id,
                int(datetime.now(UTC).timestamp() * 1e6),
            ),
        )
    assert runner._converge_completed_events(100) == 0


def test_legacy_repair_audit_failure_rolls_back_completion(state, monkeypatch):
    from facet.db.codecs import StorageFailure
    from facet.db.repositories import ineligible_events

    owner, _, _, _ = state
    runner = seed_legacy(state)
    metadata(state, ("SPAM",))

    def fail(*args, **kwargs):
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)

    monkeypatch.setattr(ineligible_events, "_audit", fail)
    with pytest.raises(StorageFailure):
        runner._converge_completed_events(100)
    assert owner._connection.execute(
        "SELECT processing,error_code FROM source_events"
    ).fetchone() == ("needs_attention", "request_conflict")
    assert owner._connection.execute(
        "SELECT state,last_error_code FROM sync_jobs"
    ).fetchone() == ("needs_attention", "request_conflict")
