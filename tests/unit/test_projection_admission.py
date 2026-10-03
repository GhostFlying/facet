from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from facet.contracts import (
    LocalId,
    PolicyVersion,
    ProviderId,
    Revision,
    Role,
    RuleKind,
    RuleRef,
    Timestamp,
    Visibility,
)
from facet.db.codecs import PrivateAddress
from facet.projection.admission import (
    AdmissionAttentionReason,
    AdmissionEvaluator,
    AdmissionRule,
    DiscoveryCandidate,
)
from facet.projection.authenticity import (
    FromAlignment,
    SourcePathStatus,
    _issuer_for_tests,
)
from facet.projection.rules import normalize_rule, normalize_sender

NOW = Timestamp(datetime(2026, 1, 1, tzinfo=UTC))
ACCOUNT = PrivateAddress("source@example.net")
MESSAGE = ProviderId("message-1")


def lid() -> LocalId:
    return LocalId(uuid4().hex)


def evidence(
    *,
    message: ProviderId = MESSAGE,
    observed: Timestamp = NOW,
    expires: Timestamp | None = None,
):
    return _issuer_for_tests().issue(
        source_role=Role.SOURCE,
        source_account=ACCOUNT,
        source_message_id=message,
        source_path=SourcePathStatus.TRUSTED,
        from_alignment=FromAlignment.ALIGNED,
        binding_revision=Revision(1),
        credential_revision=Revision(1),
        observed_at=observed,
        expires_at=expires or Timestamp(observed.value + timedelta(days=1)),
        policy_version=PolicyVersion("auth-v1"),
    )


def evaluator(*rules: AdmissionRule) -> AdmissionEvaluator:
    return AdmissionEvaluator(
        tuple(rules),
        source_account=ACCOUNT,
        binding_revision=Revision(1),
        credential_revision=Revision(1),
    )


def rule(kind: RuleKind, value: str, *, effective: Timestamp = NOW) -> AdmissionRule:
    return AdmissionRule(
        RuleRef(lid(), Revision(1)),
        normalize_rule(kind, value),
        effective,
    )


def candidate(*, sender: str = "user@example.com", **kwargs) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        source_message_id=kwargs.pop("message", MESSAGE),
        source_thread_id=ProviderId("thread-1"),
        sender=normalize_sender(sender),
        source_account=kwargs.pop("account", ACCOUNT),
        visibility=kwargs.pop("visibility", Visibility.NORMAL),
        is_draft=kwargs.pop("draft", False),
        observed_at=kwargs.pop("observed", NOW),
        evidence=kwargs.pop("evidence", evidence()),
    )


def test_trusted_aligned_candidate_is_admitted() -> None:
    result = evaluator(rule(RuleKind.ALLOW_DOMAIN, "example.com")).evaluate(
        candidate(), NOW
    )
    assert result.admit and result.rule is not None and result.attention_reason is None


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"evidence": None}, AdmissionAttentionReason.AUTHENTICITY_MISSING),
        (
            {"visibility": Visibility.SPAM},
            AdmissionAttentionReason.SOURCE_STATE_INELIGIBLE,
        ),
        ({"draft": True}, AdmissionAttentionReason.DRAFT),
        (
            {"account": PrivateAddress("other@example.net")},
            AdmissionAttentionReason.AUTHENTICITY_UNTRUSTED,
        ),
        (
            {
                "evidence": evidence(
                    observed=Timestamp(NOW.value - timedelta(days=2)),
                    expires=Timestamp(NOW.value - timedelta(days=1)),
                )
            },
            AdmissionAttentionReason.AUTHENTICITY_STALE,
        ),
    ],
)
def test_unsafe_or_ineligible_candidates_do_not_admit(kwargs, reason) -> None:
    result = evaluator(rule(RuleKind.ALLOW_DOMAIN, "example.com")).evaluate(
        candidate(**kwargs), NOW
    )
    assert not result.admit
    assert result.attention_reason is reason


def test_blacklist_precedes_allow() -> None:
    result = evaluator(
        rule(RuleKind.ALLOW_DOMAIN, "example.com"),
        rule(RuleKind.BLACKLIST_SENDER, "user@example.com"),
    ).evaluate(candidate(), NOW)
    assert result.attention_reason is AdmissionAttentionReason.BLACKLISTED


def test_future_blacklist_is_prospective() -> None:
    future = Timestamp(NOW.value + timedelta(hours=1))
    result = evaluator(
        rule(RuleKind.ALLOW_DOMAIN, "example.com"),
        rule(RuleKind.BLACKLIST_SENDER, "user@example.com", effective=future),
    ).evaluate(candidate(), NOW)
    assert result.admit


def test_admission_rules_are_bounded() -> None:
    with pytest.raises(ValueError):
        evaluator(*(rule(RuleKind.ALLOW_DOMAIN, "example.com") for _ in range(1001)))


def test_effective_at_is_prospective() -> None:
    future = Timestamp(NOW.value + timedelta(hours=1))
    result = evaluator(
        rule(RuleKind.ALLOW_DOMAIN, "example.com", effective=future)
    ).evaluate(candidate(), NOW)
    assert result.attention_reason is AdmissionAttentionReason.RULE_NOT_EFFECTIVE


def test_candidate_observation_must_fit_evidence_window() -> None:
    observed = Timestamp(NOW.value + timedelta(hours=2))
    result = evaluator(rule(RuleKind.ALLOW_DOMAIN, "example.com")).evaluate(
        candidate(observed=observed), NOW
    )
    assert result.attention_reason is AdmissionAttentionReason.CANDIDATE_INVALID


def test_evidence_policy_mismatch_is_untrusted() -> None:
    foreign = _issuer_for_tests().issue(
        source_role=Role.SOURCE,
        source_account=ACCOUNT,
        source_message_id=MESSAGE,
        source_path=SourcePathStatus.TRUSTED,
        from_alignment=FromAlignment.ALIGNED,
        binding_revision=Revision(1),
        credential_revision=Revision(1),
        observed_at=NOW,
        expires_at=Timestamp(NOW.value + timedelta(days=1)),
        policy_version=PolicyVersion("other-policy"),
    )
    result = evaluator(rule(RuleKind.ALLOW_DOMAIN, "example.com")).evaluate(
        candidate(evidence=foreign), NOW
    )
    assert result.attention_reason is AdmissionAttentionReason.AUTHENTICITY_UNTRUSTED


def test_evidence_expiry_is_exclusive() -> None:
    expiry = Timestamp(NOW.value + timedelta(days=1))
    result = evaluator(rule(RuleKind.ALLOW_DOMAIN, "example.com")).evaluate(
        candidate(evidence=evidence(expires=expiry)), expiry
    )
    assert result.attention_reason is AdmissionAttentionReason.AUTHENTICITY_STALE


def test_no_matching_rule_is_not_implicit_admission() -> None:
    result = evaluator(rule(RuleKind.ALLOW_DOMAIN, "other.com")).evaluate(
        candidate(), NOW
    )
    assert not result.admit
    assert result.attention_reason is AdmissionAttentionReason.NO_RULE


def test_evidence_cannot_be_constructed_without_owner_issuer() -> None:
    from facet.projection.authenticity import VerifiedSourceEvidence

    with pytest.raises(TypeError):
        VerifiedSourceEvidence(  # type: ignore[call-arg]
            Role.SOURCE,
            ACCOUNT,
            MESSAGE,
            SourcePathStatus.TRUSTED,
            FromAlignment.ALIGNED,
            Revision(1),
            Revision(1),
            NOW,
            Timestamp(NOW.value + timedelta(days=1)),
            PolicyVersion("auth-v1"),
        )


def test_metadata_repr_does_not_contain_private_values() -> None:
    item = candidate()
    assert repr(item) == "<discovery candidate>"
    assert "example.com" not in repr(item)
    assert repr(evidence()) == "<verified source evidence>"
