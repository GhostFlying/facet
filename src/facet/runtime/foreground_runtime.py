"""Composition of verified credentials and the foreground projection runner."""

from __future__ import annotations

from dataclasses import dataclass

from facet.config import Config
from facet.contracts import LocalId, Revision, Role, RuleRef, SourceMode
from facet.db.codecs import PrivateAddress
from facet.gmail.credential_models import (
    AccountAddress,
    ScopePolicy,
    policy_scopes,
)
from facet.gmail.credentials import CredentialManager, ProfileEvidence, ProfileReader
from facet.gmail.service_factory import GmailServiceFactory
from facet.gmail.source import SourceAdapter
from facet.gmail.target import TargetAdapter
from facet.projection.action_consumer import ActionEffectConsumer
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
            + " FROM ruleset_members WHERE projection_id=? AND ruleset_revision=?",
            (owner.projection_id.value, selected_revision.value),
        )
        rules = []
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
            rules.append(
                AdmissionRule(
                    RuleRef(member.rule_id, revision.revision),
                    normalize_rule(member.kind, member.normalized_value.value),
                    revision.effective_at,
                    revision.enabled,
                )
            )
        return AdmissionEvaluator(
            tuple(rules),
            source_account=PrivateAddress(config.projection.source_email),
            ruleset_revision=selected_revision,
        )


def _action_consumer(source: SourceAdapter, config: Config, owner):
    from facet.db.action_labels import effective

    labels = source.action_label_map(effective(owner._connection, config.projection.id))
    if labels is None:
        return None
    own_addresses = tuple(
        PrivateAddress(address) for address in config.projection.own_addresses
    )
    return ActionEffectConsumer(
        labels,
        source,
        own_addresses,
        config.projection.source_email,
    )


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
    ):
        manager = CredentialManager(self.owner.state_dir, self.config, self.owner)
        from facet.gmail.refresh_exchange import refresh_google

        probe = _ProfileProbe(self.config, self.factory)

        def exchange(role, old):
            return refresh_google(
                role, old, policy_scopes(_policy(self.config, role), role)
            )

        def refreshed_profile(role, secret, scopes):
            evidence = self.factory.profile_account(role, secret)
            return ProfileEvidence(evidence, scopes)

        if getattr(self.factory, "supports_refresh", False):
            for role in (Role.SOURCE, Role.TARGET):
                manager.reconcile_interrupted_refresh(role)
                manager.ensure_current(role, exchange, refreshed_profile)
        # verify() reads both role envelopes and probes both profiles before
        # verify_and_publish changes either binding or projection readiness.
        manager.verify_and_publish(probe)
        source_snapshot = manager.snapshot(Role.SOURCE)
        target_snapshot = manager.snapshot(Role.TARGET)
        source = SourceAdapter(
            self.factory.service(Role.SOURCE, source_snapshot),
            source_account=PrivateAddress(self.config.projection.source_email),
        )
        target = TargetAdapter(self.factory.service(Role.TARGET, target_snapshot))
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
                else _action_consumer(source, self.config, self.owner)
            ),
            admission_for_epoch=epoch_loader,
        ).run_once(max_jobs=max_jobs, max_events=max_events)


def run_foreground_once(
    owner,
    config: Config,
    factory: GmailServiceFactory,
    admission=None,
    *,
    action_consumer=None,
    max_jobs=1000,
    max_events=1000,
) -> SyncCycleReceipt:
    """Run one complete foreground cycle through the production composition."""
    return ForegroundRuntime(owner, config, factory).run_once(
        admission,
        action_consumer=action_consumer,
        max_jobs=max_jobs,
        max_events=max_events,
    )
