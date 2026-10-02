"""DB-12: factual audits of a test-owned previously verified mapping.

The fixture seeds the verified relationship using private SQL after the actual
result producer. It is NOT evidence that verify_mapping or Gmail readback ran.
"""

import sqlite3
from contextlib import suppress
from dataclasses import replace
from datetime import timedelta

import pytest
from test_db_repositories import state as state
from test_db_repositories import view
from test_db_results import known, ready, record
from test_db_schema import NOW, P

from facet.contracts import (
    ErrorCode,
    PolicyVersion,
    ProjectionId,
    ProviderId,
    Revision,
    Sha256Hex,
    Timestamp,
    Visibility,
)
from facet.db.codecs import StorageFailure
from facet.db.connection import _attach_writer
from facet.db.models import (
    MappingHistoryRow,
    MessageMappingRow,
    RevisionGuard,
    TargetOwnershipRow,
    ThreadTargetRow,
)
from facet.db.repositories import mappings, reads
from facet.db.repositories.base import _insert


def verified_fixture(state):
    _, _, session, _ = state
    original, _, _, old = ready(state)
    inserted = replace(
        known(old),
        semantic_digest=Sha256Hex("b" * 64),
        semantic_version=PolicyVersion("synthetic-mime-v1"),
        visibility=Visibility.NORMAL,
    )
    record(state, inserted)
    mapping = MessageMappingRow(
        P,
        old.source_message_id,
        old.source_thread_id,
        Revision(1),
        old.attempt_id,
        inserted.target_message_id,
        inserted.target_thread_id,
        NOW,
        Visibility.NORMAL,
        None,
        None,
    )
    with session.transaction() as uow:
        uow._execute(
            "UPDATE insert_attempts SET state='verified',verified_at=?,revision=3 "
            "WHERE projection_id=? AND attempt_id=?",
            (int(NOW.value.timestamp() * 1_000_000), P.value, old.attempt_id.value),
        )
        _insert(
            uow,
            P,
            "mapping_history",
            MappingHistoryRow(
                P,
                old.source_message_id,
                Revision(1),
                old.source_thread_id,
                old.attempt_id,
                inserted.target_message_id,
                inserted.target_thread_id,
                NOW,
                None,
            ),
        )
        _insert(uow, P, "message_mappings", mapping)
        _insert(
            uow,
            P,
            "target_ownership",
            TargetOwnershipRow(
                P,
                inserted.target_message_id,
                old.source_message_id,
                old.attempt_id,
                NOW,
            ),
        )
        _insert(
            uow,
            P,
            "thread_targets",
            ThreadTargetRow(
                P,
                old.source_thread_id,
                inserted.target_thread_id,
                True,
                old.attempt_id,
                NOW,
            ),
        )
        uow._execute(
            "DELETE FROM job_claims WHERE projection_id=? AND job_id=?",
            (P.value, original.job_id.value),
        )
        uow._execute(
            "UPDATE sync_jobs SET state='completed',revision=revision+1 "
            "WHERE projection_id=? AND job_id=?",
            (P.value, original.job_id.value),
        )
    return mapping


def audit(
    state, mapping, *, present=True, visibility=Visibility.NORMAL, at=NOW, guard=None
):
    with state[2].transaction() as uow:
        return mappings.record_target_audit(
            uow,
            P,
            mapping.source_message_id,
            present,
            visibility,
            at,
            RevisionGuard(guard or mapping.mapping_revision),
        )


@pytest.mark.parametrize("present", [True, False])
@pytest.mark.parametrize("visibility", list(Visibility))
def test_audit_is_fact_only_and_exact_replay_has_zero_writes(
    state, present, visibility
):
    value = verified_fixture(state)
    _, connection, _, _ = state
    with view(state) as reader:
        old_attempt = reads.get_attempt(reader, P, value.attempt_id)
        old_counts = reads.counts(reader, P, None)
    receipt = audit(state, value, present=present, visibility=visibility)
    assert receipt.object_id == value.source_message_id
    assert (
        receipt.revision == value.mapping_revision and receipt.disposition == "updated"
    )
    before = connection.total_changes
    assert (
        audit(state, value, present=present, visibility=visibility).disposition
        == "replayed"
    )
    assert connection.total_changes == before
    with view(state) as reader:
        actual = reads.get_mapping(reader, P, value.source_message_id)
        assert actual == replace(
            value, target_present=present, visibility=visibility, last_audit_at=NOW
        )
        assert reads.get_attempt(reader, P, value.attempt_id) == old_attempt
        assert reads.counts(reader, P, None) == old_counts
    assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (1,)
    assert connection.execute("SELECT COUNT(*) FROM insert_attempts").fetchone() == (1,)
    assert connection.execute("SELECT COUNT(*) FROM mapping_history").fetchone() == (1,)


def test_audit_monotonic_time_and_mapping_revision_guards_survive_reopen(state):
    value = verified_fixture(state)
    later = Timestamp(NOW.value + timedelta(seconds=1))
    audit(state, value, present=False, visibility=Visibility.UNKNOWN, at=later)
    with pytest.raises(StorageFailure):
        audit(state, value)
    with pytest.raises(StorageFailure):
        audit(state, value, at=later, guard=Revision(0))
    path, _, session, info = state
    session.close()
    connection = sqlite3.connect(path, autocommit=True)
    reopened = _attach_writer(connection, info)
    try:
        other = path, connection, reopened, info
        with view(other) as reader:
            actual = reads.get_mapping(reader, P, value.source_message_id)
        assert actual.target_present is False and actual.last_audit_at == later
        assert actual.mapping_revision == Revision(1)
        before = connection.total_changes
        assert (
            audit(
                other, value, present=False, visibility=Visibility.UNKNOWN, at=later
            ).disposition
            == "replayed"
        )
        assert connection.total_changes == before
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "arguments",
    [
        ("synthetic-source-msg", True, Visibility.NORMAL, NOW),
        (ProviderId("synthetic-source-msg"), 1, Visibility.NORMAL, NOW),
        (ProviderId("synthetic-source-msg"), True, "normal", NOW),
        (ProviderId("synthetic-source-msg"), True, Visibility.NORMAL, NOW.value),
    ],
)
def test_typed_audit_arguments_refuse_and_poison_the_owned_uow(state, arguments):
    value = verified_fixture(state)
    with pytest.raises(StorageFailure), state[2].transaction() as uow:
        mappings.record_target_audit(
            uow,
            P,
            value.source_message_id,
            False,
            Visibility.TRASH,
            NOW,
            RevisionGuard(Revision(1)),
        )
        with suppress(StorageFailure):
            mappings.record_target_audit(uow, P, *arguments, RevisionGuard(Revision(1)))
    with view(state) as reader:
        assert reads.get_mapping(reader, P, value.source_message_id) == value


@pytest.mark.parametrize("projection", [P, ProjectionId("another-projection")])
def test_missing_or_other_projection_mapping_is_not_adopted(state, projection):
    verified_fixture(state)
    with pytest.raises(StorageFailure), state[2].transaction() as uow:
        mappings.record_target_audit(
            uow,
            projection,
            ProviderId("missing-message"),
            False,
            Visibility.UNKNOWN,
            NOW,
            RevisionGuard(Revision(1)),
        )
    assert state[1].execute("SELECT COUNT(*) FROM message_mappings").fetchone() == (1,)


def test_actual_after_update_abort_rolls_back_facts_and_preserves_verified_mapping(
    state,
):
    value = verified_fixture(state)
    state[1].execute(
        "CREATE TEMP TRIGGER audit_failure AFTER UPDATE ON message_mappings "
        "BEGIN SELECT RAISE(ABORT,'SYNTHETIC_PRIVATE_SQL_SENTINEL'); END"
    )
    with (
        pytest.raises(StorageFailure) as caught,
        state[2].transaction() as uow,
        suppress(StorageFailure),
    ):
        mappings.record_target_audit(
            uow,
            P,
            value.source_message_id,
            False,
            Visibility.UNKNOWN,
            NOW,
            RevisionGuard(Revision(1)),
        )
    assert caught.value.code is ErrorCode.CONSISTENCY_FAILURE
    assert "SYNTHETIC_PRIVATE_SQL_SENTINEL" not in str(caught.value)
    with view(state) as reader:
        assert reads.get_mapping(reader, P, value.source_message_id) == value
    assert state[1].execute("PRAGMA integrity_check").fetchone() == ("ok",)
