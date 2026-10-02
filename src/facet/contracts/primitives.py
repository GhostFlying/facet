"""Validated, immutable p1-core-v1 values (no storage or provider dependencies)."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID


def _invalid() -> None:
    raise ValueError("invalid_input")


@dataclass(frozen=True, slots=True, repr=False)
class ProjectionId:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", self.value
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class LocalId:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or not re.fullmatch(r"[0-9a-f]{32}", self.value):
            _invalid()
        parsed = UUID(hex=self.value)
        if parsed.version != 4 or parsed.variant != "specified in RFC 4122":
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class ProviderId:
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or not self.value
            or any(unicodedata.category(c) in {"Cc", "Cs"} for c in self.value)
            or len(self.value.encode("utf-8")) > 512
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class Timestamp:
    value: datetime

    def __post_init__(self) -> None:
        if (
            type(self.value) is not datetime
            or self.value.tzinfo is None
            or self.value.utcoffset() != timedelta(0)
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class Count:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or self.value < 0:
            _invalid()
        if self.value > 2**63 - 1:
            raise ValueError("consistency_failure")


@dataclass(frozen=True, slots=True, repr=False)
class Generation(Count):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class Revision(Count):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Hex:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or not re.fullmatch(r"[0-9a-f]{64}", self.value):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class PolicyVersion:
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or len(self.value) > 64
            or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", self.value)
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class ProviderPageToken:
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or not self.value
            or "\x00" in self.value
            or any(unicodedata.category(c) == "Cs" for c in self.value)
            or len(self.value.encode("utf-8")) > 16384
        ):
            _invalid()
