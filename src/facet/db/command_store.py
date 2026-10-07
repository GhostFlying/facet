"""Fixed operation-storage helpers, not command execution or a public query API."""

import hashlib
import sqlite3
import struct
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from facet.contracts import (
    Count,
    EpochKind,
    EpochState,
    ErrorCode,
    LocalId,
    OperationState,
    PartitionProgress,
    PartitionState,
    PreviewPurpose,
    ProjectionId,
    Revision,
    Role,
    Sha256Hex,
    Timestamp,
)
from facet.contracts.records import (
    EpochDecisionRefBackfillStart,
    PartitionRefSourceWindow,
)

from .codecs import StorageFailure, encode_scalar, sqlite_failure, timestamp_from_sql
from .command_records import (
    BackfillPayloadRow,
    BackfillPreviewRequest,
    BackfillStartRequest,
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


def _owner_now():
    """Owner-observed clock fact; tests replace this private seam."""
    return Timestamp(datetime.now(UTC))


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


def authorize_operation(
    owner, projection_id, role, request_nonce, command=LocalCommandKind.AUTH_AUTHORIZE
):
    """Register one stable-keyed authorization operation before OAuth work."""

    from .repositories.base import _get
    from .transactions import UnitOfWork

    if (
        type(owner) is not UnitOfWork
        or type(projection_id) is not ProjectionId
        or type(role) is not Role
        or type(request_nonce) is not LocalId
        or type(command) is not LocalCommandKind
        or command
        not in {
            LocalCommandKind.AUTH_AUTHORIZE,
            LocalCommandKind.AUTH_REAUTHORIZE,
        }
    ):
        _fail(ErrorCode.INVALID_INPUT)
    projection = _get(owner, projection_id, "projections", ())
    binding = _get(owner, projection_id, "bindings", (("role", role),))
    from .action_labels import check_request_conflict

    check_request_conflict(owner, projection_id, request_nonce)
    if projection is None or binding is None:
        _fail(ErrorCode.OWNER_UNAVAILABLE)
    existing = _owner_fetchall(
        owner,
        "SELECT o.operation_id,o.state,a.role,a.expected_credential_revision,"
        "a.expected_role_binding_revision,a.expected_policy_revision "
        "FROM operations o JOIN operation_auth a ON "
        "a.projection_id=o.projection_id AND a.operation_id=o.operation_id "
        "WHERE o.projection_id=? AND o.request_namespace=? AND "
        "o.request_nonce=? AND o.command=? LIMIT 2",
        (
            projection_id.value,
            projection.request_namespace.value,
            request_nonce.value,
            command.value,
        ),
    )
    if len(existing) > 1:
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    expected_policy = Revision(1)
    if existing:
        row = existing[0]
        if row[2] != role.value:
            _fail(ErrorCode.REQUEST_CONFLICT)
        if row[1] in {
            OperationState.COMPLETED.value,
            OperationState.REJECTED.value,
        }:
            return LocalId(row[0])
        if (
            row[3] != binding.credential_revision.value
            or row[4] != binding.binding_revision.value
            or row[5] != expected_policy.value
        ):
            recovery = _owner_fetchall(
                owner,
                "SELECT c.phase,c.kind FROM credential_changes c "
                "JOIN operation_auth a ON a.projection_id=c.projection_id "
                "AND a.operation_id=c.operation_id WHERE c.projection_id=? "
                "AND c.operation_id=? AND c.role=? LIMIT 2",
                (projection_id.value, row[0], role.value),
            )
            if not (
                row[1] == OperationState.ACCEPTED.value
                and binding.state.value == "verified"
                and binding.credential_revision.value == row[3] + 1
                and binding.binding_revision.value == row[4]
                and row[5] == expected_policy.value
                and len(recovery) == 1
                and recovery[0][0] in {"validated", "committed"}
                and recovery[0][1]
                == (
                    "refresh"
                    if command is LocalCommandKind.AUTH_REAUTHORIZE
                    else "authorize"
                )
            ):
                _fail(ErrorCode.REQUEST_CONFLICT)
        return LocalId(row[0])
    operation_id = LocalId(uuid4().hex)
    accepted = _owner_now()
    digest = Sha256Hex(
        hashlib.sha256(
            (
                b"facet-auth-v1\x00"
                if command is LocalCommandKind.AUTH_AUTHORIZE
                else b"facet-reauth-v1\x00"
            )
            + projection_id.value.encode()
            + b"\x00"
            + role.value.encode()
            + b"\x00"
            + request_nonce.value.encode()
        ).hexdigest()
    )
    operation = OperationRow(
        projection_id,
        operation_id,
        projection.request_namespace,
        request_nonce,
        command,
        1,
        1,
        digest,
        OperationState.ACCEPTED,
        Revision(1),
        accepted,
        accepted,
        None,
        None,
        False,
        binding.binding_revision,
        projection.config_revision,
        None,
        True,
        False,
    )
    values = tuple(
        _scalar(getattr(operation, field.name)) for field in fields(operation)
    )
    _owner_execute(
        owner,
        f"INSERT INTO operations({_OPERATION_COLUMNS}) "
        f"VALUES({','.join('?' for _ in values)})",
        values,
    )
    _owner_execute(
        owner,
        "INSERT INTO operation_auth(projection_id,operation_id,role,"
        "expected_credential_revision,expected_role_binding_revision,"
        "expected_policy_revision,supersedes_change_id) VALUES(?,?,?,?,?,?,?)",
        (
            projection_id.value,
            operation_id.value,
            role.value,
            binding.credential_revision.value,
            binding.binding_revision.value,
            expected_policy.value,
            None,
        ),
    )
    return operation_id


def complete_authorize_operation(
    owner,
    projection_id,
    operation_id,
    command=LocalCommandKind.AUTH_AUTHORIZE,
):
    """Record the durable effect of a completed authorization probe."""

    from .transactions import UnitOfWork

    if (
        type(owner) is not UnitOfWork
        or type(projection_id) is not ProjectionId
        or type(operation_id) is not LocalId
        or type(command) is not LocalCommandKind
        or command
        not in {LocalCommandKind.AUTH_AUTHORIZE, LocalCommandKind.AUTH_REAUTHORIZE}
    ):
        _fail(ErrorCode.INVALID_INPUT)
    rows = _owner_fetchall(
        owner,
        "SELECT command,state,revision FROM operations "
        "WHERE projection_id=? AND operation_id=? LIMIT 2",
        (projection_id.value, operation_id.value),
    )
    if len(rows) != 1:
        _fail(ErrorCode.REQUEST_CONFLICT)
    row_command, state, revision = rows[0]
    if row_command != command.value:
        _fail(ErrorCode.REQUEST_CONFLICT)
    if state == OperationState.COMPLETED.value:
        return
    if state != OperationState.ACCEPTED.value:
        _fail(ErrorCode.REQUEST_CONFLICT)
    completed = _owner_now()
    cursor = _owner_execute(
        owner,
        "UPDATE operations SET state=?,revision=?,updated_at=?,completed_at=?,"
        "effect_completed=1 WHERE projection_id=? AND operation_id=? AND state=?",
        (
            OperationState.COMPLETED.value,
            revision + 1,
            _scalar(completed),
            _scalar(completed),
            projection_id.value,
            operation_id.value,
            OperationState.ACCEPTED.value,
        ),
    )
    if cursor.rowcount != 1:
        _fail(ErrorCode.REQUEST_CONFLICT)


def reject_authorize_operation(
    owner,
    projection_id,
    operation_id,
    code,
    command=LocalCommandKind.AUTH_AUTHORIZE,
):
    """Durably reject an authorization before any credential publication."""

    from .transactions import UnitOfWork

    if (
        type(owner) is not UnitOfWork
        or type(projection_id) is not ProjectionId
        or type(operation_id) is not LocalId
        or type(code) is not ErrorCode
        or type(command) is not LocalCommandKind
        or command
        not in {LocalCommandKind.AUTH_AUTHORIZE, LocalCommandKind.AUTH_REAUTHORIZE}
    ):
        _fail(ErrorCode.INVALID_INPUT)
    rows = _owner_fetchall(
        owner,
        "SELECT command,state FROM operations WHERE projection_id=? "
        "AND operation_id=? LIMIT 2",
        (projection_id.value, operation_id.value),
    )
    if len(rows) != 1 or rows[0][0] != command.value:
        _fail(ErrorCode.REQUEST_CONFLICT)
    if rows[0][1] == OperationState.REJECTED.value:
        return
    if rows[0][1] != OperationState.ACCEPTED.value:
        _fail(ErrorCode.REQUEST_CONFLICT)
    rejected = _owner_now()
    cursor = _owner_execute(
        owner,
        "UPDATE operations SET state=?,revision=revision+1,updated_at=?,completed_at=?,"
        "code=?,effect_completed=0 WHERE projection_id=? AND operation_id=? "
        "AND state=?",
        (
            OperationState.REJECTED.value,
            _scalar(rejected),
            _scalar(rejected),
            code.value,
            projection_id.value,
            operation_id.value,
            OperationState.ACCEPTED.value,
        ),
    )
    if cursor.rowcount != 1:
        _fail(ErrorCode.REQUEST_CONFLICT)


def resume_projection(owner, projection_id):
    """Resume a started projection through the single writer boundary."""

    from .repositories.base import _get
    from .transactions import UnitOfWork

    if type(owner) is not UnitOfWork or type(projection_id) is not ProjectionId:
        _fail(ErrorCode.INVALID_INPUT)
    projection = _get(owner, projection_id, "projections", ())
    if projection is None:
        _fail(ErrorCode.OWNER_UNAVAILABLE)
    if projection.daemon_paused:
        _owner_execute(
            owner,
            "UPDATE projections SET daemon_paused=0 WHERE projection_id=?",
            (projection_id.value,),
        )


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
    return old_operation.digest == operation.digest


def _backfill_guards(owner, projection_id):
    """Read the current owner-bound projection guards and sealed ruleset."""
    from .repositories.base import _get, _query

    projection = _get(owner, projection_id, "projections", ())
    if projection is None:
        _fail(ErrorCode.OWNER_UNAVAILABLE)
    ruleset = _get(
        owner, projection_id, "rulesets", (("revision", projection.ruleset_revision),)
    )
    if ruleset is None or not ruleset.sealed:
        _fail(ErrorCode.PREVIEW_INVALID)
    runtime = _query(
        owner,
        "SELECT binding_guard,control_revision FROM command_runtime "
        "WHERE projection_id=? LIMIT 2",
        (projection_id.value,),
        maximum=1,
    )
    bindings = _query(
        owner,
        "SELECT binding_revision,state FROM bindings WHERE projection_id=? LIMIT 3",
        (projection_id.value,),
        maximum=2,
    )
    if len(runtime) != 1 or len(bindings) != 2:
        _fail(ErrorCode.OWNER_UNAVAILABLE)
    binding_guard = runtime[0][0]
    if any(row[0] < 1 or row[1] != "verified" for row in bindings):
        _fail(ErrorCode.BINDING_MISMATCH)
    invalidation = _query(
        owner,
        "SELECT COALESCE(SUM(generation),0) FROM tracked_threads WHERE projection_id=?",
        (projection_id.value,),
        maximum=1,
    )
    if len(invalidation) != 1:
        _fail(ErrorCode.OWNER_UNAVAILABLE)
    return projection, Revision(binding_guard), ruleset, Revision(invalidation[0][0])


def _existing_backfill_request(owner, projection_id, request_nonce):
    """Find a request-keyed row before evaluating mutable current guards."""
    from .action_labels import check_request_conflict
    from .repositories.base import _get

    check_request_conflict(owner, projection_id, request_nonce)

    projection = _get(owner, projection_id, "projections", ())
    if projection is None:
        _fail(ErrorCode.OWNER_UNAVAILABLE)
    return _find_backfill(
        owner, projection_id, projection.request_namespace, request_nonce
    )


def preview_backfill(owner, projection_id, request):
    """Persist a guarded typed backfill preview in the active owner UoW."""
    from .transactions import UnitOfWork

    if type(owner) is not UnitOfWork or type(projection_id) is not ProjectionId:
        _fail(ErrorCode.INVALID_INPUT)
    if type(request) is not BackfillPreviewRequest:
        _fail(ErrorCode.INVALID_INPUT)
    owner._check()
    existing = _existing_backfill_request(owner, projection_id, request.request_nonce)
    if existing[0] is not None:
        old_operation, old_payload = existing
        if (
            old_operation.command is not LocalCommandKind.BACKFILL_PREVIEW
            or old_operation.digest != _backfill_digest(old_operation, old_payload)
            or old_payload.window_start != request.window_start
            or old_payload.window_end != request.window_end
            or old_payload.discovery_cutoff != request.discovery_cutoff
            or old_payload.scope_digest != request.scope_digest
            or old_payload.expires_at != request.expires_at
            or old_payload.invalidating_revision != request.invalidating_revision
        ):
            _fail(ErrorCode.REQUEST_CONFLICT)
        return old_operation
    observed_at = _owner_now()
    if abs((request.accepted_at.value - observed_at.value).total_seconds()) > 5:
        _fail(ErrorCode.PREVIEW_INVALID)
    if request.expires_at.value > observed_at.value + timedelta(minutes=15):
        _fail(ErrorCode.PREVIEW_INVALID)
    projection, binding_revision, _, invalidation_revision = _backfill_guards(
        owner, projection_id
    )
    if request.invalidating_revision != invalidation_revision:
        _fail(ErrorCode.PREVIEW_INVALID)
    operation = OperationRow(
        projection_id,
        request.operation_id,
        projection.request_namespace,
        request.request_nonce,
        LocalCommandKind.BACKFILL_PREVIEW,
        1,
        1,
        Sha256Hex("0" * 64),
        OperationState.ACCEPTED,
        Revision(1),
        request.accepted_at,
        request.accepted_at,
        None,
        None,
        False,
        binding_revision,
        projection.config_revision,
        None,
        False,
        False,
    )
    payload = BackfillPayloadRow(
        projection_id,
        request.operation_id,
        PreviewPurpose.START_BACKFILL,
        None,
        projection.ruleset_revision,
        request.window_start,
        request.window_end,
        request.discovery_cutoff,
        request.scope_digest,
        request.expires_at,
        request.invalidating_revision,
    )
    return _insert_backfill(
        owner,
        projection_id,
        replace(operation, digest=_backfill_digest(operation, payload)),
        payload,
    )


def _existing_backfill_epoch(owner, projection_id, operation_id):
    from .repositories.base import _get

    rows = _owner_fetchall(
        owner,
        "SELECT epoch_id FROM epochs WHERE projection_id=? AND operation_id=? LIMIT 2",
        (projection_id.value, operation_id.value),
    )
    if len(rows) > 1:
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    if not rows:
        return None
    return _get(owner, projection_id, "epochs", (("epoch_id", LocalId(rows[0][0])),))


def preflight_backfill_start(owner, projection_id, preview_id, accepted_at):
    """Validate a fresh start before OAuth/profile reads; recheck on acceptance."""
    from .repositories import epochs

    observed_at = _owner_now()
    if abs((accepted_at.value - observed_at.value).total_seconds()) > 5:
        _fail(ErrorCode.PREVIEW_INVALID)
    projection, binding_revision, _, invalidation_revision = _backfill_guards(
        owner, projection_id
    )
    preview, preview_payload = _find_backfill_by_id(owner, projection_id, preview_id)
    if (
        preview is None
        or preview.command is not LocalCommandKind.BACKFILL_PREVIEW
        or preview_payload is None
        or preview.expected_binding_revision != binding_revision
        or preview.expected_config_revision != projection.config_revision
        or preview_payload.ruleset_revision != projection.ruleset_revision
        or preview_payload.invalidating_revision != invalidation_revision
        or accepted_at.value < preview.accepted_at.value
        or preview_payload.expires_at.value < observed_at.value
        or preview_payload.expires_at.value < accepted_at.value
    ):
        _fail(ErrorCode.PREVIEW_INVALID)
    if _owner_fetchall(
        owner,
        "SELECT 1 FROM operations WHERE projection_id=? "
        "AND command='backfill_start' AND expected_preview_id=? LIMIT 1",
        (projection_id.value, preview_id.value),
    ):
        _fail(ErrorCode.REQUEST_CONFLICT)
    initial_epochs = _owner_fetchall(
        owner,
        "SELECT epoch_id FROM epochs WHERE projection_id=? "
        "AND kind='initial_backfill' LIMIT 2",
        (projection_id.value,),
    )
    if len(initial_epochs) > 1:
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    kind = (
        EpochKind.HISTORICAL_EXPANSION if initial_epochs else EpochKind.INITIAL_BACKFILL
    )
    epochs._backfill_checkpoint_guard(owner, projection_id, kind)
    return projection, binding_revision, preview, preview_payload, kind


def start_backfill(owner, projection_id, request):
    """Atomically accept a start and publish its initial/expansion epoch fence."""
    from .keys import partition_key
    from .models import EpochPartitionRow, EpochRow
    from .repositories import epochs
    from .transactions import UnitOfWork

    if type(owner) is not UnitOfWork or type(projection_id) is not ProjectionId:
        _fail(ErrorCode.INVALID_INPUT)
    if type(request) is not BackfillStartRequest:
        _fail(ErrorCode.INVALID_INPUT)
    owner._check()
    existing = _existing_backfill_request(owner, projection_id, request.request_nonce)
    if existing[0] is not None:
        old_operation, old_payload = existing
        if (
            old_operation.command is not LocalCommandKind.BACKFILL_START
            or old_operation.digest != _backfill_digest(old_operation, old_payload)
            or old_operation.expected_preview_id != request.preview_operation_id
        ):
            _fail(ErrorCode.REQUEST_CONFLICT)
        existing_epoch = _existing_backfill_epoch(
            owner, projection_id, old_operation.operation_id
        )
        if existing_epoch is None:
            raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
        if (
            existing_epoch.fence_history_id != request.fence_history_id
            or existing_epoch.fence_recorded_at != request.fence_recorded_at
        ):
            _fail(ErrorCode.REQUEST_CONFLICT)
        return old_operation, existing_epoch
    projection, binding_revision, _, preview_payload, kind = preflight_backfill_start(
        owner, projection_id, request.preview_operation_id, request.accepted_at
    )
    operation = OperationRow(
        projection_id,
        request.operation_id,
        projection.request_namespace,
        request.request_nonce,
        LocalCommandKind.BACKFILL_START,
        1,
        1,
        Sha256Hex("0" * 64),
        OperationState.ACCEPTED,
        Revision(1),
        request.accepted_at,
        request.accepted_at,
        None,
        None,
        False,
        binding_revision,
        projection.config_revision,
        request.preview_operation_id,
        True,
        False,
    )
    payload = replace(
        preview_payload,
        operation_id=request.operation_id,
        preview_operation_id=request.preview_operation_id,
    )
    operation = replace(operation, digest=_backfill_digest(operation, payload))
    operation = _insert_backfill(owner, projection_id, operation, payload)
    existing_epoch = _existing_backfill_epoch(
        owner, projection_id, operation.operation_id
    )
    if existing_epoch is not None:
        if (
            existing_epoch.fence_history_id != request.fence_history_id
            or existing_epoch.fence_recorded_at != request.fence_recorded_at
        ):
            _fail(ErrorCode.REQUEST_CONFLICT)
        return operation, existing_epoch
    decision = EpochDecisionRefBackfillStart(
        "backfill_start",
        operation.operation_id,
        request.preview_operation_id,
        payload.ruleset_revision,
    )
    epoch = EpochRow(
        projection_id,
        request.epoch_id,
        kind,
        EpochState.PREPARED,
        Revision(0),
        request.accepted_at,
        payload.window_start,
        payload.window_end,
        payload.discovery_cutoff,
        decision,
        None,
        None,
        request.fence_history_id,
        request.fence_recorded_at,
        None,
        False,
        None,
    )
    partition_ref = PartitionRefSourceWindow("source_window")
    partition = EpochPartitionRow(
        projection_id,
        request.epoch_id,
        partition_key(projection_id, partition_ref),
        PartitionProgress(
            partition_ref, PartitionState.NOT_STARTED, Count(0), Count(0), None, None
        ),
        Revision(0),
    )
    epochs.start_epoch(owner, projection_id, epoch, (partition,))
    _owner_execute(
        owner,
        "UPDATE projections SET daemon_paused=0 WHERE projection_id=?",
        (projection_id.value,),
    )
    return operation, epoch


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
    if operation.command not in {
        LocalCommandKind.BACKFILL_PREVIEW,
        LocalCommandKind.BACKFILL_START,
    }:
        return operation, None
    rows = _owner_fetchall(
        owner,
        f"SELECT {_BACKFILL_COLUMNS} FROM operation_backfill "
        "WHERE projection_id=? AND operation_id=? LIMIT 2",
        (projection.value, operation_id.value),
    )
    if len(rows) != 1:
        _fail(ErrorCode.CONSISTENCY_FAILURE)
    return operation, _payload_from_row(rows[0])
