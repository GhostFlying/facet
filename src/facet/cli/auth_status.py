"""Offline, metadata-only Gmail credential status inspection."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path

from facet.contracts import BindingState, ErrorCode, Role, Timestamp
from facet.db.codecs import StorageFailure
from facet.db.repositories.serialization import COLUMNS, _decode_row
from facet.gmail.credential_codec import encode_envelope
from facet.gmail.credentials import _expected_policy, _read_credential

from .status import (
    _check_addresses,
    _check_config_artifact,
    _open_read_only,
    _paths_and_config,
)


def _time(value: Timestamp | None) -> str | None:
    if value is None:
        return None
    return value.value.astimezone().isoformat(timespec="microseconds")


def _file_stamp(path: Path) -> tuple[int, int, int, int, int]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return (0, 0, 0, 0, 0)
    except OSError:
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE) from None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o77
        or info.st_nlink != 1
    ):
        raise StorageFailure(ErrorCode.SCOPE_REQUIRED)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _stable_read(path: Path, role: Role):
    before = _file_stamp(path)
    first = _read_credential(path, role)
    middle = _file_stamp(path)
    second = _read_credential(path, role)
    after = _file_stamp(path)
    if (
        before != middle
        or middle != after
        or encode_envelope(first) != encode_envelope(second)
    ):
        # A refresh/replacement crossed this inspection.  Do not report either
        # side as verified when the SQLite snapshot and file are not coherent.
        raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
    return second


def _decode_binding(row: tuple):
    try:
        return _decode_row("bindings", row)
    except (KeyError, TypeError, ValueError, StorageFailure):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None


def _change_row(connection: sqlite3.Connection, projection: str, role: Role, change_id):
    rows = connection.execute(
        "SELECT "
        + ",".join(COLUMNS["credential_changes"])
        + " FROM credential_changes WHERE projection_id=? AND role=? "
        + "AND change_id=? LIMIT 2",
        (projection, role.value, change_id.value),
    ).fetchall()
    if len(rows) != 1:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    try:
        return _decode_row("credential_changes", rows[0])
    except (KeyError, TypeError, ValueError, StorageFailure):
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None


def _has_open_change(
    connection: sqlite3.Connection, projection: str, role: Role
) -> bool:
    rows = connection.execute(
        "SELECT 1 FROM credential_changes WHERE projection_id=? AND role=? "
        "AND phase IN('requesting','validated','attention') LIMIT 2",
        (projection, role.value),
    ).fetchall()
    if len(rows) > 1:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    return bool(rows)


def _base(binding, config, role: Role):
    result = {
        "role": binding.role.value,
        "binding_state": binding.state.value,
        "scope_policy": _expected_policy(config, role).value,
        "unresolved_change": False,
    }
    if binding.verified_at is not None:
        result["binding_verified_at"] = _time(binding.verified_at)
    return result


def _role_status(
    connection,
    paths,
    config,
    state_instance_id: str,
    binding,
    role: Role,
    sampled_at: Timestamp,
):
    result = _base(binding, config, role)
    projection = config.projection.id.value
    if _has_open_change(connection, projection, role):
        return {
            **result,
            "credential_state": "attention",
            "code": ErrorCode.MAINTENANCE_REQUIRED.value,
            "unresolved_change": True,
        }
    if binding.state is BindingState.MISMATCH:
        return {
            **result,
            "credential_state": "attention",
            "code": ErrorCode.BINDING_MISMATCH.value,
        }
    if binding.state is BindingState.AUTH_REQUIRED:
        return {
            **result,
            "credential_state": "attention",
            "code": (
                ErrorCode.SOURCE_AUTH_REQUIRED.value
                if role is Role.SOURCE
                else ErrorCode.TARGET_AUTH_REQUIRED.value
            ),
        }
    path = paths.credentials / ("source.json" if role is Role.SOURCE else "target.json")
    try:
        envelope = _stable_read(path, role)
    except StorageFailure as error:
        if error.code in {
            ErrorCode.SOURCE_AUTH_REQUIRED,
            ErrorCode.TARGET_AUTH_REQUIRED,
        }:
            state = (
                "pending"
                if binding.state is BindingState.VERIFICATION_PENDING
                else "missing"
            )
        elif error.code is ErrorCode.INVALID_INPUT:
            state = "attention"
        else:
            state = "unknown"
        return {**result, "credential_state": state, "code": error.code.value}

    expected_revision = binding.credential_revision.value + (
        0 if binding.state is BindingState.VERIFIED else 1
    )
    if (
        envelope.projection_id != config.projection.id
        or envelope.state_instance_id.value != state_instance_id
        or envelope.role is not role
        or envelope.scope_policy is not _expected_policy(config, role)
        or envelope.binding_revision != binding.binding_revision
        or envelope.credential_revision.value != expected_revision
        or envelope.account.value.casefold()
        != binding.declared_address.value.casefold()
    ):
        return {
            **result,
            "credential_state": "attention",
            "code": ErrorCode.BINDING_MISMATCH.value,
        }
    if binding.state is not BindingState.VERIFIED:
        return {**result, "credential_state": "pending", "code": None}

    row = _change_row(connection, projection, role, envelope.change_id)
    if (
        row.phase != "committed"
        or row.state_instance_id != envelope.state_instance_id
        or row.new_revision != envelope.credential_revision
        or row.binding_revision != envelope.binding_revision
        or row.scope_policy_revision != envelope.scope_policy_revision
        or row.scope_policy != envelope.scope_policy.value
        or row.envelope_digest is None
        or row.envelope_digest.value
        != hashlib.sha256(encode_envelope(envelope)).hexdigest()
        or row.profile_verified_at != envelope.profile_verified_at
        or row.expires_at != envelope.secret.expires_at
    ):
        return {
            **result,
            "credential_state": "attention",
            "code": ErrorCode.REQUEST_CONFLICT.value,
        }
    return {
        **result,
        "credential_state": (
            "expired"
            if envelope.secret.expires_at.value <= sampled_at.value
            else "verified"
        ),
        "code": None,
        "profile_verified_at": _time(envelope.profile_verified_at),
        "expires_at": _time(envelope.secret.expires_at),
    }


def _public_role(item: dict) -> dict:
    """Project one role onto the existing public RoleStatus boundary."""

    policy_to_mode = {
        "source_readonly": "source_readonly",
        "source_convenience": "source_convenience",
        "target_default": "target_insert_readonly",
        "target_labels": "target_insert_readonly_labels",
    }
    return {
        "role": item["role"],
        "mode": policy_to_mode[item["scope_policy"]],
        "auth_state": item["binding_state"],
        "last_verified_at": item.get("binding_verified_at"),
        "freshness": "stale",
    }


def read_auth_status(options) -> dict:
    """Return an allowlisted offline credential status snapshot."""

    paths, raw, config = _paths_and_config(options)
    connection = None
    try:
        connection = _open_read_only(paths.db)
        connection.execute("BEGIN")
        projection = config.projection.id.value
        _check_config_artifact(connection, projection, raw)
        _check_addresses(connection, config, projection)
        projection_rows = connection.execute(
            "SELECT state_instance_id,binding_state FROM projections "
            "WHERE projection_id=? LIMIT 2",
            (projection,),
        ).fetchall()
        if len(projection_rows) != 1:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        state_instance_id, projection_binding_state = projection_rows[0]
        try:
            projection_binding_state = BindingState(projection_binding_state)
        except (TypeError, ValueError):
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None
        binding_rows = connection.execute(
            "SELECT "
            + ",".join(COLUMNS["bindings"])
            + " FROM bindings WHERE projection_id=? ORDER BY role",
            (projection,),
        ).fetchall()
        bindings = {
            binding.role: binding
            for binding in (_decode_binding(row) for row in binding_rows)
        }
        if set(bindings) != {Role.SOURCE, Role.TARGET}:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        ready_bindings = all(
            binding.state is BindingState.VERIFIED for binding in bindings.values()
        )
        if (projection_binding_state is BindingState.VERIFIED) != ready_bindings:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        sampled_at = Timestamp(datetime.now(UTC))
        roles = []
        for role in (Role.SOURCE, Role.TARGET):
            item = _role_status(
                connection,
                paths,
                config,
                state_instance_id,
                bindings[role],
                role,
                sampled_at,
            )
            if getattr(options, "private_metadata", False):
                item["address"] = (
                    config.projection.source_email
                    if role is Role.SOURCE
                    else config.projection.target_email
                )
            roles.append(
                _public_role(item) if getattr(options, "public", False) else item
            )
        connection.rollback()
        return {
            "offline": True,
            "live_health": "unknown",
            "freshness": "stale",
            "sampled_at": _time(sampled_at),
            "roles": roles,
        }
    finally:
        if connection is not None:
            connection.close()


__all__ = ("read_auth_status",)
