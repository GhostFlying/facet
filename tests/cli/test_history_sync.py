"""Current-rule History admission through real production CLI subprocesses."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def test_cli_new_rule_after_empty_epoch_admits_full_thread_and_restarts(tmp_path):
    with tempfile.TemporaryDirectory(
        prefix="facet-history-cli-", dir=f"/run/user/{os.geteuid()}"
    ) as private_root:
        state = Path(private_root) / "state"
        mailbox = tmp_path / "external-mailbox.json"
        mailbox.write_text(
            json.dumps(
                {
                    "revision": 1,
                    "arrived_at": 0,
                    "target": {},
                    "insert_calls": 0,
                }
            )
        )
        hook = tmp_path / "hook"
        hook.mkdir()
        (hook / "sitecustomize.py").write_text(
            "from fakes.history_cli import install\ninstall()\n"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            (str(hook), str(ROOT / "tests"), str(ROOT / "src"))
        )
        env["FACET_TEST_HISTORY_MAILBOX"] = str(mailbox)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        command = [str(Path(sys.executable).parent / "facet")]

        def invoke(*args):
            result = subprocess.run(
                command + ["--state-dir", str(state), "--json", *args],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            assert result.returncode == 0, result.stderr + result.stdout
            assert result.stderr == ""
            assert "HISTORY_BODY_SENTINEL" not in result.stdout
            assert "HISTORY_HEADER_SENTINEL" not in result.stdout
            document = json.loads(result.stdout)
            assert document["status"] == "completed"
            return document["data"]

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
        preview = invoke("backfill", "preview", "--fake", "--request-id", uuid4().hex)
        assert preview["target_writes"] == 0
        epoch = invoke(
            "backfill",
            "start",
            "--fake",
            "--preview-id",
            preview["preview_id"],
            "--yes",
            "--request-id",
            uuid4().hex,
        )
        assert invoke("run", "--once", "--fake")["projected"] == 0
        # A production CLI command installs the new current rule. The initial
        # epoch snapshot remains empty and is not rewritten by the test.
        invoke(
            "rules",
            "add-sender",
            "--sender",
            "sender@example.com",
            "--yes",
            "--request-id",
            uuid4().hex,
        )
        fixture = json.loads(mailbox.read_text())
        fixture.update(revision=2, arrived_at=int(time.time() * 1000) + 1)
        mailbox.write_text(json.dumps(fixture))
        first = invoke("run", "--once", "--fake")
        assert first["attention"] == 0
        assert first["projected"] == 2  # prior history + arriving mail; no draft
        assert json.loads(mailbox.read_text())["insert_calls"] == 2
        with sqlite3.connect(state / "facet.db") as db:
            assert db.execute(
                "SELECT source_message_id FROM message_mappings ORDER BY 1"
            ).fetchall() == [("future-new",), ("future-old",)]
            assert db.execute("SELECT tag FROM thread_admissions").fetchone() == (
                "future_rule",
            )
            assert db.execute(
                "SELECT origin_epoch_id FROM sync_jobs WHERE kind='expand_thread'"
            ).fetchone() == (epoch["epoch_id"],)
            assert db.execute("SELECT state FROM epochs").fetchone() == ("draining",)
        # Another History record for the same already-confirmed message is
        # consumed without metadata lookup or another insert after restart.
        fixture = json.loads(mailbox.read_text())
        metadata_reads = fixture["source_metadata_reads"]
        fixture["revision"] = 3
        mailbox.write_text(json.dumps(fixture))
        second = invoke("run", "--once", "--fake")
        assert second["projected"] == second["attention"] == 0
        assert json.loads(mailbox.read_text())["insert_calls"] == 2
        assert (
            json.loads(mailbox.read_text())["source_metadata_reads"] == metadata_reads
        )
        with sqlite3.connect(state / "facet.db") as db:
            assert db.execute(
                "SELECT COUNT(*) FROM insert_attempts WHERE state='verified'"
            ).fetchone() == (2,)
            assert db.execute(
                "SELECT DISTINCT processing FROM source_events"
            ).fetchall() == [("consumed",)]
        for path in state.rglob("*"):
            if path.is_file():
                assert b"HISTORY_BODY_SENTINEL" not in path.read_bytes()
                assert b"HISTORY_HEADER_SENTINEL" not in path.read_bytes()
