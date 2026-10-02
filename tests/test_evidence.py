from __future__ import annotations

from facet_spike.evidence import record, render_report


def test_report_contains_only_aggregate_evidence(tmp_path) -> None:
    path = tmp_path / "evidence.jsonl"
    record(
        path,
        "message_copied",
        {
            "comparison": {
                "rfc_message_id_equal": True,
                "date_header_equal": True,
                "mime_payloads_equal": True,
            },
            "source_message_id": "id:abc",
        },
    )

    report = render_report(path)

    assert "Raw MIME payload fidelity | pass" in report
    assert "id:abc" not in report
    assert "message_copied`" in report
    assert "owned by AI products; not a Facet release gate" in report
    assert "manual verification required" not in report


def test_report_summarizes_recovery_and_history(tmp_path) -> None:
    path = tmp_path / "evidence.jsonl"
    record(
        path,
        "pending_reconciled",
        {"status": "found", "candidate_count": 1},
    )
    record(
        path,
        "pending_reconciled",
        {"status": "duplicate", "candidate_count": 2},
    )
    record(
        path,
        "history_evaluated",
        {
            "incoming_count": 1,
            "own_sent_count": 1,
            "matching_action_label_events": 2,
            "label_event_distinct_threads": 1,
        },
    )

    report = render_report(path)

    assert "repeated insert creates duplicates" in report
    assert "Required source History events | pass" in report
