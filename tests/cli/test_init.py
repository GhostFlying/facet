import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from facet.config import dump_config, initial_template
from facet.db.codecs import StorageFailure
from facet.runtime.state_owner import StateOwner

ROOT = Path(__file__).resolve().parents[2]
REQUEST = "rq1_123e4567e89b42d3a456426614174000_123e4567e89b42d3a456426614174001"


def _run(cwd, *args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "facet", *args, "--json"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


@pytest.fixture
def trusted_root():
    def trusted(path):
        try:
            return all(
                stat.S_ISDIR(info.st_mode)
                and info.st_uid in (0, os.geteuid())
                and not stat.S_IMODE(info.st_mode) & 0o7022
                for info in (p.stat() for p in (path, *path.parents))
            )
        except OSError:
            return False

    anchor = next(
        (p for p in (Path.cwd(), Path(f"/run/user/{os.geteuid()}")) if trusted(p)),
        None,
    )
    if anchor is None:
        pytest.skip("no_verified_trusted_test_anchor")
    with TemporaryDirectory(prefix="facet-init-", dir=anchor) as value:
        yield Path(value)


def test_init_creates_private_state_and_run_stops_before_gmail(trusted_root):
    state = trusted_root / "state"
    result = _run(
        trusted_root,
        "init",
        "--state-dir",
        str(state),
        "--source",
        "source@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--request-id",
        REQUEST,
        "--yes",
    )
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["data"] == {
        "binding_state": "verification_pending",
        "replayed": False,
        "state_initialized": True,
    }
    assert "source@synthetic" not in result.stdout
    assert (state / "config.yaml").stat().st_mode & 0o77 == 0
    assert (state / "facet.db").stat().st_mode & 0o77 == 0
    blocked = _run(trusted_root, "run", "--state-dir", str(state), "--once")
    assert blocked.returncode == 3
    assert json.loads(blocked.stdout)["code"] == "binding_pending"


def test_init_replays_and_rejects_changed_payload(trusted_root):
    state = trusted_root / "state"
    first = _run(
        trusted_root,
        "init",
        "--state-dir",
        str(state),
        "--source",
        "source@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--request-id",
        REQUEST,
        "--yes",
    )
    assert first.returncode == 0
    replay = _run(
        trusted_root,
        "init",
        "--state-dir",
        str(state),
        "--source",
        "source@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--request-id",
        REQUEST,
        "--yes",
    )
    assert replay.returncode == 0
    assert json.loads(replay.stdout)["data"]["replayed"] is True
    changed = _run(
        trusted_root,
        "init",
        "--state-dir",
        str(state),
        "--source",
        "changed@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--request-id",
        REQUEST,
        "--yes",
    )
    assert changed.returncode == 3
    assert json.loads(changed.stdout)["code"] == "request_conflict"


def test_init_replay_finishes_missing_config_without_new_database(trusted_root):
    state = trusted_root / "state"
    first = _run(
        trusted_root,
        "init",
        "--state-dir",
        str(state),
        "--source",
        "source@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--request-id",
        REQUEST,
        "--yes",
    )
    assert first.returncode == 0
    database = state / "facet.db"
    before = database.stat().st_ino, database.stat().st_size
    (state / "config.yaml").unlink()
    replay = _run(
        trusted_root,
        "init",
        "--state-dir",
        str(state),
        "--source",
        "source@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--request-id",
        REQUEST,
        "--yes",
    )
    assert replay.returncode == 0
    assert json.loads(replay.stdout)["data"]["replayed"] is True
    assert (database.stat().st_ino, database.stat().st_size) == before
    assert (state / "config.yaml").is_file()


def test_init_requires_exact_request_key_and_rejects_external_config(trusted_root):
    state = trusted_root / "state"
    result = _run(
        trusted_root,
        "init",
        "--state-dir",
        str(state),
        "--source",
        "source@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--request-id",
        "synthetic-key",
        "--yes",
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "invalid_input"


def test_init_replay_refuses_active_owner(trusted_root):
    state = trusted_root / "state"
    config = initial_template("source@synthetic.example", "target@synthetic.example")
    owner = StateOwner.create(state, config, dump_config(config), request_id=REQUEST)
    try:
        result = _run(
            trusted_root,
            "init",
            "--state-dir",
            str(state),
            "--source",
            "source@synthetic.example",
            "--target",
            "target@synthetic.example",
            "--request-id",
            REQUEST,
            "--yes",
        )
        assert result.returncode == 4
        assert json.loads(result.stdout)["code"] == "owner_busy"
    finally:
        owner.close()
    result = _run(
        trusted_root,
        "init",
        "--state-dir",
        str(state),
        "--config",
        str(trusted_root / "external.yaml"),
        "--source",
        "source@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--request-id",
        REQUEST,
        "--yes",
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "invalid_input"


def test_run_rejects_changed_managed_config_after_initialization(trusted_root):
    state = trusted_root / "state"
    result = _run(
        trusted_root,
        "init",
        "--state-dir",
        str(state),
        "--source",
        "source@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--request-id",
        REQUEST,
        "--yes",
    )
    assert result.returncode == 0
    config_path = state / "config.yaml"
    config_path.write_bytes(
        config_path.read_bytes().replace(
            b"poll_interval_seconds: 30", b"poll_interval_seconds: 31"
        )
    )
    blocked = _run(trusted_root, "run", "--state-dir", str(state), "--once")
    assert blocked.returncode == 3
    assert json.loads(blocked.stdout)["code"] == "request_conflict"


def test_run_rejects_managed_config_symlink(trusted_root):
    state = trusted_root / "state"
    result = _run(
        trusted_root,
        "init",
        "--state-dir",
        str(state),
        "--source",
        "source@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--request-id",
        REQUEST,
        "--yes",
    )
    assert result.returncode == 0
    config_path = state / "config.yaml"
    external = trusted_root / "external-config.yaml"
    external.write_bytes(config_path.read_bytes())
    config_path.unlink()
    config_path.symlink_to(external)
    blocked = _run(trusted_root, "run", "--state-dir", str(state), "--once")
    assert blocked.returncode == 3
    assert json.loads(blocked.stdout)["code"] == "scope_required"


def test_missing_bootstrap_digest_is_maintenance_required():
    config = initial_template("source@synthetic.example", "target@synthetic.example")

    class EmptyConnection:
        def execute(self, *_args):
            return self

        def fetchall(self):
            return []

    owner = object.__new__(StateOwner)
    owner._connection = EmptyConnection()
    owner._config = config
    with pytest.raises(StorageFailure) as error:
        owner.verify_config_artifact(dump_config(config))
    assert error.value.code.value == "maintenance_required"
