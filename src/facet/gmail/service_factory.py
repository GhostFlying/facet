"""Small provider-service factory for the production foreground runner."""

from __future__ import annotations

from typing import Protocol

from facet.contracts import ErrorCode, Role
from facet.db.codecs import StorageFailure

from .credential_models import (
    AccessSnapshot,
    AccountAddress,
    CredentialCodecError,
    ProviderSecret,
)
from .retry import execute

__all__ = ("GmailServiceFactory", "GoogleGmailServiceFactory")


class GmailServiceFactory(Protocol):
    """Profile and service construction seam used by runtime composition."""

    def profile_account(self, role: Role, secret: ProviderSecret) -> AccountAddress:
        """Probe only the provider account using an in-memory secret."""

    def service(self, role: Role, snapshot: AccessSnapshot):
        """Build one role-scoped service from an access-only snapshot."""


class GoogleGmailServiceFactory:
    """Build Google Gmail clients without retaining or passing refresh tokens."""

    supports_refresh = True

    def profile_account(self, role: Role, secret: ProviderSecret) -> AccountAddress:
        if type(role) is not Role or type(secret) is not ProviderSecret:
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        service = self._build(role, secret.access_token.value)
        try:
            value = execute(service.users().getProfile(userId="me"), role)
            return AccountAddress(value["emailAddress"])
        except StorageFailure:
            raise
        except (CredentialCodecError, KeyError, TypeError, ValueError):
            raise StorageFailure(ErrorCode.INVALID_INPUT) from None

    def service(self, role: Role, snapshot: AccessSnapshot):
        if type(role) is not Role or type(snapshot) is not AccessSnapshot:
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        if snapshot.role is not role:
            raise StorageFailure(ErrorCode.BINDING_MISMATCH)
        return self._build(role, snapshot.access_token.value)

    @staticmethod
    def _build(role: Role, access_token: str):
        # Imports remain lazy so offline CLI help and synthetic tests do not
        # construct a provider client. No refresh token/client secret is given
        # to the Google credential object, so this service cannot refresh or
        # write credentials behind the manager's back.
        del role
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        credentials = Credentials(token=access_token)
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)
