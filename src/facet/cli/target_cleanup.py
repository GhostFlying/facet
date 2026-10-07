"""CLI-only, explicit dedicated-target maintenance composition."""

from __future__ import annotations

import hashlib
import json
import sys

from facet.contracts import BindingState, ErrorCode, LocalId, Role
from facet.db.codecs import StorageFailure
from facet.gmail.credential_models import ScopePolicy, policy_scopes
from facet.gmail.credentials import CredentialManager, ProfileEvidence
from facet.gmail.service_factory import GoogleGmailServiceFactory
from facet.maintenance.target_cleanup import CleanupJournal, check_profile
from facet.runtime.state_owner import StateOwner

from .status import _paths_and_config

WARNINGS = (
    "permanent_target_deletion_not_undoable",
    "existing_mappings_and_insert_recovery_not_reset",
    "cleanup_may_remove_insert_recovery_evidence",
    "completion_only_covers_preview_not_new_arrivals",
)


def _identity(owner, config, raw):
    bindings = owner.bindings()
    declared = {
        Role.SOURCE: config.projection.source_email,
        Role.TARGET: config.projection.target_email,
    }
    for role, binding in bindings.items():
        if binding is None or binding.state is not BindingState.VERIFIED:
            raise StorageFailure(ErrorCode.BINDING_PENDING)
        if binding.verified_address is None or (
            binding.verified_address.value.casefold() != declared[role].casefold()
        ):
            raise StorageFailure(ErrorCode.BINDING_MISMATCH)
    if declared[Role.SOURCE].casefold() == declared[Role.TARGET].casefold():
        raise StorageFailure(ErrorCode.BINDING_MISMATCH)
    fields = [
        config.projection.id.value,
        owner.owner_info.state_instance_id.value,
        hashlib.sha256(raw).hexdigest(),
        *[
            (
                role.value,
                declared[role].casefold(),
                bindings[role].binding_revision.value,
            )
            for role in Role
        ],
    ]
    return hashlib.sha256(
        json.dumps(fields, separators=(",", ":")).encode()
    ).hexdigest()


def _preview_service(owner, paths, config, factory):
    from facet.gmail.refresh_exchange import refresh_google

    manager = CredentialManager(paths.root, config, owner)
    scopes = policy_scopes(ScopePolicy.TARGET_DEFAULT, Role.TARGET)
    manager.reconcile_interrupted_refresh(Role.TARGET)
    manager.ensure_current(
        Role.TARGET,
        lambda role, old: refresh_google(role, old, scopes),
        lambda role, secret, granted: ProfileEvidence(
            factory.profile_account(role, secret), granted
        ),
    )
    return factory.service(Role.TARGET, manager.snapshot(Role.TARGET))


def run_cleanup(options):
    if getattr(options, "public", False):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    if options.action not in {"preview", "execute", "status"}:
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    if options.action == "status":
        LocalId(options.preview)
        paths, _raw, _config = _paths_and_config(options)
        journal = CleanupJournal(paths.root, readonly=True)
        try:
            return journal.receipt(options.preview), WARNINGS
        finally:
            journal.close()
    LocalId(options.request_id)
    if options.action == "execute":
        LocalId(options.preview)
        if not 1024 <= options.port <= 65535:
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        if not options.yes:
            raise StorageFailure(ErrorCode.CONFIRMATION_REQUIRED)
    paths, raw, config = _paths_and_config(options)
    if options.action == "execute" and (
        type(options.confirm_target) is not str
        or options.confirm_target.casefold()
        != config.projection.target_email.casefold()
    ):
        raise StorageFailure(ErrorCode.CONFIRMATION_REQUIRED)
    owner = StateOwner.open(paths.root, config)
    journal = None
    try:
        owner.verify_config_artifact(raw)
        identity = _identity(owner, config, raw)
        journal = CleanupJournal(paths.root)
        if options.action == "preview":
            factory = GoogleGmailServiceFactory()
            service = _preview_service(owner, paths, config, factory)
            check_profile(service, config.projection.target_email)
            identity = _identity(owner, config, raw)
            with owner.session.transaction() as uow:
                mappings = uow._execute(
                    "SELECT COUNT(*) FROM message_mappings WHERE projection_id=?",
                    (owner.projection_id.value,),
                ).fetchone()[0]
                unknown = uow._execute(
                    "SELECT COUNT(*) FROM insert_attempts WHERE projection_id=? "
                    "AND state IN ('dispatch_started','pending_recovery')",
                    (owner.projection_id.value,),
                ).fetchone()[0]
            return journal.preview(
                service,
                request_id=options.request_id,
                identity=identity,
                mappings=mappings,
                unknown_inserts=unknown,
            ), WARNINGS
        # A completed execution is an offline receipt, even after expiry. Its
        # original request and exact target confirmation are still required.
        row = journal.get(options.preview)
        if row["state"] != "completed" and (
            getattr(options, "json", False)
            or not sys.stdin.isatty()
            or not sys.stderr.isatty()
        ):
            raise StorageFailure(ErrorCode.CONFIRMATION_REQUIRED)
        if not journal.start(
            preview_id=options.preview,
            request_id=options.request_id,
            identity=identity,
            confirmation=options.confirm_target,
        ):
            return journal.receipt(options.preview), WARNINGS
        from facet.cli.bootstrap import _setup_oauth_callback_timeout
        from facet.gmail.cleanup_oauth import authorize_cleanup
        from facet.gmail.cleanup_transport import build_cleanup_service
        from facet.gmail.oauth import read_desktop_client

        access = authorize_cleanup(
            read_desktop_client(options.oauth_client),
            port=options.port,
            callback_timeout_seconds=_setup_oauth_callback_timeout(),
        )
        service = build_cleanup_service(access.token.value)
        try:
            check_profile(service, config.projection.target_email)
            # No normal credential envelope is loaded or replaced for execute.
            if _identity(owner, config, raw) != identity:
                raise StorageFailure(ErrorCode.BINDING_MISMATCH)
            return journal.execute(service, options.preview), WARNINGS
        finally:
            service.close()
    finally:
        if journal is not None:
            journal.close()
        owner.close()
