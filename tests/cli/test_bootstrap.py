import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from facet.cli import bootstrap
from facet.config import ConfigError
from facet.contracts import ErrorCode

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
        ("init", "--json", "--yes", "--request-id", "synthetic-key"),
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
