"""Private projection-scoped source action-label mapping operations."""

import sqlite3

from facet.contracts import ErrorCode, LocalId, ProjectionId, Timestamp
from facet.db.codecs import ActionKind, StorageFailure

DEFAULTS = {
    ActionKind.ADD_SENDER: "AI/AddSender",
    ActionKind.ADD_DOMAIN: "AI/AddDomain",
    ActionKind.BLACKLIST: "AI/BlackList",
}


def _valid_name(name: str) -> None:
    if (
        type(name) is not str
        or not name
        or len(name.encode()) > 512
        or any(ord(char) < 32 or ord(char) > 126 for char in name)
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)


def effective(connection, projection_id: ProjectionId) -> dict[ActionKind, str]:
    try:
        rows = connection.execute(
            "SELECT action_kind,label_name FROM action_label_mappings "
            "WHERE projection_id=?",
            (projection_id.value,),
        ).fetchall()
    except sqlite3.OperationalError:
        return dict(DEFAULTS)
    result = dict(DEFAULTS)
    for kind, name in rows:
        try:
            action_kind = ActionKind(kind)
        except ValueError:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None
        if name is not None:
            _valid_name(name)
            result[action_kind] = name
    return result


def mutate(
    owner, request_id: LocalId, kind: ActionKind, name: str | None, now: Timestamp
):
    if type(request_id) is not LocalId or type(kind) is not ActionKind:
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    if name is not None:
        _valid_name(name)
    owner.ensure_action_label_schema()
    connection = owner._connection
    prior = connection.execute(
        "SELECT action_kind,operation,label_name,revision FROM action_label_receipts "
        "WHERE projection_id=? AND request_id=?",
        (owner.projection_id.value, request_id.value),
    ).fetchone()
    operation = "set" if name is not None else "remove"
    if prior is not None:
        if prior[:3] != (kind.value, operation, name):
            raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
        return {"revision": prior[3], "idempotent": True}
    duplicate = (
        connection.execute(
            "SELECT action_kind FROM action_label_mappings WHERE projection_id=? AND "
            "label_name=? AND action_kind<>?",
            (owner.projection_id.value, name, kind.value),
        ).fetchone()
        if name is not None
        else None
    )
    if duplicate is not None:
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    current = connection.execute(
        "SELECT revision FROM action_label_mappings "
        "WHERE projection_id=? AND action_kind=?",
        (owner.projection_id.value, kind.value),
    ).fetchone()
    revision = (current[0] + 1) if current else 1
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            "INSERT INTO action_label_mappings VALUES(?,?,?,?,?) "
            "ON CONFLICT(projection_id,action_kind) DO UPDATE SET "
            "label_name=excluded.label_name,revision=excluded.revision,"
            "updated_at=excluded.updated_at",
            (
                owner.projection_id.value,
                kind.value,
                name,
                revision,
                now.value.timestamp() * 1000000,
            ),
        )
        connection.execute(
            "INSERT INTO action_label_receipts VALUES(?,?,?,?,?,?,?)",
            (
                owner.projection_id.value,
                request_id.value,
                kind.value,
                operation,
                name,
                revision,
                now.value.timestamp() * 1000000,
            ),
        )
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    return {"revision": revision, "idempotent": False}
