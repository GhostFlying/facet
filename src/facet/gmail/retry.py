"""Closed provider error mapping for the production Gmail boundary.

The adapter deliberately keeps Google client exceptions at this boundary.  A
caller receives only a stable error code and role; provider response bodies,
URLs and exception text never cross into persistence or output layers.
"""

from __future__ import annotations

from dataclasses import dataclass

from facet.contracts import ErrorCode, Role


@dataclass(frozen=True, slots=True, repr=False)
class ProviderFailure(Exception):
    code: ErrorCode
    role: Role

    def __post_init__(self) -> None:
        if type(self.code) is not ErrorCode or type(self.role) is not Role:
            raise ValueError("invalid_input")
        Exception.__init__(self, self.code.value)

    def __repr__(self) -> str:
        return f"ProviderFailure({self.code.value},{self.role.value})"


def classify_http_status(status: int, role: Role) -> ErrorCode:
    if type(status) is not int or type(role) is not Role:
        raise ValueError("invalid_input")
    if status == 401:
        return (
            ErrorCode.SOURCE_AUTH_REQUIRED
            if role is Role.SOURCE
            else ErrorCode.TARGET_AUTH_REQUIRED
        )
    if status == 403:
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


def provider_failure(error: BaseException, role: Role) -> ProviderFailure:
    """Normalize one Google/transport exception without retaining its payload."""

    if type(role) is not Role:
        raise ValueError("invalid_input")
    if isinstance(error, ProviderFailure):
        return error
    status = getattr(getattr(error, "resp", None), "status", None)
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    if type(status) is int:
        return ProviderFailure(classify_http_status(status, role), role)
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return ProviderFailure(ErrorCode.NETWORK_UNAVAILABLE, role)
    return ProviderFailure(ErrorCode.INVALID_INPUT, role)


def execute(request, role: Role):
    """Execute a fake-compatible request with retries disabled."""

    try:
        return request.execute(num_retries=0)
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt | SystemExit):
            raise
        raise provider_failure(error, role) from None
