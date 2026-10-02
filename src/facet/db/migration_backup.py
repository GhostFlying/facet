"""Storage-only snapshots, not complete bundles or permission to migrate.

The current source is an actual WriterSession, never a borrowed prior owner run.
Stopped maintenance needs its separately reviewed owner adapter. Destination
creation/permissions/fsync/publication and credentials belong to M1-03/M6.
"""

import sqlite3

from facet.contracts import ErrorCode, LocalId

from .codecs import SchemaVersion, StorageFailure, sqlite_failure
from .connection import WriterSession
from .models import DatabaseSnapshotInfo
from .schema import _inspect_v1, _pristine


def _progress(status: int, remaining: int, total: int) -> None:
    # Fixed internal callback: no caller code, logging, retry loop or sleep.
    # Abort BUSY/LOCKED rather than letting sqlite3.backup retry indefinitely.
    if status in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
        raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE)
    if status not in {sqlite3.SQLITE_OK, sqlite3.SQLITE_DONE}:
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)


def snapshot_database(source_session, destination_connection) -> DatabaseSnapshotInfo:
    if type(source_session) is not WriterSession or not isinstance(
        destination_connection, sqlite3.Connection
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    source_session._check()
    source = source_session._connection
    destination = destination_connection
    try:
        # Unsupported v2 is refused before ANY destination PRAGMA/configuration
        # or native backup; the existing successful receipt truthfully means v1.
        _inspect_v1(source)
        if (
            source is destination
            or source_session._uow is not None
            or source.in_transaction
            or destination.autocommit is not True
            or destination.in_transaction
            or destination.execute("PRAGMA query_only").fetchone() != (0,)
        ):
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        source_session._check_lineage()
        source_session._relational_guards()
        _inspect_v1(source)
        _pristine(destination)
        destination.row_factory = None
        destination.execute("PRAGMA trusted_schema=OFF")
        destination.execute("PRAGMA foreign_keys=ON")
        timeout = destination.execute("PRAGMA busy_timeout").fetchone()[0]
        destination.execute("PRAGMA busy_timeout=0")
        try:
            source.backup(destination, pages=128, progress=_progress, sleep=0.0)
        finally:
            destination.execute(f"PRAGMA busy_timeout={timeout}")
        _inspect_v1(destination)
        if destination.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        if destination.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        identity = destination.execute(
            "SELECT state_instance_id,request_namespace,last_owner_run_id "
            "FROM projections"
        ).fetchall()
        info = source_session._info
        if identity != [
            (
                info.state_instance_id.value,
                info.request_namespace.value,
                info.owner_run_id.value,
            )
        ]:
            raise StorageFailure(ErrorCode.REQUEST_LINEAGE_MISMATCH)
        # A competing/changed owner cannot turn an old copied image into a
        # current successful snapshot. This is not process-lock proof itself.
        source_session._check_lineage()
        return DatabaseSnapshotInfo(
            SchemaVersion(1), LocalId(identity[0][0]), LocalId(identity[0][1]), True
        )
    except sqlite3.Error as error:
        raise sqlite_failure(error) from None
    except StorageFailure as error:
        # The new v1-only consumer barrier retains only the existing fixed code,
        # including when its caller is already handling private input failure.
        error.__cause__ = None
        error.__context__ = None
        raise
