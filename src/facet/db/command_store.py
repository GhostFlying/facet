"""Fixed operation-storage helpers, not command execution or a public query API."""

import hashlib
import sqlite3
import struct
from dataclasses import fields

from facet.contracts import (
    Count,
    ErrorCode,
    LocalId,
    OperationState,
    PreviewPurpose,
    ProjectionId,
    Revision,
    Sha256Hex,
)

from .codecs import encode_scalar, sqlite_failure, timestamp_from_sql
from .command_records import (
    BackfillPayloadRow,
    BootstrapCommand,
    BootstrapPayloadRow,
    FreshCommandBootstrap,
    LocalCommandKind,
    OperationRow,
    RequestId,
    _fail,
)

_OPERATION_COLUMNS = (
    "projection_id,operation_id,request_namespace,request_nonce,command,"
    "payload_version,digest_version,digest,state,revision,accepted_at,updated_at,"
    "completed_at,code,effect_completed,expected_binding_revision,"
    "expected_config_revision,expected_preview_id,confirmation_yes,"
    "duplicate_risk_acknowledged"
)
_BOOTSTRAP_COLUMNS = (
    "projection_id,operation_id,config_semantic_digest,config_artifact_digest,"
    "bootstrap_request_id,initialized_schema_version"
)
_BACKFILL_COLUMNS = (
    "projection_id,operation_id,purpose,preview_operation_id,ruleset_revision,"
    "window_start,window_end,discovery_cutoff,scope_digest,expires_at,"
    "invalidating_revision"
)


def _scalar(value):
    if type(value) is int and value == 1:
        # Only the already validated closed Literal[1] version fields use ints.
        return value
    if type(value) in {LocalCommandKind, BootstrapCommand, PreviewPurpose, RequestId}:
        return value.value
    return encode_scalar(value)


def _owner_execute(owner, sql, parameters=()):
    """Execute one fixed statement on the existing owner boundary."""
    from .transactions import UnitOfWork

    if type(owner) is UnitOfWork:
        return owner._execute(sql, parameters)
    _fail(ErrorCode.INVALID_INPUT)


def _owner_fetchall(owner, sql, parameters=()):
    """Fetch one fixed query without leaking native errors."""
    try:
        return _owner_execute(owner, sql, parameters).fetchall()
    except sqlite3.Error as error:
        from .transactions import UnitOfWork

        if type(owner) is UnitOfWork:
            owner._failed = True
        raise sqlite_failure(error) from None


def _operation_from_row(row):
    return OperationRow(
        ProjectionId(row[0]),
        LocalId(row[1]),
        LocalId(row[2]),
        LocalId(row[3]),
        LocalCommandKind(row[4]),
        row[5],
        row[6],
        Sha256Hex(row[7]),
        OperationState(row[8]),
        Revision(row[9]),
        timestamp_from_sql(row[10]),
        timestamp_from_sql(row[11]),
        None if row[12] is None else timestamp_from_sql(row[12]),
        None if row[13] is None else ErrorCode(row[13]),
        _boolean(row[14]),
        Revision(row[15]),
        Revision(row[16]),
        None if row[17] is None else LocalId(row[17]),
        _boolean(row[18]),
        _boolean(row[19]),
    )


def _payload_from_row(row):
    return BackfillPayloadRow(
        ProjectionId(row[0]),
        LocalId(row[1]),
        PreviewPurpose(row[2]),
        None if row[3] is None else LocalId(row[3]),
        Revision(row[4]),
        timestamp_from_sql(row[5]),
        timestamp_from_sql(row[6]),
        timestamp_from_sql(row[7]),
        Sha256Hex(row[8]),
        timestamp_from_sql(row[9]),
        Revision(row[10]),
    )


def _digest_part(value):
    """Encode one closed scalar with a length-delimited, fixed type tag."""
    # The domain separator is the one intentional plain string. All other
    # values are closed records/enums and must pass the scalar encoder.
    if type(value) is not str:
        value = _scalar(value)
    if value is None:
        return b"N\x00"
    if type(value) is int:
        return b"I" + struct.pack(">q", value)
    if type(value) is str:
        raw = value.encode("utf-8")
        return b"S" + struct.pack(">I", len(raw)) + raw
    if type(value) is bytes:
        return b"B" + struct.pack(">I", len(value)) + value
    _fail(ErrorCode.INVALID_INPUT)


def _backfill_digest(operation, payload):
    """Return the canonical v1 digest for a typed backfill request."""
    if type(operation) is not OperationRow or type(payload) is not BackfillPayloadRow:
        _fail(ErrorCode.INVALID_INPUT)
    OperationRow.__post_init__(operation)
    BackfillPayloadRow.__post_init__(payload)
    if operation.projection_id != payload.projection_id:
        _fail(ErrorCode.INVALID_INPUT)
    values = (
        "facet-operation-v1",
        operation.projection_id,
        operation.request_namespace,
        operation.command,
        operation.payload_version,
        operation.digest_version,
        operation.expected_binding_revision,
        operation.expected_config_revision,
        operation.expected_preview_id,
        operation.confirmation_yes,
        operation.duplicate_risk_acknowledged,
        payload.purpose,
        payload.preview_operation_id,
        payload.ruleset_revision,
        payload.window_start,
        payload.window_end,
        payload.discovery_cutoff,
        payload.scope_digest,
        payload.expires_at,
        payload.invalidating_revision,
    )
    encoded = b"".join(_digest_part(value) for value in values)
    return Sha256Hex(hashlib.sha256(encoded).hexdigest())


def _insert_bootstrap(connection, projection_id, commands):
    if (
        type(projection_id) is not ProjectionId
        or type(commands) is not FreshCommandBootstrap
    ):
        _fail()
    FreshCommandBootstrap.__post_init__(commands)
    seeds = (
        (commands.current,)
        if commands.prior_config is None
        else (commands.prior_config, commands.current)
    )
    for seed in seeds:
        operation = OperationRow(
            projection_id,
            seed.operation_id,
            seed.namespace,
            seed.nonce,
            LocalCommandKind(seed.command.value),
            1,
            seed.digest_version,
            seed.digest,
            OperationState.COMPLETED,
            Revision(1),
            seed.accepted_at,
            seed.completed_at,
            seed.completed_at,
            None,
            True,
            seed.expected_binding_revision,
            seed.expected_config_revision,
            None,
            seed.confirmation_yes,
            seed.duplicate_risk_acknowledged,
        )
        payload = BootstrapPayloadRow(
            projection_id,
            seed.operation_id,
            seed.config_semantic_digest,
            seed.config_artifact_digest,
            RequestId(f"rq1_{seed.namespace.value}_{seed.nonce.value}"),
            Count(2) if seed.command is BootstrapCommand.FACET_INIT else None,
        )
        connection.execute(
            f"INSERT INTO operations({_OPERATION_COLUMNS}) "
            f"VALUES({','.join('?' for _ in fields(operation))})",
            tuple(_scalar(getattr(operation, f.name)) for f in fields(operation)),
        )
        connection.execute(
            f"INSERT INTO operation_bootstrap({_BOOTSTRAP_COLUMNS}) "
            "VALUES(?,?,?,?,?,?)",
            tuple(_scalar(getattr(payload, f.name)) for f in fields(payload)),
        )


def _insert_backfill(owner, projection_id, operation, payload):
    """Insert one already-validated preview/start operation and its child."""
    if (
        type(projection_id) is not ProjectionId
        or type(operation) is not OperationRow
        or type(payload) is not BackfillPayloadRow
        or operation.projection_id != projection_id
        or payload.projection_id != projection_id
        or payload.operation_id != operation.operation_id
        or operation.command
        not in {LocalCommandKind.BACKFILL_PREVIEW, LocalCommandKind.BACKFILL_START}
        or (
            operation.command is LocalCommandKind.BACKFILL_PREVIEW
            and payload.preview_operation_id is not None
        )
        or (
            operation.command is LocalCommandKind.BACKFILL_START
            and payload.preview_operation_id != operation.expected_preview_id
        )
    ):
        _fail(ErrorCode.INVALID_INPUT)
    OperationRow.__post_init__(operation)
    BackfillPayloadRow.__post_init__(payload)
    if operation.digest != _backfill_digest(operation, payload):
        _fail(ErrorCode.REQUEST_CONFLICT)
    existing = _find_backfill(
        owner, projection_id, operation.request_namespace, operation.request_nonce
    )
    if existing[0] is not None:
        if not _same_backfill_request(existing, (operation, payload)):
            _fail(ErrorCode.REQUEST_CONFLICT)
        return existing[0]
    values = tuple(_scalar(getattr(operation, f.name)) for f in fields(operation))
    _owner_execute(
        owner,
        f"INSERT INTO operations({_OPERATION_COLUMNS}) "
        f"VALUES({','.join('?' for _ in values)})",
        values,
    )
    values = tuple(_scalar(getattr(payload, f.name)) for f in fields(payload))
    _owner_execute(
        owner,
        f"INSERT INTO operation_backfill({_BACKFILL_COLUMNS}) "
        f"VALUES({','.join('?' for _ in values)})",
        values,
    )
    return operation


def _lookup_backfill(owner, projection_id, operation, payload):
    """Replay an exact request-keyed row or return no committed result."""
    if type(operation) is not OperationRow or type(payload) is not BackfillPayloadRow:
        _fail(ErrorCode.INVALID_INPUT)
    if operation.digest != _backfill_digest(operation, payload):
        _fail(ErrorCode.REQUEST_CONFLICT)
    existing = _find_backfill(
        owner, projection_id, operation.request_namespace, operation.request_nonce
    )
    if existing[0] is None:
        return None
    if not _same_backfill_request(existing, (operation, payload)):
        _fail(ErrorCode.REQUEST_CONFLICT)
    return existing


def _same_backfill_request(existing, requested):
    """Compare request identity and canonical payload, excluding local IDs.

    A retry may allocate a fresh local operation ID after losing the first
    response. The stable request key and digest identify the committed row;
    operation IDs are returned from that row and therefore are not part of the
    replay comparison.
    """
    old_operation, old_payload = existing
    operation, payload = requested
    if old_operation is None or old_payload is None:
        return False
    if old_operation.digest != operation.digest:
        return False
    operation_fields = tuple(
        field.name
        for field in fields(operation)
        if field.name not in {"operation_id", "digest"}
    )
    payload_fields = tuple(
        field.name for field in fields(payload) if field.name != "operation_id"
    )
    return all(
        getattr(old_operation, name) == getattr(operation, name)
        for name in operation_fields
    ) and all(
        getattr(old_payload, name) == getattr(payload, name) for name in payload_fields
    )


def _boolean(value):
    if type(value) is not int or value not in {0, 1}:
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    return bool(value)


def _find_bootstrap(connection, projection, namespace, nonce):
    rows = connection.execute(
        f"SELECT {_OPERATION_COLUMNS} FROM operations WHERE projection_id=? "
        "AND request_namespace=? AND request_nonce=? LIMIT 2",
        (projection.value, namespace.value, nonce.value),
    ).fetchall()
    if not rows:
        return None, None
    if len(rows) != 1:
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    row = rows[0]
    operation = _operation_from_row(row)
    payloads = connection.execute(
        f"SELECT {_BOOTSTRAP_COLUMNS} FROM operation_bootstrap "
        "WHERE projection_id=? AND operation_id=? LIMIT 2",
        (projection.value, operation.operation_id.value),
    ).fetchall()
    if (
        len(payloads) != 1
        or connection.execute(
            "SELECT 1 FROM operation_controls WHERE projection_id=? AND operation_id=? "
            "UNION ALL SELECT 1 FROM operation_auth "
            "WHERE projection_id=? AND operation_id=? LIMIT 1",
            (projection.value, operation.operation_id.value) * 2,
        ).fetchone()
        is not None
    ):
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    row = payloads[0]
    payload = BootstrapPayloadRow(
        ProjectionId(row[0]),
        LocalId(row[1]),
        Sha256Hex(row[2]),
        Sha256Hex(row[3]),
        RequestId(row[4]),
        None if row[5] is None else Count(row[5]),
    )
    return operation, payload


def _find_backfill(owner, projection, namespace, nonce):
    """Look up one request-keyed backfill operation and its exact child."""
    if (
        type(projection) is not ProjectionId
        or type(namespace) is not LocalId
        or type(nonce) is not LocalId
    ):
        _fail(ErrorCode.INVALID_INPUT)
    rows = _owner_fetchall(
        owner,
        f"SELECT {_OPERATION_COLUMNS} FROM operations WHERE projection_id=? "
        "AND request_namespace=? AND request_nonce=? LIMIT 2",
        (projection.value, namespace.value, nonce.value),
    )
    if not rows:
        return None, None
    if len(rows) != 1:
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    operation = _operation_from_row(rows[0])
    if operation.command not in {
        LocalCommandKind.BACKFILL_PREVIEW,
        LocalCommandKind.BACKFILL_START,
    }:
        return operation, None
    result = _find_backfill_by_id(owner, projection, operation.operation_id, operation)
    if result[1] is not None and operation.digest != _backfill_digest(*result):
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    return result


def _find_backfill_by_id(owner, projection, operation_id, operation=None):
    """Look up a backfill operation by stable local operation id."""
    if type(projection) is not ProjectionId or type(operation_id) is not LocalId:
        _fail(ErrorCode.INVALID_INPUT)
    if operation is None:
        rows = _owner_fetchall(
            owner,
            f"SELECT {_OPERATION_COLUMNS} FROM operations WHERE projection_id=? "
            "AND operation_id=? LIMIT 2",
            (projection.value, operation_id.value),
        )
        if not rows:
            return None, None
        if len(rows) != 1:
            _fail(ErrorCode.CONSISTENCY_FAILURE)
        operation = _operation_from_row(rows[0])
    if operation.projection_id != projection or operation.operation_id != operation_id:
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    rows = _owner_fetchall(
        owner,
        f"SELECT {_BACKFILL_COLUMNS} FROM operation_backfill "
        "WHERE projection_id=? AND operation_id=? LIMIT 2",
        (projection.value, operation_id.value),
    )
    if len(rows) != 1:
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    return operation, _payload_from_row(rows[0])
