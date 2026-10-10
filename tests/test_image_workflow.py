"""Static safety checks for the immutable image workflow."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOW = (ROOT / ".github/workflows/image.yml").read_text()


def test_image_workflow_uses_frozen_actions_and_base():
    frozen = {
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "docker/setup-qemu-action@29109295f81e9208d7d86ff1c6c12d2833863392",
        "docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069",
        "docker/login-action@dbcb813823bdd20940b903addbd779551569679f",
        "docker/metadata-action@dc802804100637a589fabce1cb79ff13a1411302",
        "docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc",
    }
    uses = set(re.findall(r"^\s+uses:\s+(\S+)", WORKFLOW, re.MULTILINE))
    assert uses == frozen
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref) for ref in uses)
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert (
        "python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3"
        in dockerfile
    )


def test_image_workflow_has_bounded_publish_contract():
    assert "linux/amd64,linux/arm64" in WORKFLOW
    assert "push: false" in WORKFLOW
    assert "push: true" in WORKFLOW
    assert "type=raw,value=${{ github.sha }}" in WORKFLOW
    assert (
        "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in WORKFLOW
    )
    assert "packages: write" in WORKFLOW
    assert "id-token: write" in WORKFLOW
    assert "attestations: write" in WORKFLOW
    assert WORKFLOW.count("flavor: latest=false") == 2
    assert ":latest" not in WORKFLOW
    assert "value=latest" not in WORKFLOW
    assert WORKFLOW.count("build-args: FACET_COMMIT_SHA=${{ github.sha }}") == 2
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "ARG FACET_COMMIT_SHA=unknown" in dockerfile
    assert "FACET_COMMIT_SHA=${FACET_COMMIT_SHA}" in dockerfile

    build = WORKFLOW.split("  publish:", 1)[0]
    assert "docker/login-action@" not in build
    assert "packages: write" not in build
    assert "id-token: write" not in build
    assert "attestations: write" not in build
