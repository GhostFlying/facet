"""Explicit Google OAuth refresh exchange owned by the credential manager."""

from __future__ import annotations

from datetime import UTC, datetime

from facet.contracts import ErrorCode, Role, Timestamp
from facet.db.codecs import StorageFailure

from .credential_models import (
    ProviderSecret,
    RefreshResult,
    ScopeName,
    ScopeSet,
)
from .retry import ProviderFailure, ProviderStage, classify_http_status
from .service_factory import PROVIDER_REQUEST_TIMEOUT_SECONDS

_SCOPE_URLS = {
    ScopeName.GMAIL_READONLY: "https://www.googleapis.com/auth/gmail.readonly",
    ScopeName.GMAIL_INSERT: "https://www.googleapis.com/auth/gmail.insert",
    ScopeName.GMAIL_MODIFY: "https://www.googleapis.com/auth/gmail.modify",
    ScopeName.GMAIL_LABELS: "https://www.googleapis.com/auth/gmail.labels",
}


def _role_auth(role: Role) -> ErrorCode:
    return (
        ErrorCode.SOURCE_AUTH_REQUIRED
        if role is Role.SOURCE
        else ErrorCode.TARGET_AUTH_REQUIRED
    )


def _refresh_error_code(error: BaseException, role: Role) -> ErrorCode:
    """Map Google refresh failures without retaining provider payloads."""

    response = getattr(error, "response", None) or getattr(error, "resp", None)
    status = getattr(response, "status", None)
    response_data = next(
        (value for value in getattr(error, "args", ()) if isinstance(value, dict)),
        None,
    )
    if response_data is not None:
        status = response_data.get("status", response_data.get("code", status))
        provider_error = response_data.get("error")
        provider_reason = response_data.get("reason")
    else:
        provider_error = None
        provider_reason = None
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    content = getattr(error, "content", b"")
    if not isinstance(content, bytes):
        content = b""
    markers = " ".join(
        value for value in (provider_error, provider_reason) if isinstance(value, str)
    ).lower()
    if any(value in markers for value in ("invalid_scope", "insufficient_scope")):
        return ErrorCode.SCOPE_REQUIRED
    if "invalid_grant" in markers or b"invalid_grant" in content.lower():
        return _role_auth(role)
    if type(status) is int:
        if status == 403 and any(
            value in markers for value in ("rate_limit", "ratelimit", "quota")
        ):
            return classify_http_status(429, role)
        return classify_http_status(status, role, body=content)
    if any(value in markers for value in ("rate_limit", "ratelimit", "quota")):
        return classify_http_status(429, role)
    if any(value in markers for value in ("backend", "temporarily_unavailable")):
        return ErrorCode.NETWORK_UNAVAILABLE
    if getattr(error, "retryable", False):
        return ErrorCode.NETWORK_UNAVAILABLE
    return _role_auth(role)


def _refresh_provider_failure(
    error: BaseException, role: Role, *, code: ErrorCode | None = None
) -> ProviderFailure:
    """Map one token exchange failure to closed, private metadata."""

    response = getattr(error, "response", None) or getattr(error, "resp", None)
    status = getattr(response, "status", None)
    response_data = next(
        (value for value in getattr(error, "args", ()) if isinstance(value, dict)),
        None,
    )
    if response_data is not None:
        status = response_data.get("status", response_data.get("code", status))
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    if type(status) is not int:
        status = None
    retry_after = None
    if response is not None and hasattr(response, "get"):
        raw_retry = response.get("retry-after") or response.get("Retry-After")
        if isinstance(raw_retry, str) and raw_retry.isdigit():
            retry_after = int(raw_retry)
    code = _refresh_error_code(error, role) if code is None else code
    return ProviderFailure(
        code,
        role,
        status=status,
        retry_after_seconds=retry_after,
        provider_stage=ProviderStage.TOKEN_REFRESH,
        timeout_seconds=PROVIDER_REQUEST_TIMEOUT_SECONDS,
        attempt=1,
        observed_at=Timestamp(datetime.now(UTC)),
    )


class _BoundedRequest:
    """Force the fixed token-exchange timeout at Request.__call__."""

    def __init__(self, request, timeout: int):
        self._request = request
        self._timeout = timeout

    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = self._timeout
        return self._request(*args, **kwargs)


def refresh_google(role: Role, secret: ProviderSecret, scopes: ScopeSet):
    """Exchange one manager-owned refresh token without retaining provider data."""

    if (
        type(role) is not Role
        or type(secret) is not ProviderSecret
        or type(scopes) is not ScopeSet
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    try:
        from google.auth.exceptions import RefreshError, TransportError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        credentials = Credentials(
            token=secret.access_token.value,
            refresh_token=secret.refresh_token.value,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=secret.client_id.value,
            client_secret=secret.client_secret.value,
            scopes=tuple(_SCOPE_URLS[scope] for scope in scopes.value),
        )
        credentials.refresh(
            _BoundedRequest(Request(), PROVIDER_REQUEST_TIMEOUT_SECONDS)
        )
    except RefreshError as error:
        raise _refresh_provider_failure(error, role) from None
    except StorageFailure:
        raise
    except (TransportError, TimeoutError, OSError) as error:
        raise _refresh_provider_failure(
            error, role, code=ErrorCode.NETWORK_UNAVAILABLE
        ) from None
    except Exception as error:
        raise _refresh_provider_failure(
            error, role, code=ErrorCode.NETWORK_UNAVAILABLE
        ) from None
    try:
        token = credentials.token
        expiry = credentials.expiry
        if not isinstance(token, str) or not token or not isinstance(expiry, datetime):
            raise ValueError
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= datetime.now(UTC):
            raise ValueError
        refresh_token = credentials.refresh_token or secret.refresh_token.value
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ValueError
        # ``Credentials.scopes`` is the requested set, not provider evidence.
        # Missing ``granted_scopes`` therefore means inherited scopes.
        granted = getattr(credentials, "granted_scopes", None)
        scope_set = None
        if granted is not None:
            names = {url: scope for scope, url in _SCOPE_URLS.items()}
            scope_set = ScopeSet(frozenset(names[value] for value in granted))
        result = ProviderSecret(
            secret.client_id,
            secret.client_secret,
            type(secret.access_token)(token),
            type(secret.refresh_token)(refresh_token),
            Timestamp(expiry.astimezone(UTC)),
        )
        return RefreshResult(result, scope_set)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise StorageFailure(ErrorCode.INVALID_INPUT) from None


__all__ = ("refresh_google",)
