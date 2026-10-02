"""Versioned closed metadata identities; never a general persistence serializer."""

import hashlib
import struct
from typing import get_args

from facet.contracts import (
    ErrorCode,
    JobSubject,
    LocalId,
    PartitionRef,
    ProjectionId,
    ProviderId,
    Sha256Hex,
    SourceEventKey,
)

from .codecs import KeyBytes, StorageFailure, invalid

_PREFIX = b"facet-key-v1\x00"


def _frame(components: tuple[str, ...]) -> bytes:
    parts = [_PREFIX]
    for component in components:
        if type(component) is not str:
            invalid()
        raw = component.encode("utf-8")
        parts.extend((struct.pack(">I", len(raw)), raw))
    return b"".join(parts)


def _event_components(key: SourceEventKey, projection: ProjectionId) -> tuple[str, ...]:
    from facet.contracts.records import SourceEventKey as Registered

    if type(key) not in get_args(Registered) or key.projection_id != projection:
        invalid()
    parts = (key.tag, key.history_record_id.value, key.source_message_id.value)
    if key.tag == "label_changed":
        parts += (key.label_id.value, key.change.value)
    return parts


def _partition_components(partition: PartitionRef) -> tuple[str, ...]:
    from facet.contracts.records import PartitionRef as Registered

    if type(partition) not in get_args(Registered):
        invalid()
    if partition.tag == "source_thread":
        return (partition.tag, partition.source_thread_id.value)
    return (partition.tag,)


def event_key(projection: ProjectionId, key: SourceEventKey) -> KeyBytes:
    return KeyBytes(
        _frame(("event", projection.value) + _event_components(key, projection))
    )


def partition_key(projection: ProjectionId, partition: PartitionRef) -> KeyBytes:
    return KeyBytes(
        _frame(("partition", projection.value) + _partition_components(partition))
    )


def job_key(projection: ProjectionId, subject: JobSubject) -> KeyBytes:
    from facet.contracts.records import JobSubject as Registered

    if type(projection) is not ProjectionId or type(subject) not in get_args(
        Registered
    ):
        invalid()
    tag = subject.tag
    if tag == "project_message":
        parts = (subject.source_message_id.value, str(subject.generation.value))
    elif tag == "repair_message":
        parts = (
            subject.repair_operation_id.value,
            subject.source_message_id.value,
            str(subject.generation.value),
        )
    elif tag == "expand_thread":
        parts = (
            subject.source_thread_id.value,
            subject.epoch_id.value,
            str(subject.generation.value),
        )
    elif tag == "resolve_event":
        parts = _event_components(subject.event_key, projection)
    elif tag == "operation_read":
        parts = (subject.operation_id.value,)
    elif tag == "recover_insert":
        parts = (subject.attempt_id.value,)
    elif tag in {"scan_discovery", "scan_gap", "reconcile_source", "audit_target"}:
        parts = (subject.epoch_id.value,) + _partition_components(subject.partition)
    elif tag == "cleanup_action":
        parts = (subject.action_command_id.value,)
    else:
        invalid()
    return KeyBytes(_frame(("job", projection.value, tag) + parts))


def expansion_digest(ids: tuple[ProviderId, ...]) -> Sha256Hex:
    if type(ids) is not tuple or any(type(i) is not ProviderId for i in ids):
        invalid()
    values = sorted({i.value for i in ids}, key=lambda s: s.encode("utf-8"))
    return Sha256Hex(
        hashlib.sha256(_frame(("expansion-snapshot-v1", *values))).hexdigest()
    )


def _unframe(value: bytes) -> tuple[str, ...]:
    if (
        type(value) is not bytes
        or not 1 <= len(value) <= 8192
        or not value.startswith(_PREFIX)
    ):
        invalid()
    parts = []
    offset = len(_PREFIX)
    try:
        while offset < len(value):
            if offset + 4 > len(value):
                invalid()
            length = struct.unpack_from(">I", value, offset)[0]
            offset += 4
            if length == 0 or offset + length > len(value):
                invalid()
            parts.append(value[offset : offset + length].decode("utf-8"))
            offset += length
    except (UnicodeError, struct.error):
        raise StorageFailure(ErrorCode.INVALID_INPUT) from None
    return tuple(parts)


_READ_TABLES = frozenset(
    {"sync_jobs", "insert_attempts", "source_events", "audit_events"}
)


def _read_key(
    table: str, projection: ProjectionId, timestamp: int, id: LocalId
) -> bytes:
    if (
        table not in _READ_TABLES
        or type(timestamp) is not int
        or type(id) is not LocalId
    ):
        invalid()
    return _frame(("read." + table, projection.value, str(timestamp), id.value))


def _parse_read_key(
    table: str, projection: ProjectionId, value: bytes
) -> tuple[int, str]:
    from .codecs import timestamp_from_sql

    parts = _unframe(value)
    if len(parts) != 4 or parts[:2] != ("read." + table, projection.value):
        invalid()
    try:
        timestamp = int(parts[2])
        if str(timestamp) != parts[2]:
            invalid()
        timestamp_from_sql(timestamp)
        id = LocalId(parts[3])
    except (ValueError, StorageFailure):
        raise StorageFailure(ErrorCode.INVALID_INPUT) from None
    return timestamp, id.value
