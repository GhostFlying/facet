"""Closed provider error mapping for the production Gmail boundary.

The adapter deliberately keeps Google client exceptions at this boundary.  A
caller receives only a stable error code and role; provider response bodies,
URLs and exception text never cross into persistence or output layers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from facet.contracts import ErrorCode, Role, Timestamp

_PROVIDER_REQUEST_TIMEOUT_SECONDS = 30


class ProviderReason(StrEnum):
    """Allowlisted provider codes, never arbitrary response text."""

    MISSING = "missing"
    UNKNOWN = "unknown"
    AUTH_ERROR = "authError"
    INVALID_GRANT = "invalid_grant"
    INVALID_SCOPE = "invalid_scope"
    INSUFFICIENT_SCOPE = "insufficient_scope"
    INSUFFICIENT_PERMISSIONS = "insufficientPermissions"
    DOMAIN_POLICY = "domainPolicy"
    DAILY_LIMIT = "dailyLimitExceeded"
    RATE_LIMIT = "rateLimitExceeded"
    USER_RATE_LIMIT = "userRateLimitExceeded"
    OAUTH_RATE_LIMIT = "rate_limit_exceeded"
    STORAGE_QUOTA = "storageQuotaExceeded"
    BACKEND_ERROR = "backendError"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


def provider_reason(payload: bytes | dict) -> ProviderReason:
    """Inspect only structured reason fields; drop messages and unknown values."""
    if isinstance(payload, bytes):
        if len(payload) > 65536:
            return ProviderReason.UNKNOWN
        try:
            payload = json.loads(payload)
        except (ValueError, RecursionError):
            return ProviderReason.UNKNOWN if payload else ProviderReason.MISSING
    if not isinstance(payload, dict):
        return ProviderReason.UNKNOWN
    error = payload.get("error")
    candidates = [payload.get("reason")]
    if isinstance(error, str):
        candidates.append(error)
    elif isinstance(error, dict):
        candidates.append(error.get("reason"))
        errors = error.get("errors")
        if isinstance(errors, list):
            candidates.extend(
                item.get("reason") for item in errors[:16] if isinstance(item, dict)
            )
    # Prefer a recognized reason even when another error entry is unknown.
    present = False
    for value in candidates:
        if value is None:
            continue
        present = True
        try:
            reason = ProviderReason(value)
        except (ValueError, TypeError):
            continue
        if reason not in {ProviderReason.MISSING, ProviderReason.UNKNOWN}:
            return reason
    return ProviderReason.UNKNOWN if present else ProviderReason.MISSING


class ProviderStage(StrEnum):
    """Bounded in-memory stages used for private provider diagnostics."""

    TOKEN_REFRESH = "token_refresh"
    PROFILE_PROBE = "profile_probe"
    SERVICE_DISCOVERY = "service_discovery"
    HISTORY_LIST = "history_list"
    MESSAGE_LIST = "message_list"
    MESSAGE_GET = "message_get"
    LABEL_LIST = "label_list"
    TARGET_INSERT = "target_insert"


@dataclass(slots=True, repr=False)
class ProviderFailure(Exception):
    # Exceptions must allow traceback assignment by context managers. Payload
    # metadata remains closed and is copied, not mutated, by our adapters.
    code: ErrorCode
    role: Role
    status: int | None = None
    retry_after_seconds: int | None = None
    provider_stage: ProviderStage | None = None
    timeout_seconds: int | None = None
    attempt: int | None = None
    observed_at: Timestamp | None = None
    reason: ProviderReason = ProviderReason.MISSING
    request_dispatched: bool | None = None

    def __post_init__(self) -> None:
        if type(self.code) is not ErrorCode or type(self.role) is not Role:
            raise ValueError("invalid_input")
        if self.status is not None and type(self.status) is not int:
            raise ValueError("invalid_input")
        if (
            self.retry_after_seconds is not None
            and type(self.retry_after_seconds) is not int
        ):
            raise ValueError("invalid_input")
        if (
            self.provider_stage is not None
            and type(self.provider_stage) is not ProviderStage
        ):
            raise ValueError("invalid_input")
        if self.timeout_seconds is not None and type(self.timeout_seconds) is not int:
            raise ValueError("invalid_input")
        if self.attempt is not None and type(self.attempt) is not int:
            raise ValueError("invalid_input")
        if self.attempt is not None and self.attempt != 1:
            raise ValueError("invalid_input")
        if self.observed_at is not None and type(self.observed_at) is not Timestamp:
            raise ValueError("invalid_input")
        if type(self.reason) is not ProviderReason or (
            self.request_dispatched is not None
            and type(self.request_dispatched) is not bool
        ):
            raise ValueError("invalid_input")
        Exception.__init__(self, self.code.value)

    def __repr__(self) -> str:
        return f"ProviderFailure({self.code.value},{self.role.value})"

    def with_code(
        self, code: ErrorCode, *, role: Role | None = None
    ) -> ProviderFailure:
        """Rewrap while retaining private diagnostics and retry metadata."""

        if type(code) is not ErrorCode or (role is not None and type(role) is not Role):
            raise ValueError("invalid_input")
        return replace(self, code=code, role=self.role if role is None else role)


def classify_http_status(status: int, role: Role, *, body: bytes = b"") -> ErrorCode:
    if type(status) is not int or type(role) is not Role:
        raise ValueError("invalid_input")
    if status == 401:
        return (
            ErrorCode.SOURCE_AUTH_REQUIRED
            if role is Role.SOURCE
            else ErrorCode.TARGET_AUTH_REQUIRED
        )
    if status == 403:
        reason = provider_reason(body)
        if role is Role.TARGET and reason is ProviderReason.STORAGE_QUOTA:
            return ErrorCode.TARGET_STORAGE_FULL
        if reason in {
            ProviderReason.RATE_LIMIT,
            ProviderReason.USER_RATE_LIMIT,
            ProviderReason.OAUTH_RATE_LIMIT,
            ProviderReason.DAILY_LIMIT,
        }:
            return classify_http_status(429, role)
        if reason is ProviderReason.BACKEND_ERROR:
            return ErrorCode.NETWORK_UNAVAILABLE
        return ErrorCode.SCOPE_REQUIRED
    if status == 429:
        return (
            ErrorCode.SOURCE_RATE_LIMITED
            if role is Role.SOURCE
            else ErrorCode.TARGET_RATE_LIMITED
        )
    if status >= 500:
        return ErrorCode.NETWORK_UNAVAILABLE
    return ErrorCode.INVALID_INPUT


def blocks_sync(error: ProviderFailure) -> bool:
    """Stop a batch on account-wide dependencies, retaining the current job."""
    return (
        error.code
        in {
            ErrorCode.SOURCE_AUTH_REQUIRED,
            ErrorCode.TARGET_AUTH_REQUIRED,
            ErrorCode.SCOPE_REQUIRED,
            ErrorCode.BINDING_MISMATCH,
        }
        or error.reason is ProviderReason.DAILY_LIMIT
        or error.request_dispatched is False
    )


def provider_failure(
    error: BaseException,
    role: Role,
    *,
    provider_stage: ProviderStage | None = None,
) -> ProviderFailure:
    """Normalize one Google/transport exception without retaining its payload."""

    if type(role) is not Role:
        raise ValueError("invalid_input")
    if isinstance(error, ProviderFailure):
        if provider_stage is None or error.provider_stage is not None:
            return error
        return replace(
            error,
            provider_stage=provider_stage,
            timeout_seconds=_PROVIDER_REQUEST_TIMEOUT_SECONDS,
            attempt=1,
            observed_at=Timestamp(datetime.now(UTC)),
        )
    response = getattr(error, "resp", None)
    status = getattr(response, "status", None)
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    if type(status) is int:
        body = getattr(error, "content", b"")
        if not isinstance(body, bytes):
            body = b""
        code = (
            (
                ErrorCode.SOURCE_AUTH_REQUIRED
                if role is Role.SOURCE
                else ErrorCode.TARGET_AUTH_REQUIRED
            )
            if provider_reason(body) is ProviderReason.INVALID_GRANT
            else classify_http_status(status, role, body=body)
        )
        retry_after = None
        raw_retry = None
        if response is not None and hasattr(response, "get"):
            raw_retry = response.get("retry-after") or response.get("Retry-After")
        if isinstance(raw_retry, str) and raw_retry.isdigit():
            retry_after = int(raw_retry)
        return ProviderFailure(
            code,
            role,
            status,
            retry_after,
            provider_stage,
            _PROVIDER_REQUEST_TIMEOUT_SECONDS if provider_stage is not None else None,
            1 if provider_stage is not None else None,
            Timestamp(datetime.now(UTC)) if provider_stage is not None else None,
            reason=provider_reason(body),
            request_dispatched=True,
        )
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return ProviderFailure(
            ErrorCode.NETWORK_UNAVAILABLE,
            role,
            provider_stage=provider_stage,
            timeout_seconds=(
                _PROVIDER_REQUEST_TIMEOUT_SECONDS
                if provider_stage is not None
                else None
            ),
            attempt=1 if provider_stage is not None else None,
            observed_at=(
                Timestamp(datetime.now(UTC)) if provider_stage is not None else None
            ),
        )
    return ProviderFailure(
        ErrorCode.INVALID_INPUT,
        role,
        provider_stage=provider_stage,
        timeout_seconds=(
            _PROVIDER_REQUEST_TIMEOUT_SECONDS if provider_stage is not None else None
        ),
        attempt=1 if provider_stage is not None else None,
        observed_at=(
            Timestamp(datetime.now(UTC)) if provider_stage is not None else None
        ),
    )


def execute(request, role: Role, *, provider_stage: ProviderStage | None = None):
    """Execute a fake-compatible request with retries disabled."""

    try:
        return request.execute(num_retries=0)
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt | SystemExit):
            raise
        raise provider_failure(error, role, provider_stage=provider_stage) from None
