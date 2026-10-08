"""Real setup/History/unknown/run/restart subprocesses; external fake only."""

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


def _exercise_cli(
    tmp_path, *, replacement_unknown=False, crash_at=None, replacement_crash=None
):
    with tempfile.TemporaryDirectory(
        prefix="facet-absence-cli-",
        dir=os.environ.get("FACET_TEST_PRIVATE_ROOT", f"/run/user/{os.geteuid()}"),
    ) as private:
        state = Path(private) / "state"
        mailbox = tmp_path / "mailbox.json"
        mailbox.write_text(
            json.dumps(
                {
                    "revision": 1,
                    "arrived_at": 0,
                    "target": {},
                    "insert_calls": 0,
                    "lose_first_insert_without_effect": crash_at is None,
                    "recovery_clock": True,
                    "clock_offset": 0,
                    "crash_at": crash_at,
                }
            )
        )
        hook = tmp_path / "hook"
        hook.mkdir()
        (hook / "sitecustomize.py").write_text(
            "from fakes.history_cli import install\ninstall()\n"
        )
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                (str(hook), str(ROOT / "tests"), str(ROOT / "src"))
            ),
            "FACET_TEST_HISTORY_MAILBOX": str(mailbox),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        command = [str(Path(sys.executable).parent / "facet")]

        def invoke(*args, crash=None):
            response = subprocess.run(
                command + ["--state-dir", str(state), "--json", *args],
                env=env,
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert response.stderr == ""
            for sentinel in (
                "HISTORY_BODY_SENTINEL",
                "HISTORY_HEADER_SENTINEL",
                "facet-synthetic-",
            ):
                assert sentinel not in response.stdout
            if crash is not None:
                assert response.returncode == crash
                return None
            data = json.loads(response.stdout)
            assert response.returncode == 0, data
            return data["data"]

        def external(**changes):
            fixture = json.loads(mailbox.read_text())
            fixture.update(changes)
            mailbox.write_text(json.dumps(fixture))

        def rows(sql):
            # Read-only evidence. No direct DB writes, seeding or backdating.
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
        preview = invoke("backfill", "preview", "--fake", "--request-id", uuid4().hex)
        invoke(
            "backfill",
            "start",
            "--fake",
            "--preview-id",
            preview["preview_id"],
            "--yes",
            "--request-id",
            uuid4().hex,
        )
        invoke("run", "--once", "--fake")
        invoke(
            "rules",
            "add-sender",
            "--sender",
            "sender@example.com",
            "--yes",
            "--request-id",
            uuid4().hex,
        )
        external(revision=2, arrived_at=int(time.time() * 1000) + 1)
        invoke(
            "run",
            "--once",
            "--fake",
            crash={"prepared": 81, "dispatched": 82, "known": 83}.get(crash_at),
        )
        original = rows(
            "SELECT attempt_id,state,certainty,dispatch_started_at,raw_digest "
            "FROM insert_attempts"
        )[0]
        assert (
            original[1]
            == {
                None: "pending_recovery",
                "prepared": "prepared",
                "dispatched": "dispatch_started",
                "known": "known_inserted",
            }[crash_at]
        )
        if crash_at in {None, "dispatched"}:
            invoke("run", "--once", "--fake")
            assert rows("SELECT COUNT(*) FROM message_mappings") == [(0,)]
            assert json.loads(mailbox.read_text())["insert_calls"] == 1
            external(
                clock_offset=301, lose_insert_calls=[1] if replacement_unknown else []
            )
        if replacement_crash is not None:
            external(crash_at=replacement_crash)
        invoke(
            "run",
            "--once",
            "--fake",
            crash={"prepared": 81, "dispatched": 82, "known": 83}.get(
                replacement_crash
            ),
        )
        if replacement_crash is not None:
            if replacement_crash == "dispatched":
                external(clock_offset=602)
            invoke("run", "--once", "--fake")
        if replacement_unknown:
            assert json.loads(mailbox.read_text())["insert_calls"] == 2
            assert rows("SELECT COUNT(*) FROM message_mappings") == [(0,)]
            invoke("run", "--once", "--fake")
            assert json.loads(mailbox.read_text())["insert_calls"] == 2
            external(clock_offset=602, lose_insert_calls=[])
            invoke("run", "--once", "--fake")
        assert rows("SELECT COUNT(*) FROM message_mappings") == [(2,)]
        count = json.loads(mailbox.read_text())["insert_calls"]
        assert count == (
            4
            if replacement_unknown or replacement_crash == "dispatched"
            else 3
            if crash_at in {None, "dispatched"}
            else 2
        )
        invoke("run", "--once", "--fake")
        assert json.loads(mailbox.read_text())["insert_calls"] == count
        assert rows(
            "SELECT COUNT(*) FROM sync_jobs "
            "WHERE state IN('blocked','needs_attention','claimed')"
        ) == [(0,)]
        assert rows("SELECT COUNT(*) FROM job_claims") == [(0,)]
        preserved = rows(
            "SELECT attempt_id,state,certainty,dispatch_started_at,raw_digest "
            f"FROM insert_attempts WHERE attempt_id='{original[0]}'"
        )[0]
        if crash_at in {None, "dispatched"}:
            assert preserved[1:3] == ("pending_recovery", "unknown")
            assert preserved[3:] == original[3:]
        elif crash_at == "prepared":
            assert preserved[1:3] == ("cancelled_before_dispatch", "not_attempted")
            assert preserved[3:] == original[3:]
        else:
            assert preserved[1:3] == ("verified", "inserted")
        summary = invoke("recovery", "list")
        assert summary["unknown_insert_attempts"] == 0
        assert summary["assumed_absent_insert_attempts"] == (
            2
            if replacement_unknown or replacement_crash == "dispatched"
            else 1
            if crash_at in {None, "dispatched"}
            else 0
        )
        invoke("status")
        for path in state.rglob("*"):
            if path.is_file():
                assert b"HISTORY_BODY_SENTINEL" not in path.read_bytes()


def test_automatic_absence_recovery_cli_then_restart_without_duplicate(tmp_path):
    _exercise_cli(tmp_path)


def test_automatic_replacement_unknown_uses_another_fresh_deadline(tmp_path):
    _exercise_cli(tmp_path, replacement_unknown=True)


def test_prepared_crash_restarts_without_a_stuck_intent(tmp_path):
    _exercise_cli(tmp_path, crash_at="prepared")


def test_dispatched_crash_becomes_unknown_and_recovers_by_deadline(tmp_path):
    _exercise_cli(tmp_path, crash_at="dispatched")


def test_known_result_crash_only_reads_back_and_does_not_resend(tmp_path):
    _exercise_cli(tmp_path, crash_at="known")


def test_replacement_prepared_crash_keeps_original_decision_and_can_resume(tmp_path):
    _exercise_cli(tmp_path, replacement_crash="prepared")


def test_replacement_dispatch_crash_gets_its_own_deadline(tmp_path):
    _exercise_cli(tmp_path, replacement_crash="dispatched")


def test_replacement_known_crash_is_readback_only(tmp_path):
    _exercise_cli(tmp_path, replacement_crash="known")
