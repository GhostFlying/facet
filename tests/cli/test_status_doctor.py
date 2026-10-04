import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from facet.config import load_config
from facet.private_paths import read_managed_config, select_paths
from facet.runtime.state_owner import StateOwner

ROOT = Path(__file__).resolve().parents[2]
REQUEST = "rq1_123e4567e89b42d3a456426614174000_123e4567e89b42d3a456426614174001"


def _run(cwd, *args, guard=False):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    if guard:
        guard_root = Path(cwd) / "guard"
        guard_root.mkdir(exist_ok=True)
        (guard_root / "sitecustomize.py").write_text(
            "import sys\n"
            "def deny(event, args):\n"
            "    if event in ('socket.connect', 'socket.getaddrinfo'):\n"
            "        raise RuntimeError('network_forbidden')\n"
            "    if event == 'import' and args[0].split('.')[0] in "
            "{'google', 'httplib2'}:\n"
            "        raise RuntimeError('gmail_import_forbidden')\n"
            "sys.addaudithook(deny)\n",
            encoding="utf-8",
        )
        env["PYTHONPATH"] = os.pathsep.join([str(guard_root), str(ROOT / "src")])
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
    anchor = Path(f"/run/user/{os.geteuid()}")
    if not anchor.is_dir():
        pytest.skip("no_verified_trusted_test_anchor")
    info = anchor.stat()
    if (
        info.st_uid != os.geteuid()
        or not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) & 0o77
    ):
        pytest.skip("no_verified_trusted_test_anchor")
    with TemporaryDirectory(prefix="facet-status-", dir=anchor) as value:
        yield Path(value)


def _init(root, state):
    result = _run(
        root,
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
    assert result.returncode == 0, result.stderr + result.stdout


def _files(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"facet.db-wal", "facet.db-shm"}
    }


def test_status_and_doctor_are_aggregate_only_and_read_only(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)
    before = _files(state)

    status = _run(trusted_root, "status", "--state-dir", str(state), guard=True)
    doctor = _run(trusted_root, "doctor", "--state-dir", str(state), guard=True)
    assert status.returncode == 0, status.stderr + status.stdout
    assert doctor.returncode == 0, doctor.stderr + doctor.stdout
    status_doc = json.loads(status.stdout)
    doctor_doc = json.loads(doctor.stdout)
    assert status_doc["command"] == "status"
    assert doctor_doc["command"] == "doctor"
    assert status_doc["data"]["health"] == "blocked"
    assert status_doc["data"]["binding_states"]["source"]["state"] == (
        "verification_pending"
    )
    assert {check["name"] for check in doctor_doc["data"]["checks"]} == {
        "config_artifact",
        "database",
        "bindings",
        "projection",
    }
    output = status.stdout + doctor.stdout
    assert "source@synthetic.example" not in output
    assert "target@synthetic.example" not in output
    assert "facet.db" not in output
    assert _files(state) == before


def test_status_does_not_take_writer_lock_and_private_flag_does_not_expand_output(
    trusted_root,
):
    state = trusted_root / "state"
    _init(trusted_root, state)
    config = load_config(read_managed_config(select_paths(str(state), None)))
    owner = StateOwner.open(state, config)
    try:
        plain = _run(trusted_root, "status", "--state-dir", str(state))
        private = _run(
            trusted_root,
            "status",
            "--state-dir",
            str(state),
            "--private-metadata",
        )
    finally:
        owner.close()
    assert plain.returncode == 0
    assert private.returncode == 0
    plain_data = json.loads(plain.stdout)["data"]
    private_data = json.loads(private.stdout)["data"]
    assert plain_data.keys() == private_data.keys()
    assert {key: value for key, value in plain_data.items() if key != "sampled_at"} == {
        key: value for key, value in private_data.items() if key != "sampled_at"
    }


def test_status_reports_the_synthetic_projection_closure(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)

    def invoke(*args):
        result = _run(trusted_root, *args, "--state-dir", str(state))
        assert result.returncode == 0, result.stderr + result.stdout
        return json.loads(result.stdout)

    invoke(
        "auth",
        "authorize",
        "--fake",
        "--yes",
        "--request-id",
        "00000000000040008000000000000033",
    )
    invoke(
        "rules",
        "add-sender",
        "--sender",
        "sender@example.com",
        "--yes",
        "--request-id",
        "00000000000040008000000000000034",
    )
    preview = invoke(
        "backfill",
        "preview",
        "--fake",
        "--request-id",
        "00000000000040008000000000000036",
    )["data"]["preview_id"]
    invoke(
        "backfill",
        "start",
        "--fake",
        "--preview-id",
        preview,
        "--yes",
        "--request-id",
        "00000000000040008000000000000035",
    )
    run = invoke("run", "--once", "--fake")
    assert run["data"]["projected"] == 1

    status = _run(trusted_root, "status", "--state-dir", str(state))
    assert status.returncode == 0
    data = json.loads(status.stdout)["data"]
    assert data["confirmed_mappings"] == 1
    assert data["epoch"]["state"] in {
        "draining",
        "completed",
        "completed_with_issues",
    }
    assert data["queue"]["completed"] >= 1


def test_doctor_live_is_explicitly_not_implemented(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)
    result = _run(trusted_root, "doctor", "--state-dir", str(state), "--live")
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "invalid_input"
