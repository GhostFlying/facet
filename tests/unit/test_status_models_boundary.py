"""Pure ST-01/04..10/14/15 portions; no source aggregation claims."""

import json
from dataclasses import fields, replace
from datetime import UTC, datetime

import pytest

from facet import __version__
from facet.contracts import (
    BindingState,
    Count,
    ErrorCode,
    Freshness,
    PublicHealth,
    PublicPhase,
    Role,
    Timestamp,
)
from facet.status.errors import OutputBoundaryError, catalog_entry
from facet.status.models import (
    MAX_PUBLIC_COUNT,
    Activity,
    ActivityEntry,
    CheckState,
    Component,
    Diagnostics,
    IssueGroup,
    Issues,
    LatencyMetric,
    PermissionMode,
    Pressure,
    Progress,
    PublicEnvelope,
    QueueCounts,
    RateMetric,
    RoleStatus,
    Rules,
    RuleSummary,
    Status,
    count_from_core,
)
from facet.status.serialization import (
    AuthRoleFact,
    LocalDoctorFinding,
    PrivateDoctorDetail,
    public_json,
    render_local_doctor,
    role_status_from_fact,
    serialize_public,
)

NOW = Timestamp(datetime(2026, 10, 2, 12, 0, 0, 123456, tzinfo=UTC))


class Trap:
    def __str__(self):
        raise AssertionError("must not format")

    def __repr__(self):
        raise AssertionError("must not format")

    def __getattribute__(self, name):
        if name.startswith("__"):
            return object.__getattribute__(self, name)
        raise AssertionError("must not traverse")


def unknown_status():
    return Status(
        None,
        PublicHealth.UNKNOWN,
        RoleStatus(Role.SOURCE, None, None, None, Freshness.UNAVAILABLE),
        RoleStatus(Role.TARGET, None, None, None, Freshness.UNAVAILABLE),
        None,
        None,
        None,
    )


def progress():
    return Progress(
        None,
        False,
        None,
        None,
        None,
        None,
        None,
        QueueCounts(*([None] * 9)),
        None,
        None,
        None,
        RateMetric(None, "messages_per_second", 60, 0),
        LatencyMetric(None, None, "milliseconds", 60, 0),
    )


def diagnostics():
    return Diagnostics(
        __version__,
        None,
        None,
        CheckState.UNAVAILABLE,
        CheckState.UNKNOWN,
        None,
        CheckState.UNKNOWN,
        CheckState.UNKNOWN,
        Pressure.UNKNOWN,
        Pressure.UNKNOWN,
        None,
        None,
    )


def activity():
    return Activity(
        (
            ActivityEntry(
                "allow_sender",
                "sender@example.invalid",
                2,
                NOW,
            ),
        )
    )


def envelope(data):
    return PublicEnvelope(data, 1, NOW, Freshness.UNAVAILABLE, None, "projection")


@pytest.mark.parametrize(
    "data", [unknown_status(), progress(), Issues(()), activity(), diagnostics()]
)
def test_all_families_explicit_keys_pure_and_no_missing_source_success(
    data, deny_external_network
):
    value = envelope(data)
    result = serialize_public(value)
    assert set(result) == {
        "data",
        "schema_version",
        "sampled_at",
        "freshness",
        "age_seconds",
        "scope",
    }
    assert set(result["data"]) == {f.name for f in fields(data)}
    assert result["sampled_at"] == NOW.value.astimezone().isoformat(
        timespec="microseconds"
    )
    assert result["freshness"] == "unavailable"
    assert result["age_seconds"] is None
    assert json.loads(public_json(value)) == result
    assert public_json(value) == public_json(value)
    result["data"]["injected"] = "PRIVATE_SENTINEL"
    assert "PRIVATE_SENTINEL" not in public_json(value)


def test_rules_snapshot_supports_the_configured_rule_limit():
    value = envelope(
        Rules(
            tuple(
                RuleSummary("allow_sender", f"{index:04d}" + "é" * 254, True)
                for index in range(1024)
            )
        )
    )
    encoded = public_json(value)
    assert len(encoded.encode("ascii")) < 2097152


@pytest.mark.parametrize(
    "data", [unknown_status(), progress(), Issues(()), diagnostics()]
)
def test_every_field_requires_exact_type_before_traversal(data):
    for field in fields(data):
        with pytest.raises(OutputBoundaryError):
            replace(data, **{field.name: Trap()})
    for field in fields(envelope(data)):
        with pytest.raises(OutputBoundaryError):
            replace(envelope(data), **{field.name: Trap()})


@pytest.mark.parametrize(
    "input", [Trap(), {}, None, "PRIVATE_SENTINEL", Exception("PRIVATE_SENTINEL")]
)
def test_unregistered_input_never_traversed(input):
    with pytest.raises(OutputBoundaryError) as error:
        serialize_public(input)
    assert error.value.args == ("consistency_failure",)
    assert error.value.__cause__ is None


def test_bypassed_frozen_and_subclass_refuse_at_output():
    value = envelope(unknown_status())
    object.__setattr__(value.data.source, "mode", Trap())
    with pytest.raises(OutputBoundaryError):
        public_json(value)

    class Foreign(Status):
        pass

    with pytest.raises(OutputBoundaryError):
        Foreign(None, PublicHealth.UNKNOWN, None, None, None, None, None)


@pytest.mark.parametrize("value", [True, -1, 1.0, MAX_PUBLIC_COUNT + 1, Trap()])
def test_invalid_count_types_bounds(value):
    with pytest.raises(OutputBoundaryError):
        QueueCounts(*([value] * 9))


def test_exact_counts_all_categories_and_unknowns():
    assert serialize_public(envelope(progress()))["data"]["jobs"] == {
        name: None
        for name in (
            "queued",
            "claimed",
            "retry_wait",
            "blocked",
            "needs_attention",
            "completed",
            "cancelled",
            "source_missing",
            "failed",
        )
    }
    assert count_from_core(Count(MAX_PUBLIC_COUNT)) == MAX_PUBLIC_COUNT
    with pytest.raises(OutputBoundaryError):
        count_from_core(Count(MAX_PUBLIC_COUNT + 1))
    with pytest.raises(OutputBoundaryError):
        QueueCounts(0, *([None] * 8))
    with pytest.raises(OutputBoundaryError):
        replace(progress(), known_message_total=100)
    with pytest.raises(OutputBoundaryError):
        replace(progress(), scanned_threads=0)


@pytest.mark.parametrize("value", [0, True, float("nan"), float("inf"), -1.0, Trap()])
def test_rate_requires_finite_exact_float_when_sampled(value):
    with pytest.raises(OutputBoundaryError):
        RateMetric(value, "messages_per_second", 60, 1)


def test_metric_missing_values_and_units():
    assert RateMetric(0.0, "messages_per_second", 60, 1).value == 0.0
    for construct in (
        lambda: RateMetric(0.0, "messages_per_second", 60, 0),
        lambda: RateMetric(None, "messages_per_second", 60, 1),
        lambda: RateMetric(None, "messages_per_second", 0, 0),
        lambda: RateMetric(None, "messages_per_second", 86401, 0),
        lambda: LatencyMetric(2.0, 1.0, "milliseconds", 60, 1),
        lambda: LatencyMetric(None, 1.0, "milliseconds", 60, 1),
        lambda: LatencyMetric(None, None, "seconds", 60, 0),
    ):
        with pytest.raises(OutputBoundaryError):
            construct()


def test_stale_or_unknown_cannot_claim_current_healthy():
    source = RoleStatus(
        Role.SOURCE,
        PermissionMode.SOURCE_READONLY,
        BindingState.VERIFIED,
        NOW,
        Freshness.FRESH,
    )
    target = RoleStatus(
        Role.TARGET,
        PermissionMode.TARGET_INSERT_READONLY,
        BindingState.VERIFIED,
        NOW,
        Freshness.FRESH,
    )
    status = Status(
        PublicPhase.INCREMENTAL, PublicHealth.HEALTHY, source, target, NOW, NOW, NOW
    )
    fresh = PublicEnvelope(status, 1, NOW, Freshness.FRESH, 0, "projection")
    assert serialize_public(fresh)["data"]["health"] == "healthy"
    for change in (
        {"freshness": Freshness.STALE},
        {"freshness": Freshness.UNAVAILABLE, "age_seconds": None},
        {"age_seconds": None},
        {"age_seconds": -1},
    ):
        with pytest.raises(OutputBoundaryError):
            replace(fresh, **change)
    with pytest.raises(OutputBoundaryError):
        replace(status, source=replace(source, freshness=Freshness.STALE))
    with pytest.raises(OutputBoundaryError):
        replace(source, mode=PermissionMode.TARGET_INSERT_READONLY)


def group(code=ErrorCode.NETWORK_UNAVAILABLE, role=None):
    entry = catalog_entry(code)
    return IssueGroup(
        code, entry.error_class, role, 1, NOW, NOW, False, None, entry.suggestion
    )


def test_issue_groups_exact_order_roles_catalog_and_retry_policy():
    item = group()
    assert len(Issues((item,)).groups) == 1
    with pytest.raises(OutputBoundaryError):
        Issues((item, item))
    with pytest.raises(OutputBoundaryError):
        group(ErrorCode.SOURCE_AUTH_REQUIRED)
    with pytest.raises(OutputBoundaryError):
        replace(group(ErrorCode.INSERT_RESULT_UNKNOWN), retryable=True)
    with pytest.raises(OutputBoundaryError):
        replace(item, next_retry_at=NOW)
    assert replace(item, retryable=True, next_retry_at=NOW).retryable


def test_private_doctor_output_stays_separate_and_opt_in():
    detail = PrivateDoctorDetail(
        "binding", Role.SOURCE, "sentinel@example.invalid", None
    )
    finding = LocalDoctorFinding(
        Component.SOURCE, Role.SOURCE, None, CheckState.UNKNOWN, NOW, detail
    )
    assert "detail" not in render_local_doctor(finding, private_metadata=False)
    private = render_local_doctor(finding, private_metadata=True)
    assert private["detail"]["binding_address"] == "sentinel@example.invalid"
    for bad in (finding, detail, private):
        with pytest.raises(OutputBoundaryError):
            public_json(bad)
    with pytest.raises(OutputBoundaryError):
        render_local_doctor(finding, private_metadata=1)


def test_auth_handoff_has_no_secret_and_does_not_claim_consumer_integration():
    fact = AuthRoleFact(
        Role.SOURCE,
        PermissionMode.SOURCE_READONLY,
        None,
        CheckState.UNKNOWN,
        None,
        None,
        Freshness.UNAVAILABLE,
        None,
    )
    assert role_status_from_fact(fact).auth_state is None
    with pytest.raises(OutputBoundaryError):
        replace(fact, binding_state=BindingState.VERIFIED, freshness=Freshness.FRESH)
    with pytest.raises(OutputBoundaryError):
        public_json(fact)
