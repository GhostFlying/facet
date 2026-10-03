"""Offline, versioned public-suffix and IDNA normalization."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

import idna
import tldextract

from facet.contracts import PolicyVersion

_POLICY_VERSION = PolicyVersion("psl-tldextract-5.3.2-idna-3.20")
_DOMAIN_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)


class SuffixInputError(ValueError):
    """A bounded, content-free rule normalization failure."""

    def __init__(self) -> None:
        super().__init__("invalid_input")


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalDomain:
    """ASCII lower-case domain with a known, non-public suffix."""

    value: str
    registrable: str
    policy_version: PolicyVersion = _POLICY_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or type(self.registrable) is not str
            or type(self.policy_version) is not PolicyVersion
            or not _DOMAIN_RE.fullmatch(self.value)
            or not _DOMAIN_RE.fullmatch(self.registrable)
            or not (
                self.value == self.registrable
                or self.value.endswith("." + self.registrable)
            )
            or self.policy_version != _POLICY_VERSION
        ):
            raise SuffixInputError()
        extracted = SuffixPolicy._extractor()(self.value)
        if (
            not extracted.domain
            or not extracted.suffix
            or f"{extracted.domain}.{extracted.suffix}" != self.registrable
        ):
            raise SuffixInputError()

    def __repr__(self) -> str:
        return "<canonical domain>"

    __str__ = __repr__


@lru_cache(maxsize=1)
def load_suffix_policy() -> SuffixPolicy:
    """Return the process-local resolver; it never fetches or writes a cache."""

    return SuffixPolicy()


@dataclass(frozen=True, slots=True, repr=False)
class SuffixPolicy:
    version: PolicyVersion = _POLICY_VERSION

    def __post_init__(self) -> None:
        if type(self.version) is not PolicyVersion or self.version != _POLICY_VERSION:
            raise SuffixInputError()

    def __repr__(self) -> str:
        return "<suffix policy>"

    __str__ = __repr__

    @staticmethod
    @lru_cache(maxsize=1)
    def _extractor() -> tldextract.TLDExtract:
        return tldextract.TLDExtract(
            cache_dir=None,
            suffix_list_urls=(),
            fallback_to_snapshot=True,
            include_psl_private_domains=False,
        )

    def normalize(self, value: str) -> CanonicalDomain:
        if type(value) is not str or not value or value != value.strip():
            raise SuffixInputError()
        if any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
            raise SuffixInputError()
        candidate = value.rstrip(".")
        if (
            not candidate
            or candidate != value
            or "/" in candidate
            or "@" in candidate
            or ".." in value
        ):
            raise SuffixInputError()
        try:
            ascii_value = (
                idna.encode(candidate, uts46=True, std3_rules=True)
                .decode("ascii")
                .lower()
            )
        except idna.IDNAError as exc:
            raise SuffixInputError() from exc
        try:
            ipaddress.ip_address(ascii_value)
        except ValueError:
            pass
        else:
            raise SuffixInputError()
        if not _DOMAIN_RE.fullmatch(ascii_value):
            raise SuffixInputError()
        extracted = self._extractor()(ascii_value)
        if not extracted.domain or not extracted.suffix:
            raise SuffixInputError()
        registrable = f"{extracted.domain}.{extracted.suffix}"
        return CanonicalDomain(ascii_value, registrable, self.version)


def normalize_domain(
    value: str, *, policy: SuffixPolicy | None = None
) -> CanonicalDomain:
    return (policy or load_suffix_policy()).normalize(value)


def registrable_domain(
    value: CanonicalDomain | str, *, policy: SuffixPolicy | None = None
) -> CanonicalDomain:
    if isinstance(value, CanonicalDomain):
        return CanonicalDomain(
            value.registrable, value.registrable, value.policy_version
        )
    return normalize_domain(value, policy=policy)


__all__ = (
    "CanonicalDomain",
    "SuffixInputError",
    "SuffixPolicy",
    "load_suffix_policy",
    "normalize_domain",
    "registrable_domain",
)
