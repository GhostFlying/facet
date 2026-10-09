"""Offline inspection of the sealed current admission ruleset."""

from __future__ import annotations

from facet.config import ConfigError
from facet.contracts import ErrorCode, LocalId
from facet.db.codecs import StorageFailure, timestamp_from_sql

from .status import (
    _check_config_artifact,
    _open_read_only,
    _paths_and_config,
)


def _time(value: int) -> str:
    return (
        timestamp_from_sql(value)
        .value.astimezone()
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def read_rules(options, *, show: bool = False) -> dict:
    """Read aggregate or private rule metadata without taking the writer lock."""

    if show and not getattr(options, "private_metadata", False):
        raise ConfigError(ErrorCode.SCOPE_REQUIRED)
    rule_id = None
    if show:
        try:
            rule_id = LocalId(options.rule_id)
        except (TypeError, ValueError):
            raise ConfigError(ErrorCode.INVALID_INPUT) from None

    paths, raw, config = _paths_and_config(options)
    connection = None
    try:
        connection = _open_read_only(paths.db)
        connection.execute("BEGIN")
        _check_config_artifact(connection, config.projection.id.value, raw)
        projection_id = config.projection.id.value
        projection = connection.execute(
            "SELECT ruleset_revision FROM projections WHERE projection_id=? LIMIT 2",
            (projection_id,),
        ).fetchall()
        if len(projection) != 1:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        revision = int(projection[0][0])
        ruleset = connection.execute(
            "SELECT sealed FROM rulesets WHERE projection_id=? AND revision=? LIMIT 2",
            (projection_id, revision),
        ).fetchall()
        if len(ruleset) != 1 or ruleset[0][0] != 1:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        if not show:
            count = connection.execute(
                "SELECT COUNT(*) FROM ruleset_members WHERE projection_id=? "
                "AND ruleset_revision=?",
                (projection_id, revision),
            ).fetchone()[0]
            connection.execute("COMMIT")
            return {
                "ruleset_revision": revision,
                "rule_count": int(count),
            }
        row = connection.execute(
            "SELECT r.rule_id,r.kind,r.normalized_value,r.current_revision,"
            "rr.revision,rr.enabled,rr.effective_at,rr.origin,rr.policy_version "
            "FROM ruleset_members m JOIN rules r ON r.projection_id=m.projection_id "
            "AND r.rule_id=m.rule_id JOIN rule_revisions rr "
            "ON rr.projection_id=m.projection_id AND rr.rule_id=m.rule_id "
            "AND rr.revision=m.rule_revision WHERE m.projection_id=? "
            "AND m.ruleset_revision=? AND m.rule_id=? LIMIT 2",
            (projection_id, revision, rule_id.value),
        ).fetchall()
        if len(row) != 1:
            raise ConfigError(ErrorCode.OWNER_UNAVAILABLE)
        (
            stored_id,
            kind,
            normalized_value,
            current_revision,
            rule_revision,
            enabled,
            effective_at,
            origin,
            policy_version,
        ) = row[0]
        if stored_id != rule_id.value or current_revision != rule_revision:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        connection.execute("COMMIT")
        return {
            "rule_id": stored_id,
            "kind": kind,
            "normalized_value": normalized_value,
            "revision": int(rule_revision),
            "enabled": bool(enabled),
            "effective_at": _time(effective_at),
            "origin": origin,
            "policy_version": policy_version,
            "ruleset_revision": revision,
        }
    except BaseException:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()


__all__ = ("read_rules",)
