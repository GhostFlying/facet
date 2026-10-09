"""Complete CLI entry composed from the existing guarded business operations."""

import hashlib
import json
import sys
from datetime import UTC, datetime
from types import SimpleNamespace

from facet.config import ConfigError, load_config
from facet.contracts import BindingState, ErrorCode, LocalId, ProjectionId
from facet.db.command_store import _backfill_guards
from facet.gmail.service_factory import GoogleGmailServiceFactory
from facet.private_paths import read_managed_config, select_paths
from facet.runtime.foreground_runtime import prepare_credentials
from facet.runtime.state_owner import StateOwner


def _confirm(options):
    if getattr(options, "yes", False):
        return
    if getattr(options, "json", False) or not all(
        stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)
    ):
        raise ConfigError(ErrorCode.CONFIRMATION_REQUIRED)
    print(
        "Continue the saved scope, or select current rules and the default "
        "six-month window for a new operation? Replay retains its saved scope. "
        "Admission "
        "discloses complete available non-draft threads, attachments, other "
        "participants, own replies and future thread messages. [yes/no]",
        flush=True,
    )
    try:
        confirmed = input().strip().lower() == "yes"
    except EOFError:
        confirmed = False
    if not confirmed:
        raise ConfigError(ErrorCode.CONFIRMATION_REQUIRED)


def _keys(owner, config, caller_id):
    namespace = owner.owner_info.request_namespace.value
    if caller_id is not None:
        identity = ("explicit", namespace, LocalId(caller_id).value)
    else:
        with owner.session.transaction() as uow:
            projection, _, _, _ = _backfill_guards(uow, config.projection.id)
        # Credential/binding refreshes and rule changes must not alter this
        # complete-sync request identity. Rule changes are represented by their
        # own automatic scopes; the saved complete-sync scope remains replayable.
        now = datetime.now(UTC)
        identity = (
            "default",
            namespace,
            config.projection.id.value,
            projection.config_revision.value,
            now.year,
            now.month,
        )
    encoded = json.dumps(identity, separators=(",", ":")).encode()
    keys = []
    for kind in (b"preview", b"start"):
        value = bytearray(
            hashlib.sha256(b"facet-sync-v1\x00" + kind + b"\x00" + encoded).digest()[
                :16
            ]
        )
        value[6] = (value[6] & 0x0F) | 0x40
        value[8] = (value[8] & 0x3F) | 0x80
        keys.append(LocalId(value.hex()).value)
    return tuple(keys)


def synchronize(options):
    """Select once, then keep the single writer for guarded start and execution."""

    from facet.cli.bootstrap import (
        _backfill_preview,
        _backfill_start,
        _resolved_poll_interval,
        _run_foreground_service,
        _run_once_production,
    )

    if getattr(options, "config_path", None) is not None:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    if not 1 <= options.port <= 65535 or not isinstance(options.host, str):
        raise ConfigError(ErrorCode.INVALID_INPUT)
    caller_id = getattr(options, "request_id", None)
    if caller_id is not None:
        LocalId(caller_id)
    _confirm(options)
    paths = select_paths(getattr(options, "state_dir", None), None)
    raw = read_managed_config(paths)
    config = load_config(raw)
    _resolved_poll_interval(options, config)
    if (
        getattr(options, "projection", None) is not None
        and ProjectionId(options.projection) != config.projection.id
    ):
        raise ConfigError(ErrorCode.BINDING_MISMATCH)
    owner = StateOwner.open(paths.root, config)
    try:
        owner.verify_config_artifact(raw)
        if any(
            binding is None or binding.state is not BindingState.VERIFIED
            for binding in owner.bindings().values()
        ):
            raise ConfigError(ErrorCode.BINDING_PENDING)
        prepare_credentials(owner, config, GoogleGmailServiceFactory())
        preview_key, start_key = _keys(owner, config, caller_id)
        preview, warnings = _backfill_preview(
            SimpleNamespace(request_id=preview_key), owner=owner, config=config
        )
        if warnings:
            raise ConfigError(ErrorCode.MAINTENANCE_REQUIRED)
        _, warnings = _backfill_start(
            SimpleNamespace(
                request_id=start_key, preview_id=preview["preview_id"], yes=True
            ),
            owner=owner,
            config=config,
        )
        if warnings:
            raise ConfigError(ErrorCode.MAINTENANCE_REQUIRED)
        if options.once:
            result, warnings = _run_once_production(owner, config)
        else:
            result, warnings = _run_foreground_service(
                options, owner=owner, config=config
            )
        return {
            "scope": "default_six_calendar_months",
            "disclosure": preview["disclosure"],
            "cycle": result,
        }, warnings
    finally:
        owner.close()
