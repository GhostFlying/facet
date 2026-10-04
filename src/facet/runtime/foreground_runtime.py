"""Composition of verified credentials and the foreground projection runner."""

from __future__ import annotations

from dataclasses import dataclass

from facet.config import Config
from facet.contracts import Role, SourceMode
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
        # verify() reads both role envelopes and probes both profiles before
        # verify_and_publish changes either binding or projection readiness.
        manager.verify_and_publish(_ProfileProbe(self.config, self.factory))
        source_snapshot = manager.snapshot(Role.SOURCE)
        target_snapshot = manager.snapshot(Role.TARGET)
        source_binding = self.owner.bindings()[Role.SOURCE]
        source = SourceAdapter(
            self.factory.service(Role.SOURCE, source_snapshot),
            source_account=PrivateAddress(self.config.projection.source_email),
            binding_revision=source_binding.binding_revision,
            credential_revision=source_binding.credential_revision,
        )
        target = TargetAdapter(self.factory.service(Role.TARGET, target_snapshot))
        return ForegroundSync(
            self.owner,
            source,
            target,
            admission,
            action_consumer=action_consumer,
        ).run_once(max_jobs=max_jobs, max_events=max_events)


def run_foreground_once(
    owner,
    config: Config,
    factory: GmailServiceFactory,
    admission,
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
