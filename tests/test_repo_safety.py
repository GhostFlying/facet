from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SAFETY_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check-repo-safety.sh"


def _stage(tmp_path: Path, name: str, content: str) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "--", name], cwd=tmp_path, check=True)


def _check(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SAFETY_SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_safety_allows_source_and_environment_example(tmp_path: Path) -> None:
    _stage(tmp_path, "src/example.py", "print('synthetic fixture')\n")
    _stage(tmp_path, ".env.example", "FACET_DATA_DIR=/data\n")

    result = _check(tmp_path)

    assert result.returncode == 0
    assert "baseline passed" in result.stdout


@pytest.mark.parametrize(
    "name",
    [
        ".facet-spike/accounts.json",
        ".facet/state.json",
        "data/facet.db",
        "credentials/source.json",
        "nested/credentials/source.json",
        ".env.local",
        "source-token.json",
        "sample.eml",
        "state.sqlite3-wal",
    ],
)
def test_safety_blocks_private_paths(tmp_path: Path, name: str) -> None:
    _stage(tmp_path, name, "synthetic runtime data\n")

    result = _check(tmp_path)

    assert result.returncode == 1
    assert name in result.stderr
    assert "synthetic runtime data" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "credential",
    [
        "ya29." + "synthetic" * 5,
        "ghp_" + "synthetic" * 5,
        "github_pat_" + "synthetic" * 5,
        "GOCSPX-" + "synthetic" * 5,
        "1//" + "synthetic" * 5,
        "-----BEGIN " + "PRIVATE KEY-----",
        '{"refresh_token": "' + "synthetic-private-value" + '"}',
    ],
)
def test_safety_blocks_credentials_without_printing_values(
    tmp_path: Path, credential: str
) -> None:
    _stage(tmp_path, "notes.txt", credential + "\n")

    result = _check(tmp_path)

    assert result.returncode == 1
    assert "notes.txt" in result.stdout
    assert credential not in result.stdout + result.stderr


def test_safety_checks_index_not_modified_working_copy(tmp_path: Path) -> None:
    credential = "ya29." + "synthetic" * 5
    _stage(tmp_path, "notes.txt", credential + "\n")
    (tmp_path / "notes.txt").write_text("clean working copy\n", encoding="utf-8")

    result = _check(tmp_path)

    assert result.returncode == 1
    assert credential not in result.stdout + result.stderr
