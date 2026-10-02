"""Exact trusted schema inspection. Inspection never migrates or creates state."""

import re
import sqlite3

from facet.contracts import ErrorCode

from .codecs import StorageFailure
from .migrations import CHECKSUMS, REGISTRY, REGISTRY_DIGEST, v0001


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
