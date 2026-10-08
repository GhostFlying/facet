"""Actual complete CLI with only external OAuth/Gmail fixtures."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fakes.sync_wire import Mailbox

from facet.cli import sync_entry
from facet.config import ConfigError, load_config
from facet.contracts import LocalId, Revision
from facet.private_paths import read_managed_config, select_paths
from facet.runtime.state_owner import StateOwner

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def wire(tmp_path):
    with (
        Mailbox() as mailbox,
        tempfile.TemporaryDirectory(
            prefix="facet-complete-wire-",
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

        def invoke(*args, error=None):
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
            assert result.stderr == ""
            assert not any(
                sentinel in result.stdout
                for sentinel in (
                    "WIRE_BODY_SENTINEL",
                    "WIRE_HEADER_SENTINEL",
                    "WIRE_ERROR_SENTINEL",
                    "facet-synthetic-source-access",
                    "facet-synthetic-target-access",
                    "sender@example.com",
                    "source@example.com",
                    "target@example.com",
                )
            )
            document = json.loads(result.stdout)
            if error:
                assert result.returncode != 0 and document["code"] == error
                return document
            assert result.returncode == 0, document
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
        invoke.hook = hook
        yield invoke, mailbox, state
        for path in state.rglob("*"):
            if path.is_file():
                for sentinel in (
                    b"WIRE_BODY_SENTINEL",
                    b"WIRE_HEADER_SENTINEL",
                    b"WIRE_ERROR_SENTINEL",
                ):
                    assert sentinel not in path.read_bytes()


def bind_and_rule(invoke):
    invoke("auth", "authorize", "--fake", "--yes", "--request-id", uuid4().hex)
    invoke(
        "rules",
        "add-sender",
        "--sender",
        "sender@example.com",
        "--yes",
        "--request-id",
        uuid4().hex,
    )


def rows(state, table):
    # Fixed table names from this test only. Read-only assertions, never DB seeds.
    with sqlite3.connect(f"{(state / 'facet.db').as_uri()}?mode=ro", uri=True) as db:
        return db.execute(f"SELECT * FROM {table}").fetchall()


def test_complete_sync_initial_history_restart_and_rule_expansion(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    mailbox.historical = True
    first = invoke("sync", "--once", "--yes")
    assert first["cycle"]["projected"] == 4
    assert first["disclosure"]["continues_for_future_thread_messages"]
    assert len(mailbox.inserted_raw) == 4 and len(rows(state, "message_mappings")) == 4
    original_epochs = rows(state, "epochs")
    original_attempts = rows(state, "insert_attempts")
    discovery_count = len(mailbox.discovery_queries)
    # New admissions changed generation sum; the default key must still resume.
    again = invoke("sync", "--once", "--yes")
    assert again["cycle"]["projected"] == 0
    assert len(rows(state, "epochs")) == len(original_epochs)
    assert rows(state, "insert_attempts") == original_attempts
    assert len(mailbox.discovery_queries) == discovery_count
    mailbox.arrive()
    future = invoke("sync", "--once", "--yes")
    assert future["cycle"]["projected"] == 2
    assert len(rows(state, "epochs")) == 1
    # A new intentional current-rule invocation may select a new historical scope.
    invoke(
        "rules",
        "add-sender",
        "--sender",
        "later@example.com",
        "--yes",
        "--request-id",
        uuid4().hex,
    )
    invoke("sync", "--once", "--yes")
    assert len(rows(state, "epochs")) == 2
    assert len(mailbox.inserted_raw) == 6
    before = len(rows(state, "epochs"))
    invoke("run", "--once")
    assert len(rows(state, "epochs")) == before


def test_explicit_request_replays_saved_scope_after_new_rules(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    key = uuid4().hex
    mailbox.historical = True
    invoke("sync", "--once", "--yes", "--request-id", key)
    original_epochs = len(rows(state, "epochs"))
    invoke(
        "rules",
        "add-sender",
        "--sender",
        "later@example.com",
        "--yes",
        "--request-id",
        uuid4().hex,
    )
    invoke("sync", "--once", "--yes", "--request-id", key)
    assert len(rows(state, "epochs")) == original_epochs
    assert len(mailbox.inserted_raw) == 4


def test_complete_unknown_does_not_resend_on_restart(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    mailbox.historical = True
    mailbox.fault = "lost_response"
    invoke("sync", "--once", "--yes")
    attempts = rows(state, "insert_attempts")
    assert any("pending_recovery" in attempt for attempt in attempts)
    count = len(mailbox.inserted_raw)
    assert invoke("run", "--once", "--verify-known-only")["projected"] == 0
    assert rows(state, "insert_attempts") == attempts
    invoke("sync", "--once", "--yes")
    assert rows(state, "insert_attempts") == attempts
    assert len(mailbox.inserted_raw) == count
    assert len(rows(state, "epochs")) == 1


def test_partial_scan_restarts_same_durable_scope(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    mailbox.historical = True
    mailbox.discovery_failure = True
    invoke("sync", "--once", "--yes", error="network_unavailable")
    assert len(rows(state, "epochs")) == 1 and not mailbox.inserted_raw
    mailbox.discovery_failure = False
    result = invoke("sync", "--once", "--yes")
    assert result["cycle"]["projected"] == 4
    assert len(rows(state, "epochs")) == 1


@pytest.mark.parametrize(
    "args,code",
    [
        (["--once"], "confirmation_required"),
        (["--once", "--yes", "--interval", "nan"], "invalid_input"),
        (["--once", "--yes", "--port", "0"], "invalid_input"),
        (["--once", "--yes", "--request-id", "not-valid"], "invalid_input"),
        (["--once", "--yes"], "binding_pending"),
    ],
)
def test_complete_rejects_before_scope_or_provider_work(wire, args, code):
    invoke, mailbox, state = wire
    before = rows(state, "operations")
    invoke("sync", *args, error=code)
    assert rows(state, "operations") == before
    assert not rows(state, "epochs") and not mailbox.calls


def test_single_writer_conflict_does_not_create_scope(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    paths = select_paths(str(state), None)
    config = load_config(read_managed_config(paths))
    owner = StateOwner.open(state, config)
    try:
        before = rows(state, "operations")
        invoke("sync", "--once", "--yes", error="owner_busy")
        assert rows(state, "operations") == before and not rows(state, "epochs")
        assert not mailbox.inserted_raw
    finally:
        owner.close()


def test_expired_unstarted_scope_is_not_silently_replaced(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    key = uuid4().hex
    paths = select_paths(str(state), None)
    config = load_config(read_managed_config(paths))
    owner = StateOwner.open(state, config)
    try:
        preview_key, _ = sync_entry._keys(owner, config, key)
    finally:
        owner.close()
    invoke("backfill", "preview", "--request-id", preview_key)
    # Clock fault only; the real CLI and its persisted preview remain untouched.
    with (invoke.hook / "sitecustomize.py").open("a") as stream:
        stream.write(
            "from datetime import datetime, timedelta\n"
            "from facet.cli import bootstrap\n"
            "class Later(datetime):\n"
            "    @classmethod\n"
            "    def now(cls, tz=None):\n"
            "        return datetime.now(tz)+timedelta(minutes=11)\n"
            "bootstrap.datetime=Later\n"
        )
    before = rows(state, "operations")
    invoke("sync", "--once", "--yes", "--request-id", key, error="preview_invalid")
    assert rows(state, "operations") == before and not rows(state, "epochs")
    assert not mailbox.inserted_raw


def test_explicit_keys_survive_calendar_and_revision_changes(monkeypatch):
    @contextmanager
    def transaction():
        yield object()

    owner = SimpleNamespace(
        owner_info=SimpleNamespace(request_namespace=LocalId(uuid4().hex)),
        session=SimpleNamespace(transaction=transaction),
    )
    config = SimpleNamespace(projection=SimpleNamespace(id=LocalId(uuid4().hex)))
    revision = [1]
    monkeypatch.setattr(
        sync_entry,
        "_backfill_guards",
        lambda *_: (
            SimpleNamespace(
                config_revision=Revision(1), ruleset_revision=Revision(revision[0])
            ),
            Revision(1),
            None,
            Revision(revision[0]),
        ),
    )

    class Clock:
        month = 1

        @classmethod
        def now(cls, _zone):
            return datetime(2026, cls.month, 1, tzinfo=UTC)

    monkeypatch.setattr(sync_entry, "datetime", Clock)
    key = uuid4().hex
    explicit = sync_entry._keys(owner, config, key)
    default = sync_entry._keys(owner, config, None)
    assert len(set(explicit)) == 2 and explicit == sync_entry._keys(owner, config, key)
    revision[0] = 2
    Clock.month = 2
    assert sync_entry._keys(owner, config, key) == explicit
    assert sync_entry._keys(owner, config, None) != default


@pytest.mark.parametrize("answer,accepted", [("yes", True), ("no", False)])
def test_tty_confirmation_accepts_only_explicit_yes(
    monkeypatch, capsys, answer, accepted
):
    monkeypatch.setattr(sync_entry.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(sync_entry.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sync_entry.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: answer)
    if accepted:
        sync_entry._confirm(SimpleNamespace(yes=False, json=False))
    else:
        with pytest.raises(ConfigError) as error:
            sync_entry._confirm(SimpleNamespace(yes=False, json=False))
        assert error.value.code.value == "confirmation_required"
    prompt = capsys.readouterr().out
    assert "Continue the saved scope" in prompt
    assert "Replay retains its saved scope" in prompt


@pytest.mark.parametrize("role", ["source", "target"])
def test_missing_role_credentials_block_before_scope(wire, role):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    credential = state / "credentials" / f"{role}.json"
    credential.rename(credential.with_suffix(".disabled"))  # Synthetic token loss.
    before = rows(state, "operations")
    invoke("sync", "--once", "--yes", error=f"{role}_auth_required")
    assert rows(state, "operations") == before and not rows(state, "epochs")
    assert not mailbox.inserted_raw


def test_granular_start_still_requires_confirmation(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    preview = invoke("backfill", "preview", "--request-id", uuid4().hex)
    before = rows(state, "operations")
    calls = len(mailbox.calls)
    invoke(
        "backfill",
        "start",
        "--preview-id",
        preview["preview_id"],
        "--request-id",
        uuid4().hex,
        error="confirmation_required",
    )
    assert rows(state, "operations") == before and not rows(state, "epochs")
    assert len(mailbox.calls) == calls


def test_insert_401_refresh_has_distinct_attempts_and_no_sdk_replay(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    mailbox.historical = True
    mailbox.reject_insert_once = True
    result = invoke("sync", "--once", "--yes")
    assert result["cycle"]["projected"] == 4
    assert mailbox.refresh_calls == ["target"]
    assert len(mailbox.inserted_raw) == 5 and len(mailbox.target) == 4
    with sqlite3.connect(f"{(state / 'facet.db').as_uri()}?mode=ro", uri=True) as db:
        assert db.execute(
            "SELECT state,COUNT(*) FROM insert_attempts GROUP BY state"
        ).fetchall() == [("definite_not_inserted", 1), ("verified", 4)]
    before = rows(state, "insert_attempts")
    invoke("run", "--once")
    assert rows(state, "insert_attempts") == before and len(mailbox.inserted_raw) == 5


def test_known_readback_restart_zero_insert_then_copy(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    mailbox.historical = True
    mailbox.readback_status = 401
    failure = invoke(
        "sync", "--once", "--yes", "--private-metadata", error="target_auth_required"
    )
    assert failure["data"]["provider_failure"]["reason"] == "authError"
    assert len(mailbox.target) == len(mailbox.inserted_raw) == 1
    assert not rows(state, "message_mappings")
    attempts = rows(state, "insert_attempts")
    epochs = rows(state, "epochs")
    mailbox.readback_status = None
    calls = len(mailbox.calls)
    result = invoke("run", "--once", "--verify-known-only")
    assert (
        result["projected"] == 1
        and result["discovered"] == result["history_pages"] == 0
    )
    assert len(mailbox.inserted_raw) == 1
    assert all(
        method == "GET" and not path.endswith(("/history", "/threads", "/messages"))
        for method, path in mailbox.calls[calls:]
    )
    assert len(rows(state, "insert_attempts")) == len(attempts)
    assert rows(state, "epochs") == epochs
    assert invoke("run", "--once", "--verify-known-only")["projected"] == 0
    assert invoke("run", "--once")["projected"] == 3
    assert len(mailbox.target) == len(mailbox.inserted_raw) == 4


def test_invalid_grant_keeps_definite_rejection_and_reports_reason(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    mailbox.historical = True
    mailbox.reject_insert_once = True
    mailbox.refresh_error = "invalid_grant"
    failure = invoke(
        "sync", "--once", "--yes", "--private-metadata", error="target_auth_required"
    )
    assert failure["data"]["provider_failure"]["reason"] == "invalid_grant"
    assert len(mailbox.inserted_raw) == 1 and not mailbox.target
    with sqlite3.connect(f"{(state / 'facet.db').as_uri()}?mode=ro", uri=True) as db:
        assert db.execute("SELECT state FROM insert_attempts").fetchall() == [
            ("definite_not_inserted",)
        ]
        assert db.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)


@pytest.mark.parametrize(
    "reason,code",
    [("domainPolicy", "scope_required"), ("dailyLimitExceeded", "target_rate_limited")],
)
def test_insert_403_reason_blocks_without_refresh_or_replay(wire, reason, code):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    mailbox.historical = True
    mailbox.fault = 403
    mailbox.insert_reason = reason
    failure = invoke("sync", "--once", "--yes", "--private-metadata", error=code)
    assert failure["data"]["provider_failure"]["reason"] == reason
    assert (
        len(mailbox.inserted_raw) == 1
        and not mailbox.target
        and not mailbox.refresh_calls
    )
    with sqlite3.connect(f"{(state / 'facet.db').as_uri()}?mode=ro", uri=True) as db:
        assert db.execute("SELECT state FROM insert_attempts").fetchall() == [
            ("definite_not_inserted",)
        ]
        assert db.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)


@pytest.mark.parametrize(
    "change,code", [("account", "binding_mismatch"), ("scope", "scope_required")]
)
def test_reactive_refresh_rejects_changed_account_or_scopes(wire, change, code):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    mailbox.historical = True
    mailbox.reject_insert_once = True
    if change == "account":
        mailbox.refresh_account = "unbound@example.com"
    else:
        mailbox.refresh_scopes = "https://www.googleapis.com/auth/gmail.modify"
    invoke("sync", "--once", "--yes", error=code)
    assert len(mailbox.inserted_raw) == 1 and not mailbox.target
    with sqlite3.connect(f"{(state / 'facet.db').as_uri()}?mode=ro", uri=True) as db:
        assert db.execute("SELECT state FROM insert_attempts").fetchall() == [
            ("definite_not_inserted",)
        ]
        assert db.execute("SELECT COUNT(*) FROM job_claims").fetchone() == (0,)


def test_threshold_refresh_mid_batch_uses_real_cli_manager_and_exchange(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    # Only advance the credential clock after the first successful insert.
    # Fake OAuth deliberately grants year-long tokens; no credential/DB edits.
    hook = invoke.hook / "sitecustomize.py"
    hook.write_text(
        hook.read_text()
        + """
from datetime import UTC, datetime, timedelta
import requests
import google.auth._helpers as helpers
import facet.gmail.credentials as credentials
from facet.contracts import Timestamp
advanced = False
def offset():
    return timedelta(days=365, minutes=-1) if advanced else timedelta()
credentials._owner_now = lambda: Timestamp(datetime.now(UTC) + offset())
helpers.utcnow = lambda: datetime.now(UTC).replace(tzinfo=None) + offset()
routed = requests.Session.request
def request(self, method, url, **kwargs):
    global advanced
    response = routed(self, method, url, **kwargs)
    if method == 'POST' and url.split('?')[0].endswith('/messages'):
        advanced = True
    return response
requests.Session.request = request
"""
    )
    mailbox.historical = True
    result = invoke("sync", "--once", "--yes")
    assert result["cycle"]["projected"] == 4
    assert sorted(mailbox.refresh_calls) == ["source", "target"]
    assert len(mailbox.inserted_raw) == len(mailbox.target) == 4
    assert len(rows(state, "message_mappings")) == 4


def test_startup_profile_401_refreshes_each_role_once_without_local_expiry(wire):
    invoke, mailbox, state = wire
    bind_and_rule(invoke)
    mailbox.historical = True
    mailbox.expired_profile_roles = {"source", "target"}
    result = invoke("sync", "--once", "--yes")
    assert result["cycle"]["projected"] == 4
    assert sorted(mailbox.refresh_calls) == ["source", "target"]
    assert len(mailbox.inserted_raw) == 4 and len(rows(state, "message_mappings")) == 4
