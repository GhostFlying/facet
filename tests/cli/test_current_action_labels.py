"""Current action labels through actual CLI subprocesses and external-only fake."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def current_cli(tmp_path):
    with tempfile.TemporaryDirectory(
        prefix="facet-current-labels-", dir=f"/run/user/{os.geteuid()}"
    ) as private_root:
        state = Path(private_root) / "state"
        mailbox = tmp_path / "external-mailbox.json"
        mailbox.write_text(
            json.dumps(
                {
                    "revision": 1,
                    "arrived_at": int(time.time() * 1000),
                    "target": {},
                    "insert_calls": 0,
                    "action_mode": True,
                    "tags": [],
                }
            )
        )
        hook = tmp_path / "hook"
        hook.mkdir()
        (hook / "sitecustomize.py").write_text(
            "from fakes.history_cli import install\ninstall()\n"
        )
        env = os.environ.copy()
        env.update(
            PYTHONPATH=os.pathsep.join(
                (str(hook), str(ROOT / "tests"), str(ROOT / "src"))
            ),
            FACET_TEST_HISTORY_MAILBOX=str(mailbox),
            PYTHONDONTWRITEBYTECODE="1",
        )

        def invoke(*args):
            result = subprocess.run(
                [
                    str(Path(sys.executable).parent / "facet"),
                    "--state-dir",
                    str(state),
                    "--json",
                    *args,
                ],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            for line in result.stderr.splitlines():
                assert json.loads(line)["kind"] in {
                    "lifecycle",
                    "work_summary",
                    "boundary_failure",
                }
            for sentinel in (
                "HISTORY_BODY_SENTINEL",
                "HISTORY_HEADER_SENTINEL",
                "facet-synthetic-source-access",
                "facet-synthetic-target-access",
            ):
                assert sentinel not in result.stdout + result.stderr
            return json.loads(result.stdout)["data"]

        def change(**kwargs):
            fixture = json.loads(mailbox.read_text())
            fixture.update(kwargs)
            fixture["revision"] += 1
            mailbox.write_text(json.dumps(fixture))

        def query(sql):
            with sqlite3.connect(f"file:{state / 'facet.db'}?mode=ro", uri=True) as db:
                return db.execute(sql).fetchall()

        invoke(
            "init",
            "--source",
            "source@example.com",
            "--target",
            "target@example.com",
            "--yes",
            "--request-id",
            f"rq1_{uuid4().hex}_{uuid4().hex}",
        )
        invoke("auth", "authorize", "--fake", "--yes", "--request-id", uuid4().hex)
        for kind, name in (
            ("add_sender", "Facet/AddSender"),
            ("add_domain", "Facet/AddDomain"),
        ):
            invoke(
                "rules",
                "action-label",
                "set",
                "--kind",
                kind,
                "--name",
                name,
                "--yes",
                "--request-id",
                uuid4().hex,
            )
        yield state, mailbox, invoke, change, query
        for file in state.rglob("*"):
            if file.is_file():
                data = file.read_bytes()
                assert b"HISTORY_BODY_SENTINEL" not in data
                assert b"HISTORY_HEADER_SENTINEL" not in data


def start(invoke):
    preview = invoke("backfill", "preview", "--fake", "--request-id", uuid4().hex)
    assert preview["target_writes"] == 0
    return invoke(
        "backfill",
        "start",
        "--fake",
        "--preview-id",
        preview["preview_id"],
        "--yes",
        "--request-id",
        uuid4().hex,
    )


def test_current_tags_not_historical_direction_and_restart_dedup(current_cli):
    state, mailbox, invoke, change, query = current_cli
    start(invoke)
    assert invoke("run", "--once", "--fake")["projected"] == 0
    change(tags=["current-sender"], removed_event=True)
    result = invoke("run", "--once", "--fake")
    assert result["attention"] == 0
    assert result["projected"] == 4
    assert query("SELECT COUNT(*) FROM current_action_receipts") == [(1,)]
    assert query("SELECT COUNT(*) FROM action_commands") == [(0,)]
    assert query("SELECT COUNT(*) FROM message_mappings") == [(4,)]
    assert query("SELECT DISTINCT processing FROM source_events") == [("consumed",)]
    # New participant plus repeated notification cannot re-learn a sticky tag.
    change(sender="new@example.net")
    assert invoke("run", "--once", "--fake")["attention"] == 0
    assert query("SELECT COUNT(*) FROM current_action_receipts") == [(1,)]
    assert query("SELECT COUNT(*) FROM rules") == [(1,)]
    assert json.loads(mailbox.read_text())["insert_calls"] == 4
    # Observed absence then presence activates again, without re-expansion.
    change(tags=[])
    assert invoke("run", "--once", "--fake")["attention"] == 0
    change(tags=["current-sender"])
    assert invoke("run", "--once", "--fake")["attention"] == 0
    assert query(
        "SELECT activation_sequence FROM current_action_receipts ORDER BY 1"
    ) == [(1,), (2,)]
    assert query("SELECT COUNT(*) FROM rules") == [(2,)]
    assert json.loads(mailbox.read_text())["insert_calls"] == 4


def test_initial_tags_are_baseline_only_and_h0_is_durable(current_cli):
    state, mailbox, invoke, change, query = current_cli
    fixture = json.loads(mailbox.read_text())
    fixture["tags"] = ["current-sender"]
    mailbox.write_text(json.dumps(fixture))
    start(invoke)
    assert query("SELECT fence_history_id FROM epochs") == [("history-1",)]
    assert query(
        "SELECT complete FROM current_action_baselines WHERE action_kind='add_sender'"
    ) == [(0,)]
    assert invoke("run", "--once", "--fake")["projected"] == 0
    change(sender="different@example.net")
    assert invoke("run", "--once", "--fake")["attention"] == 0
    assert query("SELECT COUNT(*) FROM current_action_receipts") == [(0,)]
    assert query("SELECT COUNT(*) FROM rules") == [(0,)]


def test_blacklist_wins_and_removal_does_not_revive(current_cli):
    state, mailbox, invoke, change, query = current_cli
    start(invoke)
    invoke("run", "--once", "--fake")
    change(tags=["current-sender"])
    invoke("run", "--once", "--fake")
    change(tags=["current-sender", "current-domain", "current-blacklist"])
    assert invoke("run", "--once", "--fake")["attention"] == 0
    stopped = query("SELECT active,generation FROM tracked_threads")
    assert stopped[0][0] == 0
    change(tags=[])
    invoke("run", "--once", "--fake")
    change(tags=["current-sender", "current-domain"])
    assert invoke("run", "--once", "--fake")["attention"] == 0
    assert query("SELECT active,generation FROM tracked_threads") == stopped
    assert json.loads(mailbox.read_text())["insert_calls"] == 4


def test_provider_failure_is_not_absence_or_ack(current_cli):
    state, mailbox, invoke, change, query = current_cli
    start(invoke)
    invoke("run", "--once", "--fake")
    change(tags=["current-sender"], source_failure=True)
    result = invoke("run", "--once", "--fake")
    assert result["attention"] > 0
    assert query("SELECT COUNT(*) FROM current_action_receipts") == [(0,)]
    assert query("SELECT COUNT(*) FROM rules") == [(0,)]
    change(source_failure=False)
    time.sleep(1.1)
    result = invoke("run", "--once", "--fake")
    assert result["attention"] == 0
    assert query("SELECT COUNT(*) FROM current_action_receipts") == [(1,)]
