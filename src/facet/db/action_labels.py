"""Private projection-scoped source action-label mapping operations."""

import sqlite3

from facet.contracts import ErrorCode, LocalId, ProjectionId, Revision, Role, Timestamp
from facet.db.codecs import (
    ActionKind,
    AuditKind,
    AuditObjectKind,
    StorageFailure,
    next_revision,
    sqlite_failure,
    timestamp_to_sql,
)

DEFAULTS = {
    ActionKind.ADD_SENDER: "AI/AddSender",
    ActionKind.ADD_DOMAIN: "AI/AddDomain",
    ActionKind.BLACKLIST: "AI/BlackList",
}


def _valid_name(name: str) -> None:
    if (
        type(name) is not str
        or not name.strip()
        or len(name.encode()) > 512
        or any(ord(char) < 32 or ord(char) > 126 for char in name)
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)


def effective(connection, projection_id: ProjectionId) -> dict[ActionKind, str]:
    """Only a trusted v2 schema has implicit defaults; v3 errors are fatal."""
    from facet.db.migrations import _FRESH_V2_MANIFEST
    from facet.db.schema import _inspect_manifest

    if type(projection_id) is not ProjectionId:
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 2:
            _inspect_manifest(connection, _FRESH_V2_MANIFEST)
            return dict(DEFAULTS)
        if version != 3:
            raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
        rows = connection.execute(
            "SELECT action_kind,label_name FROM action_label_mappings "
            "WHERE projection_id=?",
            (projection_id.value,),
        ).fetchall()
        result = dict(DEFAULTS)
        for kind, name in rows:
            action_kind = ActionKind(kind)
            if name is not None:
                _valid_name(name)
                result[action_kind] = name
        if len(set(result.values())) != len(result):
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        return result
    except sqlite3.Error as error:
        raise sqlite_failure(error) from None
    except (ValueError, TypeError):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None


def check_request_conflict(context, projection_id, request_id):
    """Refuse a label receipt reused by another command (v2 has no receipts)."""
    version = context._execute("PRAGMA user_version").fetchone()[0]
    if (
        version == 3
        and context._execute(
            "SELECT 1 FROM action_label_receipts WHERE projection_id=? "
            "AND request_id=?",
            (projection_id.value, request_id.value),
        ).fetchone()
    ):
        raise StorageFailure(ErrorCode.REQUEST_CONFLICT)


def mutate(owner, request_id, kind, name, now, config_bytes):
    """Atomic mapping, stable receipt and existing typed maintenance audit."""
    from facet.cli.bootstrap import _auth_role_nonce
    from facet.db.repositories.audit import _audit

    if (
        type(request_id) is not LocalId
        or type(kind) is not ActionKind
        or type(now) is not Timestamp
        or type(config_bytes) is not bytes
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    if name is not None:
        _valid_name(name)
    owner.verify_config_artifact(config_bytes)
    connection = owner._connection
    # Check collisions and effective uniqueness BEFORE any schema/backup write.
    nonces = (request_id.value,) + tuple(
        _auth_role_nonce(request_id, role).value for role in Role
    )
    with owner.session.transaction() as uow:
        if uow._execute(
            "SELECT 1 FROM operations WHERE projection_id=? "
            "AND request_nonce IN (?,?,?) UNION ALL "
            "SELECT 1 FROM rules WHERE projection_id=? AND rule_id=? LIMIT 1",
            (
                owner.projection_id.value,
                *nonces,
                owner.projection_id.value,
                request_id.value,
            ),
        ).fetchone():
            raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
        names = effective(connection, owner.projection_id)
        if connection.execute("PRAGMA user_version").fetchone()[0] == 3:
            prior = uow._execute(
                "SELECT action_kind,operation,label_name,revision "
                "FROM action_label_receipts WHERE projection_id=? AND request_id=?",
                (owner.projection_id.value, request_id.value),
            ).fetchone()
            if prior is not None:
                if prior[:3] != (
                    kind.value,
                    "set" if name is not None else "remove",
                    name,
                ):
                    raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
                return {"revision": prior[3], "idempotent": True}
        names[kind] = DEFAULTS[kind] if name is None else name
        if len(set(names.values())) != len(names):
            raise StorageFailure(ErrorCode.INVALID_INPUT)
    owner.ensure_action_label_schema(request_id, config_bytes)
    with owner.session.transaction() as uow:
        current = uow._execute(
            "SELECT revision FROM action_label_mappings "
            "WHERE projection_id=? AND action_kind=?",
            (owner.projection_id.value, kind.value),
        ).fetchone()
        before = Revision(current[0] if current else 0)
        revision = next_revision(before)
        uow._execute(
            "INSERT INTO action_label_mappings VALUES(?,?,?,?,?) "
            "ON CONFLICT(projection_id,action_kind) DO UPDATE SET "
            "label_name=excluded.label_name,revision=excluded.revision,"
            "updated_at=excluded.updated_at",
            (
                owner.projection_id.value,
                kind.value,
                name,
                revision.value,
                timestamp_to_sql(now),
            ),
        )
        uow._execute(
            "INSERT INTO action_label_receipts VALUES(?,?,?,?,?,?,?)",
            (
                owner.projection_id.value,
                request_id.value,
                kind.value,
                "set" if name is not None else "remove",
                name,
                revision.value,
                timestamp_to_sql(now),
            ),
        )
        _audit(
            uow,
            owner.projection_id,
            AuditKind.MAINTENANCE_COMPLETED,
            AuditObjectKind.PROJECTION,
            now,
            before_revision=before,
            after_revision=revision,
        )
    return {"revision": revision.value, "idempotent": False}
