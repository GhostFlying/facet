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
from .retry import ProviderStage, execute, provider_failure

__all__ = (
    "GmailServiceFactory",
    "GoogleGmailServiceFactory",
    "PROVIDER_REQUEST_TIMEOUT_SECONDS",
)

PROVIDER_REQUEST_TIMEOUT_SECONDS = 30


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
            value = execute(
                service.users().getProfile(userId="me"),
                role,
                provider_stage=ProviderStage.PROFILE_PROBE,
            )
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
        import httplib2
        from google.oauth2.credentials import Credentials
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build

        credentials = Credentials(token=access_token)
        transport = httplib2.Http(timeout=PROVIDER_REQUEST_TIMEOUT_SECONDS)
        authorized_http = AuthorizedHttp(credentials, http=transport)
        try:
            return build(
                "gmail",
                "v1",
                http=authorized_http,
                cache_discovery=False,
                num_retries=0,
            )
        except BaseException as error:
            if isinstance(error, KeyboardInterrupt | SystemExit):
                raise
            raise provider_failure(
                error, role, provider_stage=ProviderStage.SERVICE_DISCOVERY
            ) from None
