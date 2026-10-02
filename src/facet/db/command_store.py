"""Fixed bootstrap storage helpers, not command execution or a public query API."""

from dataclasses import fields

from facet.contracts import (
    Count,
    ErrorCode,
    LocalId,
    OperationState,
    ProjectionId,
    Revision,
    Sha256Hex,
)

from .codecs import encode_scalar, timestamp_from_sql
from .command_records import (
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


def _scalar(value):
    if type(value) is int and value == 1:
        # Only the already validated closed Literal[1] version fields use ints.
        return value
    if type(value) in {LocalCommandKind, BootstrapCommand, RequestId}:
        return value.value
    return encode_scalar(value)


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
    operation = OperationRow(
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
