"""Real CLI processes; only external Google HTTP and OAuth are synthetic."""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from facet.cli.status import _paths_and_config
from facet.runtime.state_owner import StateOwner

ROOT = Path(__file__).resolve().parents[2]
HOOK = """
import os
import sys
from datetime import UTC, datetime, timedelta
from fakes.cleanup_http import CleanupHttp
from googleapiclient.discovery import build
from facet.gmail.cleanup_oauth import CleanupAccess
from facet.gmail.credential_models import SecretText
from facet.gmail.service_factory import GoogleGmailServiceFactory
import facet.gmail.cleanup_oauth as oauth

def client(role, access_token):
    return build("gmail", "v1", http=CleanupHttp(os.environ["CLEANUP_HTTP_STATE"]),
                 cache_discovery=False, num_retries=0)
GoogleGmailServiceFactory._build = staticmethod(client)
def authorize(client, **kwargs):
    return CleanupAccess(SecretText("CLEANUP_ACCESS_SENTINEL"),
                         datetime.now(UTC) + timedelta(hours=1))
oauth.authorize_cleanup = authorize
if os.environ.get("CLEANUP_TEST_TTY") == "1":
    sys.stdin.isatty = lambda: True
    sys.stderr.isatty = lambda: True
def deny(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise RuntimeError("unexpected_live_network")
sys.addaudithook(deny)
"""


@pytest.fixture
def cli(tmp_path):
    root = Path(
        tempfile.mkdtemp(prefix="facet-cleanup-cli-", dir=f"/run/user/{os.geteuid()}")
    )
    state = root / "state"
    guard = root / "guard"
    guard.mkdir(mode=0o700)
    (guard / "sitecustomize.py").write_text(HOOK)
    http = root / "external-http.json"
    http.write_text("{}")
    client = root / "client.json"
    client.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "synthetic-client",
                    # Synthetic Desktop fixture; match the existing OAuth
                    # tests' credential-shaped-literal scanner convention.
                    "client" + "_secret": "synthetic-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
        )
    )
    client.chmod(0o600)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(guard), str(ROOT / "src"), str(ROOT / "tests")]
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CLEANUP_HTTP_STATE"] = str(http)
    env["CLEANUP_TEST_TTY"] = "1"

    def invoke(*args, success=True, tty=True):
        child_env = env.copy()
        child_env["CLEANUP_TEST_TTY"] = "1" if tty else "0"
        result = subprocess.run(
            [
                str(Path(sys.executable).parent / "facet"),
                "--state-dir",
                str(state),
                *args,
            ],
            env=child_env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert bool(result.returncode == 0) == success, result.stderr + result.stdout
        if not success and "--json" not in args:
            assert result.stdout == ""
            assert result.stderr.startswith("facet: ")
            assert "SENTINEL" not in result.stderr
            return {"code": result.stderr.removeprefix("facet: ").strip()}
        assert result.stderr == "", result.stderr
        assert "CLEANUP_ACCESS_SENTINEL" not in result.stdout
        assert "BODY_CREDENTIAL_SENTINEL" not in result.stdout
        return json.loads(result.stdout)

    try:
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
        invoke("auth", "authorize", "--fake", "--yes", "--request-id", uuid4().hex)
        yield SimpleNamespace(invoke=invoke, state=state, http=http, client=client)
    finally:
        shutil.rmtree(root)


def credentials(state):
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (state / "credentials").iterdir()
        if path.is_file()
    }


def business(state):
    db = sqlite3.connect(f"{(state / 'facet.db').as_uri()}?mode=ro", uri=True)
    try:
        return {
            name: db.execute("SELECT * FROM " + name).fetchall()
            for name in (
                "bindings",
                "message_mappings",
                "sync_jobs",
                "insert_attempts",
                "epochs",
                "rules",
            )
        }
    finally:
        db.close()


def preview(cli):
    return cli.invoke(
        "target-cleanup", "preview", "--request-id", uuid4().hex, "--json"
    )["data"]


def execute(cli, preview_id, key, **kwargs):
    return cli.invoke(
        "target-cleanup",
        "execute",
        "--preview",
        preview_id,
        "--request-id",
        key,
        "--yes",
        "--confirm-target",
        "target@example.com",
        "--oauth-client",
        str(cli.client),
        **kwargs,
    )


def test_real_cli_cleanup_path_and_offline_replay(cli):
    before = business(cli.state), credentials(cli.state)
    receipt = preview(cli)
    identifier = receipt["preview_id"]
    assert receipt["total"] == 3 and receipt["drafts"] == 1
    provider = json.loads(cli.http.read_text())
    assert all(method == "GET" for method, _, _ in provider["calls"])
    provider["ids"].append("new_arrival")
    cli.http.write_text(json.dumps(provider))
    key = uuid4().hex
    result = execute(cli, identifier, key)
    assert result["data"]["state"] == "completed"
    assert result["data"]["confirmed_absent"] == 3
    assert json.loads(cli.http.read_text())["ids"] == ["new_arrival"]
    assert before == (business(cli.state), credentials(cli.state))
    calls = cli.http.read_bytes()
    assert (
        cli.invoke("target-cleanup", "status", "--preview", identifier, "--json")[
            "data"
        ]["remaining"]
        == 0
    )
    assert execute(cli, identifier, key, tty=False)["data"]["state"] == "completed"
    assert cli.http.read_bytes() == calls
    outputs = json.dumps(result)
    for private in (
        "source@example.com",
        "target@example.com",
        "mail1",
        "spam1",
        "draft_old",
    ):
        assert private not in outputs
    for path in cli.state.rglob("*"):
        if path.is_file():
            assert b"CLEANUP_ACCESS_SENTINEL" not in path.read_bytes()


def test_real_cli_response_loss_then_new_process_resume(cli):
    receipt = preview(cli)
    provider = json.loads(cli.http.read_text())
    provider["lost"] = True
    cli.http.write_text(json.dumps(provider))
    key = uuid4().hex
    assert (
        execute(cli, receipt["preview_id"], key, success=False)["code"]
        == "network_unavailable"
    )
    status = cli.invoke(
        "target-cleanup", "status", "--preview", receipt["preview_id"], "--json"
    )["data"]
    assert status["unknown_deletions"] == 1
    assert execute(cli, receipt["preview_id"], key)["data"]["state"] == "completed"
    operations = json.loads(cli.http.read_text())["calls"]
    deleted = [path for method, path, _ in operations if method == "DELETE"]
    assert len(deleted) == len(set(deleted)) == 3


def test_real_cli_writer_exclusion_and_offline_status(cli):
    identifier = preview(cli)["preview_id"]
    paths, raw, config = _paths_and_config(SimpleNamespace(state_dir=str(cli.state)))
    owner = StateOwner.open(paths.root, config)
    try:
        owner.verify_config_artifact(raw)
        before = business(cli.state), credentials(cli.state), cli.http.read_bytes()
        assert (
            cli.invoke("target-cleanup", "status", "--preview", identifier, "--json")[
                "data"
            ]["state"]
            == "ready"
        )
        assert (
            cli.invoke(
                "target-cleanup",
                "preview",
                "--request-id",
                uuid4().hex,
                "--json",
                success=False,
            )["code"]
            == "owner_busy"
        )
        assert before == (
            business(cli.state),
            credentials(cli.state),
            cli.http.read_bytes(),
        )
    finally:
        owner.close()


@pytest.mark.parametrize("flag", ["--json", "non_tty", "no_yes", "wrong_target"])
def test_real_cli_confirmation_before_oauth_or_delete(cli, flag):
    identifier = preview(cli)["preview_id"]
    args = [
        "target-cleanup",
        "execute",
        "--preview",
        identifier,
        "--request-id",
        uuid4().hex,
        "--confirm-target",
        "source@example.com" if flag == "wrong_target" else "target@example.com",
        "--oauth-client",
        str(cli.client),
    ]
    if flag != "no_yes":
        args.append("--yes")
    if flag == "--json":
        args.append(flag)
    before = cli.http.read_bytes()
    result = cli.invoke(*args, success=False, tty=flag != "non_tty")
    assert result["code"] == "confirmation_required"
    assert cli.http.read_bytes() == before


def test_real_cli_cleanup_scope_does_not_allow_wrong_oauth_account(cli):
    identifier = preview(cli)["preview_id"]
    provider = json.loads(cli.http.read_text())
    provider["profile"] = "source@example.com"
    cli.http.write_text(json.dumps(provider))
    before = credentials(cli.state)
    assert (
        execute(cli, identifier, uuid4().hex, success=False)["code"]
        == "binding_mismatch"
    )
    assert not any(
        method == "DELETE" for method, _, _ in json.loads(cli.http.read_text())["calls"]
    )
    assert credentials(cli.state) == before


def test_real_cli_public_flag_rejected_without_provider_calls(cli):
    before = cli.http.read_bytes()
    assert (
        cli.invoke(
            "target-cleanup",
            "preview",
            "--request-id",
            uuid4().hex,
            "--public",
            "--json",
            success=False,
        )["code"]
        == "invalid_input"
    )
    assert cli.http.read_bytes() == before


@pytest.mark.parametrize("action", ["preview", "status", "execute"])
def test_cleanup_help_needs_no_mutation_arguments(cli, action):
    before = business(cli.state), credentials(cli.state), cli.http.read_bytes()
    result = subprocess.run(
        [
            str(Path(sys.executable).parent / "facet"),
            "target-cleanup",
            action,
            "--help",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "usage: facet target-cleanup" in result.stdout
    assert result.stderr == ""
    assert before == (
        business(cli.state),
        credentials(cli.state),
        cli.http.read_bytes(),
    )
