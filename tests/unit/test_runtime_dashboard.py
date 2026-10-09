"""Aggregate runtime Dashboard snapshots stay private and read-only."""

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))

from test_projection_worker import _ready_owner

from facet.cli import bootstrap
from facet.cli.bootstrap import _foreground_gate
from facet.contracts import BindingState, ErrorCode, PublicHealth
from facet.runtime.dashboard import LiveSnapshotProvider, snapshot_from_owner

pytest_plugins = ("test_foreground_runtime",)


@pytest.fixture
def trusted_state_parent():
    with TemporaryDirectory(
        prefix="facet-dashboard-", dir=f"/run/user/{os.geteuid()}"
    ) as root:
        yield Path(root)


def test_provider_is_unavailable_until_a_snapshot_is_published():
    provider = LiveSnapshotProvider()
    assert provider.ready() is False
    assert provider.snapshot("status").freshness.value == "unavailable"


def test_snapshot_from_initialized_owner_is_aggregate_only(
    trusted_state_parent, monkeypatch
):
    owner = _ready_owner(trusted_state_parent, object(), monkeypatch, seed=False)
    try:
        snapshots = snapshot_from_owner(owner, owner.config)
        status = snapshots["status"].data
        progress = snapshots["progress"].data
        assert status.health is PublicHealth.UNKNOWN
        assert status.source.auth_state is BindingState.VERIFIED
        assert status.target.auth_state is BindingState.VERIFIED
        assert progress.confirmed_messages == 0
        encoded = str(snapshots)
        for forbidden in (
            "source@example",
            "target@example",
            "subject",
            "body",
            "raw",
            "RUNTIME_PRIVATE_SENTINEL",
        ):
            assert forbidden not in encoded
    finally:
        owner.close()


def test_snapshot_reports_epoch_thread_progress_without_private_values(
    trusted_state_parent, monkeypatch
):
    owner = _ready_owner(trusted_state_parent, object(), monkeypatch, seed=True)
    try:
        progress = snapshot_from_owner(owner, owner.config)["progress"].data
        assert progress.discovery_complete is False
        assert progress.discovered_threads == 1
        assert progress.completed_threads == 0
        assert progress.known_message_total is None
    finally:
        owner.close()


def test_foreground_gate_blocks_pending_bindings_without_provider_access(
    trusted_state_parent,
):
    from facet.config import initial_template
    from facet.runtime.state_owner import StateOwner

    owner = StateOwner.create(
        trusted_state_parent / "state",
        initial_template("source@example.invalid", "target@example.invalid"),
        b"synthetic-config",
    )
    try:
        assert _foreground_gate(owner) == (False, ErrorCode.BINDING_PENDING)
    finally:
        owner.close()


def test_idle_wait_refreshes_local_snapshot_without_shortening_interval(monkeypatch):
    class Stop:
        def __init__(self):
            self.waits = []

        def is_set(self):
            return False

        def wait(self, value):
            self.waits.append(value)
            return False

    clock = iter((0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0))
    monkeypatch.setattr(bootstrap, "monotonic", lambda: next(clock))
    stop = Stop()
    refreshed = []
    assert bootstrap._wait_with_local_heartbeat(
        stop, 60.0, lambda: refreshed.append(True)
    )
    assert stop.waits == [10.0] * 5
    assert len(refreshed) == 5


def test_idle_wait_stop_does_not_publish_an_extra_heartbeat():
    class Stop:
        def is_set(self):
            return False

        def wait(self, _value):
            return True

    refreshed = []
    assert not bootstrap._wait_with_local_heartbeat(
        Stop(), 60.0, lambda: refreshed.append(True)
    )
    assert refreshed == []
