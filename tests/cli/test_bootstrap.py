import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from facet.cli import bootstrap
from facet.config import ConfigError
from facet.contracts import ErrorCode, Role, Timestamp

ROOT = Path(__file__).resolve().parents[2]
CONFIG = b"""projection:
  id: private-selector
  source_email: source-sentinel@synthetic.example
  target_email: target-sentinel@synthetic.example
rules:
  allow_domains: [private-rule.synthetic.example]
target:
  projected_label: private-label-sentinel
"""
PRIVATE = [
    "source-sentinel",
    "target-sentinel",
    "private-selector",
    "private-rule",
    "private-label",
    "private-path-sentinel",
]
FORBIDDEN = ["BODY_CREDENTIAL_SENTINEL", "RAW_HEADER_SENTINEL", "ATTACHMENT_SENTINEL"]


def setup(tmp_path):
    config = tmp_path / "private-path-sentinel.yaml"
    config.write_bytes(CONFIG)
    config.chmod(0o600)
    guard = tmp_path / "guard"
    guard.mkdir()
    # Test-only site hook fails both live networking and forbidden production
    # imports, including any attempted reuse of the spike or DB runtime.
    (guard / "sitecustomize.py").write_text(
        "import sys\n"
        "def guard(event, args):\n"
        "    if event in ('socket.connect', 'socket.getaddrinfo'):\n"
        "        raise RuntimeError('offline_test_network_guard')\n"
        "    if event == 'open' and '.facet-spike' in str(args[0]):\n"
        "        raise RuntimeError('offline_test_spike_read_guard')\n"
        "    if event == 'import' and args[0].split('.')[0] in "
        "{'google', 'httplib2', 'sqlite3', 'facet_spike'}:\n"
        "        raise RuntimeError('offline_test_import_guard')\n"
        "sys.addaudithook(guard)\n",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(guard), str(ROOT / "src")])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return config, env


def snapshot(root):
    return {
        str(p.relative_to(root)): (
            p.stat().st_mode,
            hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        for p in root.rglob("*")
        if p.is_file()
    }


def run(tmp_path, env, *arguments, module=False):
    prefix = (
        [sys.executable, "-m", "facet"]
        if module
        else [str(Path(sys.executable).parent / "facet")]
    )
    return subprocess.run(
        prefix + list(arguments),
        cwd=tmp_path,
        env=env,
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ("--help",),
        ("--version",),
        ("--json", "--help"),
        ("--json", "--version"),
        (
            "config",
            "init",
            "--json",
            "--source",
            "s@synthetic.example",
            "--target",
            "t@synthetic.example",
            "--yes",
            "--request-id",
            "synthetic-key",
        ),
        ("config", "apply", "--file", "unread-input.yaml", "--json", "--yes"),
        ("config", "validate", "--json"),
    ],
)
def test_help_version_and_unavailable_routes_are_zero_effect(tmp_path, arguments):
    _, env = setup(tmp_path)
    state = tmp_path / ".facet"
    state.mkdir(mode=0o700)
    (state / "bootstrap.json").write_text("BODY_CREDENTIAL_SENTINEL")
    (state / "config.yaml").write_bytes(CONFIG)
    (state / "config.yaml").chmod(0o600)
    spike = tmp_path / ".facet-spike"
    spike.mkdir(mode=0o700)
    (spike / "token.json").write_text("RAW_HEADER_SENTINEL")
    before = snapshot(tmp_path)
    result = run(tmp_path, env, *arguments)
    assert snapshot(tmp_path) == before
    assert not any(s in result.stdout + result.stderr for s in PRIVATE + FORBIDDEN)
    if "--help" in arguments or "--version" in arguments:
        assert result.returncode == 0
    else:
        assert result.returncode == 4
        assert json.loads(result.stdout)["code"] == "owner_unavailable"


def test_init_missing_scope_is_zero_effect(tmp_path):
    _, env = setup(tmp_path)
    before = snapshot(tmp_path)
    result = run(
        tmp_path,
        env,
        "init",
        "--source",
        "source@synthetic.example",
        "--target",
        "target@synthetic.example",
        "--json",
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "confirmation_required"
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("position", ["before", "middle", "after"])
@pytest.mark.parametrize("action", ["validate", "show"])
def test_real_structural_reads_flags_and_json(tmp_path, position, action):
    config, env = setup(tmp_path)
    flags = ["--config", str(config), "--json", "--timeout", "3"]
    arguments = {
        "before": flags + ["config", action],
        "middle": ["config"] + flags + [action],
        "after": ["config", action] + flags,
    }[position]
    before = snapshot(tmp_path)
    result = run(tmp_path, env, *arguments)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    document = json.loads(result.stdout)
    assert set(document) == {
        "schema_version",
        "command",
        "status",
        "code",
        "data",
        "warnings",
    }
    assert document["schema_version"] == 1
    assert document["command"] == f"config.{action}"
    assert document["status"] == "completed" and document["code"] is None
    assert document["data"]["validation_scope"] == "structural_only"
    assert "binding_verification_pending" in document["warnings"]
    assert "managed_state_check_pending" in document["warnings"]
    assert "rule_validation_pending" in document["warnings"]
    assert snapshot(tmp_path) == before
    assert not (tmp_path / ".facet").exists()
    assert not any(s in result.stdout + result.stderr for s in PRIVATE + FORBIDDEN)


def test_private_metadata_exact_allowlist_and_public_refusal(tmp_path):
    config, env = setup(tmp_path)
    result = run(
        tmp_path,
        env,
        "config",
        "show",
        "--config",
        str(config),
        "--private-metadata",
        "--json",
    )
    assert result.returncode == 0
    metadata = json.loads(result.stdout)["data"]["private_metadata"]
    assert set(metadata) == {
        "projection",
        "source_email",
        "target_email",
        "own_addresses",
        "allow_domains",
        "allow_senders",
        "blacklist_senders",
        "projected_label",
        "state_dir",
        "config",
    }
    assert metadata["source_email"] == "source-sentinel@synthetic.example"
    assert not any(s in result.stdout + result.stderr for s in FORBIDDEN)
    result = run(
        tmp_path, env, "config", "show", "--config", str(config), "--public", "--json"
    )
    assert result.returncode == 3
    assert json.loads(result.stdout)["code"] == "scope_required"


@pytest.mark.parametrize(
    "arguments,code,exit_code",
    [
        (("unknown-private-input",), "invalid_input", 2),
        (("config", "validate", "--timeout", "nan"), "invalid_input", 2),
        (("config", "validate", "--timeout", "inf"), "invalid_input", 2),
        (("config", "validate", "--timeout", "0"), "invalid_input", 2),
        (("config", "validate", "--public", "--private-metadata"), "invalid_input", 2),
        (
            (
                "--config",
                "private-path-sentinel",
                "config",
                "validate",
                "--config",
                "other",
            ),
            "invalid_input",
            2,
        ),
        (
            ("config", "validate", "--projection", "../private-path-sentinel"),
            "invalid_input",
            2,
        ),
        (
            ("config", "validate", "--invalid", "BODY_CREDENTIAL_SENTINEL"),
            "invalid_input",
            2,
        ),
    ],
)
def test_controlled_errors_do_not_echo_argv(tmp_path, arguments, code, exit_code):
    _, env = setup(tmp_path)
    before = snapshot(tmp_path)
    result = run(tmp_path, env, *arguments, "--json")
    assert result.returncode == exit_code
    assert json.loads(result.stdout)["code"] == code
    assert not result.stderr
    assert not any(s in result.stdout + result.stderr for s in PRIVATE + FORBIDDEN)
    assert snapshot(tmp_path) == before


def test_selector_mismatch_permissions_yaml_and_text_errors(tmp_path):
    config, env = setup(tmp_path)
    result = run(
        tmp_path,
        env,
        "config",
        "validate",
        "--config",
        str(config),
        "--projection",
        "another-selector",
        "--json",
    )
    assert result.returncode == 3
    assert json.loads(result.stdout)["code"] == "binding_mismatch"
    config.chmod(0o644)
    result = run(tmp_path, env, "config", "validate", "--config", str(config))
    assert result.returncode == 3 and result.stdout == ""
    assert result.stderr == "facet: scope_required\n"
    config.chmod(0o600)
    config.write_bytes(CONFIG + b"BODY_CREDENTIAL_SENTINEL: [bad")
    result = run(tmp_path, env, "config", "validate", "--config", str(config), "--json")
    assert result.returncode == 2
    assert not any(s in result.stdout + result.stderr for s in PRIVATE + FORBIDDEN)


def test_module_entry_and_no_subprocess_import_runtime(tmp_path):
    _, env = setup(tmp_path)
    result = run(tmp_path, env, "--version", module=True)
    assert result.returncode == 0 and result.stdout == "0.1.0\n"


def test_fake_cli_sync_closure_survives_restart_without_duplicate_insert(tmp_path):
    """Exercise the user-visible production command path, not DB seeding."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    trusted_root = Path(
        tempfile.mkdtemp(prefix="facet-cli-", dir=f"/run/user/{os.geteuid()}")
    )
    state = trusted_root / "state"
    prefix = [str(Path(sys.executable).parent / "facet")]

    def invoke(*arguments):
        result = subprocess.run(
            prefix + ["--state-dir", str(state), "--json", *arguments],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert result.stderr == ""
        document = json.loads(result.stdout)
        assert document["status"] == "completed"
        return document

    invoke(
        "init",
        "--source",
        "source@example.com",
        "--target",
        "target@example.com",
        "--yes",
        "--request-id",
        "rq1_00000000000040008000000000000031_00000000000040008000000000000032",
    )
    auth_request = "00000000000040008000000000000033"
    invoke(
        "auth",
        "authorize",
        "--fake",
        "--yes",
        "--request-id",
        auth_request,
    )
    invoke("auth", "authorize", "--fake", "--yes", "--request-id", auth_request)
    rule_request = "00000000000040008000000000000034"
    invoke(
        "rules",
        "add-sender",
        "--sender",
        "sender@example.com",
        "--yes",
        "--request-id",
        rule_request,
    )
    invoke(
        "rules",
        "add-sender",
        "--sender",
        "sender@example.com",
        "--yes",
        "--request-id",
        rule_request,
    )
    preview_request = "00000000000040008000000000000036"
    preview_document = invoke(
        "backfill",
        "preview",
        "--fake",
        "--request-id",
        preview_request,
    )
    preview = preview_document["data"]["preview_id"]
    assert preview_document["data"]["target_writes"] == 0
    assert preview_document["data"]["requires_explicit_start"] is True
    assert preview_document["data"]["disclosure"] == {
        "scope": "source_thread",
        "includes_available_non_draft_history": True,
        "includes_attachments_participants_and_replies": True,
        "continues_for_future_thread_messages": True,
    }
    replayed_preview = invoke(
        "backfill",
        "preview",
        "--fake",
        "--request-id",
        preview_request,
    )
    assert replayed_preview["data"] == preview_document["data"]
    with sqlite3.connect(state / "facet.db") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM insert_attempts"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM message_mappings"
        ).fetchone() == (0,)
    start_request = "00000000000040008000000000000035"
    invoke(
        "backfill",
        "start",
        "--fake",
        "--preview-id",
        preview,
        "--yes",
        "--request-id",
        start_request,
    )
    assert (
        invoke(
            "backfill",
            "start",
            "--fake",
            "--preview-id",
            preview,
            "--yes",
            "--request-id",
            start_request,
        )["data"]["epoch_id"]
        == invoke(
            "backfill",
            "start",
            "--fake",
            "--preview-id",
            preview,
            "--yes",
            "--request-id",
            start_request,
        )["data"]["epoch_id"]
    )
    first = invoke("run", "--once", "--fake")
    second = invoke("run", "--once", "--fake")
    assert first["data"]["projected"] == 1
    assert second["data"]["projected"] == 0

    with sqlite3.connect(state / "facet.db") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM message_mappings"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM insert_attempts WHERE state='verified'"
        ).fetchone() == (1,)


def test_gmail_auth_status_is_offline_metadata_only(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    trusted_root = Path(
        tempfile.mkdtemp(prefix="facet-auth-status-", dir=f"/run/user/{os.geteuid()}")
    )
    state = trusted_root / "state"

    def invoke(*arguments):
        result = run(tmp_path, env, "--state-dir", str(state), *arguments)
        assert result.returncode == 0, result.stderr + result.stdout
        return json.loads(result.stdout)

    invoke(
        "init",
        "--source",
        "source@example.com",
        "--target",
        "target@example.com",
        "--yes",
        "--request-id",
        "rq1_00000000000040008000000000000041_00000000000040008000000000000042",
    )
    pending = invoke("gmail", "auth-status")
    assert {item["credential_state"] for item in pending["data"]["roles"]} == {
        "pending"
    }
    invoke(
        "auth",
        "authorize",
        "--fake",
        "--yes",
        "--request-id",
        "00000000000040008000000000000043",
    )
    status = invoke("gmail", "auth-status")
    data = status["data"]
    assert data["offline"] is True
    assert data["live_health"] == "unknown"
    assert {item["credential_state"] for item in data["roles"]} == {"verified"}
    assert all("address" not in item for item in data["roles"])
    assert "source@example.com" not in json.dumps(status)
    assert "target@example.com" not in json.dumps(status)

    private = invoke("gmail", "auth-status", "--private-metadata")
    assert {item["address"] for item in private["data"]["roles"]} == {
        "source@example.com",
        "target@example.com",
    }

    from facet.gmail.credential_codec import decode_envelope, encode_envelope

    source = state / "credentials" / "source.json"
    envelope = decode_envelope(source.read_bytes())
    expired = replace(
        envelope,
        secret=replace(
            envelope.secret,
            expires_at=Timestamp(datetime.now(UTC) - timedelta(minutes=1)),
        ),
    )
    expired_raw = encode_envelope(expired)
    source.write_bytes(expired_raw)
    with sqlite3.connect(state / "facet.db") as connection:
        connection.execute(
            "UPDATE credential_changes SET envelope_digest=?,expires_at=? "
            "WHERE role='source' AND phase='committed'",
            (
                hashlib.sha256(expired_raw).hexdigest(),
                int(expired.secret.expires_at.value.timestamp() * 1_000_000),
            ),
        )
        connection.commit()
    expired_status = invoke("gmail", "auth-status")
    source_status = next(
        item for item in expired_status["data"]["roles"] if item["role"] == "source"
    )
    assert source_status["credential_state"] == "expired"

    source.write_bytes(b"invalid credential sentinel")
    malformed = invoke("gmail", "auth-status")
    source_status = next(
        item for item in malformed["data"]["roles"] if item["role"] == "source"
    )
    assert source_status["credential_state"] == "attention"
    assert source_status["code"] == "invalid_input"

    with sqlite3.connect(state / "facet.db") as connection:
        connection.execute(
            "UPDATE credential_changes SET phase='attention',"
            "error='maintenance_required' WHERE role='source' "
            "AND phase='committed'"
        )
        connection.commit()
    unresolved = invoke("gmail", "auth-status")
    source_status = next(
        item for item in unresolved["data"]["roles"] if item["role"] == "source"
    )
    assert source_status["credential_state"] == "attention"
    assert source_status["unresolved_change"] is True

    (state / "credentials" / "target.json").unlink()
    missing = invoke("gmail", "auth-status")
    target_status = next(
        item for item in missing["data"]["roles"] if item["role"] == "target"
    )
    assert target_status["credential_state"] == "missing"
    assert target_status["code"] == "target_auth_required"

    with sqlite3.connect(state / "facet.db") as connection:
        connection.execute("UPDATE bindings SET state='mismatch' WHERE role='target'")
        connection.commit()
    mismatch = invoke("gmail", "auth-status")
    target_status = next(
        item for item in mismatch["data"]["roles"] if item["role"] == "target"
    )
    assert target_status["credential_state"] == "attention"
    assert target_status["code"] == "binding_mismatch"


def test_fake_cli_tampered_raw_stops_before_target_insert(tmp_path, monkeypatch):
    """A transport-level raw failure remains attention in the runtime path."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    trusted_root = Path(
        tempfile.mkdtemp(prefix="facet-cli-tamper-", dir=f"/run/user/{os.geteuid()}")
    )
    state = trusted_root / "state"
    prefix = [str(Path(sys.executable).parent / "facet")]

    def invoke(*arguments):
        result = subprocess.run(
            prefix + ["--state-dir", str(state), "--json", *arguments],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert result.stderr == ""
        return json.loads(result.stdout)

    invoke(
        "init",
        "--source",
        "source@example.com",
        "--target",
        "target@example.com",
        "--yes",
        "--request-id",
        "rq1_00000000000040008000000000000081_00000000000040008000000000000082",
    )
    invoke(
        "auth",
        "authorize",
        "--fake",
        "--yes",
        "--request-id",
        "00000000000040008000000000000083",
    )
    invoke(
        "rules",
        "add-sender",
        "--sender",
        "sender@example.com",
        "--yes",
        "--request-id",
        "00000000000040008000000000000084",
    )
    preview = invoke(
        "backfill",
        "preview",
        "--fake",
        "--request-id",
        "00000000000040008000000000000085",
    )["data"]["preview_id"]
    invoke(
        "backfill",
        "start",
        "--fake",
        "--preview-id",
        preview,
        "--yes",
        "--request-id",
        "00000000000040008000000000000086",
    )

    from facet.gmail.synthetic import SyntheticGmailServiceFactory

    class TamperedFactory(SyntheticGmailServiceFactory):
        def __init__(self, source_account, target_account):
            super().__init__(source_account, target_account)
            self._services[
                Role.SOURCE
            ]._raw = b"From: sender@example.com\r\n\r\nunsigned\r\n"

    monkeypatch.setattr(
        "facet.gmail.synthetic.SyntheticGmailServiceFactory", TamperedFactory
    )
    data, warnings = bootstrap._run_once_fake(
        SimpleNamespace(state_dir=str(state), config_path=None)
    )
    assert warnings == ()
    assert data["projected"] == 0
    with sqlite3.connect(state / "facet.db") as connection:
        assert connection.execute("SELECT state FROM epoch_partitions").fetchone() == (
            "needs_attention",
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM insert_attempts"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM message_mappings"
        ).fetchone() == (0,)


def test_recovery_check_uses_target_evidence_without_second_insert(
    tmp_path, monkeypatch, capsys
):
    """The CLI recovery check searches/readbacks a real unknown-attempt path."""
    from facet.gmail.retry import ProviderFailure
    from facet.gmail.synthetic import SyntheticGmailServiceFactory
    from facet.gmail.target import TargetAdapter
    from facet.runtime import locks, private_root

    shared = SyntheticGmailServiceFactory("source@example.com", "target@example.com")
    lose_response = True
    original_insert = TargetAdapter.insert

    def insert_then_lose(self, raw, *, thread_id=None, date_header=True):
        nonlocal lose_response
        result = original_insert(
            self, raw, thread_id=thread_id, date_header=date_header
        )
        if lose_response:
            lose_response = False
            raise ProviderFailure(ErrorCode.NETWORK_UNAVAILABLE, Role.TARGET)
        return result

    monkeypatch.setattr(TargetAdapter, "insert", insert_then_lose)
    monkeypatch.setattr(
        "facet.gmail.synthetic.SyntheticGmailServiceFactory",
        lambda _source, _target: shared,
    )
    state = (
        Path(
            tempfile.mkdtemp(
                prefix="facet-cli-recovery-", dir=f"/run/user/{os.geteuid()}"
            )
        )
        / "state"
    )

    def invoke(*arguments, private=False):
        args = ["--state-dir", str(state), "--json", *arguments]
        if private:
            args.insert(3, "--private-metadata")
        assert bootstrap.main(args) == 0
        document = json.loads(capsys.readouterr().out)
        assert document["status"] == "completed"
        return document

    invoke(
        "init",
        "--source",
        "source@example.com",
        "--target",
        "target@example.com",
        "--yes",
        "--request-id",
        "rq1_00000000000040008000000000000091_00000000000040008000000000000092",
    )
    invoke(
        "auth",
        "authorize",
        "--fake",
        "--yes",
        "--request-id",
        "00000000000040008000000000000093",
    )
    invoke(
        "rules",
        "add-sender",
        "--sender",
        "sender@example.com",
        "--yes",
        "--request-id",
        "00000000000040008000000000000094",
    )
    preview = invoke(
        "backfill",
        "preview",
        "--fake",
        "--request-id",
        "00000000000040008000000000000095",
    )["data"]["preview_id"]
    invoke(
        "backfill",
        "start",
        "--fake",
        "--preview-id",
        preview,
        "--yes",
        "--request-id",
        "00000000000040008000000000000096",
    )
    receipt = invoke("run", "--once", "--fake")
    assert receipt["data"]["projected"] == 0
    with sqlite3.connect(state / "facet.db") as connection:
        recovery_job = connection.execute(
            "SELECT job_id FROM sync_jobs WHERE kind='recover_insert'"
        ).fetchone()[0]
        before = connection.execute(
            "SELECT state,revision,recovery_checks FROM insert_attempts"
        ).fetchone()
        owner_before = (
            connection.execute("SELECT last_owner_run_id FROM projections").fetchone(),
            connection.execute("SELECT owner_run_id FROM command_runtime").fetchone(),
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM message_mappings"
        ).fetchone() == (0,)

    listing = invoke("recovery", "list")
    assert listing["data"]["unknown_insert_attempts"] == 1
    shown = invoke("recovery", "show", "--job", recovery_job, private=True)
    assert shown["data"]["attempt"]["state"] == "pending_recovery"
    assert shown["data"]["job"]["kind"] == "recover_insert"

    original_find = TargetAdapter.find_by_rfc_message_id

    def find_without_owner_lease(self, value):
        # The remote evidence phase must not retain Facet's writer lease.
        with (
            private_root.open_existing_root(str(state / "runtime-locks")) as root,
            locks.acquire_owner(root),
        ):
            pass
        return original_find(self, value)

    monkeypatch.setattr(
        TargetAdapter, "find_by_rfc_message_id", find_without_owner_lease
    )
    checked = invoke(
        "recovery",
        "check",
        "--job",
        recovery_job,
        "--fake",
        private=True,
    )
    assert checked["data"]["result"] == "unique_match", checked
    assert checked["data"]["retry_authorized"] is False
    assert checked["data"]["insert_invocations"] == 0
    assert checked["data"]["target_writes"] == 0
    with sqlite3.connect(state / "facet.db") as connection:
        assert (
            connection.execute(
                "SELECT state,revision,recovery_checks FROM insert_attempts"
            ).fetchone()
            == before
        )
        assert (
            connection.execute("SELECT last_owner_run_id FROM projections").fetchone(),
            connection.execute("SELECT owner_run_id FROM command_runtime").fetchone(),
        ) == owner_before
        assert connection.execute(
            "SELECT COUNT(*) FROM message_mappings"
        ).fetchone() == (0,)
    target_service = shared._services[Role.TARGET]
    target_service._inserted["target-message-2"] = dict(
        target_service._inserted["target-message-1"]
    )
    duplicate = invoke(
        "recovery",
        "check",
        "--job",
        recovery_job,
        "--fake",
        private=True,
    )
    assert duplicate["data"]["result"] == "duplicate_candidates"
    target_service._inserted.clear()
    missing = invoke(
        "recovery",
        "check",
        "--job",
        recovery_job,
        "--fake",
        private=True,
    )
    assert missing["data"]["result"] == "not_found"


def test_domain_rule_cli_publishes_and_replays_existing_ruleset_path(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    state = (
        Path(
            tempfile.mkdtemp(
                prefix="facet-domain-rule-", dir=f"/run/user/{os.geteuid()}"
            )
        )
        / "state"
    )

    def invoke(*arguments):
        result = run(tmp_path, env, "--state-dir", str(state), *arguments, "--json")
        assert result.returncode == 0, result.stderr + result.stdout
        assert result.stderr == ""
        return json.loads(result.stdout)

    invoke(
        "init",
        "--source",
        "source@example.com",
        "--target",
        "target@example.com",
        "--yes",
        "--request-id",
        "rq1_00000000000040008000000000000071_00000000000040008000000000000072",
    )
    invoke(
        "auth",
        "authorize",
        "--fake",
        "--yes",
        "--request-id",
        "00000000000040008000000000000073",
    )
    first = invoke(
        "rules",
        "add-domain",
        "--domain",
        "example.net",
        "--yes",
        "--request-id",
        "00000000000040008000000000000074",
    )
    second = invoke(
        "rules",
        "add-domain",
        "--domain",
        "example.net",
        "--yes",
        "--request-id",
        "00000000000040008000000000000074",
    )
    assert first["data"] == second["data"]
    with sqlite3.connect(state / "facet.db") as connection:
        assert connection.execute(
            "SELECT kind,normalized_value FROM rules WHERE projection_id=?",
            ("gmail-default",),
        ).fetchone() == ("allow_domain", "example.net")

    invalid = run(
        tmp_path,
        env,
        "--state-dir",
        str(state),
        "rules",
        "add-domain",
        "--domain",
        "com",
        "--yes",
        "--request-id",
        "00000000000040008000000000000075",
        "--json",
    )
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)["code"] == "invalid_input"


def test_domain_rule_cli_refuses_pending_bindings(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    state = (
        Path(
            tempfile.mkdtemp(
                prefix="facet-domain-rule-", dir=f"/run/user/{os.geteuid()}"
            )
        )
        / "state"
    )
    result = run(
        tmp_path,
        env,
        "--state-dir",
        str(state),
        "init",
        "--source",
        "source@example.com",
        "--target",
        "target@example.com",
        "--yes",
        "--request-id",
        "rq1_00000000000040008000000000000081_00000000000040008000000000000082",
        "--json",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    result = run(
        tmp_path,
        env,
        "--state-dir",
        str(state),
        "rules",
        "add-domain",
        "--domain",
        "example.net",
        "--yes",
        "--request-id",
        "00000000000040008000000000000083",
        "--json",
    )
    assert result.returncode == 3
    assert json.loads(result.stdout)["code"] == "binding_pending"


def test_invalid_enum_error_does_not_expose_original_value(tmp_path):
    config, env = setup(tmp_path)
    config.write_bytes(
        CONFIG.replace(
            b"projection:\n",
            b"projection:\n  source_mode: BODY_CREDENTIAL_SENTINEL\n",
        )
    )
    result = run(tmp_path, env, "config", "validate", "--config", str(config), "--json")
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "invalid_input"
    assert not result.stderr
    assert not any(s in result.stdout for s in PRIVATE + FORBIDDEN)


def test_injected_persistence_error_is_fixed_exit_seven(monkeypatch, capsys):
    def failure(*a, **kw):
        raise OSError("BODY_CREDENTIAL_SENTINEL /private-path-sentinel")

    monkeypatch.setattr(bootstrap, "config_read", failure)
    assert bootstrap.main(["config", "show", "--json"]) == 7
    captured = capsys.readouterr()
    assert json.loads(captured.out)["code"] == "persistence_failure"
    assert captured.err == ""
    assert "SENTINEL" not in captured.out


def test_owner_busy_fixed_exit_four(monkeypatch, capsys):
    def failure(*a, **kw):
        raise ConfigError(ErrorCode.OWNER_BUSY)

    monkeypatch.setattr(bootstrap, "config_read", failure)
    assert bootstrap.main(["config", "show", "--json"]) == 4
    assert json.loads(capsys.readouterr().out)["code"] == "owner_busy"


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (("config",), "{validate,show,init,apply}"),
        (("config", "validate"), "Validate standalone config structure only"),
        (("config", "show"), "Show a standalone config summary"),
        (("config", "init"), "Unavailable until single-owner init integration"),
        (("config", "apply"), "--file FILE"),
    ],
)
@pytest.mark.parametrize("json_mode", [False, True])
def test_child_help_is_specific_and_private(tmp_path, arguments, expected, json_mode):
    config, env = setup(tmp_path)
    before = snapshot(tmp_path)
    flags = ["--config", str(config), "--projection", "private-selector", "--help"]
    if json_mode:
        flags.append("--json")
    result = run(tmp_path, env, *arguments, *flags)
    assert result.returncode == 0 and result.stderr == ""
    help_text = (
        json.loads(result.stdout)["data"]["help"] if json_mode else result.stdout
    )
    assert "usage: facet config" in help_text
    assert expected in help_text
    assert not any(s in result.stdout for s in PRIVATE + FORBIDDEN)
    if arguments == ("config", "apply"):
        assert "Unavailable until single-owner execution" in help_text
        assert "--set" not in help_text
    assert snapshot(tmp_path) == before


def test_canonical_apply_file_is_parsed_but_never_opened(tmp_path):
    _, env = setup(tmp_path)
    spike = tmp_path / ".facet-spike"
    spike.mkdir(mode=0o700)
    file = spike / "token.json"
    file.write_text("BODY_CREDENTIAL_SENTINEL")
    file.chmod(0o600)
    before = snapshot(tmp_path)
    result = run(
        tmp_path,
        env,
        "config",
        "apply",
        "--file",
        str(file),
        "--yes",
        "--request-id",
        "synthetic-key",
        "--json",
    )
    assert result.returncode == 4
    assert json.loads(result.stdout)["code"] == "owner_unavailable"
    assert result.stderr == ""
    assert snapshot(tmp_path) == before
    assert not any(s in result.stdout for s in PRIVATE + FORBIDDEN)


def test_unallocated_apply_set_flag_is_refused_without_echo(tmp_path):
    _, env = setup(tmp_path)
    result = run(
        tmp_path, env, "config", "apply", "--set", "BODY_CREDENTIAL_SENTINEL", "--json"
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "invalid_input"
    assert result.stderr == ""
    assert "SENTINEL" not in result.stdout
