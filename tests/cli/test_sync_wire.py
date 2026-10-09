"""Real CLI + production SDK/Requests against external-only loopback Gmail."""

import base64
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
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
    gap=False,
    gap_fault=None,
    learned_rule=False,
    delayed_recovery_index=False,
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
            for line in result.stderr.splitlines():
                assert json.loads(line)["kind"] in {
                    "lifecycle",
                    "work_summary",
                    "boundary_failure",
                    "dependency_state",
                }
            for sentinel in (
                "WIRE_BODY_SENTINEL",
                "WIRE_HEADER_SENTINEL",
                "WIRE_ERROR_SENTINEL",
                "facet-synthetic-source-access",
                "facet-synthetic-target-access",
            ):
                assert sentinel not in result.stdout + result.stderr
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
        if learned_rule:
            invoke(
                "rules",
                "action-label",
                "set",
                "--kind",
                "add_sender",
                "--name",
                "Facet/AddSender",
                "--yes",
                "--request-id",
                uuid4().hex,
            )
            mailbox.learn_sender = True
        else:
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
        mailbox.recovery_search_hidden = delayed_recovery_index
        first = invoke("run", "--once")
        if learned_rule:
            from facet.projection.rules import load_rule_policy

            with sqlite3.connect(state / "facet.db") as db:
                assert db.execute(
                    "SELECT policy_version FROM rule_revisions WHERE enabled=1"
                ).fetchall() == [
                    (load_rule_policy().version.value,),
                ]
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
        if fault:
            with sqlite3.connect(state / "facet.db") as db:
                recovery = db.execute(
                    "SELECT state,recovery_checks,next_recovery_at,error_code "
                    "FROM insert_attempts"
                ).fetchone()
                assert recovery[1] == 1
                if mailbox.target and not delayed_recovery_index:
                    assert recovery[0] == "needs_attention"
                    assert recovery[3] == "attribution_unknown"
                else:
                    assert recovery[0] == "pending_recovery"
                    assert recovery[2] is not None
            # A further actual process must retain the check deadline/ambiguity,
            # not reset the schedule or send the original message again.
            invoke("run", "--once")
            assert len(mailbox.inserted_raw) == inserts
            with sqlite3.connect(state / "facet.db") as db:
                assert (
                    db.execute(
                        "SELECT state,recovery_checks,next_recovery_at,error_code "
                        "FROM insert_attempts"
                    ).fetchone()
                    == recovery
                )
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
            # A later rule gets its own bounded scope; it must not widen the
            # already-sealed sender expansion.
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
            if lost_response:
                # The old effect is present but has no independently proven
                # ownership. Source scan/History are durable; new writes fail
                # closed rather than treating matching content as ours.
                invoke("run", "--once", error="attribution_unknown")
                assert len(mailbox.inserted_raw) == inserts
                with sqlite3.connect(state / "facet.db") as db:
                    assert (
                        db.execute("SELECT * FROM message_mappings").fetchall()
                        == old_maps
                    )
                    assert db.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (
                        0,
                    )
                    assert (
                        db.execute(
                            "SELECT COUNT(*) FROM sync_jobs WHERE state='queued'"
                        ).fetchone()[0]
                        > 0
                    )
                    assert db.execute(
                        "SELECT COUNT(*) FROM insert_attempts"
                    ).fetchone()[0] == len(attempts)
                invoke("run", "--once", error="attribution_unknown")
                assert len(mailbox.inserted_raw) == inserts
                return
            result = invoke("run", "--once")
            assert result["projected"] == (2 if expansion_fault else 4)
            new_inserts = 3 if expansion_fault else 4
            assert len(mailbox.inserted_raw) == inserts + new_inserts
            # The current sender expansion keeps its original pagination, and
            # the newly added later rule contributes one separate query.
            query_count = (3 if partial_discovery else 2) + 1
            assert len(mailbox.discovery_queries) == query_count
            sender_queries = [
                query
                for query in mailbox.discovery_queries
                if 'from:"sender@example.com"' in query["q"][0]
            ]
            assert sender_queries
            assert all(
                "later@example.com" not in query["q"][0] for query in sender_queries
            )
            sender_query_count = len(sender_queries)
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
            assert len(mailbox.discovery_queries) >= query_count
            assert (
                len(
                    [
                        query
                        for query in mailbox.discovery_queries
                        if 'from:"sender@example.com"' in query["q"][0]
                    ]
                )
                == sender_query_count
            )
            for raw in mailbox.inserted_raw[inserts:]:
                identifier = (
                    raw.split(b"Message-ID: <", 1)[1].split(b"@", 1)[0].decode()
                )
                encoded = mailbox.message(identifier, raw=True)["raw"]
                assert raw == base64.urlsafe_b64decode(
                    encoded + "=" * (-len(encoded) % 4)
                )
        if gap:
            with sqlite3.connect(state / "facet.db") as db:
                cursor = db.execute(
                    "SELECT cursor FROM history_checkpoints"
                ).fetchone()[0]
                old_attempts = db.execute("SELECT * FROM insert_attempts").fetchall()
                effective = db.execute(
                    "SELECT effective_at FROM rule_revisions WHERE enabled=1"
                ).fetchone()[0]
            mailbox.expired_cursors.add(cursor)
            mailbox.revision += 1
            mailbox.gap = True
            # The known gap includes these messages, but their arrival precedes
            # rule creation. Recovery uses the scan-time rule, not that order.
            mailbox.gap_arrived_at = int(time.time() * 1000) - 120_000
            assert mailbox.gap_arrived_at * 1000 < effective
            invoke("run", "--once", error="maintenance_required")
            assert len(mailbox.inserted_raw) == inserts
            with sqlite3.connect(state / "facet.db") as db:
                assert db.execute(
                    "SELECT cursor FROM history_checkpoints"
                ).fetchone() == (cursor,)
                assert db.execute("SELECT COUNT(*) FROM history_gaps").fetchone() == (
                    1,
                )
                assert (
                    db.execute("SELECT * FROM insert_attempts").fetchall()
                    == old_attempts
                )
            status = invoke("status")
            assert status["status"]["data"]["phase"] == "recovering"
            assert status["status"]["data"]["health"] != "healthy"
            mailbox.gap_page_failure = gap_fault == "discovery"
            mailbox.catchup_page_failure = gap_fault == "catchup"
            if gap_fault:
                invoke("run", "--once", error="network_unavailable")
                assert len(mailbox.inserted_raw) == inserts
                with sqlite3.connect(state / "facet.db") as db:
                    assert db.execute(
                        "SELECT cursor FROM history_checkpoints"
                    ).fetchone() == (cursor,)
                mailbox.gap_page_failure = mailbox.catchup_page_failure = False
            if lost_response:
                invoke("run", "--once", error="attribution_unknown")
                assert len(mailbox.inserted_raw) == inserts
                with sqlite3.connect(state / "facet.db") as db:
                    assert db.execute(
                        "SELECT cursor FROM history_checkpoints"
                    ).fetchone() == (f"history-{mailbox.revision}",)
                    assert db.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (
                        0,
                    )
                    assert db.execute(
                        "SELECT COUNT(*) FROM insert_attempts"
                    ).fetchone()[0] == len(old_attempts)
                    assert all(
                        attempt
                        in db.execute("SELECT * FROM insert_attempts").fetchall()
                        for attempt in old_attempts
                    )
                invoke("run", "--once", error="attribution_unknown")
                assert len(mailbox.inserted_raw) == inserts
                return
            result = invoke("run", "--once")
            assert result["projected"] == (7 if not fault else 6)
            assert len(mailbox.inserted_raw) == inserts + (7 if not fault else 6)
            with sqlite3.connect(state / "facet.db") as db:
                start, end = db.execute(
                    "SELECT window_start,window_end FROM epochs "
                    "WHERE kind='history_gap'"
                ).fetchone()
                expected_window = (
                    f"after:{start // 1_000_000 - 1} before:{end // 1_000_000 + 1}"
                )
                assert start <= mailbox.gap_arrived_at * 1000 <= end
                assert any(
                    expected_window in q["q"][0] for q in mailbox.discovery_queries
                )
                assert db.execute(
                    "SELECT cursor FROM history_checkpoints"
                ).fetchone() == (f"history-{mailbox.revision}",)
                assert db.execute(
                    "SELECT COUNT(*) FROM tracked_threads "
                    "WHERE source_thread_id='historical-thread'"
                ).fetchone() == (0,)
                assert db.execute(
                    "SELECT state FROM epochs WHERE kind='history_gap'"
                ).fetchone() == ("completed_with_issues" if fault else "completed",)
                for attempt in old_attempts:
                    assert (
                        attempt
                        in db.execute("SELECT * FROM insert_attempts").fetchall()
                    )
            assert invoke("run", "--once")["projected"] == 0
            assert len(mailbox.inserted_raw) == inserts + (7 if not fault else 6)
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


def test_cli_action_learned_rule_backfills_history_and_restarts(tmp_path):
    run_cli_wire(tmp_path, learned_rule=True, historical=True)


def test_cli_action_learned_rule_recovers_gap_and_restarts(tmp_path):
    run_cli_wire(tmp_path, learned_rule=True, gap=True)


def test_cli_gap_scans_catches_up_maps_and_restarts(tmp_path):
    run_cli_wire(tmp_path, gap=True)


def test_cli_gap_resumes_failed_discovery_page(tmp_path):
    run_cli_wire(tmp_path, gap=True, gap_fault="discovery")


def test_cli_gap_resumes_failed_catchup_page(tmp_path):
    run_cli_wire(tmp_path, gap=True, gap_fault="catchup")


def test_cli_gap_preserves_unknown_insert_without_resend(tmp_path):
    run_cli_wire(tmp_path, gap=True, lost_response=True)


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


def test_cli_delayed_recovery_index_keeps_durable_checks_on_restart(tmp_path):
    run_cli_wire(tmp_path, lost_response=True, delayed_recovery_index=True)


def test_cli_production_wire_503_stays_in_recovery_on_restart(tmp_path):
    run_cli_wire(tmp_path, fault=503)


def test_cli_production_wire_307_stays_in_recovery_on_restart(tmp_path):
    run_cli_wire(tmp_path, fault=307)


def test_cli_production_wire_308_stays_in_recovery_on_restart(tmp_path):
    run_cli_wire(tmp_path, fault=308)
