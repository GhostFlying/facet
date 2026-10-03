"""Closed row codec coverage. Relational authorization is separately real-DB tested."""

from dataclasses import fields, replace
from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints

import pytest
from test_db_repositories import T, job
from test_db_schema import NOW, P, lid

from facet import contracts as c
from facet.contracts import records as core
from facet.db import codecs
from facet.db.keys import event_key, partition_key
from facet.db.repositories.serialization import ROW_CLASSES, _decode_row, _encode_row


def scalar(annotation):
    if get_origin(annotation) is UnionType and type(None) in get_args(annotation):
        return None
    if get_origin(annotation) is Literal:
        return get_args(annotation)[0]
    values = {
        c.Count: c.Count(0),
        c.Generation: c.Generation(1),
        c.Revision: c.Revision(0),
        c.LocalId: lid(100),
        c.ProjectionId: P,
        c.ProviderId: T,
        c.PolicyVersion: c.PolicyVersion("synthetic-v1"),
        c.Sha256Hex: c.Sha256Hex("a" * 64),
        c.Timestamp: NOW,
        codecs.SchemaVersion: codecs.SchemaVersion(1),
        codecs.MigrationName: codecs.MigrationName("v0001"),
        codecs.PrivateAddress: codecs.PrivateAddress("synthetic@example.invalid"),
        codecs.RuleValue: codecs.RuleValue("example.invalid"),
        bool: False,
    }
    if annotation in values:
        return values[annotation]
    return next(iter(annotation))


def allocated_row(table):
    cls = ROW_CLASSES[table]
    if table == "sync_jobs":
        return job(100)
    overrides = {}
    if table == "thread_admissions":
        overrides["admission"] = core.AdmissionRefFutureRule(
            "future_rule",
            c.RuleRef(lid(10), c.Revision(1)),
            c.PolicyVersion("synthetic-v1"),
        )
    if table == "epochs":
        overrides.update(
            kind=c.EpochKind.TARGET_AUDIT,
            decision=core.EpochDecisionRefScheduledTargetAudit(
                "scheduled_target_audit"
            ),
        )
    if table == "source_events":
        key = core.SourceEventKeyMessageAdded("message_added", P, T, T)
        overrides.update(event=c.SourceEvent(key, NOW, T), event_key=event_key(P, key))
    if table == "epoch_partitions":
        ref = core.PartitionRefSourceWindow("source_window")
        overrides.update(
            partition_key=partition_key(P, ref),
            progress=c.PartitionProgress(
                ref, c.PartitionState.NOT_STARTED, c.Count(0), c.Count(0), None, None
            ),
        )
    if table == "job_claims":
        overrides["claim"] = c.Claim(
            lid(200), lid(1), NOW, None, c.Revision(1), c.ClaimPhase.PREPARING
        )
    if table == "audit_events":
        overrides.update(
            kind=codecs.AuditKind.JOB_STATE_CHANGED,
            object_kind=codecs.AuditObjectKind.JOB,
            local_object_id=lid(100),
        )
    hints = get_type_hints(cls)
    return cls(
        **{
            f.name: overrides[f.name] if f.name in overrides else scalar(hints[f.name])
            for f in fields(cls)
        }
    )


@pytest.mark.parametrize("table", tuple(ROW_CLASSES))
def test_all_32_closed_row_families_sql_roundtrip(table):
    value = allocated_row(table)
    assert _decode_row(table, _encode_row(table, value)) == value


@pytest.mark.parametrize(
    "tag", ["initial_backfill", "future_rule", "manual_thread", "action_label"]
)
def test_admission_union_sql_roundtrip_all_branches(tag):
    values = {
        "initial_backfill": core.AdmissionRefInitialBackfill(
            "initial_backfill",
            lid(50),
            c.RuleRef(lid(10), c.Revision(1)),
            c.PolicyVersion("synthetic-v1"),
        ),
        "future_rule": core.AdmissionRefFutureRule(
            "future_rule",
            c.RuleRef(lid(10), c.Revision(1)),
            c.PolicyVersion("synthetic-v1"),
        ),
        "manual_thread": core.AdmissionRefManualThread("manual_thread", lid(50)),
        "action_label": core.AdmissionRefActionLabel("action_label", lid(50)),
    }
    row = replace(allocated_row("thread_admissions"), admission=values[tag])
    assert (
        _decode_row("thread_admissions", _encode_row("thread_admissions", row)) == row
    )


def test_foreign_objects_and_bad_sql_rows_only_emit_controlled_failure():
    marker = "PRIVATE_PROVIDER_EXCEPTION_SENTINEL"
    for args in [("rules", {"normalized_value": marker}), (marker, object())]:
        with pytest.raises(codecs.StorageFailure) as error:
            _encode_row(*args)
        assert marker not in str(error.value) + repr(error.value)
    row = allocated_row("projections")
    bad = list(_encode_row("projections", row))
    bad[6] = marker  # source_mode closed enum
    with pytest.raises(codecs.StorageFailure, match="consistency_failure") as error:
        _decode_row("projections", tuple(bad))
    assert marker not in str(error.value) + repr(error.value)
