"""Typed profile verification publication for the existing binding rows."""

from facet.contracts import BindingState, ErrorCode, ProjectionId, Revision, Role

from ..codecs import StorageFailure, timestamp_to_sql
from ..models import WriteReceipt
from .base import _get, _mutating

__all__ = ("verify_bindings",)


def _conflict(code: ErrorCode = ErrorCode.REQUEST_CONFLICT) -> None:
    raise StorageFailure(code)


@_mutating
def verify_bindings(uow, projection_id: ProjectionId, verified):
    """Publish both verified profiles in one existing-writer transaction.

    ``verified`` is intentionally duck-typed at this repository boundary: the
    credential manager owns the profile value and validates its exact class
    before calling this function. No arbitrary row or provider payload enters
    storage here.
    """

    profiles = getattr(verified, "profiles", None)
    if type(profiles) is not tuple or len(profiles) != 2:
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
