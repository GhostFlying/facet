from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_compose_uses_immutable_image_and_setup_only_oauth_listener():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "build:" not in compose
    assert "FACET_IMAGE:?" in compose
    assert "pull_policy: never" in compose
    assert "facet-setup:" in compose
    assert "profiles: [setup]" in compose
    assert "/run/secrets/google-client.json" in compose
    assert "target: google-client.json" in compose
    assert "127.0.0.1:${FACET_OAUTH_PORT:-18080}" in compose
    assert "facet-state:/var/lib/facet" in compose
    assert 'user: "10001:10001"' in compose
    assert "backfill start" not in compose
    assert ".facet/production" not in compose


def test_dockerfile_only_provisions_state_parent():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "mkdir -p /var/lib/facet" in dockerfile
    assert "chmod 0700 /var/lib/facet" in dockerfile
    assert "chown 10001:10001 /var/lib/facet" in dockerfile
    assert 'CMD ["run", "--state-dir", "/var/lib/facet/production"' in dockerfile
    assert "mkdir -p /var/lib/facet/production" not in dockerfile


def test_compose_image_ref_check_rejects_mutable_tags():
    checker = ROOT / "scripts" / "check-compose-image-ref.sh"
    valid = os.environ | {
        "FACET_IMAGE": "ghcr.io/ghostflying/facet:"
        "0123456789abcdef0123456789abcdef01234567"
    }
    accepted = subprocess.run([str(checker)], env=valid, capture_output=True)
    assert accepted.returncode == 0
    rejected = subprocess.run(
        [str(checker)],
        env=valid | {"FACET_IMAGE": "ghcr.io/ghostflying/facet:latest"},
        capture_output=True,
    )
    assert rejected.returncode == 2


def test_compose_config_parses_with_synthetic_inputs(tmp_path):
    docker = subprocess.run(
        ["docker", "compose", "version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if docker.returncode != 0:
        return
    client = tmp_path / "client.json"
    secret_key = "client" + "_secret"
    client.write_text(
        json.dumps({"installed": {"client_id": "synthetic", secret_key: "synthetic"}})
    )
    client.chmod(0o600)
    env = os.environ | {
        "FACET_IMAGE": "ghcr.io/ghostflying/facet:synthetic-full-commit",
        "FACET_OAUTH_CLIENT": str(client),
        "FACET_SETUP_REQUEST_ID": "rq1_synthetic_request",
    }
    result = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
