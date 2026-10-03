"""Pure sender/domain rule normalization and exact matching."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from facet.config import RulesConfig
from facet.contracts import PolicyVersion, RuleKind
from facet.db.codecs import RuleValue

from .suffixes import (
    CanonicalDomain,
    SuffixInputError,
    SuffixPolicy,
    load_suffix_policy,
    normalize_domain,
)

_SENDER_RE = re.compile(r"^[^@\s]+@[^@\s]+$")


class RuleInputError(ValueError):
    def __init__(self) -> None:
        super().__init__("invalid_input")


class LearnReason(StrEnum):
    INVALID = "invalid"
    SOURCE_PRIMARY_DOMAIN = "source_primary_domain"
    OWN_DOMAIN = "own_domain"


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalSender:
    local: str
    domain: CanonicalDomain

    @property
    def value(self) -> str:
        return f"{self.local}@{self.domain.value}"

    def __post_init__(self) -> None:
        if (
            type(self.local) is not str
            or type(self.domain) is not CanonicalDomain
            or not self.local
            or len(self.local.encode("utf-8")) > 320
            or any(unicodedata.category(c) in {"Cc", "Cs"} for c in self.local)
            or not _SENDER_RE.fullmatch(self.value)
            or any(char in self.local for char in "*?[]")
        ):
            raise RuleInputError()

    def __repr__(self) -> str:
        return "<canonical sender>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class RulePolicy:
    suffix: SuffixPolicy

    @property
    def version(self):
        return self.suffix.version

    def __post_init__(self) -> None:
        if type(self.suffix) is not SuffixPolicy:
            raise RuleInputError()

    def __repr__(self) -> str:
        return "<rule policy>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class NormalizedRule:
    kind: RuleKind
    value: CanonicalSender | CanonicalDomain
    storage_value: RuleValue

    def __post_init__(self) -> None:
        valid = (
            (self.kind is RuleKind.ALLOW_SENDER and type(self.value) is CanonicalSender)
            or (
                self.kind is RuleKind.ALLOW_DOMAIN
                and type(self.value) is CanonicalDomain
            )
            or (
                self.kind is RuleKind.BLACKLIST_SENDER
                and type(self.value) is CanonicalSender
            )
        )
        if not valid or type(self.storage_value) is not RuleValue:
            raise RuleInputError()

    def __repr__(self) -> str:
        return "<normalized rule>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class RuleSet:
    allow_senders: tuple[NormalizedRule, ...]
    allow_domains: tuple[NormalizedRule, ...]
    blacklist_senders: tuple[NormalizedRule, ...]
    policy_version: PolicyVersion

    def __post_init__(self) -> None:
        if (
            type(self.allow_senders) is not tuple
            or type(self.allow_domains) is not tuple
            or type(self.blacklist_senders) is not tuple
            or type(self.policy_version) is not PolicyVersion
            or any(
                type(item) is not NormalizedRule
                for item in (
                    *self.allow_senders,
                    *self.allow_domains,
                    *self.blacklist_senders,
                )
            )
            or any(
                item.kind is not RuleKind.ALLOW_SENDER for item in self.allow_senders
            )
            or any(
                item.kind is not RuleKind.ALLOW_DOMAIN for item in self.allow_domains
            )
            or any(
                item.kind is not RuleKind.BLACKLIST_SENDER
                for item in self.blacklist_senders
            )
        ):
            raise RuleInputError()

    def __repr__(self) -> str:
        return "<rule set>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class RuleMatch:
    matched: bool
    rule: NormalizedRule | None = None
    blacklisted: bool = False

    def __post_init__(self) -> None:
        if type(self.matched) is not bool or type(self.blacklisted) is not bool:
            raise RuleInputError()
        if self.matched != (self.rule is not None):
            raise RuleInputError()

    def __repr__(self) -> str:
        return "<rule match>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class LearnResult:
    domain: CanonicalDomain | None
    reason: LearnReason | None = None

    def __post_init__(self) -> None:
        if type(self.domain) not in {CanonicalDomain, type(None)} or type(
            self.reason
        ) not in {LearnReason, type(None)}:
            raise RuleInputError()

    def __repr__(self) -> str:
        return "<learn result>"

    __str__ = __repr__


def load_rule_policy() -> RulePolicy:
    return RulePolicy(load_suffix_policy())


def normalize_sender(
    value: str, *, policy: RulePolicy | None = None
) -> CanonicalSender:
    if type(value) is not str or not _SENDER_RE.fullmatch(value):
        raise RuleInputError()
    local, domain = value.rsplit("@", 1)
    if not local or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value):
        raise RuleInputError()
    try:
        canonical_domain = normalize_domain(
            domain, policy=(policy or load_rule_policy()).suffix
        )
    except SuffixInputError as exc:
        raise RuleInputError() from exc
    return CanonicalSender(local, canonical_domain)


def normalize_rule(
    kind: RuleKind, value: str, *, policy: RulePolicy | None = None
) -> NormalizedRule:
    if type(kind) is not RuleKind or type(value) is not str:
        raise RuleInputError()
    selected = policy or load_rule_policy()
    if kind is RuleKind.ALLOW_DOMAIN:
        try:
            normalized: CanonicalSender | CanonicalDomain = normalize_domain(
                value, policy=selected.suffix
            )
        except SuffixInputError as exc:
            raise RuleInputError() from exc
    elif kind in {RuleKind.ALLOW_SENDER, RuleKind.BLACKLIST_SENDER}:
        normalized = normalize_sender(value, policy=selected)
    else:
        raise RuleInputError()
    return NormalizedRule(kind, normalized, RuleValue(normalized.value))


def _dedupe(items: tuple[NormalizedRule, ...]) -> tuple[NormalizedRule, ...]:
    seen: set[tuple[RuleKind, str]] = set()
    output: list[NormalizedRule] = []
    for item in items:
        key = (item.kind, item.storage_value.value)
        if key not in seen:
            seen.add(key)
            output.append(item)
    return tuple(output)


def normalize_rules(
    config: RulesConfig, *, policy: RulePolicy | None = None
) -> RuleSet:
    if type(config) is not RulesConfig:
        raise RuleInputError()
    if any(
        type(values) is not tuple
        for values in (
            config.allow_senders,
            config.allow_domains,
            config.blacklist_senders,
        )
    ):
        raise RuleInputError()
    if config.authenticity != "require_trusted_auth":
        raise RuleInputError()
    selected = policy or load_rule_policy()
    senders = _dedupe(
        tuple(
            normalize_rule(RuleKind.ALLOW_SENDER, value, policy=selected)
            for value in config.allow_senders
        )
    )
    domains = _dedupe(
        tuple(
            normalize_rule(RuleKind.ALLOW_DOMAIN, value, policy=selected)
            for value in config.allow_domains
        )
    )
    blacklist = _dedupe(
        tuple(
            normalize_rule(RuleKind.BLACKLIST_SENDER, value, policy=selected)
            for value in config.blacklist_senders
        )
    )
    return RuleSet(senders, domains, blacklist, selected.version)


def domain_matches(domain: CanonicalDomain, rule: CanonicalDomain) -> bool:
    if type(domain) is not CanonicalDomain or type(rule) is not CanonicalDomain:
        raise RuleInputError()
    return domain.value == rule.value or domain.value.endswith("." + rule.value)


def match_sender(sender: CanonicalSender, rules: RuleSet) -> RuleMatch:
    if type(sender) is not CanonicalSender or type(rules) is not RuleSet:
        raise RuleInputError()
    for rule in rules.blacklist_senders:
        if rule.value.value == sender.value:
            return RuleMatch(True, rule, True)
    for rule in rules.allow_senders:
        if rule.value.value == sender.value:
            return RuleMatch(True, rule)
    for rule in rules.allow_domains:
        if domain_matches(sender.domain, rule.value):
            return RuleMatch(True, rule)
    return RuleMatch(False)


def learn_domain(
    sender: CanonicalSender | str,
    *,
    source_primary: str,
    own: tuple[str, ...] = (),
    policy: RulePolicy | None = None,
) -> LearnResult:
    selected = policy or load_rule_policy()
    try:
        normalized_sender = (
            sender
            if type(sender) is CanonicalSender
            else normalize_sender(sender, policy=selected)
        )
        candidate = normalized_sender.domain.registrable
        primary = normalize_sender(source_primary, policy=selected).domain.registrable
        own_domains = {
            normalize_sender(address, policy=selected).domain.registrable
            for address in own
        }
    except (RuleInputError, SuffixInputError):
        return LearnResult(None, LearnReason.INVALID)
    if candidate == primary:
        return LearnResult(None, LearnReason.SOURCE_PRIMARY_DOMAIN)
    if candidate in own_domains:
        return LearnResult(None, LearnReason.OWN_DOMAIN)
    return LearnResult(CanonicalDomain(candidate, candidate, selected.suffix.version))


__all__ = (
    "CanonicalSender",
    "LearnReason",
    "LearnResult",
    "NormalizedRule",
    "RuleInputError",
    "RuleMatch",
    "RulePolicy",
    "RuleSet",
    "domain_matches",
    "learn_domain",
    "load_rule_policy",
    "match_sender",
    "normalize_rule",
    "normalize_rules",
    "normalize_sender",
)
