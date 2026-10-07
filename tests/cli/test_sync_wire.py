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


def run_cli_wire(
    tmp_path,
    *,
    lost_response=False,
    fault=None,
    historical=False,
    expansion_fault=None,
    partial_discovery=False,
):
    if lost_response:
        fault = "lost_response"
    with (
        Mailbox() as mailbox,
        tempfile.TemporaryDirectory(
            prefix="facet-sync-wire-",
            dir=os.environ.get(
                "FACET_TEST_PRIVATE_PARENT", f"/run/user/{os.geteuid()}"
            ),
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

        def invoke(*args, error=None):
            result = subprocess.run(
                command + ["--state-dir", str(state), "--json", *args],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if error is not None:
                assert result.returncode != 0
                assert json.loads(result.stdout)["code"] == error
                return
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
        if historical:
            # Fresh scopes must work with existing tracked generations. Nothing
            # below seeds production tables: even state inspection is read-only.
            with sqlite3.connect(state / "facet.db") as db:
                checkpoint = db.execute("SELECT * FROM history_checkpoints").fetchall()
                attempts = db.execute("SELECT * FROM insert_attempts").fetchall()
                old_maps = db.execute("SELECT * FROM message_mappings").fetchall()
                effective = db.execute(
                    "SELECT effective_at FROM rule_revisions WHERE enabled=1"
                ).fetchone()[0]
            calls = len(mailbox.calls)
            request_key = uuid4().hex
            preview = invoke("backfill", "preview", "--request-id", request_key)
            assert invoke("backfill", "preview", "--request-id", request_key) == preview
            assert len(mailbox.calls) == calls  # No OAuth or Gmail for preview.
            assert preview["target_writes"] == 0
            start_key = uuid4().hex
            start_args = (
                "backfill",
                "start",
                "--preview-id",
                preview["preview_id"],
                "--yes",
                "--request-id",
                start_key,
            )
            expansion = invoke(*start_args)
            calls = len(mailbox.calls)
            assert invoke(*start_args) == expansion
            assert len(mailbox.calls) == calls  # Lost-response lookup, no new fence.
            invoke(
                "backfill",
                "start",
                "--preview-id",
                preview["preview_id"],
                "--yes",
                "--request-id",
                uuid4().hex,
                error="request_conflict",
            )
            assert len(mailbox.calls) == calls
            with sqlite3.connect(state / "facet.db") as db:
                assert (
                    db.execute("SELECT * FROM history_checkpoints").fetchall()
                    == checkpoint
                )
                assert db.execute(
                    "SELECT kind FROM epochs WHERE epoch_id=?",
                    (expansion["epoch_id"],),
                ).fetchone() == ("historical_expansion",)
                assert (
                    db.execute("SELECT * FROM insert_attempts").fetchall() == attempts
                )
                assert (
                    db.execute("SELECT * FROM message_mappings").fetchall() == old_maps
                )
            # A later rule must not enter the already-sealed historical query.
            invoke(
                "rules",
                "add-sender",
                "--sender",
                "later@example.com",
                "--yes",
                "--request-id",
                uuid4().hex,
            )
            old_ms = int(mailbox.message("historical-new")["internalDate"])
            assert old_ms * 1000 < effective
            mailbox.historical = True
            mailbox.fault = expansion_fault
            if partial_discovery:
                mailbox.discovery_failure = True
                invoke("run", "--once", error="network_unavailable")
                assert len(mailbox.inserted_raw) == inserts
                with sqlite3.connect(state / "facet.db") as db:
                    assert db.execute(
                        "SELECT completed_pages FROM epoch_partitions WHERE epoch_id=?",
                        (expansion["epoch_id"],),
                    ).fetchone() == (1,)
                mailbox.discovery_failure = False
            result = invoke("run", "--once")
            assert result["projected"] == (2 if expansion_fault else 4)
            new_inserts = 3 if expansion_fault else 4
            assert len(mailbox.inserted_raw) == inserts + new_inserts
            query_count = 3 if partial_discovery else 2
            assert len(mailbox.discovery_queries) == query_count
            assert all(
                'from:"sender@example.com"' in query["q"][0]
                and "later@example.com" not in query["q"][0]
                for query in mailbox.discovery_queries
            )
            with sqlite3.connect(state / "facet.db") as db:
                assert db.execute(
                    "SELECT state FROM epochs WHERE epoch_id=?",
                    (expansion["epoch_id"],),
                ).fetchone() == ("catching_up" if expansion_fault else "completed",)
                assert db.execute(
                    "SELECT COUNT(*) FROM message_mappings"
                ).fetchone() == (len(old_maps) + (2 if expansion_fault else 4),)
                for attempt in attempts:
                    assert (
                        attempt
                        in db.execute("SELECT * FROM insert_attempts").fetchall()
                    )
                for mapping in old_maps:
                    assert (
                        mapping
                        in db.execute("SELECT * FROM message_mappings").fetchall()
                    )
                assert db.execute(
                    "SELECT origin FROM history_polls ORDER BY started_at DESC LIMIT 1"
                ).fetchone() == ("checkpoint",)
            assert invoke("run", "--once")["projected"] == 0
            assert len(mailbox.inserted_raw) == inserts + new_inserts
            assert len(mailbox.discovery_queries) == query_count  # Scan isn't repeated.
            for raw in mailbox.inserted_raw[inserts:]:
                identifier = (
                    raw.split(b"Message-ID: <", 1)[1].split(b"@", 1)[0].decode()
                )
                encoded = mailbox.message(identifier, raw=True)["raw"]
                assert raw == base64.urlsafe_b64decode(
                    encoded + "=" * (-len(encoded) % 4)
                )
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


def test_cli_historical_expansion_after_initial_empty_scope(tmp_path):
    run_cli_wire(tmp_path, historical=True)


def test_cli_historical_expansion_preserves_old_unknown_and_mappings(tmp_path):
    run_cli_wire(tmp_path, lost_response=True, historical=True)


def test_cli_historical_expansion_resumes_pagination_after_process_failure(tmp_path):
    run_cli_wire(tmp_path, historical=True, partial_discovery=True)


def test_cli_historical_unknown_keeps_expansion_pending_without_resend(tmp_path):
    run_cli_wire(tmp_path, historical=True, expansion_fault="lost_response")


def test_cli_production_wire_unknown_insert_is_not_resent_on_restart(tmp_path):
    run_cli_wire(tmp_path, lost_response=True)


def test_cli_production_wire_503_stays_in_recovery_on_restart(tmp_path):
    run_cli_wire(tmp_path, fault=503)


def test_cli_production_wire_307_stays_in_recovery_on_restart(tmp_path):
    run_cli_wire(tmp_path, fault=307)


def test_cli_production_wire_308_stays_in_recovery_on_restart(tmp_path):
    run_cli_wire(tmp_path, fault=308)
