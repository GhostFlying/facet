"""Pure automatic-discovery admission consumer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from facet.contracts import (
    ProviderId,
    RuleKind,
    RuleRef,
    Timestamp,
    Visibility,
)
from facet.db.codecs import PrivateAddress

from .rules import CanonicalSender, NormalizedRule, RuleInputError, domain_matches


class AdmissionAttentionReason(StrEnum):
    SOURCE_STATE_INELIGIBLE = "source_state_ineligible"
    SOURCE_ACCOUNT_MISMATCH = "source_account_mismatch"
    DRAFT = "draft"
    NO_RULE = "no_rule"
    BLACKLISTED = "blacklisted"
    RULE_NOT_EFFECTIVE = "rule_not_effective"
    CANDIDATE_INVALID = "candidate_invalid"


@dataclass(frozen=True, slots=True, repr=False)
class DiscoveryCandidate:
    source_message_id: ProviderId
    source_thread_id: ProviderId
    sender: CanonicalSender
    source_account: PrivateAddress
    visibility: Visibility
    is_draft: bool
    observed_at: Timestamp

    def __post_init__(self) -> None:
        if (
            type(self.source_message_id) is not ProviderId
            or type(self.source_thread_id) is not ProviderId
            or type(self.sender) is not CanonicalSender
            or type(self.source_account) is not PrivateAddress
            or type(self.visibility) is not Visibility
            or type(self.is_draft) is not bool
            or type(self.observed_at) is not Timestamp
        ):
            raise ValueError("invalid_input")

    def __repr__(self) -> str:
        return "<discovery candidate>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class AdmissionRule:
    ref: RuleRef
    normalized: NormalizedRule
    effective_at: Timestamp
    enabled: bool = True

    def __post_init__(self) -> None:
        if (
            type(self.ref) is not RuleRef
            or type(self.normalized) is not NormalizedRule
            or type(self.effective_at) is not Timestamp
            or type(self.enabled) is not bool
            or self.ref.revision.value < 1
        ):
            raise ValueError("invalid_input")

    def __repr__(self) -> str:
        return "<admission rule>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class AdmissionResult:
    admit: bool
    rule: RuleRef | None = None
    attention_reason: AdmissionAttentionReason | None = None

    def __post_init__(self) -> None:
        if (
            type(self.admit) is not bool
            or type(self.rule) not in {RuleRef, type(None)}
            or type(self.attention_reason) not in {AdmissionAttentionReason, type(None)}
        ):
            raise ValueError("invalid_input")
        if (
            self.admit != (self.rule is not None)
            or (self.admit and self.attention_reason is not None)
            or (not self.admit and self.attention_reason is None)
        ):
            raise ValueError("invalid_input")

    def __repr__(self) -> str:
        return "<admission result>"

    __str__ = __repr__


def _attention(reason: AdmissionAttentionReason) -> AdmissionResult:
    return AdmissionResult(False, attention_reason=reason)


class AdmissionEvaluator:
    """Evaluate one typed candidate without persistence, Gmail or network calls."""

    def __init__(
        self,
        rules: tuple[AdmissionRule, ...],
        *,
        source_account: PrivateAddress,
    ) -> None:
        if (
            type(rules) is not tuple
            or any(type(rule) is not AdmissionRule for rule in rules)
            or len(rules) > 1000
            or type(source_account) is not PrivateAddress
        ):
            raise ValueError("invalid_input")
        self._rules = rules
        self._source_account = source_account

    def evaluate(
        self, candidate: DiscoveryCandidate, now: Timestamp
    ) -> AdmissionResult:
        if type(candidate) is not DiscoveryCandidate or type(now) is not Timestamp:
            raise ValueError("invalid_input")
        if candidate.visibility is not Visibility.NORMAL:
            return _attention(AdmissionAttentionReason.SOURCE_STATE_INELIGIBLE)
        if candidate.is_draft:
            return _attention(AdmissionAttentionReason.DRAFT)
        if candidate.source_account != self._source_account:
            return _attention(AdmissionAttentionReason.SOURCE_ACCOUNT_MISMATCH)
        if candidate.observed_at.value > now.value:
            return _attention(AdmissionAttentionReason.CANDIDATE_INVALID)

        enabled = tuple(rule for rule in self._rules if rule.enabled)
        for rule in enabled:
            if (
                rule.normalized.kind is RuleKind.BLACKLIST_SENDER
                and candidate.observed_at.value >= rule.effective_at.value
                and _matches(rule.normalized, candidate.sender)
            ):
                return _attention(AdmissionAttentionReason.BLACKLISTED)
        matches = tuple(
            rule
            for rule in enabled
            if rule.normalized.kind in {RuleKind.ALLOW_SENDER, RuleKind.ALLOW_DOMAIN}
            and _matches(rule.normalized, candidate.sender)
        )
        if not matches:
            return _attention(AdmissionAttentionReason.NO_RULE)
        selected = min(
            matches, key=lambda rule: (rule.effective_at.value, rule.ref.rule_id.value)
        )
        if candidate.observed_at.value < selected.effective_at.value:
            return _attention(AdmissionAttentionReason.RULE_NOT_EFFECTIVE)
        return AdmissionResult(True, selected.ref)


def _matches(rule: NormalizedRule, sender: CanonicalSender) -> bool:
    if rule.kind in {RuleKind.ALLOW_SENDER, RuleKind.BLACKLIST_SENDER}:
        return rule.value.value == sender.value
    if rule.kind is RuleKind.ALLOW_DOMAIN:
        return domain_matches(sender.domain, rule.value)
    raise RuleInputError()


__all__ = (
    "AdmissionAttentionReason",
    "AdmissionEvaluator",
    "AdmissionResult",
    "AdmissionRule",
    "DiscoveryCandidate",
)
