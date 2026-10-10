"""Closed logging/exports, with process-global bootstrap tested only in children."""

from dataclasses import fields, replace
from datetime import UTC, datetime

import pytest

import facet.status as status
from facet.contracts import ErrorCode, Role, Timestamp
from facet.status.errors import OutputBoundaryError
from facet.status.logging import LogEventKind, SafeLogEvent, SafeLogLevel
from facet.status.models import Component


def test_exact_public_exports_have_no_private_values():
    assert set(status.__all__) == {
        "PublicEnvelope",
        "Status",
        "Progress",
        "Issues",
        "Diagnostics",
        "RoleStatus",
        "EpochSummary",
        "QueueCounts",
        "RateMetric",
        "LatencyMetric",
        "IssueGroup",
        "PermissionMode",
        "CheckState",
        "Pressure",
        "Component",
        "Suggestion",
        "serialize_public",
        "public_json",
        "catalog_entry",
        "present_error",
        "emit_safe",
        "configure_production_logging",
    }
    assert len(status.__all__) == 22


@pytest.mark.parametrize(
    "kind,code,count",
    [
        (LogEventKind.LIFECYCLE, None, None),
        (LogEventKind.WORK_SUMMARY, None, 0),
        (LogEventKind.BOUNDARY_FAILURE, ErrorCode.CONSISTENCY_FAILURE, None),
        (LogEventKind.DEPENDENCY_STATE, ErrorCode.NETWORK_UNAVAILABLE, None),
    ],
)
def test_safe_log_closed_branches(kind, code, count):
    event = SafeLogEvent(
        kind,
        SafeLogLevel.INFO,
        Timestamp(datetime(2026, 10, 2, tzinfo=UTC)),
        Component.RUNTIME,
        None,
        code,
        count,
    )
    for field in fields(event):
        with pytest.raises(OutputBoundaryError):
            replace(event, **{field.name: object()})
    with pytest.raises(OutputBoundaryError):
        replace(event, role=Role.SOURCE)
    with pytest.raises(OutputBoundaryError):
        replace(event, component=Component.SOURCE)
    assert (
        replace(event, component=Component.SOURCE, role=Role.SOURCE).role is Role.SOURCE
    )


def test_fixed_public_record_field_inventory():
    from facet.status import models

    expected = {
        "RoleStatus": ["role", "mode", "auth_state", "last_verified_at", "freshness"],
        "Status": [
            "phase",
            "health",
            "source",
            "target",
            "last_poll_at",
            "last_verified_insert_at",
            "heartbeat_at",
            "cycle_in_progress",
        ],
        "EpochSummary": ["kind", "state", "started_at"],
        "QueueCounts": [
            "queued",
            "claimed",
            "retry_wait",
            "blocked",
            "needs_attention",
            "completed",
            "cancelled",
            "source_missing",
            "failed",
        ],
        "RateMetric": ["value", "unit", "window_seconds", "sample_count"],
        "LatencyMetric": ["p50", "p95", "unit", "window_seconds", "sample_count"],
        "Progress": [
            "epoch",
            "discovery_complete",
            "scanned_threads",
            "discovered_threads",
            "completed_threads",
            "known_message_total",
            "confirmed_messages",
            "jobs",
            "oldest_runnable_job_age_seconds",
            "verified_last_hour",
            "verified_last_day",
            "rate",
            "latency",
        ],
        "IssueGroup": [
            "code",
            "error_class",
            "role",
            "count",
            "first_at",
            "last_at",
            "retryable",
            "next_retry_at",
            "suggestion",
        ],
        "Issues": ["groups"],
        "ActivityEntry": [
            "rule_kind",
            "rule_value",
            "matched_count",
            "observed_at",
        ],
        "Activity": ["entries"],
        "Diagnostics": [
            "app_version",
            "schema_version",
            "sync_owner_count",
            "db_readable",
            "db_writable",
            "source_mode",
            "source_scope_ready",
            "target_scope_ready",
            "memory_pressure",
            "disk_pressure",
            "heartbeat_at",
            "checked_at",
            "commit_sha",
        ],
        "PublicEnvelope": [
            "data",
            "schema_version",
            "sampled_at",
            "freshness",
            "age_seconds",
            "scope",
        ],
    }
    for name, names in expected.items():
        assert [field.name for field in fields(getattr(models, name))] == names
