"""Closed provider error mapping for the production Gmail boundary.

The adapter deliberately keeps Google client exceptions at this boundary.  A
caller receives only a stable error code and role; provider response bodies,
URLs and exception text never cross into persistence or output layers.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from facet.contracts import ErrorCode, Role, Timestamp

_PROVIDER_REQUEST_TIMEOUT_SECONDS = 30


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


@dataclass(frozen=True, slots=True, repr=False)
class ProviderFailure(Exception):
    code: ErrorCode
    role: Role
    status: int | None = None
    retry_after_seconds: int | None = None
    provider_stage: ProviderStage | None = None
    timeout_seconds: int | None = None
    attempt: int | None = None
    observed_at: Timestamp | None = None

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
        lowered = body.lower()
        if role is Role.TARGET and (
            b"storagequota" in lowered or b"storage quota" in lowered
        ):
            return ErrorCode.TARGET_STORAGE_FULL
        if not any(
            token in lowered for token in (b"ratelimit", b"rate_limit", b"backenderror")
        ):
            return (
                ErrorCode.SOURCE_AUTH_REQUIRED
                if role is Role.SOURCE
                else ErrorCode.TARGET_AUTH_REQUIRED
            )
        return (
            ErrorCode.SOURCE_RATE_LIMITED
            if role is Role.SOURCE
            else ErrorCode.TARGET_RATE_LIMITED
        )
    if status == 429:
        return (
            ErrorCode.SOURCE_RATE_LIMITED
            if role is Role.SOURCE
            else ErrorCode.TARGET_RATE_LIMITED
        )
    if status >= 500:
        return ErrorCode.NETWORK_UNAVAILABLE
    return ErrorCode.INVALID_INPUT


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
            if b"invalid_grant" in body.lower()
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
