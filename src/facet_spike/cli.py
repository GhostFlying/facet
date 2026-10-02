"""Command-line entry point for live Gmail projection experiments."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

from googleapiclient.errors import HttpError

from facet_spike import evidence, experiments
from facet_spike.constants import DEFAULT_OAUTH_PORT
from facet_spike.errors import SpikeError
from facet_spike.files import load_json, write_private_json, write_private_text
from facet_spike.gmail import GmailSpike, sanitize_history
from facet_spike.oauth import authorize
from facet_spike.privacy import fingerprint, mask_email
from facet_spike.runtime import RuntimePaths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="facet-spike",
        description="Phase 0 Gmail projection experiments for Facet",
    )
    parser.add_argument(
        "--runtime-dir",
        help="private runtime directory (default: .facet-spike)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    auth = commands.add_parser("auth", help="authorize a Gmail role")
    auth.add_argument("role", choices=("source", "target"))
    auth.add_argument("--port", type=int, default=DEFAULT_OAUTH_PORT)
    auth.add_argument(
        "--open-browser",
        action="store_true",
        help="open a browser on the execution host",
    )

    commands.add_parser("doctor", help="verify OAuth and distinct account bindings")

    search = commands.add_parser("search", help="search one Gmail account")
    search.add_argument("role", choices=("source", "target"))
    search.add_argument("--query", required=True)
    search.add_argument("--max-results", type=int, default=10)
    search.add_argument(
        "--show-headers",
        action="store_true",
        help="print sender and subject instead of stable fingerprints",
    )

    copy_message = commands.add_parser(
        "copy-message",
        help="copy and compare one source message",
    )
    copy_message.add_argument("source_message_id")
    copy_message.add_argument("--yes", action="store_true")

    copy_thread = commands.add_parser(
        "copy-thread",
        help="copy and compare a complete source thread oldest first",
    )
    copy_thread.add_argument("source_thread_id")
    copy_thread.add_argument("--yes", action="store_true")

    crash = commands.add_parser(
        "crash-insert",
        help="insert once and terminate before recording the target response",
    )
    crash.add_argument("source_message_id")
    crash.add_argument("--yes", action="store_true")

    repeat = commands.add_parser(
        "repeat-insert",
        help="repeat a crash experiment insert to observe duplicate behavior",
    )
    repeat.add_argument("experiment_id")
    repeat.add_argument("--yes", action="store_true")

    reconcile = commands.add_parser(
        "reconcile",
        help="search target for pending crash experiments",
    )
    reconcile.add_argument("experiment_id", nargs="?")

    commands.add_parser(
        "history-start",
        help="capture the current source History cursor",
    )
    history_poll = commands.add_parser(
        "history-poll",
        help="inspect source History events since the captured cursor",
    )
    history_poll.add_argument("--advance", action="store_true")
    history_poll.add_argument(
        "--expected-subject",
        help="evaluate only events whose Subject contains this test marker",
    )
    history_poll.add_argument(
        "--action-label",
        help="evaluate labelAdded events for this user label name",
    )

    inspect_auth = commands.add_parser(
        "inspect-auth",
        help="summarize authentication results in one source message",
    )
    inspect_auth.add_argument("source_message_id")

    commands.add_parser("report", help="generate the redacted Markdown report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = RuntimePaths.from_value(args.runtime_dir)
    gmail = GmailSpike(paths)
    try:
        if args.command == "auth":
            authorize(
                paths,
                args.role,
                port=args.port,
                open_browser=args.open_browser,
            )
            profile = gmail.profile(args.role)
            print(f"Authorized {args.role}: {mask_email(profile['emailAddress'])}")
            return 0
        if args.command == "doctor":
            return _doctor(gmail)
        if args.command == "search":
            gmail.profile(args.role)
            results = gmail.search(
                args.role,
                args.query,
                max_results=args.max_results,
                show_headers=args.show_headers,
            )
            _print_json(results)
            return 0
        if args.command == "copy-message":
            _require_write_confirmation(args.yes)
            _print_json(gmail.copy_message(args.source_message_id))
            return 0
        if args.command == "copy-thread":
            _require_write_confirmation(args.yes)
            _print_json(gmail.copy_thread(args.source_thread_id))
            return 0
        if args.command == "crash-insert":
            _require_write_confirmation(args.yes)
            return _crash_insert(gmail, args.source_message_id)
        if args.command == "repeat-insert":
            _require_write_confirmation(args.yes)
            return _repeat_insert(gmail, args.experiment_id)
        if args.command == "reconcile":
            return _reconcile(gmail, args.experiment_id)
        if args.command == "history-start":
            return _history_start(gmail)
        if args.command == "history-poll":
            return _history_poll(
                gmail,
                advance=args.advance,
                expected_subject=args.expected_subject,
                action_label=args.action_label,
            )
        if args.command == "inspect-auth":
            return _inspect_auth(gmail, args.source_message_id)
        if args.command == "report":
            report = evidence.render_report(paths.evidence)
            write_private_text(paths.report, report)
            print(paths.report)
            return 0
    except SpikeError as error:
        parser.exit(2, f"error: {error}\n")
    except HttpError as error:
        status = getattr(error.resp, "status", "unknown")
        reason = getattr(error, "reason", "Gmail API request failed")
        parser.exit(2, f"Gmail API error {status}: {reason}\n")
    except (TimeoutError, ConnectionError) as error:
        parser.exit(2, f"network error while calling Gmail API: {error}\n")
    return 1


def _doctor(gmail: GmailSpike) -> int:
    source, target = gmail.verify_distinct_accounts()
    details = {
        "source": fingerprint(source["emailAddress"], prefix="account"),
        "target": fingerprint(target["emailAddress"], prefix="account"),
        "source_history_present": bool(source.get("historyId")),
        "target_history_present": bool(target.get("historyId")),
    }
    evidence.record(gmail.paths.evidence, "doctor_passed", details)
    _print_json(
        {
            "source": mask_email(source["emailAddress"]),
            "target": mask_email(target["emailAddress"]),
            "accounts_distinct": True,
            "status": "healthy",
        }
    )
    return 0


def _crash_insert(gmail: GmailSpike, source_message_id: str) -> int:
    gmail.verify_distinct_accounts()
    _, analysis = gmail.fetch_raw("source", source_message_id)
    experiment = experiments.create_pending(
        gmail.paths,
        source_message_id=source_message_id,
        analysis=analysis,
    )
    print(
        "Prepared pending experiment "
        f"{experiment['id']}; process will exit with status 86 after insert succeeds.",
        flush=True,
    )
    gmail.insert_for_crash_experiment(source_message_id)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(86)


def _repeat_insert(gmail: GmailSpike, experiment_id: str) -> int:
    records = experiments.load_records(gmail.paths)
    record = records.get(experiment_id)
    if record is None:
        raise SpikeError(f"unknown experiment: {experiment_id}")
    target = gmail.insert_for_crash_experiment(record["source_message_id"])
    evidence.record(
        gmail.paths.evidence,
        "experiment_insert_repeated",
        {
            "experiment_id": experiment_id,
            "target_message_id": fingerprint(target.get("id")),
            "target_thread_id": fingerprint(target.get("threadId"), prefix="thread"),
        },
    )
    print("Repeated insert completed; run reconcile for the experiment.")
    return 0


def _reconcile(gmail: GmailSpike, experiment_id: str | None) -> int:
    gmail.verify_distinct_accounts()
    records = experiments.load_records(gmail.paths)
    selected = (
        [experiment_id]
        if experiment_id is not None
        else [
            key
            for key, value in records.items()
            if value.get("status") in {"pending", "not_found", "found", "duplicate"}
        ]
    )
    if not selected:
        print("No crash experiments to reconcile.")
        return 0

    output = []
    for selected_id in selected:
        record = records.get(selected_id)
        if record is None:
            raise SpikeError(f"unknown experiment: {selected_id}")
        candidates = gmail.find_target_by_rfc_message_id(record["rfc_message_id"])
        check = {
            "checked_at": datetime.now(UTC).isoformat(),
            "candidate_count": len(candidates),
            "candidate_ids": [item["id"] for item in candidates],
        }
        record.setdefault("checks", []).append(check)
        if len(candidates) == 0:
            record["status"] = "not_found"
        elif len(candidates) == 1:
            record["status"] = "found"
            record["target_message_id"] = candidates[0]["id"]
            record["target_thread_id"] = candidates[0].get("threadId")
        else:
            record["status"] = "duplicate"
        details = {
            "experiment_id": selected_id,
            "status": record["status"],
            "candidate_count": len(candidates),
            "check_number": len(record["checks"]),
        }
        evidence.record(gmail.paths.evidence, "pending_reconciled", details)
        output.append(details)
    experiments.save_records(gmail.paths, records)
    _print_json(output)
    return 0


def _history_start(gmail: GmailSpike) -> int:
    profile = gmail.profile("source")
    state = load_json(gmail.paths.state, {})
    state["history_cursor"] = profile["historyId"]
    state["history_started_at"] = datetime.now(UTC).isoformat()
    write_private_json(gmail.paths.state, state)
    evidence.record(
        gmail.paths.evidence,
        "history_started",
        {"history_id_present": True},
    )
    print("Captured source History cursor. Perform the test mailbox actions now.")
    return 0


def _history_poll(
    gmail: GmailSpike,
    *,
    advance: bool,
    expected_subject: str | None,
    action_label: str | None,
) -> int:
    state = load_json(gmail.paths.state, {})
    cursor = state.get("history_cursor")
    if cursor is None:
        raise SpikeError("no History cursor; run history-start first")
    result = gmail.history_since(cursor)
    sanitized = sanitize_history(result["history"])
    details = {
        "record_count": len(result["history"]),
        "sanitized_event_record_count": len(sanitized),
        "events": sanitized,
        "advanced": advance,
    }
    evidence.record(gmail.paths.evidence, "history_polled", details)
    if expected_subject is not None:
        evaluation = gmail.evaluate_history(
            result["history"],
            expected_subject=expected_subject,
            action_label=action_label,
        )
        details["evaluation"] = evaluation
        evidence.record(gmail.paths.evidence, "history_evaluated", evaluation)
    if advance:
        state["history_cursor"] = result["history_id"]
        state["history_advanced_at"] = datetime.now(UTC).isoformat()
        write_private_json(gmail.paths.state, state)
    _print_json(details)
    return 0


def _inspect_auth(gmail: GmailSpike, source_message_id: str) -> int:
    _, analysis = gmail.fetch_raw("source", source_message_id)
    details = {
        "source_message_id": fingerprint(source_message_id),
        "authentication": analysis.auth_results,
        "parsed_date": analysis.parsed_date,
        "mime_part_types": [part.content_type for part in analysis.parts],
    }
    evidence.record(gmail.paths.evidence, "authentication_inspected", details)
    _print_json(details)
    return 0


def _require_write_confirmation(confirmed: bool) -> None:
    if not confirmed:
        raise SpikeError(
            "this command writes to target Gmail; rerun with --yes after verifying "
            "that the target is disposable"
        )


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
