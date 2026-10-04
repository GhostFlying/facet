"""Typed profile verification publication for the existing binding rows."""

from facet.contracts import (
    BindingState,
    ErrorCode,
    ProjectionId,
    Revision,
    Role,
    Timestamp,
)

from ..codecs import StorageFailure, timestamp_to_sql
from ..models import WriteReceipt
from .base import _get, _mutating

__all__ = ("verify_bindings", "verify_profile", "publish_refreshed_credential")


def _conflict(code: ErrorCode = ErrorCode.REQUEST_CONFLICT) -> None:
    raise StorageFailure(code)


@_mutating
def verify_bindings(uow, projection_id: ProjectionId, verified):
    """Publish both verified profiles in one existing-writer transaction.

    Only the closed credential verification values may cross this boundary. No
    arbitrary row or provider payload enters storage here.
    """

    from facet.gmail.credentials import VerifiedBindings, VerifiedProfile

    if type(verified) is not VerifiedBindings:
        _conflict(ErrorCode.INVALID_INPUT)
    profiles = getattr(verified, "profiles", None)
    if (
        type(profiles) is not tuple
        or len(profiles) != 2
        or any(type(profile) is not VerifiedProfile for profile in profiles)
    ):
        _conflict(ErrorCode.INVALID_INPUT)
    if {profile.role for profile in profiles} != {Role.SOURCE, Role.TARGET}:
        _conflict(ErrorCode.INVALID_INPUT)
    current = {
        role: _get(uow, projection_id, "bindings", (("role", role),)) for role in Role
    }
    if any(row is None for row in current.values()):
        _conflict(ErrorCode.CONSISTENCY_FAILURE)
    for profile in profiles:
        row = current[profile.role]
        if (
            profile.projection_id != projection_id
            or profile.binding_revision != row.binding_revision
            or profile.credential_revision.value < 1
            or profile.account.value.casefold() != row.declared_address.value.casefold()
        ):
            _conflict(ErrorCode.BINDING_MISMATCH)
        if row.state is BindingState.VERIFIED:
            verified_address = (
                None
                if row.verified_address is None
                else row.verified_address.value.casefold()
            )
            if (
                verified_address != profile.account.value.casefold()
                or row.credential_revision != profile.credential_revision
            ):
                _conflict(ErrorCode.BINDING_MISMATCH)
            continue
        if row.state is not BindingState.VERIFICATION_PENDING:
            _conflict(ErrorCode.BINDING_PENDING)
        uow._execute(
            "UPDATE bindings SET verified_address=?,credential_revision=?,state=?,"
            "verified_at=? WHERE projection_id=? AND role=? AND binding_revision=?",
            (
                profile.account.value,
                profile.credential_revision.value,
                BindingState.VERIFIED.value,
                timestamp_to_sql(profile.verified_at),
                projection_id.value,
                profile.role.value,
                row.binding_revision.value,
            ),
        )
    refreshed = {
        role: _get(uow, projection_id, "bindings", (("role", role),)) for role in Role
    }
    addresses = tuple(row.verified_address for row in refreshed.values())
    if any(address is None for address in addresses):
        _conflict(ErrorCode.BINDING_PENDING)
    if addresses[0].value.casefold() == addresses[1].value.casefold():
        _conflict(ErrorCode.BINDING_MISMATCH)
    projection = _get(uow, projection_id, "projections", ())
    if projection is None:
        _conflict(ErrorCode.CONSISTENCY_FAILURE)
    if projection.binding_state is not BindingState.VERIFIED:
        uow._execute(
            "UPDATE projections SET binding_state=? WHERE projection_id=?",
            (BindingState.VERIFIED.value, projection_id.value),
        )
    return tuple(
        WriteReceipt("updated", projection_id, Revision(row.binding_revision.value))
        for row in refreshed.values()
    )


@_mutating
def verify_profile(uow, projection_id: ProjectionId, profile):
    """Publish one independently consented role without faking readiness."""

    from facet.gmail.credentials import VerifiedProfile

    if type(profile) is not VerifiedProfile or profile.projection_id != projection_id:
        _conflict(ErrorCode.INVALID_INPUT)
    row = _get(uow, projection_id, "bindings", (("role", profile.role),))
    if row is None:
        _conflict(ErrorCode.CONSISTENCY_FAILURE)
    if (
        profile.binding_revision != row.binding_revision
        or profile.account.value.casefold() != row.declared_address.value.casefold()
        or profile.credential_revision.value < 1
    ):
        _conflict(ErrorCode.BINDING_MISMATCH)
    if row.state is BindingState.VERIFIED:
        if (
            row.verified_address is None
            or row.verified_address.value.casefold() != profile.account.value.casefold()
            or row.credential_revision != profile.credential_revision
        ):
            _conflict(ErrorCode.BINDING_MISMATCH)
    elif row.state is BindingState.VERIFICATION_PENDING:
        uow._execute(
            "UPDATE bindings SET verified_address=?,credential_revision=?,state=?,"
            "verified_at=? WHERE projection_id=? AND role=? AND binding_revision=?",
            (
                profile.account.value,
                profile.credential_revision.value,
                BindingState.VERIFIED.value,
                timestamp_to_sql(profile.verified_at),
                projection_id.value,
                profile.role.value,
                row.binding_revision.value,
            ),
        )
    else:
        _conflict(ErrorCode.BINDING_PENDING)
    refreshed = {
        role: _get(uow, projection_id, "bindings", (("role", role),)) for role in Role
    }
    if all(
        item is not None and item.state is BindingState.VERIFIED
        for item in refreshed.values()
    ):
        addresses = tuple(item.verified_address for item in refreshed.values())
        if any(address is None for address in addresses):
            _conflict(ErrorCode.BINDING_PENDING)
        if addresses[0].value.casefold() == addresses[1].value.casefold():
            _conflict(ErrorCode.BINDING_MISMATCH)
        uow._execute(
            "UPDATE projections SET binding_state=? WHERE projection_id=?",
            (BindingState.VERIFIED.value, projection_id.value),
        )
    return WriteReceipt("updated", projection_id, profile.binding_revision)


@_mutating
def publish_refreshed_credential(
    uow,
    projection_id: ProjectionId,
    role: Role,
    binding_revision: Revision,
    old_credential_revision: Revision,
    new_credential_revision: Revision,
    verified_at: Timestamp,
):
    """Advance one already-verified role after a credential CAS."""

    if (
        type(role) is not Role
        or type(binding_revision) is not Revision
        or type(old_credential_revision) is not Revision
        or type(new_credential_revision) is not Revision
        or type(verified_at) is not Timestamp
        or new_credential_revision.value != old_credential_revision.value + 1
    ):
        _conflict(ErrorCode.INVALID_INPUT)
    row = _get(uow, projection_id, "bindings", (("role", role),))
    if row is None:
        _conflict(ErrorCode.CONSISTENCY_FAILURE)
    if (
        row.state is not BindingState.VERIFIED
        or row.binding_revision != binding_revision
        or row.credential_revision != old_credential_revision
        or row.verified_address is None
    ):
        _conflict(ErrorCode.REQUEST_CONFLICT)
    cursor = uow._execute(
        "UPDATE bindings SET credential_revision=?,verified_at=? "
        "WHERE projection_id=? AND role=? AND binding_revision=? "
        "AND state='verified' AND credential_revision=?",
        (
            new_credential_revision.value,
            timestamp_to_sql(verified_at),
            projection_id.value,
            role.value,
            binding_revision.value,
            old_credential_revision.value,
        ),
    )
    if cursor.rowcount != 1:
        _conflict(ErrorCode.REQUEST_CONFLICT)
    return WriteReceipt("updated", projection_id, new_credential_revision)
