"""Exact trusted schema inspection. Inspection never migrates or creates state."""

import re
import sqlite3

from facet.contracts import ErrorCode

from .codecs import StorageFailure
from .migrations import (
    _FRESH_V2_MANIFEST,
    _FRESH_V3_MANIFEST,
    CHECKSUMS,
    REGISTRY,
    REGISTRY_DIGEST,
    _SchemaManifest,
    v0001,
)


def _catalogue():
    result = {}
    for sql in v0001.STATEMENTS:
        match = re.match(r"CREATE (?:UNIQUE )?(TABLE|INDEX|TRIGGER) (\w+)", sql)
        assert match is not None
        kind, name = match.groups()
        result[(kind.lower(), name)] = sql
    return result


TRUSTED_CATALOGUE = _catalogue()


def _inspect(connection: sqlite3.Connection) -> None:
    """Recognize exact supported schemas; consumers still choose their version."""
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version == 2:
        _inspect_manifest(connection, _FRESH_V2_MANIFEST)
        return
    if version == 3:
        _inspect_manifest(connection, _FRESH_V3_MANIFEST)
        return
    _inspect_v1(connection)


def _inspect_v1(connection: sqlite3.Connection) -> None:
    """Supplied private owner/view connection only; never a path or fallback."""
    application_id = connection.execute("PRAGMA application_id").fetchone()[0]
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > v0001.VERSION:
        raise StorageFailure(ErrorCode.UNSUPPORTED_VERSION)
    if application_id != v0001.APPLICATION_ID or version != v0001.VERSION:
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
    catalogue = {
        (kind, name): sql
        for kind, name, sql in connection.execute(
            "SELECT type,name,sql FROM sqlite_schema "
            "WHERE name NOT GLOB 'sqlite_autoindex_*'"
        ).fetchall()
    }
    if catalogue != TRUSTED_CATALOGUE:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    metadata = connection.execute(
        "SELECT singleton,schema_version,registry_digest FROM schema_metadata"
    ).fetchall()
    ledger = connection.execute(
        "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    expected = [
        (version, name, checksum)
        for (version, name, _), checksum in zip(REGISTRY, CHECKSUMS, strict=True)
    ]
    if metadata != [(1, v0001.VERSION, REGISTRY_DIGEST)] or ledger != expected:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    projections = connection.execute("SELECT projection_id FROM projections").fetchall()
    if len(projections) != 1:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if connection.execute(
        "SELECT role FROM bindings WHERE projection_id=? ORDER BY role",
        projections[0],
    ).fetchall() != [("source",), ("target",)]:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if (
        connection.execute(
            "SELECT COUNT(*) FROM history_checkpoints WHERE projection_id=?",
            projections[0],
        ).fetchone()[0]
        != 1
    ):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)


def _pristine(connection: sqlite3.Connection) -> None:
    if (
        connection.in_transaction
        or connection.execute("PRAGMA application_id").fetchone()[0] != 0
        or connection.execute("PRAGMA user_version").fetchone()[0] != 0
        or connection.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone()
    ):
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)


def _inspect_manifest(
    connection: sqlite3.Connection, manifest: _SchemaManifest
) -> None:
    """Private compiled-manifest inspection; never discovers migration SQL."""
    if type(manifest) is not _SchemaManifest:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if connection.execute("PRAGMA application_id").fetchone() != (
        v0001.APPLICATION_ID,
    ) or connection.execute("PRAGMA user_version").fetchone() != (
        manifest.version.value,
    ):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    catalogue = {
        (kind, name): sql
        for kind, name, sql in connection.execute(
            "SELECT type,name,sql FROM sqlite_schema "
            "WHERE name NOT GLOB 'sqlite_autoindex_*'"
        ).fetchall()
    }
    if catalogue != {(kind, name): sql for kind, name, sql in manifest.catalogue}:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if connection.execute(
        "SELECT singleton,schema_version,registry_digest FROM schema_metadata"
    ).fetchall() != [(1, manifest.version.value, manifest.registry_digest.value)]:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if connection.execute(
        "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
    ).fetchall() != list(manifest.ledger):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    projections = connection.execute("SELECT projection_id FROM projections").fetchall()
    if len(projections) != 1:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if connection.execute(
        "SELECT role FROM bindings WHERE projection_id=? ORDER BY role",
        projections[0],
    ).fetchall() != [("source",), ("target",)]:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if connection.execute(
        "SELECT COUNT(*) FROM history_checkpoints WHERE projection_id=?",
        projections[0],
    ).fetchone() != (1,):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
