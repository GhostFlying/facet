"""MG07: freshly owned actual SIGKILL, complete old-or-target kernel reopen."""

import fcntl
import os
import select
import signal
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "unit"))

from test_db_migration_entry import (  # noqa: E402
    SOURCE,
    STEP,
    TARGET,
    Scope,
    kernel_owner,
    make_fixture,
    reopened,
    sandbox,
)

from facet.db import migration_entry as engine  # noqa: E402

CHILD = Path(__file__).with_name("migration_entry_child.py")


@contextmanager
def child(phase, root):
    participant = subprocess.Popen(
        [sys.executable, "-B", str(CHILD), phase, str(root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    try:
        yield participant
    finally:
        if participant.poll() is None:
            # Only this freshly spawned test-owned process may be signalled.
            participant.kill()
        _, errors = participant.communicate(timeout=8)
        assert errors == b""


def handshake(participant):
    ready, _, _ = select.select([participant.stdout], [], [], 8)
    assert ready, "owned_migration_child_handshake_timeout"
    line = participant.stdout.readline()
    assert line, "owned_migration_child_missing_handshake"
    return line.decode().strip()


@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
def test_mg07_sigkill_preserves_complete_old_or_target_with_real_freeze(
    monkeypatch, deny_external_network, phase
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", TARGET)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", (STEP,))
    monkeypatch.setattr(engine, "_MIGRATION_PROVIDER_TYPES", (Scope,))
    with sandbox() as parent:
        root = make_fixture(parent)
        before = reopened(root, SOURCE)
        with child(phase, root) as participant:
            assert handshake(participant) == "ready_" + phase
            assert kernel_owner(root) == "owner_busy"
            for role in ("source", "target"):
                descriptor = os.open(
                    root / "credentials" / (role + ".lock"),
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                )
                try:
                    with pytest.raises(BlockingIOError):
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(descriptor)
            participant.kill()
            assert participant.wait(timeout=8) == -signal.SIGKILL
        # Actual reacquisition includes ownerEX/viewEX/source+target locks. Crash
        # WAL/SHM are read as existing sidecars, never immutable-main-only.
        expected = SOURCE if phase == "before_commit" else TARGET
        actual = reopened(root, expected)
        for name in before.keys() - {"schema_metadata", "schema_migrations"}:
            assert actual[name] == before[name]
        assert actual["schema_metadata"][0][3] == before["schema_metadata"][0][3]
        assert actual["schema_migrations"][0] == before["schema_migrations"][0]
        if phase == "before_commit":
            assert actual == before
        else:
            assert len(actual["schema_migrations"]) == 2
            assert actual["schema_metadata"][0][1] == 9002
        assert kernel_owner(root) == "held"


@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
def test_mg07_paired_unsignalled_child_commits_same_complete_target(
    monkeypatch, deny_external_network, phase
):
    monkeypatch.setattr(engine, "_CURRENT_MANIFEST", TARGET)
    monkeypatch.setattr(engine, "_EXISTING_STEPS", (STEP,))
    monkeypatch.setattr(engine, "_MIGRATION_PROVIDER_TYPES", (Scope,))
    with sandbox() as parent:
        root = make_fixture(parent)
        before = reopened(root, SOURCE)
        with child(phase, root) as participant:
            assert handshake(participant) == "ready_" + phase
            assert kernel_owner(root) == "owner_busy"
            participant.stdin.write(b"continue\n")
            participant.stdin.flush()
            assert handshake(participant) == "migrated"
            assert participant.wait(timeout=8) == 0
        actual = reopened(root, TARGET)
        for name in before.keys() - {"schema_metadata", "schema_migrations"}:
            assert actual[name] == before[name]
        assert len(actual["schema_migrations"]) == 2
        assert actual["schema_migrations"][0] == before["schema_migrations"][0]
        assert kernel_owner(root) == "held"
