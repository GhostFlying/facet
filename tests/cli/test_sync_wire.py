"""Real CLI + production SDK/Requests against external-only loopback Gmail."""

import base64
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from fakes.sync_wire import Mailbox

ROOT = Path(__file__).resolve().parents[2]


def run_cli_wire(tmp_path, *, lost_response=False, fault=None):
    if lost_response:
        fault = "lost_response"
    with (
        Mailbox() as mailbox,
        tempfile.TemporaryDirectory(
            prefix="facet-sync-wire-", dir=f"/run/user/{os.geteuid()}"
        ) as private_root,
    ):
        state = Path(private_root) / "state"
        hook = tmp_path / "hook"
        hook.mkdir()
        (hook / "sitecustomize.py").write_text(
            "from fakes.sync_wire import install_route\ninstall_route()\n"
        )
        env = os.environ.copy()
        env["FACET_TEST_WIRE_ORIGIN"] = mailbox.origin
        env["PYTHONPATH"] = os.pathsep.join(
            (str(hook), str(ROOT / "tests"), str(ROOT / "src"))
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        command = [str(Path(sys.executable).parent / "facet")]

        def invoke(*args):
            result = subprocess.run(
                command + ["--state-dir", str(state), "--json", *args],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr + result.stdout
            assert result.stderr == ""
            for sentinel in (
                "WIRE_BODY_SENTINEL",
                "WIRE_HEADER_SENTINEL",
                "WIRE_ERROR_SENTINEL",
                "facet-synthetic-source-access",
                "facet-synthetic-target-access",
            ):
                assert sentinel not in result.stdout
            value = json.loads(result.stdout)
            assert value["status"] == "completed"
            return value["data"]

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
        # Only OAuth exchange/profile evidence is synthetic. Every subsequent
        # command uses the unchanged normal factory and real SDK/Requests.
        invoke("auth", "authorize", "--fake", "--yes", "--request-id", uuid4().hex)
        preview = invoke("backfill", "preview", "--request-id", uuid4().hex)
        assert preview["target_writes"] == 0
        assert not mailbox.inserted_raw
        invoke(
            "backfill",
            "start",
            "--preview-id",
            preview["preview_id"],
            "--yes",
            "--request-id",
            uuid4().hex,
        )
        assert invoke("run", "--once")["projected"] == 0
        invoke(
            "rules",
            "add-sender",
            "--sender",
            "sender@example.com",
            "--yes",
            "--request-id",
            uuid4().hex,
        )
        mailbox.arrive()
        mailbox.fault = fault
        first = invoke("run", "--once")
        assert first["projected"] == (0 if fault else 2)
        assert len(mailbox.inserted_raw) == (1 if fault else 2)
        # Confirm SDK payload preserves the exact external raw bytes.
        for raw in mailbox.inserted_raw:
            mid = "future-new" if b"<future-new@" in raw else "future-old"
            encoded = mailbox.message(mid, raw=True)["raw"]
            assert raw == base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        with sqlite3.connect(state / "facet.db") as db:
            assert db.execute("SELECT COUNT(*) FROM message_mappings").fetchone() == (
                (0 if fault else 2),
            )
            if fault:
                assert db.execute("SELECT state FROM insert_attempts").fetchall() == [
                    ("pending_recovery",)
                ]
                assert db.execute(
                    "SELECT state FROM sync_jobs WHERE kind='recover_insert'"
                ).fetchall() == [("queued",)]
        inserts = len(mailbox.inserted_raw)
        mailbox.revision += 1
        again = invoke("run", "--once")
        assert again["projected"] == 0
        assert len(mailbox.inserted_raw) == inserts
        for path in state.rglob("*"):
            if path.is_file():
                for sentinel in (
                    b"WIRE_BODY_SENTINEL",
                    b"WIRE_HEADER_SENTINEL",
                    b"WIRE_ERROR_SENTINEL",
                ):
                    assert sentinel not in path.read_bytes()


def test_cli_production_wire_projects_and_restarts(tmp_path):
    run_cli_wire(tmp_path)


def test_cli_production_wire_unknown_insert_is_not_resent_on_restart(tmp_path):
    run_cli_wire(tmp_path, lost_response=True)


def test_cli_production_wire_503_stays_in_recovery_on_restart(tmp_path):
    run_cli_wire(tmp_path, fault=503)


def test_cli_production_wire_307_stays_in_recovery_on_restart(tmp_path):
    run_cli_wire(tmp_path, fault=307)


def test_cli_production_wire_308_stays_in_recovery_on_restart(tmp_path):
    run_cli_wire(tmp_path, fault=308)
