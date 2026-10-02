"""Test-only same-value jobs; never SQL rows, provider facts or product IPC."""

import re
from datetime import UTC, datetime

from facet.contracts import (
    Count,
    ErrorCode,
    Generation,
    JobKind,
    JobState,
    LabelChange,
    LocalId,
    Priority,
    ProjectionId,
    ProviderId,
    ReadTaskKind,
    Revision,
    Timestamp,
)
from facet.contracts.records import (
    JobSubjectAuditTarget,
    JobSubjectCleanupAction,
    JobSubjectExpandThread,
    JobSubjectOperationRead,
    JobSubjectProjectMessage,
    JobSubjectReconcileSource,
    JobSubjectRecoverInsert,
    JobSubjectRepairMessage,
    JobSubjectResolveEvent,
    JobSubjectScanDiscovery,
    JobSubjectScanGap,
    PartitionRefMappedTargetSet,
    PartitionRefSourceThread,
    PartitionRefSourceWindow,
    PartitionRefTargetCatalog,
    SourceEventKeyLabelChanged,
    SourceEventKeyMessageAdded,
    SourceEventKeyMessageDeleted,
)
from facet.db.codecs import (
    MAX_TIMESTAMP,
    MIN_TIMESTAMP,
    KeyBytes,
    StorageFailure,
    timestamp_from_sql,
    timestamp_to_sql,
)
from facet.db.models import SyncJobRow


class JobMaterializationFailure(Exception):
    def __init__(self):
        super().__init__("test_job_materialization_failed")


def _fail():
    raise JobMaterializationFailure()


def _length(value, size):
    if type(value) is not list or len(value) != size:
        _fail()


def _scalar(value, cls):
    # Only statically selected primitive classes reach this helper.
    primitive = int if cls in {Count, Generation, Revision} else str
    if type(value) is not primitive:
        _fail()
    return cls(value)


def _value(value, cls):
    if type(value) is not cls:
        _fail()
    return _scalar(value.value, cls).value


def _enum(value, cls):
    if type(value) is not str:
        _fail()
    return cls(value)


def _enum_value(value, cls):
    if type(value) is not cls:
        _fail()
    return _enum(value.value, cls).value


def _time(value):
    if type(value) is not int or not MIN_TIMESTAMP <= value <= MAX_TIMESTAMP:
        _fail()
    return timestamp_from_sql(value)


def _time_value(value):
    if (
        type(value) is not Timestamp
        or type(value.value) is not datetime
        or value.value.tzinfo is not UTC
    ):
        _fail()
    result = timestamp_to_sql(value)
    _time(result)
    return result


def _hex(value):
    if (
        type(value) is not str
        or re.fullmatch(r"(?:[0-9a-f]{2}){1,8192}", value) is None
    ):
        _fail()
    return KeyBytes(bytes.fromhex(value))


def _hex_value(value):
    if type(value) is not KeyBytes or type(value.value) is not bytes:
        _fail()
    return _hex(value.value.hex()).value.hex()


def _tag(value, expected):
    if type(value.tag) is not str or value.tag != expected:
        _fail()


def _pack_event(value):
    cls = type(value)
    if cls is SourceEventKeyMessageAdded:
        _tag(value, "message_added")
        result = ["message_added"]
    elif cls is SourceEventKeyMessageDeleted:
        _tag(value, "message_deleted")
        result = ["message_deleted"]
    elif cls is SourceEventKeyLabelChanged:
        _tag(value, "label_changed")
        result = ["label_changed"]
    else:
        _fail()
    result.extend(
        [
            _value(value.projection_id, ProjectionId),
            _value(value.history_record_id, ProviderId),
            _value(value.source_message_id, ProviderId),
        ]
    )
    if cls is SourceEventKeyLabelChanged:
        result.extend(
            [_value(value.label_id, ProviderId), _enum_value(value.change, LabelChange)]
        )
    return result


def _unpack_event(value):
    if type(value) is not list or not value or type(value[0]) is not str:
        _fail()
    tag = value[0]
    if tag in {"message_added", "message_deleted"}:
        _length(value, 4)
        p, history, message = (
            _scalar(value[1], ProjectionId),
            _scalar(value[2], ProviderId),
            _scalar(value[3], ProviderId),
        )
        if tag == "message_added":
            return SourceEventKeyMessageAdded(tag, p, history, message)
        return SourceEventKeyMessageDeleted(tag, p, history, message)
    if tag == "label_changed":
        _length(value, 6)
        return SourceEventKeyLabelChanged(
            tag,
            _scalar(value[1], ProjectionId),
            _scalar(value[2], ProviderId),
            _scalar(value[3], ProviderId),
            _scalar(value[4], ProviderId),
            _enum(value[5], LabelChange),
        )
    _fail()


def _pack_partition(value):
    cls = type(value)
    if cls is PartitionRefSourceWindow:
        _tag(value, "source_window")
        return ["source_window"]
    if cls is PartitionRefSourceThread:
        _tag(value, "source_thread")
        return ["source_thread", _value(value.source_thread_id, ProviderId)]
    if cls is PartitionRefTargetCatalog:
        _tag(value, "target_catalog")
        return ["target_catalog"]
    if cls is PartitionRefMappedTargetSet:
        _tag(value, "mapped_target_set")
        return ["mapped_target_set"]
    _fail()


def _unpack_partition(value):
    if type(value) is not list or not value or type(value[0]) is not str:
        _fail()
    if value[0] == "source_thread":
        _length(value, 2)
        return PartitionRefSourceThread("source_thread", _scalar(value[1], ProviderId))
    _length(value, 1)
    if value[0] == "source_window":
        return PartitionRefSourceWindow("source_window")
    if value[0] == "target_catalog":
        return PartitionRefTargetCatalog("target_catalog")
    if value[0] == "mapped_target_set":
        return PartitionRefMappedTargetSet("mapped_target_set")
    _fail()


def _pack_subject(value):
    cls = type(value)
    if cls is JobSubjectProjectMessage:
        _tag(value, "project_message")
        return [
            "project_message",
            _value(value.source_message_id, ProviderId),
            _value(value.source_thread_id, ProviderId),
            _value(value.generation, Generation),
        ]
    if cls is JobSubjectRepairMessage:
        _tag(value, "repair_message")
        return [
            "repair_message",
            _value(value.repair_operation_id, LocalId),
            _value(value.source_message_id, ProviderId),
            _value(value.source_thread_id, ProviderId),
            _value(value.generation, Generation),
        ]
    if cls is JobSubjectExpandThread:
        _tag(value, "expand_thread")
        return [
            "expand_thread",
            _value(value.source_thread_id, ProviderId),
            _value(value.epoch_id, LocalId),
            _value(value.generation, Generation),
        ]
    if cls is JobSubjectResolveEvent:
        _tag(value, "resolve_event")
        return ["resolve_event", _pack_event(value.event_key)]
    if cls is JobSubjectOperationRead:
        _tag(value, "operation_read")
        return [
            "operation_read",
            _value(value.operation_id, LocalId),
            _enum_value(value.read_kind, ReadTaskKind),
        ]
    if cls is JobSubjectRecoverInsert:
        _tag(value, "recover_insert")
        return ["recover_insert", _value(value.attempt_id, LocalId)]
    if cls is JobSubjectScanDiscovery:
        _tag(value, "scan_discovery")
        return [
            "scan_discovery",
            _value(value.epoch_id, LocalId),
            _pack_partition(value.partition),
        ]
    if cls is JobSubjectScanGap:
        _tag(value, "scan_gap")
        return [
            "scan_gap",
            _value(value.epoch_id, LocalId),
            _pack_partition(value.partition),
        ]
    if cls is JobSubjectReconcileSource:
        _tag(value, "reconcile_source")
        return [
            "reconcile_source",
            _value(value.epoch_id, LocalId),
            _pack_partition(value.partition),
        ]
    if cls is JobSubjectAuditTarget:
        _tag(value, "audit_target")
        return [
            "audit_target",
            _value(value.epoch_id, LocalId),
            _pack_partition(value.partition),
        ]
    if cls is JobSubjectCleanupAction:
        _tag(value, "cleanup_action")
        return ["cleanup_action", _value(value.action_command_id, LocalId)]
    _fail()


def _unpack_subject(value):
    if type(value) is not list or not value or type(value[0]) is not str:
        _fail()
    tag = value[0]
    if tag == "project_message":
        _length(value, 4)
        return JobSubjectProjectMessage(
            tag,
            _scalar(value[1], ProviderId),
            _scalar(value[2], ProviderId),
            _scalar(value[3], Generation),
        )
    if tag == "repair_message":
        _length(value, 5)
        return JobSubjectRepairMessage(
            tag,
            _scalar(value[1], LocalId),
            _scalar(value[2], ProviderId),
            _scalar(value[3], ProviderId),
            _scalar(value[4], Generation),
        )
    if tag == "expand_thread":
        _length(value, 4)
        return JobSubjectExpandThread(
            tag,
            _scalar(value[1], ProviderId),
            _scalar(value[2], LocalId),
            _scalar(value[3], Generation),
        )
    if tag == "resolve_event":
        _length(value, 2)
        return JobSubjectResolveEvent(tag, _unpack_event(value[1]))
    if tag == "operation_read":
        _length(value, 3)
        return JobSubjectOperationRead(
            tag, _scalar(value[1], LocalId), _enum(value[2], ReadTaskKind)
        )
    if tag == "recover_insert":
        _length(value, 2)
        return JobSubjectRecoverInsert(tag, _scalar(value[1], LocalId))
    if tag in {"scan_discovery", "scan_gap", "reconcile_source", "audit_target"}:
        _length(value, 3)
        epoch, partition = _scalar(value[1], LocalId), _unpack_partition(value[2])
        if tag == "scan_discovery":
            return JobSubjectScanDiscovery(tag, epoch, partition)
        if tag == "scan_gap":
            return JobSubjectScanGap(tag, epoch, partition)
        if tag == "reconcile_source":
            return JobSubjectReconcileSource(tag, epoch, partition)
        return JobSubjectAuditTarget(tag, epoch, partition)
    if tag == "cleanup_action":
        _length(value, 2)
        return JobSubjectCleanupAction(tag, _scalar(value[1], LocalId))
    _fail()


def pack_job(row):
    try:
        if type(row) is not SyncJobRow:
            _fail()
        result = [
            1,
            _value(row.projection_id, ProjectionId),
            _value(row.job_id, LocalId),
            _enum_value(row.kind, JobKind),
            _value(row.key_version, Count),
            _hex_value(row.stable_key),
            _enum_value(row.priority, Priority),
            _enum_value(row.state, JobState),
            _value(row.revision, Revision),
            _time_value(row.created_at),
            _time_value(row.updated_at),
            _time_value(row.next_attempt_at)
            if row.next_attempt_at is not None
            else None,
            _value(row.attempt_count, Count),
            _enum_value(row.last_error_code, ErrorCode)
            if row.last_error_code is not None
            else None,
            _value(row.origin_epoch_id, LocalId)
            if row.origin_epoch_id is not None
            else None,
            _pack_subject(row.subject),
        ]
        unpack_job(result, row.projection_id)
        return result
    except (ValueError, TypeError, AttributeError, OverflowError, StorageFailure):
        raise JobMaterializationFailure() from None


def unpack_job(value, expected_projection):
    try:
        _length(value, 16)
        if type(value[0]) is not int or value[0] != 1:
            _fail()
        if type(expected_projection) is not ProjectionId:
            _fail()
        expected = _scalar(expected_projection.value, ProjectionId)
        row = SyncJobRow(
            _scalar(value[1], ProjectionId),
            _scalar(value[2], LocalId),
            _enum(value[3], JobKind),
            _scalar(value[4], Count),
            _hex(value[5]),
            _enum(value[6], Priority),
            _enum(value[7], JobState),
            _scalar(value[8], Revision),
            _time(value[9]),
            _time(value[10]),
            _time(value[11]) if value[11] is not None else None,
            _scalar(value[12], Count),
            _enum(value[13], ErrorCode) if value[13] is not None else None,
            _scalar(value[14], LocalId) if value[14] is not None else None,
            _unpack_subject(value[15]),
        )
        if row.projection_id != expected or (
            type(row.subject) is JobSubjectResolveEvent
            and row.subject.event_key.projection_id != expected
        ):
            _fail()
        return row
    except (ValueError, TypeError, AttributeError, OverflowError, StorageFailure):
        raise JobMaterializationFailure() from None
