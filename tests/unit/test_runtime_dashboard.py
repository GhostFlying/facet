"""Aggregate runtime Dashboard snapshots stay private and read-only."""

import os
import sqlite3
import sys
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))

from test_projection_worker import (
    _payload,
    _raw,
    _ready_owner,
    _worker_adapters,
)

from facet.cli import bootstrap
from facet.cli.bootstrap import _foreground_gate
from facet.contracts import BindingState, ErrorCode, PublicHealth
from facet.runtime.dashboard import (
    LiveSnapshotProvider,
    _activity,
    _commit_sha,
    _disk_pressure,
    _memory_pressure,
    _resource_pressure,
    _scope_state,
    snapshot_from_owner,
)

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


def test_diagnostics_provenance_and_pressure_boundaries(monkeypatch):
    monkeypatch.setenv("FACET_COMMIT_SHA", "A" * 40)
    assert _commit_sha() == "a" * 40
    monkeypatch.setenv("FACET_COMMIT_SHA", "manual-tag")
    assert _commit_sha() is None
    assert _resource_pressure(4, 100).value == "critical"
    assert _resource_pressure(14, 100).value == "elevated"
    assert _resource_pressure(15, 100).value == "normal"
    assert _resource_pressure(None, 100).value == "unknown"


def test_memory_disk_measurements_and_unavailable_reads(monkeypatch):
    from facet.runtime import dashboard

    values = {
        "/sys/fs/cgroup/memory.max": "100",
        "/sys/fs/cgroup/memory.current": "96",
        "/proc/meminfo": "MemTotal: 100 kB\nMemAvailable: 50 kB\n",
    }

    def read(path, **kwargs):
        return StringIO(values[path])

    monkeypatch.setattr("builtins.open", read)
    assert _memory_pressure().value == "critical"
    values["/sys/fs/cgroup/memory.max"] = "max"
    assert _memory_pressure().value == "normal"

    def unavailable(*args, **kwargs):
        raise OSError

    monkeypatch.setattr("builtins.open", unavailable)
    assert _memory_pressure().value == "unknown"
    monkeypatch.setattr(
        dashboard.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=14, total=100),
    )
    assert _disk_pressure(SimpleNamespace(_state_dir="unused")).value == "elevated"
    monkeypatch.setattr(dashboard.shutil, "disk_usage", unavailable)
    assert _disk_pressure(SimpleNamespace(_state_dir="unused")).value == "unknown"


def test_scope_readiness_requires_current_committed_credential_lineage():
    from facet.config import initial_template
    from facet.contracts import Role

    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE credential_changes (projection_id TEXT,role TEXT,phase TEXT,"
        "new_revision INTEGER,binding_revision INTEGER,scope_policy TEXT,"
        "updated_at INTEGER)"
    )
    uow = SimpleNamespace(_execute=connection.execute)
    config = initial_template("source@example.invalid", "target@example.invalid")
    projection = config.projection.id
    binding = SimpleNamespace(
        state=BindingState.VERIFIED,
        credential_revision=SimpleNamespace(value=2),
        binding_revision=SimpleNamespace(value=3),
    )
    assert (
        _scope_state(uow, projection, binding, config, Role.SOURCE).value == "unknown"
    )
    connection.execute(
        "INSERT INTO credential_changes VALUES (?,?,?,?,?,?,?)",
        (projection.value, "source", "committed", 2, 3, "source_readonly", 1),
    )
    assert _scope_state(uow, projection, binding, config, Role.SOURCE).value == "ok"
    binding.binding_revision.value = 4
    assert (
        _scope_state(uow, projection, binding, config, Role.SOURCE).value == "unknown"
    )
    binding.state = BindingState.AUTH_REQUIRED
    assert _scope_state(uow, projection, binding, config, Role.SOURCE).value == "failed"


def test_activity_aggregates_domain_caps_rows_and_keeps_manual_as_other():
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE mapping_history (
          projection_id TEXT, source_message_id TEXT, mapping_revision INTEGER,
          source_thread_id TEXT, attempt_id TEXT, target_message_id TEXT,
          target_thread_id TEXT, verified_at INTEGER
        );
        CREATE TABLE insert_attempts (
          projection_id TEXT, attempt_id TEXT, source_thread_id TEXT, generation INTEGER
        );
        CREATE TABLE thread_admissions (
          projection_id TEXT, source_thread_id TEXT, generation INTEGER, rule_id TEXT
        );
        CREATE TABLE rules (
          projection_id TEXT, rule_id TEXT, kind TEXT, normalized_value TEXT
        );
        """
    )
    for index in range(101):
        rule_id = "sender-rule" if index % 2 else "domain-rule"
        thread = f"thread-{index}"
        attempt = f"attempt-{index}"
        connection.execute(
            "INSERT INTO insert_attempts VALUES (?,?,?,?)",
            ("projection", attempt, thread, 1),
        )
        connection.execute(
            "INSERT INTO thread_admissions VALUES (?,?,?,?)",
            ("projection", thread, 1, rule_id),
        )
        connection.execute(
            "INSERT INTO mapping_history VALUES (?,?,?,?,?,?,?,?)",
            (
                "projection",
                f"message-{index}",
                1,
                thread,
                attempt,
                f"target-{index}",
                f"target-thread-{index}",
                (index + 1) * 60_000_000,
            ),
        )
    connection.executemany(
        "INSERT INTO rules VALUES (?,?,?,?)",
        (
            ("projection", "sender-rule", "allow_sender", "sender@example.test"),
            ("projection", "domain-rule", "allow_domain", "example.test"),
        ),
    )
    # A later admission must not recategorize the earlier generation's result.
    connection.execute(
        "INSERT INTO thread_admissions VALUES (?,?,?,?)",
        ("projection", "thread-100", 3, "sender-rule"),
    )
    # Two mappings attributed to the same rule and minute are one batch.
    connection.execute(
        "INSERT INTO mapping_history VALUES (?,?,?,?,?,?,?,?)",
        (
            "projection",
            "another-message",
            1,
            "thread-100",
            "attempt-100",
            "another-target",
            "target-thread-100",
            101 * 60_000_000 + 1,
        ),
    )
    uow = SimpleNamespace(_execute=connection.execute)
    activity = _activity(uow, SimpleNamespace(value="projection"))
    assert len(activity.entries) == 100
    assert activity.entries[0].rule_kind == "allow_domain"
    assert activity.entries[0].matched_count == 2
    assert all(
        left.observed_at.value >= right.observed_at.value
        for left, right in zip(activity.entries, activity.entries[1:], strict=False)
    )
    assert {entry.rule_kind for entry in activity.entries} == {
        "allow_sender",
        "allow_domain",
    }

    connection.execute(
        "INSERT INTO insert_attempts VALUES (?,?,?,?)",
        ("projection", "manual-attempt", "manual-thread", 1),
    )
    connection.execute(
        "INSERT INTO thread_admissions VALUES (?,?,?,?)",
        ("projection", "manual-thread", 1, None),
    )
    connection.execute(
        "INSERT INTO mapping_history VALUES (?,?,?,?,?,?,?,?)",
        (
            "projection",
            "manual-message",
            1,
            "manual-thread",
            "manual-attempt",
            "manual-target",
            "manual-target-thread",
            9_999_000_000,
        ),
    )
    connection.execute(
        "INSERT INTO mapping_history VALUES (?,?,?,?,?,?,?,?)",
        (
            "projection",
            "manual-message",
            2,
            "manual-thread",
            "manual-attempt",
            "manual-target",
            "manual-target-thread",
            9_999_000_000,
        ),
    )
    other = _activity(uow, SimpleNamespace(value="projection"))
    assert other.entries[0].rule_kind == "other"
    assert other.entries[0].rule_value == "Other authorized thread"
    assert other.entries[0].matched_count == 1


def test_snapshot_from_initialized_owner_is_aggregate_only(
    trusted_state_parent, monkeypatch
):
    owner = _ready_owner(trusted_state_parent, object(), monkeypatch, seed=False)
    try:
        snapshots = snapshot_from_owner(owner, owner.config, cycle_verified=True)
        status = snapshots["status"].data
        progress = snapshots["progress"].data
        assert status.health is PublicHealth.HEALTHY
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


def test_snapshot_marks_an_inflight_cycle_without_claiming_healthy(
    trusted_state_parent, monkeypatch
):
    owner = _ready_owner(trusted_state_parent, object(), monkeypatch, seed=False)
    try:
        status = snapshot_from_owner(
            owner, owner.config, cycle_verified=False, cycle_in_progress=True
        )["status"].data
        assert status.health is PublicHealth.UNKNOWN
        assert status.cycle_in_progress is True
    finally:
        owner.close()


def test_activity_uses_first_verified_rule_batch_and_survives_restart(
    trusted_state_parent, gmail_controller, monkeypatch
):
    gmail_controller.seed(
        "source",
        "m-activity",
        "thread-1",
        _raw("activity", "ACTIVITY_SENTINEL"),
        payload=_payload(_raw("activity", "ACTIVITY_SENTINEL")),
    )
    owner = _ready_owner(trusted_state_parent, gmail_controller, monkeypatch)
    try:
        worker, source, target = _worker_adapters(gmail_controller, owner)
        assert worker.run(max_jobs=5).verified == 1
        snapshot = snapshot_from_owner(owner, owner.config, cycle_verified=True)
        entries = snapshot["activity"].data.entries
        assert [
            (entry.rule_kind, entry.rule_value, entry.matched_count)
            for entry in entries
        ] == [("allow_sender", "synthetic@example.com", 1)]
        assert "ACTIVITY_SENTINEL" not in repr(snapshot)
        with owner.session.transaction() as uow:
            uow._execute(
                "INSERT INTO mapping_history "
                "SELECT projection_id,source_message_id,2,source_thread_id,"
                "attempt_id,target_message_id,target_thread_id,verified_at,NULL "
                "FROM mapping_history WHERE projection_id=? AND mapping_revision=1",
                (owner.projection_id.value,),
            )
        assert (
            len(snapshot_from_owner(owner, owner.config)["activity"].data.entries) == 1
        )
        owner.close()
        reopened = __import__(
            "facet.runtime.state_owner", fromlist=["StateOwner"]
        ).StateOwner.open(trusted_state_parent / "state", owner.config)
        try:
            replay = _worker_adapters(gmail_controller, reopened)[0]
            assert replay.run(max_jobs=5).processed == 0
            assert (
                len(
                    snapshot_from_owner(reopened, reopened.config)[
                        "activity"
                    ].data.entries
                )
                == 1
            )
        finally:
            reopened.close()
    finally:
        if owner._connection is not None:
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


def test_foreground_loop_publishes_start_and_retains_error_until_success(monkeypatch):
    from itertools import count

    from facet.config import initial_template
    from facet.gmail.retry import ProviderFailure
    from facet.runtime import dashboard, foreground_runtime

    published = []

    class Provider:
        def publish_from_owner(self, owner, config, **values):
            published.append(values)

        def invalidate(self):
            raise AssertionError("unexpected invalidation")

    server = SimpleNamespace(
        serve_forever=lambda: None, shutdown=lambda: None, server_close=lambda: None
    )
    monkeypatch.setattr("facet.web.server.DashboardServer", lambda *args: server)
    monkeypatch.setattr(dashboard, "LiveSnapshotProvider", Provider)
    monkeypatch.setattr(bootstrap, "read_managed_config", lambda paths: b"config")
    monkeypatch.setattr(bootstrap, "_foreground_gate", lambda owner: (True, None))
    monkeypatch.setattr(bootstrap, "monotonic", lambda: next(ticks))
    ticks = count(step=3)

    def wait(stop, interval, refresh):
        refresh()
        return True

    monkeypatch.setattr(bootstrap, "_wait_with_local_heartbeat", wait)
    calls = 0

    def cycle(owner, config, factory, *, progress, should_stop):
        nonlocal calls
        calls += 1
        assert published[-1]["cycle_in_progress"] is True
        if calls == 1:
            raise ProviderFailure(ErrorCode.SOURCE_AUTH_REQUIRED, Role.SOURCE)
        assert published[-1]["error_code"] is ErrorCode.SOURCE_AUTH_REQUIRED
        progress()
        assert published[-1]["error_code"] is ErrorCode.SOURCE_AUTH_REQUIRED
        should_stop.__self__.set()
        return SimpleNamespace(warnings=(), projected=SimpleNamespace(verified=0))

    from facet.contracts import Role

    monkeypatch.setattr(foreground_runtime, "run_foreground_once", cycle)
    owner = SimpleNamespace(verify_config_artifact=lambda raw: None)
    config = initial_template("source@example.invalid", "target@example.invalid")
    options = SimpleNamespace(host="127.0.0.1", port=18084, interval=60)
    bootstrap._run_foreground_service(options, owner=owner, config=config)
    assert calls == 2
    assert any(
        values["cycle_in_progress"] is False
        and values["error_code"] is ErrorCode.SOURCE_AUTH_REQUIRED
        for values in published
    )
    assert published[-1] == {
        "error_code": None,
        "cycle_verified": True,
        "cycle_in_progress": False,
    }
