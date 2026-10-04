import hashlib
import json
import os
import sqlite3
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
    files = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and path.name != "facet.db-shm"
    }
    return files


def _without_times(value):
    if isinstance(value, dict):
        return {
            key: _without_times(item)
            for key, item in value.items()
            if key not in {"sampled_at", "checked_at"}
        }
    if isinstance(value, list):
        return [_without_times(item) for item in value]
    return value


def test_status_and_doctor_are_aggregate_only_and_read_only(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)
    before = _files(state)

    status = _run(trusted_root, "status", "--state-dir", str(state), guard=True)
    doctor = _run(trusted_root, "doctor", "--state-dir", str(state), guard=True)
    assert status.returncode == 0, status.stderr + status.stdout
    assert doctor.returncode == 3, doctor.stderr + doctor.stdout
    status_doc = json.loads(status.stdout)
    doctor_doc = json.loads(doctor.stdout)
    assert status_doc["command"] == "status"
    assert doctor_doc["command"] == "doctor"
    assert status_doc["data"]["status"]["data"]["health"] == "blocked"
    assert status_doc["data"]["status"]["data"]["source"]["auth_state"] == (
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
    after = _files(state)
    for name, digest in before.items():
        assert after.get(name) == digest
    # A read-only SQLite connection may create an empty WAL coordination file;
    # an existing WAL payload, like the main database, must remain unchanged.
    if "facet.db-wal" in before:
        assert after["facet.db-wal"] == before["facet.db-wal"]


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
    assert _without_times(plain_data) == _without_times(private_data)


def test_aggregate_maintenance_views_reuse_offline_status_snapshot(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)
    before = _files(state)

    commands = (
        ("backfill", "status"),
        ("queue", "list"),
        ("review", "list"),
    )
    outputs = []
    for command in commands:
        result = _run(
            trusted_root,
            *command,
            "--state-dir",
            str(state),
            guard=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        outputs.append(json.loads(result.stdout))

    backfill, queue, review = outputs
    assert backfill["command"] == "backfill.status"
    assert backfill["data"]["data"]["jobs"]["completed"] == 0
    assert queue["command"] == "queue.list"
    assert set(queue["data"]) == {
        "jobs",
        "oldest_runnable_job_age_seconds",
        "sampled_at",
        "freshness",
        "age_seconds",
        "scope",
    }
    assert queue["data"]["jobs"] == backfill["data"]["data"]["jobs"]
    assert review["command"] == "review.list"
    assert review["data"]["data"]["groups"] == []
    output = "".join(json.dumps(value, sort_keys=True) for value in outputs)
    assert "source@synthetic.example" not in output
    assert "target@synthetic.example" not in output
    assert "facet.db" not in output
    after = _files(state)
    for name, digest in before.items():
        assert after.get(name) == digest


def test_rule_views_are_sealed_read_only_and_private_by_default(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)

    empty = _run(
        trusted_root,
        "rules",
        "list",
        "--state-dir",
        str(state),
        guard=True,
    )
    assert empty.returncode == 0, empty.stderr + empty.stdout
    assert json.loads(empty.stdout)["data"] == {
        "ruleset_revision": 0,
        "rule_count": 0,
    }

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
        "00000000000040008000000000000051",
    )
    rule = invoke(
        "rules",
        "add-sender",
        "--sender",
        "sender@example.com",
        "--yes",
        "--request-id",
        "00000000000040008000000000000052",
    )
    assert rule["data"]["ruleset_revision"] == 1
    listed = invoke("rules", "list")
    assert listed["data"] == {"ruleset_revision": 1, "rule_count": 1}

    public = _run(
        trusted_root,
        "rules",
        "show",
        "--rule-id",
        "00000000000040008000000000000052",
        "--state-dir",
        str(state),
        guard=True,
    )
    assert public.returncode == 3
    assert json.loads(public.stdout)["code"] == "scope_required"

    private = _run(
        trusted_root,
        "rules",
        "show",
        "--rule-id",
        "00000000000040008000000000000052",
        "--private-metadata",
        "--state-dir",
        str(state),
        guard=True,
    )
    assert private.returncode == 0, private.stderr + private.stdout
    private_data = json.loads(private.stdout)["data"]
    assert private_data["rule_id"] == "00000000000040008000000000000052"
    assert private_data["normalized_value"] == "sender@example.com"
    assert private_data["kind"] == "allow_sender"
    assert private_data["enabled"] is True
    assert private_data["origin"] == "cli"

    malformed = _run(
        trusted_root,
        "rules",
        "show",
        "--rule-id",
        "not-a-uuid",
        "--private-metadata",
        "--state-dir",
        str(state),
    )
    assert malformed.returncode == 2
    assert json.loads(malformed.stdout)["code"] == "invalid_input"
    foreign = _run(
        trusted_root,
        "rules",
        "show",
        "--rule-id",
        "00000000000040008000000000000053",
        "--private-metadata",
        "--state-dir",
        str(state),
    )
    assert foreign.returncode == 4
    assert json.loads(foreign.stdout)["code"] == "owner_unavailable"


def test_queue_show_is_private_read_only_job_metadata(trusted_root):
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
        "00000000000040008000000000000061",
    )
    invoke(
        "rules",
        "add-sender",
        "--sender",
        "sender@example.com",
        "--yes",
        "--request-id",
        "00000000000040008000000000000062",
    )
    preview = invoke(
        "backfill",
        "preview",
        "--fake",
        "--request-id",
        "00000000000040008000000000000063",
    )["data"]["preview_id"]
    invoke(
        "backfill",
        "start",
        "--fake",
        "--preview-id",
        preview,
        "--yes",
        "--request-id",
        "00000000000040008000000000000064",
    )
    invoke("run", "--once", "--fake")
    with sqlite3.connect(state / "facet.db") as connection:
        job_id = connection.execute(
            "SELECT job_id FROM sync_jobs ORDER BY created_at LIMIT 1"
        ).fetchone()[0]

    public = _run(
        trusted_root,
        "queue",
        "show",
        "--job-id",
        job_id,
        "--state-dir",
        str(state),
        guard=True,
    )
    assert public.returncode == 3
    assert json.loads(public.stdout)["code"] == "scope_required"
    public_malformed = _run(
        trusted_root,
        "queue",
        "show",
        "--job-id",
        "not-a-uuid",
        "--state-dir",
        str(state),
        guard=True,
    )
    assert public_malformed.returncode == 2
    assert json.loads(public_malformed.stdout)["code"] == "invalid_input"
    private = _run(
        trusted_root,
        "queue",
        "show",
        "--job-id",
        job_id,
        "--private-metadata",
        "--state-dir",
        str(state),
        guard=True,
    )
    assert private.returncode == 0, private.stderr + private.stdout
    data = json.loads(private.stdout)["data"]
    assert data["job_id"] == job_id
    assert data["state"] == "completed"
    assert data["kind"] in {"expand_thread", "project_message", "resolve_event"}
    assert isinstance(data["attempt_count"], int)
    assert data["source_thread_id"] is not None
    malformed = _run(
        trusted_root,
        "queue",
        "show",
        "--job-id",
        "not-a-uuid",
        "--private-metadata",
        "--state-dir",
        str(state),
    )
    assert malformed.returncode == 2
    assert json.loads(malformed.stdout)["code"] == "invalid_input"


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
    assert data["progress"]["data"]["confirmed_messages"] == 1
    assert data["progress"]["data"]["epoch"]["state"] in {
        "draining",
        "completed",
        "completed_with_issues",
    }
    assert data["progress"]["data"]["jobs"]["completed"] >= 1
    assert data["status"]["data"]["health"] == "unknown"


def test_status_reports_paused_epoch_as_blocked(trusted_root):
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
        "00000000000040008000000000000043",
    )
    invoke(
        "rules",
        "add-sender",
        "--sender",
        "sender@example.com",
        "--yes",
        "--request-id",
        "00000000000040008000000000000044",
    )
    preview = invoke(
        "backfill",
        "preview",
        "--fake",
        "--request-id",
        "00000000000040008000000000000046",
    )["data"]["preview_id"]
    invoke(
        "backfill",
        "start",
        "--fake",
        "--preview-id",
        preview,
        "--yes",
        "--request-id",
        "00000000000040008000000000000045",
    )
    config = load_config(read_managed_config(select_paths(str(state), None)))
    owner = StateOwner.open(state, config)
    try:
        with owner.session.transaction() as uow:
            uow._execute(
                "UPDATE epochs SET state='paused' WHERE projection_id=?",
                (config.projection.id.value,),
            )
    finally:
        owner.close()
    result = _run(trusted_root, "status", "--state-dir", str(state))
    assert result.returncode == 0
    data = json.loads(result.stdout)["data"]
    assert data["status"]["data"]["health"] == "blocked"
    assert data["status"]["data"]["phase"] == "paused"


def test_status_rejects_a_different_projection_selector(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)
    result = _run(
        trusted_root,
        "status",
        "--state-dir",
        str(state),
        "--projection",
        "other-projection",
    )
    assert result.returncode == 3
    assert json.loads(result.stdout)["code"] == "binding_mismatch"


def test_doctor_live_is_explicitly_not_implemented(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)
    result = _run(trusted_root, "doctor", "--state-dir", str(state), "--live")
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "invalid_input"


def test_doctor_retains_findings_with_typed_exit(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)
    result = _run(trusted_root, "doctor", "--state-dir", str(state))
    assert result.returncode == 3
    document = json.loads(result.stdout)
    assert document["code"] == "binding_pending"
    checks = {check["name"]: check for check in document["data"]["checks"]}
    assert checks["bindings"] == {
        "name": "bindings",
        "state": "attention",
        "code": "binding_pending",
    }


def test_doctor_classifies_verified_bindings_before_backfill_as_maintenance(
    trusted_root,
):
    state = trusted_root / "state"
    _init(trusted_root, state)
    result = _run(
        trusted_root,
        "auth",
        "authorize",
        "--fake",
        "--yes",
        "--request-id",
        "00000000000040008000000000000053",
        "--state-dir",
        str(state),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    result = _run(trusted_root, "doctor", "--state-dir", str(state))
    assert result.returncode == 4, result.stdout + result.stderr
    document = json.loads(result.stdout)
    assert document["code"] == "maintenance_required"


def test_status_rejects_mismatched_verified_address_without_disclosure(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)
    result = _run(
        trusted_root,
        "auth",
        "authorize",
        "--fake",
        "--yes",
        "--request-id",
        "00000000000040008000000000000063",
        "--state-dir",
        str(state),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    config = load_config(read_managed_config(select_paths(str(state), None)))
    owner = StateOwner.open(state, config)
    try:
        with owner.session.transaction() as uow:
            uow._execute(
                "UPDATE bindings SET verified_address=? WHERE projection_id=? "
                "AND role=?",
                (
                    "wrong@synthetic.example",
                    config.projection.id.value,
                    "source",
                ),
            )
    finally:
        owner.close()
    result = _run(trusted_root, "status", "--state-dir", str(state))
    assert result.returncode == 3
    document = json.loads(result.stdout)
    assert document["code"] == "binding_mismatch"
    assert "wrong@synthetic.example" not in result.stdout
