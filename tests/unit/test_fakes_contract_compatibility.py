"""CT-01..04: actual core values with helpers, not a duplicate business model."""

from dataclasses import MISSING, FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from typing import Literal, get_args, get_type_hints

import pytest
from fakes.faults import InjectedFailure
from fakes.privacy import Marker, MarkerKind, Profile, assert_private_boundary, markers
from fakes.transport import TransportFactory

from facet import contracts as c
from facet.contracts import enums, primitives
from facet.contracts import records as r

pytestmark = pytest.mark.usefixtures("deny_external_network")

# Expected manifests are assertions from p1-core-v1, not substitute types.
PRIMITIVES = [
    "ProjectionId",
    "LocalId",
    "ProviderId",
    "Timestamp",
    "Count",
    "Generation",
    "Revision",
    "Sha256Hex",
    "PolicyVersion",
    "ProviderPageToken",
]
ENUMS = {
    "Role": "source target",
    "SourceMode": "readonly convenience",
    "BindingState": "verification_pending verified mismatch auth_required",
    "RestoreState": "normal revalidation_required maintenance_incomplete",
    "RuleOrigin": "initial_config cli action_label",
    "RuleKind": "allow_sender allow_domain blacklist_sender",
    "AdmissionOrigin": "initial_backfill future_rule manual_thread action_label",
    "EpochKind": (
        "initial_backfill historical_expansion history_gap "
        "source_reconcile target_audit"
    ),
    "EpochState": (
        "prepared scanning catching_up draining paused completed "
        "completed_with_issues needs_attention"
    ),
    "JobKind": (
        "project_message repair_message expand_thread resolve_event operation_read "
        "recover_insert scan_discovery scan_gap reconcile_source "
        "audit_target cleanup_action"
    ),
    "JobState": (
        "queued claimed retry_wait blocked needs_attention completed cancelled "
        "source_missing failed"
    ),
    "Priority": "stop realtime recovery backfill audit",
    "InsertState": (
        "prepared dispatch_started definite_not_inserted known_inserted "
        "pending_recovery verified needs_attention cancelled_before_dispatch"
    ),
    "OutcomeCertainty": "not_attempted definitely_not_inserted inserted unknown",
    "Visibility": "normal spam trash unknown",
    "DatePolicy": "valid_date_header fallback_received_time",
    "OperationState": "accepted executing completed blocked needs_attention rejected",
    "PreviewPurpose": (
        "track_thread approve_admission start_backfill repair_missing "
        "retry_unknown_insert approve_gap change_mode maintenance_restore "
        "maintenance_migrate operational_change"
    ),
    "ErrorClass": "input guard ownership dependency attention persistence",
    "ErrorCode": (
        "invalid_input unsupported_version request_conflict request_not_received "
        "request_outcome_unknown request_lineage_mismatch confirmation_required "
        "scope_required binding_mismatch binding_pending preview_invalid "
        "generation_stale owner_unavailable owner_busy maintenance_incomplete "
        "wait_timeout source_auth_required target_auth_required source_rate_limited "
        "target_rate_limited network_unavailable target_storage_full "
        "insert_result_unknown duplicate_candidates attribution_unknown "
        "fidelity_mismatch source_missing target_missing database_unavailable "
        "persistence_failure consistency_failure maintenance_required"
    ),
    "Freshness": "fresh stale unavailable",
    "PublicPhase": (
        "uninitialized initializing backfill incremental recovering paused maintenance"
    ),
    "PublicHealth": "healthy degraded blocked unknown",
    "LabelChange": "added removed",
    "ReadTaskKind": (
        "thread_preview review_preview backfill_preview repair_preview "
        "recovery_preview gap_preview doctor_live"
    ),
    "PartitionState": "not_started scanning complete needs_attention",
    "ClaimPhase": "preparing dispatching verifying",
}
UNIONS = {
    "AdmissionRef": {
        "initial_backfill": "epoch_id rule policy_version",
        "future_rule": "rule policy_version",
        "manual_thread": "preview_id",
        "action_label": "action_command_id",
    },
    "EpochDecisionRef": {
        "backfill_start": "operation_id preview_id ruleset_revision",
        "gap_approval": "operation_id preview_id ruleset_revision",
        "scheduled_reconcile": "ruleset_revision",
        "requested_reconcile": "operation_id ruleset_revision",
        "scheduled_target_audit": "",
        "requested_target_audit": "operation_id",
    },
    "PartitionRef": {
        "source_window": "",
        "source_thread": "source_thread_id",
        "target_catalog": "",
        "mapped_target_set": "",
    },
    "SourceEventKey": {
        "message_added": "projection_id history_record_id source_message_id",
        "message_deleted": "projection_id history_record_id source_message_id",
        "label_changed": (
            "projection_id history_record_id source_message_id label_id change"
        ),
    },
    "JobSubject": {
        "project_message": "source_message_id source_thread_id generation",
        "repair_message": (
            "repair_operation_id source_message_id source_thread_id generation"
        ),
        "expand_thread": "source_thread_id epoch_id generation",
        "resolve_event": "event_key",
        "operation_read": "operation_id read_kind",
        "recover_insert": "attempt_id",
        "scan_discovery": "epoch_id partition",
        "scan_gap": "epoch_id partition",
        "reconcile_source": "epoch_id partition",
        "audit_target": "epoch_id partition",
        "cleanup_action": "action_command_id",
    },
    "ThreadGenerationGuard": {"untracked": "", "tracked": "generation"},
}
RECORDS = {
    "RuleRef": "rule_id revision",
    "PartitionProgress": (
        "partition state completed_pages observed_items page_token "
        "after_source_message_id"
    ),
    "SourceEvent": "key observed_at source_thread_id",
    "Claim": "claim_id owner_run_id acquired_at thread_generation job_revision phase",
}
VARIANTS = [
    (union, tag, payload)
    for union, tags in UNIONS.items()
    for tag, payload in tags.items()
]


def _constructor(union, tag):
    # One required canonical name, never a fallback or synthetic constructor.
    return getattr(r, union + "".join(part.capitalize() for part in tag.split("_")))


def _assert_inventory(exports):
    expected = set(PRIMITIVES) | ENUMS.keys() | UNIONS.keys() | RECORDS.keys()
    assert len(expected) == 47
    assert set(exports) == expected
    for name in PRIMITIVES:
        assert exports[name] is getattr(primitives, name)
        assert exports[name].__module__ == "facet.contracts.primitives"
    for name in ENUMS:
        assert exports[name] is getattr(enums, name)
        assert exports[name].__module__ == "facet.contracts.enums"
    for name in UNIONS.keys() | RECORDS.keys():
        assert exports[name] is getattr(r, name)


def test_ct01_exact_exports_and_missing_or_drifted_negative_controls():
    assert len(c.__all__) == len(set(c.__all__)) == 47
    exports = {name: getattr(c, name) for name in c.__all__}
    _assert_inventory(exports)
    for changed in (
        {name: value for name, value in exports.items() if name != "Claim"},
        exports | {"Role": c.SourceMode},
        exports | {"ProviderResult": object},
    ):
        with pytest.raises(AssertionError):
            _assert_inventory(changed)


@pytest.mark.parametrize("name,values", ENUMS.items(), ids=list(ENUMS))
def test_ct01_exact_closed_enum_values(name, values):
    enum = getattr(c, name)
    assert issubclass(enum, StrEnum)
    assert [member.value for member in enum] == values.split()
    assert len(enum.__members__) == len(values.split())  # No alias drift.
    for value in values.split():
        assert enum(value).value == value
    with pytest.raises(ValueError):
        enum("unallocated_variant")


@pytest.fixture
def core_values(fake_clock):
    local = c.LocalId("123456781234423482341234567890ab")
    provider = c.ProviderId("synthetic-provider-metadata-0123")
    key = r.SourceEventKeyMessageAdded(
        "message_added", c.ProjectionId("synthetic"), c.ProviderId("907"), provider
    )
    values = {
        name: local
        for name in [
            "epoch_id",
            "rule_id",
            "preview_id",
            "action_command_id",
            "operation_id",
            "repair_operation_id",
            "attempt_id",
            "claim_id",
            "owner_run_id",
        ]
    }
    values.update(
        {
            name: provider
            for name in ("source_message_id", "source_thread_id", "label_id")
        }
    )
    values.update(
        projection_id=key.projection_id,
        history_record_id=key.history_record_id,
        rule=c.RuleRef(local, c.Revision(1)),
        revision=c.Revision(1),
        ruleset_revision=c.Revision(1),
        job_revision=c.Revision(1),
        policy_version=c.PolicyVersion("synthetic-v1"),
        generation=c.Generation(1),
        partition=r.PartitionRefSourceWindow("source_window"),
        event_key=key,
        key=key,
        change=c.LabelChange.ADDED,
        read_kind=c.ReadTaskKind.DOCTOR_LIVE,
        state=c.PartitionState.NOT_STARTED,
        completed_pages=c.Count(0),
        observed_items=c.Count(0),
        page_token=None,
        after_source_message_id=None,
        observed_at=c.Timestamp(fake_clock.now()),
        acquired_at=c.Timestamp(fake_clock.now()),
        thread_generation=None,
        phase=c.ClaimPhase.PREPARING,
    )
    return values


def _assert_closed_record(constructor, payload):
    assert constructor.__module__ == "facet.contracts.records"
    assert [field.name for field in fields(constructor)] == list(payload)
    assert all(
        field.default is MISSING and field.default_factory is MISSING
        for field in fields(constructor)
    )
    instance = constructor(**payload)
    assert instance == constructor(**payload)
    with pytest.raises(FrozenInstanceError):
        setattr(instance, next(iter(payload)), None)
    for name in payload:
        with pytest.raises(TypeError):
            constructor(**{key: value for key, value in payload.items() if key != name})
        with pytest.raises(ValueError, match="^invalid_input$"):
            constructor(**(payload | {name: object()}))
    with pytest.raises(TypeError):
        constructor(**payload, unallocated_payload="synthetic")


@pytest.mark.parametrize("union", UNIONS)
def test_ct01_closed_union_members(union):
    assert set(get_args(getattr(c, union))) == {
        _constructor(union, tag) for tag in UNIONS[union]
    }


@pytest.mark.parametrize(
    "union,tag,field_names", VARIANTS, ids=[f"{u}-{t}" for u, t, _ in VARIANTS]
)
def test_ct01_every_tagged_constructor_and_required_fields(
    union, tag, field_names, core_values
):
    constructor = _constructor(union, tag)
    payload = {"tag": tag} | {name: core_values[name] for name in field_names.split()}
    if tag == "audit_target":
        payload["partition"] = r.PartitionRefTargetCatalog("target_catalog")
    assert get_type_hints(constructor)["tag"] == Literal[tag]
    _assert_closed_record(constructor, payload)
    with pytest.raises(ValueError, match="^invalid_input$"):
        constructor(**(payload | {"tag": "unallocated_variant"}))


@pytest.mark.parametrize("name,field_names", RECORDS.items(), ids=list(RECORDS))
def test_ct01_direct_records_and_required_nullables(name, field_names, core_values):
    payload = {name: core_values[name] for name in field_names.split()}
    _assert_closed_record(getattr(c, name), payload)


@pytest.mark.parametrize(
    "name,valid,invalid",
    [
        ("ProjectionId", ["p", "p" * 64], ["", "p" * 65, "bad/name", 1]),
        (
            "LocalId",
            ["123456781234423482341234567890ab"],
            [
                "a" * 32,
                "123456781234123482341234567890ab",
                "123456781234423482341234567890AB",
            ],
        ),
        ("ProviderId", ["001", "907", "é" * 256], ["", "x\n", "\0", "é" * 257, 907]),
        ("ProviderPageToken", ["opaque", "p" * 16384], ["", "p" * 16385, "x\0", 3]),
        ("Sha256Hex", ["a" * 64], ["A" * 64, "a" * 63, "z" * 64]),
        ("PolicyVersion", ["v1", "p" * 64], ["", "p" * 65, "V1", "bad/version"]),
    ],
    ids=["projection", "local", "provider", "page", "digest", "policy"],
)
def test_ct02_primitive_boundaries(name, valid, invalid):
    constructor = getattr(c, name)
    for value in valid:
        assert constructor(value).value == value
    for value in invalid:
        with pytest.raises(ValueError, match="^invalid_input$"):
            constructor(value)


@pytest.mark.parametrize("constructor", [c.Count, c.Generation, c.Revision])
def test_ct02_integer_units_reject_bool_and_overflow(constructor):
    for value in (0, 1, 2**63 - 1):
        assert constructor(value).value == value
    for value in (True, False, -1, 1.0, "1"):
        with pytest.raises(ValueError, match="^invalid_input$"):
            constructor(value)
    with pytest.raises(ValueError, match="^consistency_failure$"):
        constructor(2**63)


def test_ct02_clock_utc_and_noncontiguous_provider_keys(gmail_controller, fake_clock):
    source = gmail_controller.service("source")
    gmail_controller.script(
        "source",
        "history.list",
        {"userId": "me", "startHistoryId": "001"},
        {"history": [{"id": "907"}], "historyId": "4007"},
    )
    wire = source.users().history().list(userId="me", startHistoryId="001").execute()
    history = c.ProviderId(wire["history"][0]["id"])
    assert history.value == "907"
    assert c.ProviderId(wire["historyId"]).value == "4007"
    assert c.ProviderId("001").value == "001"
    observed = c.Timestamp(fake_clock.now())
    assert observed.value.utcoffset() == timedelta(0)
    for value in (
        datetime(2026, 1, 1),
        datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1))),
    ):
        with pytest.raises(ValueError):
            c.Timestamp(value)
    assert c.Timestamp(datetime(2026, 1, 1, tzinfo=UTC)).value.year == 2026
    args = (c.ProjectionId("synthetic"), history, c.ProviderId("source-message"))
    added = r.SourceEventKeyMessageAdded("message_added", *args)
    deleted = r.SourceEventKeyMessageDeleted("message_deleted", *args)
    label_added = r.SourceEventKeyLabelChanged(
        "label_changed", *args, c.ProviderId("label"), c.LabelChange.ADDED
    )
    label_removed = replace(label_added, change=c.LabelChange.REMOVED)
    assert len({added, deleted, label_added, label_removed}) == 4
    assert added == r.SourceEventKeyMessageAdded("message_added", *args)
    unresolved = c.SourceEvent(added, observed, None)
    enriched = replace(unresolved, source_thread_id=c.ProviderId("thread"))
    assert enriched.key is unresolved.key


@pytest.mark.parametrize("tag", ["project_message", "repair_message", "expand_thread"])
def test_ct02_job_generation_guards(tag, core_values):
    payload = {name: core_values[name] for name in UNIONS["JobSubject"][tag].split()}
    constructor = _constructor("JobSubject", tag)
    assert constructor(tag=tag, **payload).generation.value == 1
    with pytest.raises(ValueError):
        constructor(tag=tag, **(payload | {"generation": c.Generation(0)}))


def test_ct02_tracked_guard_and_claim_nullable_generation(core_values):
    with pytest.raises(ValueError):
        r.ThreadGenerationGuardTracked("tracked", c.Generation(0))
    guard = r.ThreadGenerationGuardTracked("tracked", c.Generation(1))
    assert guard.generation.value == 1
    assert r.ThreadGenerationGuardUntracked("untracked").tag == "untracked"
    claim = c.Claim(**{key: core_values[key] for key in RECORDS["Claim"].split()})
    assert claim.thread_generation is None
    assert (
        replace(claim, thread_generation=guard.generation).thread_generation
        is guard.generation
    )


@pytest.mark.parametrize(
    "job_tag,allowed",
    [
        ("scan_discovery", {"source_window"}),
        ("scan_gap", {"source_window", "source_thread"}),
        ("reconcile_source", {"source_window", "source_thread"}),
        ("audit_target", {"target_catalog", "mapped_target_set"}),
    ],
)
def test_ct02_job_partition_guards(job_tag, allowed, core_values):
    for tag, names in UNIONS["PartitionRef"].items():
        partition = _constructor("PartitionRef", tag)(
            tag=tag, **{n: core_values[n] for n in names.split()}
        )
        constructor = _constructor("JobSubject", job_tag)
        if tag in allowed:
            assert (
                constructor(job_tag, core_values["epoch_id"], partition).partition
                is partition
            )
        else:
            with pytest.raises(ValueError):
                constructor(job_tag, core_values["epoch_id"], partition)


@pytest.mark.parametrize("tag", UNIONS["PartitionRef"])
def test_ct02_progress_cursor_and_state_guards(tag, core_values):
    partition = _constructor("PartitionRef", tag)(
        tag=tag, **{n: core_values[n] for n in UNIONS["PartitionRef"][tag].split()}
    )
    base = c.PartitionProgress(
        partition, c.PartitionState.NOT_STARTED, c.Count(0), c.Count(0), None, None
    )
    assert base.partition is partition
    token = c.ProviderPageToken("synthetic-page-token")
    after = c.ProviderId("synthetic-after-message")
    for changes in (
        {"completed_pages": c.Count(1)},
        {"observed_items": c.Count(1)},
        {"page_token": token},
        {"after_source_message_id": after},
    ):
        with pytest.raises(ValueError):
            replace(base, **changes)
    scanning = replace(base, state=c.PartitionState.SCANNING)
    for field, value, allowed in (
        ("page_token", token, {"source_window", "target_catalog"}),
        ("after_source_message_id", after, {"mapped_target_set"}),
    ):
        if tag in allowed:
            assert getattr(replace(scanning, **{field: value}), field) is value
        else:
            with pytest.raises(ValueError):
                replace(scanning, **{field: value})
    with pytest.raises(ValueError):
        replace(scanning, state=c.PartitionState.COMPLETE, page_token=token)


def test_ct03_actual_metadata_two_privacy_layers(core_values):
    event = c.SourceEvent(
        core_values["key"], core_values["observed_at"], core_values["source_thread_id"]
    )
    subject = r.JobSubjectOperationRead(
        "operation_read", core_values["operation_id"], c.ReadTaskKind.DOCTOR_LIVE
    )
    claim = c.Claim(**{key: core_values[key] for key in RECORDS["Claim"].split()})
    rule = core_values["rule"]
    # Explicit test-owned inspection buffer, NOT a production DB/DTO serializer.
    metadata = " ".join(
        (
            event.key.source_message_id.value,
            rule.rule_id.value,
            subject.operation_id.value,
            claim.owner_run_id.value,
            claim.phase.value,
        )
    )
    private_markers = tuple(
        Marker(MarkerKind.METADATA, value)
        for value in (event.key.source_message_id.value, rule.rule_id.value)
    )
    assert_private_boundary(metadata, private_markers, Profile.METADATA)
    assert_private_boundary(metadata, private_markers, Profile.PRIVATE_CLI)
    with pytest.raises(AssertionError, match="metadata"):
        assert_private_boundary(metadata, private_markers, Profile.PUBLIC)
    for marker in markers():
        if marker.kind is MarkerKind.METADATA:
            continue
        for profile in (Profile.METADATA, Profile.PRIVATE_CLI, Profile.PUBLIC):
            with pytest.raises(AssertionError):
                assert_private_boundary(metadata + marker.value, (marker,), profile)
    assert_private_boundary(
        c.ErrorCode.INSERT_RESULT_UNKNOWN.value,
        private_markers + markers(),
        Profile.PUBLIC,
    )


def test_ct04_fault_callbacks_hold_real_selectors_without_transition_or_trace_leaks(
    core_values, fake_faults, fake_clock
):
    recovery = r.JobSubjectRecoverInsert("recover_insert", core_values["attempt_id"])
    read = r.JobSubjectOperationRead(
        "operation_read", core_values["operation_id"], c.ReadTaskKind.RECOVERY_PREVIEW
    )
    guard = r.ThreadGenerationGuardTracked("tracked", core_values["generation"])
    claim = c.Claim(**{key: core_values[key] for key in RECORDS["Claim"].split()})
    axes = (
        c.JobState.BLOCKED,
        c.InsertState.PENDING_RECOVERY,
        c.OutcomeCertainty.UNKNOWN,
    )
    assert tuple(type(axis) for axis in axes) == (
        c.JobState,
        c.InsertState,
        c.OutcomeCertainty,
    )
    selectors = (recovery, read, guard, claim, axes)
    observed = []

    def hold_actual_values():
        observed.append(selectors)

    fake_faults.at("dispatch.before_guard", repeat=2, callback=hold_actual_values)
    fake_faults.at("provider.before_execute", repeat=2)
    transport = TransportFactory(fake_clock).new()
    failures = []
    for _ in range(2):
        fake_faults.hit("dispatch.before_guard")
        with pytest.raises(InjectedFailure) as error, transport.call("messages.get"):
            fake_faults.hit("provider.before_execute")
        failures.append(str(error.value))
    assert len(observed) == 2 and all(value is selectors for value in observed)
    assert recovery.attempt_id is core_values["attempt_id"]
    assert read.operation_id is core_values["operation_id"]
    assert guard.generation is core_values["generation"]
    assert claim.thread_generation is None
    assert axes == (
        c.JobState.BLOCKED,
        c.InsertState.PENDING_RECOVERY,
        c.OutcomeCertainty.UNKNOWN,
    )
    assert [
        v.occurrence for v in fake_faults.visits() if v.hook == "dispatch.before_guard"
    ] == [1, 2]
    assert [call.status for call in transport.calls()] == ["failed", "failed"]
    evidence = repr((fake_faults.visits(), transport.calls(), failures))
    private = (Marker(MarkerKind.METADATA, recovery.attempt_id.value),) + markers()
    assert_private_boundary(evidence, private, Profile.LOG)
    assert_private_boundary(evidence, private, Profile.PUBLIC)
    with pytest.raises(AssertionError):
        assert_private_boundary(
            evidence + recovery.attempt_id.value, private, Profile.PUBLIC
        )
    fake_faults.assert_consumed()
    # These were helper exceptions, not process crashes, SQL commits or recovery.
