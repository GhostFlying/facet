"""Finite existing-state migration, not a path opener or maintenance issuer.

Both shipping producer and predecessor inventories remain empty. Exact types,
receipts and schema versions never substitute for real uninterrupted ownership,
no-create preflight or a complete durable config/binding/credential bundle.
"""

import os
import sqlite3
import threading
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from types import FunctionType

from facet.contracts import ErrorCode, LocalId, ProjectionId, Revision, Timestamp

from .codecs import StorageFailure, sqlite_failure, timestamp_to_sql
from .migrations import _CURRENT_MANIFEST, _EXISTING_STEPS, _ExistingStep, v0001
from .models import (
    MigrationBackupReceipt,
    MigrationResult,
    MigrationState,
    OwnerSessionInfo,
)
from .schema import _inspect_manifest

__all__ = ("migrate_existing",)

_MIGRATION_PROVIDER_TYPES: tuple[type, ...] = ()
_REGISTRY_PID = os.getpid()


def _fail(code):
    # Even an enclosing caller exception must not become private error context.
    try:
        raise StorageFailure(code) from None
    except StorageFailure as error:
        error.__cause__ = None
        error.__context__ = None
        raise


def _call(provider, name, *args):
    cls = type(provider)
    if not any(cls is enrolled for enrolled in _MIGRATION_PROVIDER_TYPES):
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
    method = vars(cls).get(name)
    if type(method) is not FunctionType:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if method(provider, *args) is not None:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)


def _manifest(connection):
    application = connection.execute("PRAGMA application_id").fetchone()
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > _CURRENT_MANIFEST.version.value:
        raise StorageFailure(ErrorCode.UNSUPPORTED_VERSION)
    if application != (v0001.APPLICATION_ID,):
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
    if version == _CURRENT_MANIFEST.version.value:
        return _CURRENT_MANIFEST, None
    if type(_EXISTING_STEPS) is not tuple or len(_EXISTING_STEPS) > 1:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if _EXISTING_STEPS:
        step = _EXISTING_STEPS[0]
        if type(step) is not _ExistingStep or step.target != _CURRENT_MANIFEST:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        if version == step.source.version.value:
            return step.source, step
    raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)


def _state(connection, manifest):
    _inspect_manifest(connection, manifest)
    row = connection.execute(
        "SELECT projection_id,state_instance_id,request_namespace,"
        "config_revision,last_owner_run_id FROM projections"
    ).fetchone()
    roles = connection.execute(
        "SELECT role,credential_revision FROM bindings "
        "WHERE projection_id=? ORDER BY role",
        (row[0],),
    ).fetchall()
    if len(roles) != 2 or tuple(role for role, _ in roles) != ("source", "target"):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    return MigrationState(
        ProjectionId(row[0]),
        LocalId(row[1]),
        LocalId(row[2]),
        manifest.version,
        Revision(row[3]),
        Revision(roles[0][1]),
        Revision(roles[1][1]),
        None if row[4] is None else LocalId(row[4]),
    )


def _owner(state, owner):
    if (
        state.state_instance_id != owner.state_instance_id
        or state.request_namespace != owner.request_namespace
    ):
        raise StorageFailure(ErrorCode.REQUEST_LINEAGE_MISMATCH)


def _backup(connection, provider, receipt, state):
    if type(receipt) is not MigrationBackupReceipt:
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
    if (
        receipt.state_instance_id != state.state_instance_id
        or receipt.request_namespace != state.request_namespace
        or receipt.schema_version != state.schema_version
        or receipt.config_revision != state.config_revision
        or receipt.source_credential_revision != state.source_credential_revision
        or receipt.target_credential_revision != state.target_credential_revision
    ):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    _call(provider, "_validate_migration_backup", connection, receipt, state)


def _result(disposition, before, after):
    return MigrationResult(
        disposition,
        before.schema_version,
        after.schema_version,
        after.state_instance_id,
        after.request_namespace,
    )


def _close_uncertain(connection):
    # Exact native connection, one close attempt, never a retry or replacement.
    with suppress(BaseException):
        connection.close()


def migrate_existing(
    connection: sqlite3.Connection,
    owner: OwnerSessionInfo,
    *,
    backup: MigrationBackupReceipt | None,
    provider: object | None,
) -> MigrationResult:
    """Inspect current state or apply one compiled step under a real provider."""
    begin_attempted = False
    attempted_commit = False
    pid, thread = os.getpid(), threading.current_thread()
    code = ErrorCode.CONSISTENCY_FAILURE
    try:
        if (
            type(connection) is not sqlite3.Connection
            or type(owner) is not OwnerSessionInfo
            or (backup is not None and type(backup) is not MigrationBackupReceipt)
        ):
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        if pid != _REGISTRY_PID:
            raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
        # No connection property, provider-instance lookup or SQL precedes this
        # fixed producer's actual creator/enrollment/maintenance ownership check.
        _call(provider, "_check_migration_connection", connection, owner)
        if (
            connection.autocommit is not True
            or connection.in_transaction
            or connection.row_factory is not None
            or connection.text_factory is not str
        ):
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        if sqlite3.sqlite_version_info < (3, 37, 0):
            raise StorageFailure(ErrorCode.UNSUPPORTED_VERSION)
        for name, expected in (
            ("query_only", 0),
            ("journal_mode", "wal"),
            ("foreign_keys", 1),
            ("trusted_schema", 0),
        ):
            if connection.execute(f"PRAGMA {name}").fetchone() != (expected,):
                raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE)
        manifest, step = _manifest(connection)
        before = _state(connection, manifest)
        _owner(before, owner)
        _call(provider, "_check_migration_connection", connection, owner)
        if step is None:
            return _result("unchanged", before, before)
        _backup(connection, provider, backup, before)
        _call(provider, "_check_migration_connection", connection, owner)
        if connection.in_transaction:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        # Native BEGIN can succeed before Python receives its acknowledgement.
        # Arm only after genuine enrollment/backup and the final idle check;
        # refused foreign creators/external UoWs never enter owned cleanup.
        begin_attempted = True
        connection.execute("BEGIN IMMEDIATE")
        if _state(connection, step.source) != before:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        _call(provider, "_check_migration_connection", connection, owner)
        for sql in step.statements:
            connection.execute(sql)
        target = step.target
        # Existing compiled UPDATE guards remain enabled. This singleton has
        # no incoming FK; replace only its version/digest inside the same owned
        # transaction, preserving the actual original creation observation.
        created = connection.execute(
            "SELECT created_at FROM schema_metadata WHERE singleton=1"
        ).fetchall()
        if (
            len(created) != 1
            or connection.execute(
                "DELETE FROM schema_metadata WHERE singleton=1"
            ).rowcount
            != 1
        ):
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        if (
            connection.execute(
                "INSERT INTO schema_metadata(singleton,schema_version,registry_digest,"
                "created_at) VALUES(1,?,?,?)",
                (target.version.value, target.registry_digest.value, created[0][0]),
            ).rowcount
            != 1
        ):
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        version, name, checksum = target.ledger[-1]
        # Preserve every predecessor ledger row/time. Only the new step receives
        # the actual internal observation time; there is no caller clock input.
        applied = timestamp_to_sql(Timestamp(datetime.now(UTC)))
        connection.execute(
            "INSERT INTO schema_migrations(version,name,checksum,applied_at) "
            "VALUES(?,?,?,?)",
            (version, name, checksum, applied),
        )
        connection.execute(f"PRAGMA user_version={target.version.value}")
        expected = replace(before, schema_version=target.version)
        after = _state(connection, target)
        if after != expected:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        _call(provider, "_check_migration_connection", connection, owner)
        attempted_commit = True
        connection.execute("COMMIT")
        after = _state(connection, target)
        if after != expected:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        _call(provider, "_check_migration_connection", connection, owner)
        return _result("migrated", before, after)
    except StorageFailure as error:
        code = (
            error.code
            if type(error) is StorageFailure
            else ErrorCode.CONSISTENCY_FAILURE
        )
    except sqlite3.Error as error:
        code = sqlite_failure(error).code
    except MemoryError:
        code = ErrorCode.PERSISTENCE_FAILURE
    except Exception:
        pass
    except BaseException:
        code = ErrorCode.PERSISTENCE_FAILURE
    # Refused foreign/fork callers cannot poison or close the genuine resource.
    if os.getpid() != pid or threading.current_thread() is not thread:
        _fail(ErrorCode.OWNER_UNAVAILABLE)
    if attempted_commit:
        _close_uncertain(connection)
        code = ErrorCode.PERSISTENCE_FAILURE
    elif begin_attempted:
        try:
            # Denied/unreached BEGIN stays idle; acknowledgement loss may not.
            if connection.in_transaction:
                connection.execute("ROLLBACK")
                if connection.in_transaction:
                    raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)
        except BaseException:
            _close_uncertain(connection)
            code = ErrorCode.PERSISTENCE_FAILURE
    _fail(code)
