"""SI01/02: fixed 37-table manifests, actual SQL constraints and v1 consumers."""

import hashlib
import sqlite3

import pytest
from test_command_bootstrap_storage import expect_fixed, logical, opened, storage
from unit.test_db_schema import create_state, lid

from facet.contracts import ErrorCode
from facet.db.codecs import SchemaVersion, StorageFailure
from facet.db.migration_backup import snapshot_database
from facet.db.migrations import (
    _CURRENT_MANIFEST,
    _EXISTING_STEPS,
    _FRESH_V2_MANIFEST,
    CHECKSUMS,
    FRESH_V2_CHECKSUMS,
    FRESH_V2_REGISTRY,
    FRESH_V2_REGISTRY_DIGEST,
    REGISTRY,
    v0001,
    v0002,
)
from facet.db.schema import _inspect, _inspect_manifest, _inspect_v1


def expect_inspection_code(function, code=None):
    # Existing private schema helpers have no new external error boundary.
    # Their downstream Source A entries separately test sealed caller context.
    with pytest.raises(StorageFailure) as caught:
        function()
    if code is not None:
        assert caught.value.code is code


def test_exact_v1_and_separate_v2_catalogue_ledgers():
    assert REGISTRY == ((1, "v0001", v0001.STATEMENTS),)
    assert _CURRENT_MANIFEST.version == SchemaVersion(1)
    assert _EXISTING_STEPS == ()
    assert FRESH_V2_REGISTRY[:-1] == REGISTRY
    assert FRESH_V2_CHECKSUMS[:-1] == CHECKSUMS
    assert (
        FRESH_V2_CHECKSUMS[-1]
        == hashlib.sha256("\n".join(v0002.STATEMENTS).encode()).hexdigest()
    )
    with storage() as (_, _, connection, _, _, *_):
        _inspect(connection)
        _inspect_manifest(connection, _FRESH_V2_MANIFEST)
        catalogue = connection.execute(
            "SELECT type,name,sql FROM sqlite_schema "
            "WHERE name NOT GLOB 'sqlite_autoindex_*'"
        ).fetchall()
        assert set(catalogue) == set(_FRESH_V2_MANIFEST.catalogue)
        assert len([r for r in catalogue if r[0] == "table"]) == 38
        assert connection.execute(
            "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
        ).fetchall() == list(_FRESH_V2_MANIFEST.ledger)
        assert connection.execute(
            "SELECT registry_digest FROM schema_metadata"
        ).fetchone() == (FRESH_V2_REGISTRY_DIGEST,)
        expect_inspection_code(
            lambda: _inspect_v1(connection), ErrorCode.UNSUPPORTED_VERSION
        )


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE unapproved(value INTEGER)",
        "DROP INDEX operations_listing",
        "DROP TRIGGER operations_identity",
        "PRAGMA user_version=3",
        "PRAGMA user_version=1",
        "PRAGMA application_id=1",
    ],
)
def test_altered_extra_partial_mixed_and_future_catalogues_refuse(sql):
    with storage() as (_, _, connection, _, _, *_):
        connection.execute(sql)
        expect_inspection_code(lambda: _inspect(connection))


@pytest.mark.parametrize(
    "sql,parameters",
    [
        ("UPDATE operations SET request_nonce=?", (lid(90).value,)),
        ("UPDATE operations SET digest=?", ("d" * 64,)),
        ("UPDATE operations SET operation_id=?", (lid(90).value,)),
        ("DELETE FROM operations", ()),
        ("UPDATE operation_bootstrap SET config_semantic_digest=?", ("d" * 64,)),
        ("DELETE FROM operation_bootstrap", ()),
        ("UPDATE command_runtime SET binding_guard=0", ()),
        ("UPDATE command_runtime SET shutdown_phase='requested'", ()),
        ("UPDATE operations SET payload_version=2", ()),
        ("UPDATE operations SET completed_at=NULL", ()),
        ("UPDATE operations SET effect_completed=2", ()),
    ],
)
def test_actual_constraints_keep_receipt_identity_and_rows(sql, parameters):
    with storage() as (_, _, connection, _, _, *_):
        before = logical(connection)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(sql, parameters)
        assert logical(connection) == before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("table", ["operation_controls", "operation_auth"])
def test_real_child_kind_guard_refuses_wrong_family(table):
    with storage() as (_, _, connection, _, _, *_):
        before = logical(connection)
        values = (
            ("synthetic-projection", lid(10).value, 1, 0, 0, 1)
            if table == "operation_controls"
            else ("synthetic-projection", lid(10).value, "source", 0, 1, 0, None)
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                f"INSERT INTO {table} VALUES({','.join('?' for _ in values)})",
                values,
            )
        assert logical(connection) == before


def test_binding_guard_role_change_transaction_and_credential_only_stability():
    with storage() as (_, _, connection, _, _, *_):
        assert connection.execute(
            "SELECT binding_guard FROM command_runtime"
        ).fetchone() == (1,)
        # An unchanged role revision is not a new role publication.
        connection.execute("UPDATE bindings SET binding_revision=binding_revision")
        assert connection.execute(
            "SELECT binding_guard FROM command_runtime"
        ).fetchone() == (1,)
        before = logical(connection)
        connection.execute("BEGIN IMMEDIATE")
        # Matching immutable history is published in the same transaction.
        connection.execute(
            "INSERT INTO binding_revisions SELECT projection_id,role,2,"
            "declared_address,verified_address,state,verified_at FROM bindings "
            "WHERE role='source'"
        )
        connection.execute("UPDATE bindings SET binding_revision=2 WHERE role='source'")
        assert connection.execute(
            "SELECT binding_guard FROM command_runtime"
        ).fetchone() == (2,)
        connection.execute("ROLLBACK")
        assert logical(connection) == before


def test_v2_snapshot_refuses_before_any_destination_setting_or_backup(tmp_path):
    with storage() as (_, _, connection, session, _, *_):
        destination = opened(tmp_path / "destination.db")
        try:
            before = (tmp_path / "destination.db").read_bytes()
            trace = []
            destination.set_trace_callback(trace.append)
            expect_fixed(
                lambda: snapshot_database(session, destination),
                ErrorCode.UNSUPPORTED_VERSION,
            )
            assert trace == []
            assert (tmp_path / "destination.db").read_bytes() == before
            assert sorted(p.name for p in tmp_path.iterdir()) == ["destination.db"]
            assert destination.execute("PRAGMA trusted_schema").fetchone() == (1,)
            assert not connection.in_transaction
        finally:
            destination.close()


def test_v1_attach_inspection_and_native_snapshot_remain_positive(tmp_path):
    connection, session, _ = create_state(tmp_path / "v1.db")
    destination = opened(tmp_path / "snapshot.db")
    try:
        _inspect(connection)
        _inspect_v1(connection)
        result = snapshot_database(session, destination)
        assert result.schema_version == SchemaVersion(1)
        assert logical(destination) == logical(connection)
        assert len(logical(destination)) == 32
    finally:
        destination.close()
        session.close()
