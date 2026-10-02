"""JM01-JM06: fixed same-value transport, separate from actual getter proofs."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta, tzinfo

import pytest
from db_view_job_values import JobMaterializationFailure, pack_job, unpack_job
from test_db_repositories import T, ready_test_metadata, view
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
    Count,
    ErrorCode,
    Generation,
    JobKind,
    JobState,
    LabelChange,
    Priority,
    ProjectionId,
    ProviderId,
    ReadTaskKind,
    Revision,
    SourceEvent,
    Timestamp,
)
from facet.contracts import records as r
from facet.db.codecs import (
    MAX_TIMESTAMP,
    MIN_TIMESTAMP,
    EventProcessing,
    KeyBytes,
    PageLimit,
)
from facet.db.keys import event_key, job_key
from facet.db.models import SourceEventRow, SyncJobRow
from facet.db.repositories import jobs
from facet.db.repositories.base import _insert


def sample(subject, n=601):
    return SyncJobRow(
        P,
        lid(n),
        JobKind(subject.tag),
        Count(1),
        job_key(P, subject),
        Priority.REALTIME,
        JobState.QUEUED,
        Revision(7),
        Timestamp(datetime(1960, 1, 1, tzinfo=UTC)),
        NOW,
        Timestamp(NOW.value + timedelta(minutes=1)),
        Count(9),
        ErrorCode.NETWORK_UNAVAILABLE,
        lid(701),
        subject,
    )


SUBJECTS = (
    r.JobSubjectProjectMessage(
        "project_message", ProviderId("message"), T, Generation(2)
    ),
    r.JobSubjectRepairMessage(
        "repair_message", lid(71), ProviderId("message"), T, Generation(3)
    ),
    r.JobSubjectExpandThread("expand_thread", T, lid(72), Generation(4)),
    r.JobSubjectResolveEvent(
        "resolve_event",
        r.SourceEventKeyMessageAdded(
            "message_added", P, ProviderId("history"), ProviderId("message")
        ),
    ),
    r.JobSubjectResolveEvent(
        "resolve_event",
        r.SourceEventKeyMessageDeleted(
            "message_deleted", P, ProviderId("history"), ProviderId("message")
        ),
    ),
    r.JobSubjectResolveEvent(
        "resolve_event",
        r.SourceEventKeyLabelChanged(
            "label_changed",
            P,
            ProviderId("history"),
            ProviderId("message"),
            ProviderId("label"),
            LabelChange.ADDED,
        ),
    ),
    r.JobSubjectResolveEvent(
        "resolve_event",
        r.SourceEventKeyLabelChanged(
            "label_changed",
            P,
            ProviderId("history"),
            ProviderId("message"),
            ProviderId("label"),
            LabelChange.REMOVED,
        ),
    ),
    r.JobSubjectOperationRead("operation_read", lid(73), ReadTaskKind.GAP_PREVIEW),
    r.JobSubjectRecoverInsert("recover_insert", lid(74)),
    r.JobSubjectScanDiscovery(
        "scan_discovery", lid(75), r.PartitionRefSourceWindow("source_window")
    ),
    r.JobSubjectScanGap(
        "scan_gap", lid(76), r.PartitionRefSourceThread("source_thread", T)
    ),
    r.JobSubjectScanGap(
        "scan_gap", lid(77), r.PartitionRefSourceWindow("source_window")
    ),
    r.JobSubjectReconcileSource(
        "reconcile_source", lid(78), r.PartitionRefSourceThread("source_thread", T)
    ),
    r.JobSubjectReconcileSource(
        "reconcile_source", lid(79), r.PartitionRefSourceWindow("source_window")
    ),
    r.JobSubjectAuditTarget(
        "audit_target", lid(80), r.PartitionRefTargetCatalog("target_catalog")
    ),
    r.JobSubjectAuditTarget(
        "audit_target", lid(81), r.PartitionRefMappedTargetSet("mapped_target_set")
    ),
    r.JobSubjectCleanupAction("cleanup_action", lid(82)),
)


@pytest.mark.parametrize("subject", SUBJECTS)
def test_all_closed_subject_event_partition_values_round_trip_without_sql(subject):
    row = sample(subject)
    assert unpack_job(pack_job(row), P) == row


def test_independent_positional_vector_keeps_every_field_and_null_distinction():
    subject = r.JobSubjectCleanupAction("cleanup_action", lid(82))
    row = sample(subject)
    # Literal frame (registered job/projection/kind/action ID), not pack output reused
    # as the expected grammar. Private SQL companion IDs are never represented.
    frame = (
        b"facet-key-v1\x00\x00\x00\x00\x03job"
        b"\x00\x00\x00\x14synthetic-projection"
        b"\x00\x00\x00\x0ecleanup_action\x00\x00\x00\x20"
        b"00000000000040008000000000000052"
    )
    assert frame == row.stable_key.value
    vector = [
        1,
        "synthetic-projection",
        "00000000000040008000000000000259",
        "cleanup_action",
        1,
        frame.hex(),
        "realtime",
        "queued",
        7,
        -315619200000000,
        1790899200000000,
        1790899260000000,
        9,
        "network_unavailable",
        "000000000000400080000000000002bd",
        ["cleanup_action", "00000000000040008000000000000052"],
    ]
    assert pack_job(row) == vector and unpack_job(vector, P) == row
    absent = replace(
        row, next_attempt_at=None, last_error_code=None, origin_epoch_id=None
    )
    nullable = pack_job(absent)
    assert nullable[11] is nullable[13] is nullable[14] is None
    assert unpack_job(nullable, P) == absent


@pytest.mark.parametrize("key", [subject.event_key for subject in SUBJECTS[3:7]])
def test_actual_isolated_resolve_getter_materializes_validated_companion_not_fake_id(
    state, key
):
    _, connection, session, _ = state
    ready_test_metadata(connection, session)
    local_event_id = lid(501)
    selected = SourceEventRow(
        P,
        local_event_id,
        event_key(P, key),
        SourceEvent(key, NOW, T),
        EventProcessing.PENDING,
        Revision(0),
        None,
    )
    row = replace(
        sample(r.JobSubjectResolveEvent("resolve_event", key)),
        revision=Revision(0),
        created_at=NOW,
        updated_at=NOW,
        next_attempt_at=None,
        attempt_count=Count(0),
        last_error_code=None,
        origin_epoch_id=None,
    )
    assert local_event_id != row.job_id
    assert local_event_id.value not in {
        key.history_record_id.value,
        key.source_message_id.value,
    }
    with session.transaction() as uow:
        _insert(uow, P, "source_events", selected)
        jobs.enqueue(uow, P, row)
    with view(state) as probe:
        assert probe.get_event(P, local_event_id) == selected
        assert probe.get_job(P, row.job_id) == row
        page = probe.list_jobs(P, PageLimit(2), None)
        assert page.items == (row,) and page.next_key is None


@pytest.mark.parametrize(
    "index,bad",
    [
        (0, True),
        (0, 2),
        (1, "invalid projection"),
        (2, "not-a-uuid"),
        (3, "repair_message"),
        (4, 2),
        (4, True),
        (5, "aa"),
        (5, " AA"),
        (5, "1"),
        (5, "a" * 16386),
        (6, "unregistered"),
        (7, "unregistered"),
        (8, True),
        (8, 1.5),
        (8, 1 << 63),
        (8, -1),
        (9, MIN_TIMESTAMP - 1),
        (9, False),
        (10, MAX_TIMESTAMP + 1),
        (11, "0"),
        (12, False),
        (12, -1),
        (13, "private error"),
        (14, "private origin"),
        (15, ["cleanup_action"]),
        (15, ["unregistered", "private"]),
    ],
)
def test_corrupted_closed_job_cells_refuse_fixed_without_private_output(
    index, bad, capsys
):
    value = pack_job(sample(SUBJECTS[-1]))
    value[index] = bad
    with pytest.raises(JobMaterializationFailure) as error:
        unpack_job(value, P)
    assert str(error.value) == "test_job_materialization_failed"
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("bad", [[], [1], {}, None])
def test_exact_list_and_arity_reject_before_constructor(bad):
    with pytest.raises(JobMaterializationFailure):
        unpack_job(bad, P)


def test_subject_generation_partition_tag_and_event_projection_guards_are_preserved():
    values = []
    for row, index, replacement in (
        (sample(SUBJECTS[0]), 3, 0),
        (sample(SUBJECTS[9]), 2, ["target_catalog"]),
        (sample(SUBJECTS[10]), 2, ["mapped_target_set"]),
        (sample(SUBJECTS[14]), 2, ["source_window"]),
    ):
        value = pack_job(row)
        value[15][index] = replacement
        values.append(value)
    foreign_event = pack_job(sample(SUBJECTS[3]))
    foreign_event[15][1][1] = "foreign-projection"
    values.append(foreign_event)
    for value in values:
        with pytest.raises(JobMaterializationFailure):
            unpack_job(value, P)
    with pytest.raises(JobMaterializationFailure):
        unpack_job(pack_job(sample(SUBJECTS[0])), ProjectionId("other"))


def test_subclass_hostile_forged_nested_values_and_timezone_do_not_execute_hooks():
    class Foreign:
        @property
        def value(self):
            raise AssertionError("foreign property")

        def __repr__(self):
            raise AssertionError("foreign repr")

    class PrivateZone(tzinfo):
        def utcoffset(self, value):
            raise AssertionError("foreign timezone")

    class Array(list):
        def __len__(self):
            raise AssertionError("foreign length")

    class Row(SyncJobRow):
        pass

    with pytest.raises(JobMaterializationFailure):
        unpack_job(Array(), P)
    for value in (Foreign(), object.__new__(SyncJobRow), object.__new__(Row)):
        with pytest.raises(JobMaterializationFailure):
            pack_job(value)
    row = sample(SUBJECTS[0])
    for field in ("job_id", "subject", "stable_key", "created_at"):
        forged = deepcopy(row)
        object.__setattr__(forged, field, Foreign())
        with pytest.raises(JobMaterializationFailure):
            pack_job(forged)
    forged = deepcopy(row)
    stamp = object.__new__(Timestamp)
    object.__setattr__(stamp, "value", datetime(2026, 1, 1, tzinfo=PrivateZone()))
    object.__setattr__(forged, "created_at", stamp)
    with pytest.raises(JobMaterializationFailure):
        pack_job(forged)
    # The helper is not a SQL codec and must not accept a KeyBytes/raw row as a job.
    with pytest.raises(JobMaterializationFailure):
        pack_job(KeyBytes(b"valid-bytes"))
