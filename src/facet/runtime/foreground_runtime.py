"""Composition of verified credentials and the foreground projection runner."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import timedelta

from facet.config import Config
from facet.contracts import LocalId, Revision, Role, RuleKind, RuleRef, SourceMode
from facet.db.codecs import PrivateAddress
from facet.gmail.credential_models import (
    AccountAddress,
    ScopePolicy,
    policy_scopes,
)
from facet.gmail.credentials import CredentialManager, ProfileEvidence, ProfileReader
from facet.gmail.retry import ProviderFailure, ProviderStage
from facet.gmail.service_factory import GmailServiceFactory
from facet.gmail.source import SourceAdapter
from facet.gmail.target import TargetAdapter
from facet.projection.current_actions import (
    CurrentActionConsumer,
    finish_baseline,
    initialize_baseline,
)
from facet.sync import ForegroundSync, SyncCycleReceipt

__all__ = ("ForegroundRuntime", "run_foreground_once")


def _policy(config: Config, role: Role) -> ScopePolicy:
    if role is Role.SOURCE:
        return (
            ScopePolicy.SOURCE_READONLY
            if config.projection.source_mode is SourceMode.READONLY
            else ScopePolicy.SOURCE_CONVENIENCE
        )
    return ScopePolicy.TARGET_DEFAULT


class _ProfileProbe(ProfileReader):
    def __init__(self, config: Config, factory: GmailServiceFactory):
        self._config = config
        self._factory = factory

    def get_profile(self, role, secret):
        account = self._factory.profile_account(role, secret)
        if type(account) is not AccountAddress:
            raise ValueError("invalid_input")
        return ProfileEvidence(
            account, policy_scopes(_policy(self._config, role), role)
        )


def load_persisted_admission(owner, config, ruleset_revision=None):
    """Load one sealed ruleset revision into the policy evaluator."""

    from facet.db.repositories.base import _get, _query
    from facet.db.repositories.serialization import COLUMNS
    from facet.projection.admission import AdmissionEvaluator, AdmissionRule
    from facet.projection.rules import normalize_rule

    with owner.session.transaction() as uow:
        projection = _get(uow, owner.projection_id, "projections", ())
        if projection is None:
            raise ValueError("owner_unavailable")
        selected_revision = (
            projection.ruleset_revision
            if ruleset_revision is None
            else ruleset_revision
        )
        if type(selected_revision) is not Revision:
            raise ValueError("invalid_input")
        rows = _query(
            uow,
            "SELECT "
            + ",".join(COLUMNS["ruleset_members"])
            + " FROM ruleset_members WHERE projection_id=? "
            "AND ruleset_revision IN (?,?)",
            (
                owner.projection_id.value,
                selected_revision.value,
                projection.ruleset_revision.value,
            ),
        )
        rules = []
        current_blacklists = []
        for row in rows:
            member = _get(
                uow,
                owner.projection_id,
                "rules",
                (("rule_id", LocalId(row[2])),),
            )
            revision = _get(
                uow,
                owner.projection_id,
                "rule_revisions",
                (("rule_id", LocalId(row[2])), ("revision", Revision(row[3]))),
            )
            if member is None or revision is None:
                raise ValueError("consistency_failure")
            rule = AdmissionRule(
                RuleRef(member.rule_id, revision.revision),
                normalize_rule(member.kind, member.normalized_value.value),
                revision.effective_at,
                revision.enabled,
            )
            if row[1] == selected_revision.value:
                rules.append(rule)
            if (
                row[1] == projection.ruleset_revision.value
                and rule.enabled
                and rule.normalized.kind is RuleKind.BLACKLIST_SENDER
            ):
                current_blacklists.append(rule)
        return AdmissionEvaluator(
            tuple(rules),
            source_account=PrivateAddress(config.projection.source_email),
            ruleset_revision=selected_revision,
            current_blacklists=tuple(current_blacklists),
        )


def _action_consumer(source: SourceAdapter, config: Config, owner):
    from facet.db.action_labels import effective

    labels = source.action_label_map(effective(owner._connection, config.projection.id))
    initialize_baseline(owner, labels)
    finish_baseline(owner, source, labels)
    own_addresses = tuple(
        PrivateAddress(address) for address in config.projection.own_addresses
    )
    return CurrentActionConsumer(
        labels,
        source,
        own_addresses,
        config.projection.source_email,
    )


def prepare_credentials(owner, config, factory):
    """Use the existing refresh/profile guards before any complete-entry work."""

    from facet.gmail.refresh_exchange import refresh_google

    manager = CredentialManager(owner.state_dir, config, owner)
    probe = _ProfileProbe(config, factory)

    def exchange(role, old):
        return refresh_google(role, old, policy_scopes(_policy(config, role), role))

    def refreshed_profile(role, secret, scopes):
        return ProfileEvidence(factory.profile_account(role, secret), scopes)

    if getattr(factory, "supports_refresh", False):
        for role in (Role.SOURCE, Role.TARGET):
            manager.reconcile_interrupted_refresh(role)
            manager.ensure_current(role, exchange, refreshed_profile)
    reactive_roles = set()
    while True:
        try:
            manager.verify_and_publish(probe)
            break
        except ProviderFailure as error:
            if (
                not getattr(factory, "supports_refresh", False)
                or error.status != 401
                or error.provider_stage is not ProviderStage.PROFILE_PROBE
                or error.role in reactive_roles
            ):
                raise
            reactive_roles.add(error.role)
            manager.refresh(error.role, exchange, profile=refreshed_profile)
    return manager.snapshot(Role.SOURCE), manager.snapshot(Role.TARGET)


def _request_token_provider(owner, config, factory, snapshot):
    """One role-local cache; all actual publication stays with the manager."""
    from facet.gmail.credentials import _owner_now
    from facet.gmail.refresh_exchange import refresh_google

    manager = CredentialManager(owner.state_dir, config, owner)
    role = snapshot.role

    def exchange(role, old):
        return refresh_google(role, old, policy_scopes(_policy(config, role), role))

    def profile(role, secret, scopes):
        return ProfileEvidence(factory.profile_account(role, secret), scopes)

    def token(*, force=False):
        nonlocal snapshot
        if force:
            snapshot = manager.refresh(role, exchange, profile=profile)
        elif snapshot.expires_at.value - _owner_now().value <= timedelta(seconds=300):
            snapshot = manager.ensure_current(role, exchange, profile)
        return snapshot.access_token.value

    return token


@dataclass(frozen=True, slots=True, repr=False)
class ForegroundRuntime:
    owner: object
    config: Config
    factory: GmailServiceFactory

    def run_once(
        self,
        admission,
        *,
        action_consumer=None,
        max_jobs=1000,
        max_events=1000,
        verify_known_only=False,
    ):
        source_snapshot, target_snapshot = prepare_credentials(
            self.owner, self.config, self.factory
        )
        if not verify_known_only:
            from uuid import uuid4

            from facet.private_paths import read_managed_config, select_paths

            self.owner.ensure_insert_absence_schema(
                LocalId(uuid4().hex),
                read_managed_config(select_paths(self.owner.state_dir, None)),
            )
        with ExitStack() as services:

            def service(role, snapshot):
                build = getattr(self.factory, "service_with_refresh", None)
                if callable(build):
                    return build(
                        role,
                        snapshot,
                        _request_token_provider(
                            self.owner, self.config, self.factory, snapshot
                        ),
                    )
                return self.factory.service(role, snapshot)

            source_service = service(Role.SOURCE, source_snapshot)
            close = getattr(source_service, "close", None)
            if callable(close):
                services.callback(close)
            target_service = service(Role.TARGET, target_snapshot)
            close = getattr(target_service, "close", None)
            if callable(close):
                services.callback(close)
            source = SourceAdapter(
                source_service,
                source_account=PrivateAddress(self.config.projection.source_email),
            )
            target = TargetAdapter(target_service)
            initial_admission = (
                load_persisted_admission(self.owner, self.config)
                if admission is None
                else admission
            )

            def admission_for_epoch(epoch):
                return load_persisted_admission(
                    self.owner,
                    self.config,
                    epoch.decision.ruleset_revision,
                )

            epoch_loader = admission_for_epoch if admission is None else None
            return ForegroundSync(
                self.owner,
                source,
                target,
                initial_admission,
                action_consumer=(
                    action_consumer
                    if action_consumer is not None
                    else None
                    if verify_known_only
                    else _action_consumer(source, self.config, self.owner)
                ),
                admission_for_epoch=epoch_loader,
                admission_for_history=(
                    (lambda: load_persisted_admission(self.owner, self.config))
                    if admission is None
                    else None
                ),
            ).run_once(
                max_jobs=max_jobs,
                max_events=max_events,
                **({"verify_known_only": True} if verify_known_only else {}),
            )


def run_foreground_once(
    owner,
    config: Config,
    factory: GmailServiceFactory,
    admission=None,
    *,
    action_consumer=None,
    max_jobs=1000,
    max_events=1000,
    verify_known_only=False,
) -> SyncCycleReceipt:
    """Run one complete foreground cycle through the production composition."""
    return ForegroundRuntime(owner, config, factory).run_once(
        admission,
        action_consumer=action_consumer,
        max_jobs=max_jobs,
        max_events=max_events,
        verify_known_only=verify_known_only,
    )
