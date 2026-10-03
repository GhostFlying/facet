"""Private closed row/SQL codec. Not an export or arbitrary dictionary writer."""

from dataclasses import fields
from types import UnionType
from typing import get_args, get_origin, get_type_hints

from facet.contracts import (
    Claim,
    ErrorCode,
    LocalId,
    PartitionProgress,
    ProviderId,
    Revision,
    RuleRef,
    SourceEvent,
)
from facet.contracts import records as core

from .. import models
from ..codecs import (
    KeyBytes,
    StorageFailure,
    encode_scalar,
    invalid,
    timestamp_from_sql,
)
from ..keys import partition_key
from ..migrations.v0001 import _SUBJECT_FIELDS, TABLES

ROW_CLASSES = {
    "schema_metadata": models.SchemaMetadataRow,
    "schema_migrations": models.SchemaMigrationRow,
    "projections": models.ProjectionRow,
    "bindings": models.BindingRow,
    "binding_revisions": models.BindingRevisionRow,
    "credential_changes": models.CredentialChangeRow,
    "rules": models.RuleRow,
    "rule_revisions": models.RuleRevisionRow,
    "rulesets": models.RulesetRow,
    "ruleset_members": models.RulesetMemberRow,
    "tracked_threads": models.TrackedThreadRow,
    "thread_admissions": models.ThreadAdmissionRow,
    "epochs": models.EpochRow,
    "history_gaps": models.HistoryGapRow,
    "epoch_partitions": models.EpochPartitionRow,
    "source_events": models.SourceEventRow,
    "history_checkpoints": models.HistoryCheckpointRow,
    "history_polls": models.HistoryPollRow,
    "history_pages": models.HistoryPageRow,
    "history_page_events": models.HistoryPageEventRow,
    "sync_jobs": models.SyncJobRow,
    "epoch_jobs": models.EpochJobRow,
    "job_claims": models.JobClaimRow,
    "insert_attempts": models.InsertAttemptRow,
    "message_mappings": models.MessageMappingRow,
    "mapping_history": models.MappingHistoryRow,
    "target_ownership": models.TargetOwnershipRow,
    "thread_targets": models.ThreadTargetRow,
    "action_commands": models.ActionCommandRow,
    "error_events": models.ErrorEventRow,
    "audit_events": models.AuditEventRow,
    "thread_expansion_runs": models.ThreadExpansionRunRow,
    "thread_expansion_items": models.ThreadExpansionItemRow,
}
COLUMNS = {table.name: tuple(c[0] for c in table.columns) for table in TABLES}
COLUMNS["credential_changes"] = (
    "projection_id",
    "state_instance_id",
    "change_id",
    "role",
    "kind",
    "phase",
    "old_revision",
    "new_revision",
    "binding_revision",
    "scope_policy_revision",
    "operation_id",
    "supersedes_change_id",
    "envelope_digest",
    "scope_policy",
    "grant_kind",
    "granted_scopes",
    "grant_parent_revision",
    "grant_observed_at",
    "profile_verified_at",
    "expires_at",
    "started_at",
    "updated_at",
    "error",
)
_ADMISSION_FIELDS = (
    "tag",
    "epoch_id",
    "rule_id",
    "rule_revision",
    "policy_version",
    "preview_id",
    "action_command_id",
)
_DECISION_FIELDS = ("tag", "operation_id", "preview_id", "ruleset_revision")
_EVENT_FIELDS = (
    "tag",
    "history_record_id",
    "source_message_id",
    "label_id",
    "change",
    "observed_at",
    "source_thread_id",
)
_PARTITION_FIELDS = (
    "tag",
    "source_thread_id",
    "state",
    "completed_pages",
    "observed_items",
    "page_token",
    "after_source_message_id",
)
_CLAIM_FIELDS = (
    "claim_id",
    "owner_run_id",
    "acquired_at",
    "thread_generation",
    "job_revision",
    "phase",
)


def _empty(fields):
    return dict.fromkeys(fields)


def _flatten_union(value, names):
    result = _empty(names)
    for field in fields(value):
        item = getattr(value, field.name)
        if field.name == "rule":
            result["rule_id"] = item.rule_id
            result["rule_revision"] = item.revision
        else:
            result[field.name] = item
    return result


def _encode_row(table: str, row, *, event_id: LocalId | None = None) -> tuple:
    if table not in ROW_CLASSES or type(row) is not ROW_CLASSES[table]:
        invalid()
    values = {f.name: getattr(row, f.name) for f in fields(row)}
    if table == "thread_admissions":
        values.update(_flatten_union(values.pop("admission"), _ADMISSION_FIELDS))
    elif table == "epochs":
        values.update(_flatten_union(values.pop("decision"), _DECISION_FIELDS))
    elif table == "source_events":
        event = values.pop("event")
        values.update(_flatten_union(event.key, _EVENT_FIELDS))
        values["observed_at"] = event.observed_at
        values["source_thread_id"] = event.source_thread_id
    elif table == "epoch_partitions":
        progress = values.pop("progress")
        values.update(_flatten_union(progress.partition, _PARTITION_FIELDS))
        values.update(
            {
                f.name: getattr(progress, f.name)
                for f in fields(progress)
                if f.name != "partition"
            }
        )
    elif table == "job_claims":
        values.update(_flatten_union(values.pop("claim"), _CLAIM_FIELDS))
    elif table == "sync_jobs":
        subject = values.pop("subject")
        values.update(_empty(_SUBJECT_FIELDS))
        for field in fields(subject):
            item = getattr(subject, field.name)
            if field.name == "tag":
                continue
            if field.name == "event_key":
                if type(event_id) is not LocalId:
                    invalid()
                values["event_id"] = event_id
            elif field.name == "epoch_id":
                values["subject_epoch_id"] = item
            elif field.name == "partition":
                values["partition_epoch_id"] = subject.epoch_id
                values["partition_key"] = partition_key(row.projection_id, item)
            else:
                values[field.name] = item
    result = []
    for column in COLUMNS[table]:
        item = values[column]
        if (
            column
            in {
                "tag",
                "before_state",
                "after_state",
                "kind",
                "phase",
                "scope_policy",
                "grant_kind",
                "granted_scopes",
            }
            and type(item) is str
        ):
            result.append(item)
        else:
            result.append(encode_scalar(item))
    return tuple(result)


def _scalar_from_sql(value, annotation):
    if get_origin(annotation) is UnionType:
        choices = get_args(annotation)
        if value is None and type(None) in choices:
            return None
        annotation = next(a for a in choices if a is not type(None))
    if annotation is bool:
        if type(value) is not int or value not in {0, 1}:
            raise ValueError("consistency_failure")
        return bool(value)
    if annotation is models.Timestamp:
        return timestamp_from_sql(value)
    return annotation(value)


def _construct_union(tag, variants, values):
    cls = variants.get(tag)
    if cls is None:
        raise ValueError("consistency_failure")
    hints = get_type_hints(cls)
    result = {"tag": tag}
    for field in fields(cls):
        if field.name == "tag":
            continue
        if field.name == "rule":
            result["rule"] = RuleRef(
                LocalId(values["rule_id"]), Revision(values["rule_revision"])
            )
        else:
            result[field.name] = _scalar_from_sql(values[field.name], hints[field.name])
    return cls(**result)


_ADMISSIONS = {
    "initial_backfill": core.AdmissionRefInitialBackfill,
    "future_rule": core.AdmissionRefFutureRule,
    "manual_thread": core.AdmissionRefManualThread,
    "action_label": core.AdmissionRefActionLabel,
}
_DECISIONS = {
    "backfill_start": core.EpochDecisionRefBackfillStart,
    "gap_approval": core.EpochDecisionRefGapApproval,
    "scheduled_reconcile": core.EpochDecisionRefScheduledReconcile,
    "requested_reconcile": core.EpochDecisionRefRequestedReconcile,
    "scheduled_target_audit": core.EpochDecisionRefScheduledTargetAudit,
    "requested_target_audit": core.EpochDecisionRefRequestedTargetAudit,
}
_PARTITIONS = {
    "source_window": core.PartitionRefSourceWindow,
    "source_thread": core.PartitionRefSourceThread,
    "target_catalog": core.PartitionRefTargetCatalog,
    "mapped_target_set": core.PartitionRefMappedTargetSet,
}
_EVENTS = {
    "message_added": core.SourceEventKeyMessageAdded,
    "message_deleted": core.SourceEventKeyMessageDeleted,
    "label_changed": core.SourceEventKeyLabelChanged,
}
_JOBS = {
    "project_message": core.JobSubjectProjectMessage,
    "repair_message": core.JobSubjectRepairMessage,
    "expand_thread": core.JobSubjectExpandThread,
    "resolve_event": core.JobSubjectResolveEvent,
    "operation_read": core.JobSubjectOperationRead,
    "recover_insert": core.JobSubjectRecoverInsert,
    "scan_discovery": core.JobSubjectScanDiscovery,
    "scan_gap": core.JobSubjectScanGap,
    "reconcile_source": core.JobSubjectReconcileSource,
    "audit_target": core.JobSubjectAuditTarget,
    "cleanup_action": core.JobSubjectCleanupAction,
}


def _decode_row(table: str, sql_values: tuple, *, event=None, partition=None):
    if table not in ROW_CLASSES or type(sql_values) is not tuple:
        invalid()
    if len(sql_values) != len(COLUMNS[table]):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    values = dict(zip(COLUMNS[table], sql_values, strict=True))
    cls = ROW_CLASSES[table]
    hints = get_type_hints(cls)
    decoded = {}
    try:
        if table == "thread_admissions":
            decoded["admission"] = _construct_union(values["tag"], _ADMISSIONS, values)
        elif table == "epochs":
            decoded["decision"] = _construct_union(values["tag"], _DECISIONS, values)
        elif table == "source_events":
            key = _construct_union(values["tag"], _EVENTS, values)
            decoded["event"] = SourceEvent(
                key,
                timestamp_from_sql(values["observed_at"]),
                None
                if values["source_thread_id"] is None
                else ProviderId(values["source_thread_id"]),
            )
        elif table == "epoch_partitions":
            p = _construct_union(values["tag"], _PARTITIONS, values)
            kwargs = {"partition": p}
            for name, hint in get_type_hints(PartitionProgress).items():
                if name != "partition":
                    kwargs[name] = _scalar_from_sql(values[name], hint)
            decoded["progress"] = PartitionProgress(**kwargs)
            if KeyBytes(values["partition_key"]) != partition_key(
                models.ProjectionId(values["projection_id"]), p
            ):
                raise ValueError("consistency_failure")
        elif table == "job_claims":
            decoded["claim"] = Claim(
                **{
                    name: _scalar_from_sql(values[name], hint)
                    for name, hint in get_type_hints(Claim).items()
                }
            )
        elif table == "sync_jobs":
            job_cls = _JOBS[values["kind"]]
            kwargs = {"tag": values["kind"]}
            for field in fields(job_cls):
                if field.name == "tag":
                    continue
                if field.name == "event_key":
                    if event is None:
                        raise ValueError("consistency_failure")
                    kwargs[field.name] = event
                elif field.name == "partition":
                    if partition is None:
                        raise ValueError("consistency_failure")
                    kwargs[field.name] = partition
                else:
                    name = (
                        "subject_epoch_id" if field.name == "epoch_id" else field.name
                    )
                    kwargs[field.name] = _scalar_from_sql(
                        values[name], get_type_hints(job_cls)[field.name]
                    )
            decoded["subject"] = job_cls(**kwargs)
        for field in fields(cls):
            if field.name in decoded:
                continue
            hint = hints[field.name]
            if table == "audit_events" and field.name in {
                "before_state",
                "after_state",
            }:
                hint = {
                    "projection": models.BindingState,
                    "epoch": models.EpochState,
                    "job": models.JobState,
                    "attempt": models.InsertState,
                }.get(values["object_kind"])
                decoded[field.name] = (
                    None if values[field.name] is None else hint(values[field.name])
                )
            else:
                decoded[field.name] = _scalar_from_sql(values[field.name], hint)
        return cls(**decoded)
    except (ValueError, TypeError, KeyError, StorageFailure):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None
