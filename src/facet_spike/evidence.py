"""Redacted experiment evidence and report rendering."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from facet_spike.files import append_private_json_line


def record(path: Path, event: str, details: dict[str, Any]) -> None:
    append_private_json_line(
        path,
        {
            "recorded_at": datetime.now(UTC).isoformat(),
            "event": event,
            "details": details,
        },
    )


def load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid evidence JSON at {path}:{line_number}"
                ) from error
    return entries


def render_report(path: Path) -> str:
    entries = load(path)
    by_event: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_event.setdefault(entry["event"], []).append(entry)

    fidelity = _fidelity_status(by_event.get("message_copied", []))
    thread = _thread_status(by_event.get("thread_copied", []))
    recovery = _recovery_status(by_event.get("pending_reconciled", []))
    history = _history_status(by_event.get("history_evaluated", []))
    oauth = "pass" if by_event.get("doctor_passed") else "untested"
    authentication = _authentication_status(
        by_event.get("authentication_inspected", [])
    )

    lines = [
        "# Facet Gmail Phase 0 Evidence",
        "",
        "This report is generated from redacted local evidence. It does not contain",
        "OAuth tokens, raw MIME, subjects, sender addresses, or message bodies.",
        "",
        "| Architectural assumption | Status |",
        "| --- | --- |",
        f"| Distinct source and target OAuth accounts | {oauth} |",
        f"| Raw MIME payload fidelity | {fidelity} |",
        f"| Target thread reconstruction | {thread} |",
        f"| Insert-crash reconciliation | {recovery} |",
        f"| Required source History events | {history} |",
        f"| Sender SPF, DKIM, and DMARC sample | {authentication} |",
        "| AI connector retrieval | owned by AI products; not a Facet release gate |",
        "",
        "## Evidence counts",
        "",
    ]
    if not by_event:
        lines.append("No live evidence has been recorded yet.")
    else:
        for name in sorted(by_event):
            lines.append(f"- `{name}`: {len(by_event[name])}")
    lines.append("")
    return "\n".join(lines)


def _fidelity_status(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "untested"
    comparisons = [entry["details"]["comparison"] for entry in entries]
    if all(
        comparison.get("rfc_message_id_equal")
        and comparison.get("date_header_equal")
        and comparison.get("mime_payloads_equal")
        for comparison in comparisons
    ):
        return "pass"
    return "partial or fail"


def _thread_status(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "untested"
    if all(entry["details"].get("target_thread_count") == 1 for entry in entries):
        return "pass"
    return "partial or fail"


def _recovery_status(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "untested"
    found = any(
        entry["details"].get("status") == "found"
        and entry["details"].get("candidate_count") == 1
        for entry in entries
    )
    duplicate = any(
        entry["details"].get("status") == "duplicate"
        and entry["details"].get("candidate_count", 0) > 1
        for entry in entries
    )
    if found and duplicate:
        return "pass; repeated insert creates duplicates"
    if found:
        return "pass"
    return "partial or fail"


def _history_status(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "untested"
    if any(
        entry["details"].get("incoming_count", 0) >= 1
        and entry["details"].get("own_sent_count", 0) >= 1
        and entry["details"].get("matching_action_label_events", 0) >= 1
        and entry["details"].get("label_event_distinct_threads") == 1
        for entry in entries
    ):
        return "pass"
    return "partial or fail"


def _authentication_status(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "untested"
    for entry in entries:
        authentication = entry["details"].get("authentication", {})
        if all(
            authentication.get(mechanism) == ["pass"]
            for mechanism in ("spf", "dkim", "dmarc")
        ):
            return "pass for sampled mail"
    return "partial or fail"
