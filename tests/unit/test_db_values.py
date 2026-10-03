"""DB-01/02/05: closed scalars and identities, independent of a DB connection."""

import dataclasses
import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from typing import get_type_hints

import pytest

from facet.contracts import (
    Count,
    ErrorCode,
    Generation,
    LabelChange,
    LocalId,
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
    PartitionRefSourceThread,
    PartitionRefSourceWindow,
    PartitionRefTargetCatalog,
    SourceEventKeyLabelChanged,
    SourceEventKeyMessageAdded,
)
from facet.db import models
from facet.db.codecs import (
    MAX_TIMESTAMP,
    MIN_TIMESTAMP,
    KeyBytes,
    MigrationName,
    PageLimit,
    PrivateAddress,
    RfcMessageId,
    RuleValue,
    SchemaVersion,
    StorageFailure,
    encode_scalar,
    next_revision,
    sqlite_failure,
    timestamp_from_sql,
    timestamp_to_sql,
)
from facet.db.keys import (
    _frame,
    _parse_read_key,
    _read_key,
    event_key,
    expansion_digest,
    job_key,
    partition_key,
)

P = ProjectionId("synthetic")
L = LocalId("00000000000040008000000000000001")
V = ProviderId("synthetic-provider-id")


@pytest.mark.parametrize("us", [MIN_TIMESTAMP, MAX_TIMESTAMP, -1, 0, 1, -1000001])
def test_timestamp_round_trip_exact(us):
    assert timestamp_to_sql(timestamp_from_sql(us)) == us


@pytest.mark.parametrize(
    "bad", [True, 1.5, MIN_TIMESTAMP - 1, MAX_TIMESTAMP + 1, "secret"]
)
def test_timestamp_bad_values_are_fixed(bad):
    with pytest.raises(StorageFailure, match="^consistency_failure$") as raised:
        timestamp_from_sql(bad)
    assert "secret" not in repr(raised.value)


@pytest.mark.parametrize(
    "codec,good,bad",
    [
        (PrivateAddress, "synthetic@example.invalid", "secret\x00address"),
        (RuleValue, "example.invalid", "secret\x85rule"),
        (RfcMessageId, "<synthetic@example.invalid>", "secret\ud800id"),
        (SchemaVersion, 1, True),
        (MigrationName, "v0001", "secret migration"),
        (PageLimit, 500, 501),
        (KeyBytes, b"x", b""),
    ],
)
def test_storage_scalar_limits_and_private_repr(codec, good, bad):
    value = codec(good)
    assert "value=" not in repr(value)
    if type(good) is str:
        assert good not in repr(value)
    with pytest.raises(StorageFailure, match="^invalid_input$"):
        codec(bad)


def test_bool_is_not_count_or_page_and_overflow_is_not_wraparound():
    for bad in (True, 0, -1):
        with pytest.raises(StorageFailure):
            PageLimit(bad)
    with pytest.raises(StorageFailure, match="^consistency_failure$"):
        next_revision(Revision(2**63 - 1))
    assert next_revision(Revision(0)) == Revision(1)


def test_unknown_enum_or_arbitrary_value_is_not_a_scalar_serializer():
    class Unregistered(StrEnum):
        SECRET = "secret unregistered enum"

    class Secret:
        value = "secret arbitrary value"

    for value in (Unregistered.SECRET, Secret(), {}, object(), "secret", 1):
        with pytest.raises(StorageFailure, match="^invalid_input$"):
            encode_scalar(value)
    assert encode_scalar(Count(3)) == 3
    assert encode_scalar(True) == 1
    assert encode_scalar(Timestamp(datetime(1970, 1, 1, tzinfo=UTC))) == 0


def test_fixed_exception_never_contains_sql_or_provider_message():
    error = sqlite3.IntegrityError("private SQL or provider sentinel")
    mapped = sqlite_failure(error)
    assert str(mapped) == "persistence_failure"
    assert "private" not in repr(mapped)
    assert str(StorageFailure("private")) == "consistency_failure"


def test_key_framing_is_collision_safe_and_utf8_exact():
    assert _frame(("é",)) == b"facet-key-v1\0\x00\x00\x00\x02\xc3\xa9"
    assert _frame(("a", "bc")) != _frame(("ab", "c"))
    assert _frame(("a:b",)) != _frame(("a", "b"))


def test_event_keys_use_all_opaque_identity_facts():
    args = (
        "label_changed",
        P,
        ProviderId("History-Z:not-contiguous"),
        V,
        ProviderId("label"),
    )
    add = SourceEventKeyLabelChanged(*args, LabelChange.ADDED)
    remove = SourceEventKeyLabelChanged(*args, LabelChange.REMOVED)
    assert event_key(P, add) != event_key(P, remove)
    with pytest.raises(StorageFailure):
        event_key(ProjectionId("different"), add)


def test_all_eleven_job_keys_and_generation_variants():
    event = SourceEventKeyMessageAdded("message_added", P, ProviderId("h-z"), V)
    window = PartitionRefSourceWindow("source_window")
    thread = PartitionRefSourceThread("source_thread", V)
    target = PartitionRefTargetCatalog("target_catalog")
    subjects = (
        JobSubjectProjectMessage("project_message", V, V, Generation(1)),
        JobSubjectRepairMessage("repair_message", L, V, V, Generation(1)),
        JobSubjectExpandThread("expand_thread", V, L, Generation(1)),
        JobSubjectResolveEvent("resolve_event", event),
        JobSubjectOperationRead("operation_read", L, ReadTaskKind.THREAD_PREVIEW),
        JobSubjectRecoverInsert("recover_insert", L),
        JobSubjectScanDiscovery("scan_discovery", L, window),
        JobSubjectScanGap("scan_gap", L, thread),
        JobSubjectReconcileSource("reconcile_source", L, window),
        JobSubjectAuditTarget("audit_target", L, target),
        JobSubjectCleanupAction("cleanup_action", L),
    )
    assert len({job_key(P, s).value for s in subjects}) == 11
    assert job_key(P, subjects[0]) != job_key(
        P, dataclasses.replace(subjects[0], generation=Generation(10))
    )
    # Read-kind is a conflict check, not a second operation identity.
    assert job_key(P, subjects[4]) == job_key(
        P, dataclasses.replace(subjects[4], read_kind=ReadTaskKind.DOCTOR_LIVE)
    )
    assert partition_key(P, window) != partition_key(P, thread)


def test_expansion_digest_is_set_and_utf8_sorted_metadata_only():
    a, b = ProviderId("é"), ProviderId("a")
    assert expansion_digest((a, b, a)) == expansion_digest((b, a))
    assert expansion_digest(()) != expansion_digest((a,))


def test_registered_read_cursor_has_exact_table_projection_and_signed_time():
    key = _read_key("sync_jobs", P, -1, L)
    assert _parse_read_key("sync_jobs", P, key) == (-1, L.value)
    for table, projection, raw in (
        ("source_events", P, key),
        ("sync_jobs", ProjectionId("other"), key),
        ("sync_jobs", P, key[:-1]),
        ("sync_jobs", P, b"private-token"),
        ("sync_jobs", P, _frame(("read.sync_jobs", P.value, "-01", L.value))),
    ):
        with pytest.raises(StorageFailure, match="^invalid_input$"):
            _parse_read_key(table, projection, raw)


def test_row_inventory_is_closed_required_nullable_and_immutable():
    assert len(models._ROW_TYPES) == 32
    for cls in models._ROW_TYPES:
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen
        assert not cls.__dataclass_params__.repr
        hints = get_type_hints(cls)
        for field in dataclasses.fields(cls):
            assert field.name in hints
            assert field.default is dataclasses.MISSING
            assert field.default_factory is dataclasses.MISSING
    with pytest.raises(TypeError):
        models.OwnerSessionInfo(L, L)
    with pytest.raises(StorageFailure):
        models.OwnerSessionInfo(L, L, "private")
    with pytest.raises(StorageFailure):
        models.WriteReceipt("anything", L, Revision(0))
    assert models.WriteReceipt("created", P, Revision(0)).object_id == P
    assert StorageFailure(ErrorCode.INVALID_INPUT).code is ErrorCode.INVALID_INPUT


def test_key_entries_refuse_foreign_projection_before_property_access():
    class Foreign:
        @property
        def value(self):
            pytest.fail("foreign private value property was accessed")

    key = SourceEventKeyMessageAdded("message_added", P, V, V)
    partition = PartitionRefSourceWindow("source_window")
    subject = JobSubjectProjectMessage("project_message", V, V, Generation(1))
    for foreign in (Foreign(), "private", None):
        for action in (
            lambda foreign=foreign: event_key(foreign, key),
            lambda foreign=foreign: partition_key(foreign, partition),
            lambda foreign=foreign: job_key(foreign, subject),
            lambda foreign=foreign: _read_key("sync_jobs", foreign, 0, L),
            lambda foreign=foreign: _parse_read_key(
                "sync_jobs", foreign, _read_key("sync_jobs", P, 0, L)
            ),
        ):
            with pytest.raises(StorageFailure, match="^invalid_input$"):
                action()


@pytest.mark.parametrize("bad", [MIN_TIMESTAMP - 1, MAX_TIMESTAMP + 1, True])
def test_read_key_rejects_out_of_range_time(bad):
    with pytest.raises(StorageFailure, match="^invalid_input$"):
        _read_key("sync_jobs", P, bad, L)


def test_read_key_never_accepts_unknown_table_or_unbounded_frame():
    for table in ("unregistered", "private", None, 1, []):
        with pytest.raises(StorageFailure, match="^invalid_input$"):
            _read_key(table, P, 0, L)
        with pytest.raises(StorageFailure, match="^invalid_input$"):
            _parse_read_key(
                table, P, _frame(("read.unregistered", P.value, "0", L.value))
            )
    for key in (
        b"x" * 8193,
        b"",
        b"private",
        _frame(("read.unregistered", P.value, "0", L.value)),
    ):
        with pytest.raises(StorageFailure, match="^invalid_input$"):
            models.ReadPage((), key)
    good = _read_key("sync_jobs", P, 0, L)
    assert models.ReadPage((), good).next_key == good


def test_read_page_is_homogeneous_and_cursor_family_is_checked():
    projection = models.ProjectionRow(
        P,
        Count(1),
        L,
        L,
        Revision(0),
        Revision(0),
        models.SourceMode.READONLY,
        models.BindingState.VERIFICATION_PENDING,
        models.RestoreState.NORMAL,
        True,
        None,
        Timestamp(datetime(2026, 1, 1, tzinfo=UTC)),
    )
    schema = models.SchemaMetadataRow(
        Count(1), SchemaVersion(1), models.Sha256Hex("a" * 64), projection.created_at
    )
    with pytest.raises(StorageFailure):
        models.ReadPage((projection, schema), None)
    with pytest.raises(StorageFailure):
        models.ReadPage((projection,), _read_key("sync_jobs", P, 0, L))
