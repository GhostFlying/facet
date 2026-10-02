"""Minimal durable records for the insert/crash experiment."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from facet_spike.errors import SpikeError
from facet_spike.files import load_json, write_private_json
from facet_spike.message import MessageAnalysis
from facet_spike.runtime import RuntimePaths


def create_pending(
    paths: RuntimePaths,
    *,
    source_message_id: str,
    analysis: MessageAnalysis,
) -> dict[str, Any]:
    if not analysis.rfc_message_id:
        raise SpikeError("crash experiment requires a source RFC Message-ID")
    records = load_json(paths.experiments, {})
    experiment_id = uuid4().hex[:12]
    record = {
        "id": experiment_id,
        "created_at": datetime.now(UTC).isoformat(),
        "source_message_id": source_message_id,
        "rfc_message_id": analysis.rfc_message_id,
        "source_raw_sha256": analysis.raw_sha256,
        "status": "pending",
        "checks": [],
    }
    records[experiment_id] = record
    write_private_json(paths.experiments, records)
    return record


def load_records(paths: RuntimePaths) -> dict[str, dict[str, Any]]:
    return load_json(paths.experiments, {})


def save_records(paths: RuntimePaths, records: dict[str, dict[str, Any]]) -> None:
    write_private_json(paths.experiments, records)
