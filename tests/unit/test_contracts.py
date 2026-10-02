import dataclasses
from datetime import UTC, datetime, timedelta, timezone
from typing import get_args
from uuid import uuid4

import pytest

import facet.contracts as core
from facet.contracts import records

PRIMITIVES = {
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
}
ENUMS = {
    "Role",
    "SourceMode",
    "BindingState",
    "RestoreState",
    "RuleOrigin",
    "RuleKind",
    "AdmissionOrigin",
    "EpochKind",
    "EpochState",
    "JobKind",
    "JobState",
    "Priority",
    "InsertState",
    "OutcomeCertainty",
    "Visibility",
    "DatePolicy",
    "OperationState",
    "PreviewPurpose",
    "ErrorClass",
    "ErrorCode",
    "Freshness",
    "PublicPhase",
    "PublicHealth",
    "LabelChange",
    "ReadTaskKind",
    "PartitionState",
    "ClaimPhase",
}
VALUES = {
    "RuleRef",
    "AdmissionRef",
    "EpochDecisionRef",
    "PartitionRef",
    "PartitionProgress",
    "SourceEventKey",
    "SourceEvent",
    "JobSubject",
    "ThreadGenerationGuard",
    "Claim",
}


def local():
    return core.LocalId(uuid4().hex)


def samples():
    r = records
    pid = core.ProviderId("opaque-history-or-message")
    lid = local()
    rule = core.RuleRef(lid, core.Revision(0))
    rev = core.Revision(2)
    policy = core.PolicyVersion("auth-v1")
    window = records.PartitionRefSourceWindow("source_window")
    catalog = records.PartitionRefTargetCatalog("target_catalog")
    key = records.SourceEventKeyMessageAdded(
        "message_added",
        core.ProjectionId("gmail-default"),
        pid,
        pid,
    )
    values = {
        "RuleRef": rule,
        "AdmissionRefInitialBackfill": records.AdmissionRefInitialBackfill(
            "initial_backfill", lid, rule, policy
        ),
        "AdmissionRefFutureRule": records.AdmissionRefFutureRule(
            "future_rule", rule, policy
        ),
        "AdmissionRefManualThread": records.AdmissionRefManualThread(
            "manual_thread", lid
        ),
        "AdmissionRefActionLabel": records.AdmissionRefActionLabel("action_label", lid),
        "EpochDecisionRefBackfillStart": records.EpochDecisionRefBackfillStart(
            "backfill_start", lid, lid, rev
        ),
        "EpochDecisionRefGapApproval": records.EpochDecisionRefGapApproval(
            "gap_approval", lid, lid, rev
        ),
        "EpochDecisionRefScheduledReconcile": r.EpochDecisionRefScheduledReconcile(
            "scheduled_reconcile", rev
        ),
        "EpochDecisionRefRequestedReconcile": r.EpochDecisionRefRequestedReconcile(
            "requested_reconcile", lid, rev
        ),
        "EpochDecisionRefScheduledTargetAudit": r.EpochDecisionRefScheduledTargetAudit(
            "scheduled_target_audit"
        ),
        "EpochDecisionRefRequestedTargetAudit": r.EpochDecisionRefRequestedTargetAudit(
            "requested_target_audit", lid
        ),
        "PartitionRefSourceWindow": window,
        "PartitionRefSourceThread": records.PartitionRefSourceThread(
            "source_thread", pid
        ),
        "PartitionRefTargetCatalog": catalog,
        "PartitionRefMappedTargetSet": records.PartitionRefMappedTargetSet(
            "mapped_target_set"
        ),
        "PartitionProgress": core.PartitionProgress(
            window,
            core.PartitionState.SCANNING,
            core.Count(0),
            core.Count(1),
            core.ProviderPageToken("opaque\npage"),
            None,
        ),
        "SourceEventKeyMessageAdded": key,
        "SourceEventKeyMessageDeleted": records.SourceEventKeyMessageDeleted(
            "message_deleted", core.ProjectionId("gmail-default"), pid, pid
        ),
        "SourceEventKeyLabelChanged": records.SourceEventKeyLabelChanged(
            "label_changed",
            core.ProjectionId("gmail-default"),
            pid,
            pid,
            pid,
            core.LabelChange.ADDED,
        ),
        "SourceEvent": core.SourceEvent(key, core.Timestamp(datetime.now(UTC)), None),
        "JobSubjectProjectMessage": records.JobSubjectProjectMessage(
            "project_message", pid, pid, core.Generation(1)
        ),
        "JobSubjectRepairMessage": records.JobSubjectRepairMessage(
            "repair_message", lid, pid, pid, core.Generation(1)
        ),
        "JobSubjectExpandThread": records.JobSubjectExpandThread(
            "expand_thread", pid, lid, core.Generation(1)
        ),
        "JobSubjectResolveEvent": records.JobSubjectResolveEvent("resolve_event", key),
        "JobSubjectOperationRead": records.JobSubjectOperationRead(
            "operation_read", lid, core.ReadTaskKind.GAP_PREVIEW
        ),
        "JobSubjectRecoverInsert": records.JobSubjectRecoverInsert(
            "recover_insert", lid
        ),
        "JobSubjectScanDiscovery": records.JobSubjectScanDiscovery(
            "scan_discovery", lid, window
        ),
        "JobSubjectScanGap": records.JobSubjectScanGap("scan_gap", lid, window),
        "JobSubjectReconcileSource": records.JobSubjectReconcileSource(
            "reconcile_source", lid, window
        ),
        "JobSubjectAuditTarget": records.JobSubjectAuditTarget(
            "audit_target", lid, catalog
        ),
        "JobSubjectCleanupAction": records.JobSubjectCleanupAction(
            "cleanup_action", lid
        ),
        "ThreadGenerationGuardUntracked": records.ThreadGenerationGuardUntracked(
            "untracked"
        ),
        "ThreadGenerationGuardTracked": records.ThreadGenerationGuardTracked(
            "tracked", core.Generation(1)
        ),
        "Claim": core.Claim(
            lid,
            local(),
            core.Timestamp(datetime.now(UTC)),
            None,
            rev,
            core.ClaimPhase.PREPARING,
        ),
    }
    return values


def test_exact_inventory_and_closed_required_fields():
    assert set(core.__all__) == PRIMITIVES | ENUMS | VALUES
    assert len(core.__all__) == 47
    values = samples()
    expected = set()
    for name in VALUES:
        value_type = getattr(core, name)
        expected.update(
            branch.__name__ for branch in (get_args(value_type) or (value_type,))
        )
    assert set(values) == expected
    for name, value in values.items():
        assert type(value).__name__ == name
        for field in dataclasses.fields(value):
            assert field.default is dataclasses.MISSING
            assert field.default_factory is dataclasses.MISSING
            kwargs = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
            kwargs[field.name] = object()
            with pytest.raises(ValueError, match="^invalid_input$"):
                type(value)(**kwargs)
        with pytest.raises(TypeError):
            type(value)(unknown_field="never allowed")
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, dataclasses.fields(value)[0].name, "forbidden")


@pytest.mark.parametrize("constructor", [core.Count, core.Generation, core.Revision])
@pytest.mark.parametrize("bad", [True, False, -1, 1.0, "1", None, 2**63])
def test_integer_bounds(constructor, bad):
    with pytest.raises(ValueError):
        constructor(bad)
    assert constructor(2**63 - 1).value == 2**63 - 1


@pytest.mark.parametrize(
    "constructor,bad",
    [
        (core.ProjectionId, "../private"),
        (core.ProjectionId, "a" * 65),
        (core.ProjectionId, "é"),
        (core.LocalId, "a" * 32),
        (core.LocalId, uuid4().hex.upper()),
        (core.ProviderId, ""),
        (core.ProviderId, "hidden\nvalue"),
        (core.ProviderId, "é" * 257),
        (core.PolicyVersion, "NOT-version"),
        (core.PolicyVersion, "a" * 65),
        (core.Sha256Hex, "A" * 64),
        (core.Sha256Hex, "a" * 63),
        (core.ProviderPageToken, ""),
        (core.ProviderPageToken, "a" * 16385),
        (core.ProviderPageToken, "opaque\x00token"),
        (core.Timestamp, datetime.now()),
        (core.Timestamp, datetime.now(timezone(timedelta(hours=1)))),
    ],
)
def test_primitive_rejection_is_fixed_and_private(constructor, bad):
    with pytest.raises(ValueError, match="^invalid_input$"):
        constructor(bad)


def test_event_identity_keeps_every_field_and_missing_thread():
    event = samples()["SourceEvent"]
    assert event.source_thread_id is None
    changed = dataclasses.replace(
        event.key, history_record_id=core.ProviderId("not-number")
    )
    assert event.key != changed
    assert len({event.key, changed}) == 2
    label = samples()["SourceEventKeyLabelChanged"]
    assert label != dataclasses.replace(label, change=core.LabelChange.REMOVED)
    assert label != dataclasses.replace(label, label_id=core.ProviderId("other"))
    assert "opaque-history" not in repr(event)
    assert "opaque-history" not in repr(event.key.source_message_id)


def test_generation_guards_and_partition_cross_fields():
    values = samples()
    for name in [
        "JobSubjectProjectMessage",
        "JobSubjectRepairMessage",
        "JobSubjectExpandThread",
        "ThreadGenerationGuardTracked",
    ]:
        with pytest.raises(ValueError):
            dataclasses.replace(values[name], generation=core.Generation(0))
    progress = values["PartitionProgress"]
    for changes in [
        {"state": core.PartitionState.NOT_STARTED},
        {"state": core.PartitionState.COMPLETE},
        {"partition": values["PartitionRefSourceThread"]},
        {"after_source_message_id": core.ProviderId("cursor")},
    ]:
        with pytest.raises(ValueError):
            dataclasses.replace(progress, **changes)
    with pytest.raises(ValueError):
        dataclasses.replace(
            values["JobSubjectScanDiscovery"],
            partition=values["PartitionRefTargetCatalog"],
        )
    with pytest.raises(ValueError):
        dataclasses.replace(
            values["JobSubjectAuditTarget"],
            partition=values["PartitionRefSourceWindow"],
        )


def test_core_import_has_no_runtime_provider_or_storage_dependencies():
    from pathlib import Path

    for path in Path(core.__file__).parent.glob("*.py"):
        text = path.read_text()
        assert "import sqlite" not in text
        assert "import google" not in text
        assert "import facet.config" not in text
        assert "from facet.runtime" not in text
