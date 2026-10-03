"""Metadata-only credential replacement CAS operations."""

from facet.contracts import ErrorCode, LocalId, ProjectionId, Role

from ..codecs import StorageFailure, encode_scalar, timestamp_to_sql
from ..models import CredentialChangeRow, WriteReceipt
from .base import _decode, _insert, _mutating, _query, _require_row

__all__ = (
    "get_change",
    "get_open_change",
    "begin_change",
    "mark_validated",
    "commit_change",
    "abandon_change",
    "mark_attention",
)

_KINDS = {"authorize", "reauthorize", "refresh"}
_PHASES = {"requesting", "validated", "committed", "abandoned", "attention"}
_POLICIES = {
    "source_readonly",
    "source_convenience",
    "target_default",
    "target_labels",
}
_GRANTS = {
    "authorization_explicit",
    "authorization_omitted_equal",
    "refresh_explicit",
    "refresh_omitted_inherited",
}
_SCOPES = {
    "gmail_insert",
    "gmail_labels",
    "gmail_modify",
    "gmail_readonly",
}
_POLICY_SCOPES = {
    "source_readonly": ("gmail_readonly",),
    "source_convenience": ("gmail_modify",),
    "target_default": ("gmail_insert", "gmail_readonly"),
    "target_labels": ("gmail_insert", "gmail_labels", "gmail_readonly"),
}


def _fail(code: ErrorCode) -> None:
    raise StorageFailure(code)


def _validate(row: CredentialChangeRow) -> None:
    _require_row(row.projection_id, "credential_changes", row)
    if (
        row.kind not in _KINDS
        or row.phase not in _PHASES
        or row.scope_policy not in _POLICIES
        or row.old_revision.value + 1 != row.new_revision.value
        or (row.kind == "authorize" and row.old_revision.value != 0)
        or (row.kind != "authorize" and row.old_revision.value < 1)
        or row.updated_at.value < row.started_at.value
    ):
        _fail(ErrorCode.INVALID_INPUT)
    if row.grant_kind is not None and row.grant_kind not in _GRANTS:
        _fail(ErrorCode.INVALID_INPUT)
    expected_scopes = ",".join(_POLICY_SCOPES[row.scope_policy])
    if row.granted_scopes is not None and (
        type(row.granted_scopes) is not str
        or row.granted_scopes != expected_scopes
        or any(scope not in _SCOPES for scope in row.granted_scopes.split(","))
    ):
        _fail(ErrorCode.INVALID_INPUT)
    if row.phase == "requesting" and (
        row.envelope_digest is not None
        or row.grant_kind is not None
        or row.granted_scopes is not None
        or row.error is not None
    ):
        _fail(ErrorCode.INVALID_INPUT)
    if row.phase in {"validated", "committed"} and (
        row.envelope_digest is None
        or row.grant_kind is None
        or row.granted_scopes != expected_scopes
        or row.error is not None
    ):
        _fail(ErrorCode.INVALID_INPUT)
    if row.phase in {"abandoned", "attention"} and row.error is None:
        _fail(ErrorCode.INVALID_INPUT)


def _find(uow, projection_id: ProjectionId, role: Role, change_id):
    columns = (
        "projection_id",
        "state_instance_id",
        "change_id",
        "role",
        "kind",
        "phase",
        "old_revision",
        "new_revision",
        "binding_revision",
        "scope_policy_revision",
        "operation_id",
        "supersedes_change_id",
        "envelope_digest",
        "scope_policy",
        "grant_kind",
        "granted_scopes",
        "grant_parent_revision",
        "grant_observed_at",
        "profile_verified_at",
        "expires_at",
        "started_at",
        "updated_at",
        "error",
    )
    rows = _query(
        uow,
        "SELECT "
        + ",".join(columns)
        + " FROM credential_changes WHERE projection_id=? AND role=? AND change_id=?",
        (projection_id.value, role.value, change_id.value),
        maximum=1,
    )
    if not rows:
        return None
    row = _decode(uow, projection_id, "credential_changes", rows[0])
    _validate(row)
    return row


def get_change(context, projection_id: ProjectionId, role: Role, change_id):
    if type(role) is not Role:
        _fail(ErrorCode.INVALID_INPUT)
    return _find(context, projection_id, role, change_id)


def get_open_change(context, projection_id: ProjectionId, role: Role):
    """Read a role's unresolved change through the owner transaction."""

    if type(role) is not Role:
        _fail(ErrorCode.INVALID_INPUT)
    rows = _query(
        context,
        "SELECT change_id FROM credential_changes WHERE projection_id=? AND role=? "
        "AND phase IN('requesting','validated','attention') LIMIT 1",
        (projection_id.value, role.value),
        maximum=1,
    )
    if not rows:
        return None
    return _find(context, projection_id, role, LocalId(rows[0][0]))


@_mutating
def begin_change(uow, projection_id: ProjectionId, row: CredentialChangeRow):
    _validate(row)
    if row.projection_id != projection_id or row.phase != "requesting":
        _fail(ErrorCode.INVALID_INPUT)
    if row.operation_id is not None:
        auth = uow._execute(
            "SELECT o.command,a.role,a.expected_credential_revision,"
            "a.expected_role_binding_revision,a.expected_policy_revision "
            "FROM operations o JOIN operation_auth a "
            "ON a.projection_id=o.projection_id AND a.operation_id=o.operation_id "
            "WHERE o.projection_id=? AND o.operation_id=?",
            (projection_id.value, row.operation_id.value),
        ).fetchone()
        if auth is None or auth[0] not in {"auth_authorize", "auth_reauthorize"}:
            _fail(ErrorCode.REQUEST_LINEAGE_MISMATCH)
        if (
            auth[1] != row.role.value
            or auth[2] != row.old_revision.value
            or auth[3] != row.binding_revision.value
            or auth[4] != row.scope_policy_revision.value
        ):
            _fail(ErrorCode.REQUEST_LINEAGE_MISMATCH)
    unresolved = uow._execute(
        "SELECT 1 FROM credential_changes WHERE projection_id=? AND role=? "
        "AND phase IN('requesting','validated','attention') LIMIT 1",
        (projection_id.value, row.role.value),
    ).fetchone()
    if unresolved is not None:
        _fail(ErrorCode.REQUEST_CONFLICT)
    _insert(uow, projection_id, "credential_changes", row)
    return WriteReceipt("created", row.change_id, row.new_revision)


@_mutating
def mark_validated(uow, projection_id: ProjectionId, row: CredentialChangeRow):
    _validate(row)
    if row.projection_id != projection_id or row.phase != "validated":
        _fail(ErrorCode.INVALID_INPUT)
    current = _find(uow, projection_id, row.role, row.change_id)
    if current is None or current.phase != "requesting":
        _fail(ErrorCode.REQUEST_CONFLICT)
    if (
        current.state_instance_id != row.state_instance_id
        or current.old_revision != row.old_revision
        or current.new_revision != row.new_revision
        or current.binding_revision != row.binding_revision
        or current.scope_policy_revision != row.scope_policy_revision
    ):
        _fail(ErrorCode.REQUEST_LINEAGE_MISMATCH)
    uow._execute(
        "UPDATE credential_changes SET phase=?,envelope_digest=?,grant_kind=?,"
        "granted_scopes=?,grant_parent_revision=?,grant_observed_at=?,"
        "profile_verified_at=?,expires_at=?,updated_at=?,error=NULL "
        "WHERE projection_id=? AND change_id=? AND role=? AND phase='requesting'",
        (
            row.phase,
            encode_scalar(row.envelope_digest),
            row.grant_kind,
            row.granted_scopes,
            encode_scalar(row.grant_parent_revision),
            encode_scalar(row.grant_observed_at),
            timestamp_to_sql(row.profile_verified_at),
            timestamp_to_sql(row.expires_at),
            timestamp_to_sql(row.updated_at),
            projection_id.value,
            row.change_id.value,
            row.role.value,
        ),
    )
    return WriteReceipt("updated", row.change_id, row.new_revision)


@_mutating
def commit_change(uow, projection_id: ProjectionId, row: CredentialChangeRow):
    if type(row) is not CredentialChangeRow or row.projection_id != projection_id:
        _fail(ErrorCode.INVALID_INPUT)
    current = _find(uow, projection_id, row.role, row.change_id)
    if current is None or current != row or row.phase != "validated":
        _fail(ErrorCode.REQUEST_CONFLICT)
    from .bindings import publish_refreshed_credential

    publish_refreshed_credential(
        uow,
        projection_id,
        row.role,
        row.binding_revision,
        row.old_revision,
        row.new_revision,
        row.profile_verified_at,
    )
    uow._execute(
        "UPDATE credential_changes SET phase='committed',updated_at=? "
        "WHERE projection_id=? AND change_id=? AND role=? AND phase='validated'",
        (
            timestamp_to_sql(row.updated_at),
            projection_id.value,
            row.change_id.value,
            row.role.value,
        ),
    )
    return WriteReceipt("updated", row.change_id, row.new_revision)


@_mutating
def abandon_change(
    uow, projection_id: ProjectionId, role: Role, change_id, error: ErrorCode
):
    if type(role) is not Role or type(error) is not ErrorCode:
        _fail(ErrorCode.INVALID_INPUT)
    current = _find(uow, projection_id, role, change_id)
    if current is None or current.phase not in {"requesting", "validated"}:
        _fail(ErrorCode.REQUEST_CONFLICT)
    uow._execute(
        "UPDATE credential_changes SET phase='abandoned',error=?,updated_at=? "
        "WHERE projection_id=? AND role=? AND change_id=? "
        "AND phase IN('requesting','validated')",
        (
            error.value,
            timestamp_to_sql(current.updated_at),
            projection_id.value,
            role.value,
            change_id.value,
        ),
    )
    return WriteReceipt("updated", change_id, current.new_revision)


@_mutating
def mark_attention(
    uow, projection_id: ProjectionId, role: Role, change_id, error: ErrorCode
):
    """Retain a durable attention state after file publication uncertainty.

    A credential file is replaced before the binding CAS can commit.  If the
    following transaction has an unknown outcome, callers must not abandon the
    change as if the old file were still authoritative.  This transition keeps
    the unresolved row visible for restart/reconciliation while refusing to
    guess whether the binding CAS committed.
    """

    if type(role) is not Role or type(error) is not ErrorCode:
        _fail(ErrorCode.INVALID_INPUT)
    current = _find(uow, projection_id, role, change_id)
    if current is None or current.phase not in {"requesting", "validated", "attention"}:
        _fail(ErrorCode.REQUEST_CONFLICT)
    uow._execute(
        "UPDATE credential_changes SET phase='attention',error=?,updated_at=? "
        "WHERE projection_id=? AND role=? AND change_id=? "
        "AND phase IN('requesting','validated','attention')",
        (
            error.value,
            timestamp_to_sql(current.updated_at),
            projection_id.value,
            role.value,
            change_id.value,
        ),
    )
    return WriteReceipt("updated", change_id, current.new_revision)
