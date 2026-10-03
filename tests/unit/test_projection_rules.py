from dataclasses import replace

import pytest

from facet.config import RulesConfig
from facet.contracts import PolicyVersion, RuleKind
from facet.db.codecs import RuleValue
from facet.projection.rules import (
    RuleInputError,
    domain_matches,
    learn_domain,
    load_rule_policy,
    match_sender,
    normalize_domain,
    normalize_rule,
    normalize_rules,
    normalize_sender,
)


def test_normalization_is_ascii_and_preserves_local_part() -> None:
    sender = normalize_sender("User+tag@BÜCHER.DE")
    assert sender.local == "User+tag"
    assert sender.domain.value == "xn--bcher-kva.de"
    assert sender.value == "User+tag@xn--bcher-kva.de"


@pytest.mark.parametrize(
    "value",
    [
        "com",
        "co.uk",
        "example.invalid",
        "example.com/path",
        "example.com/*",
        "127.0.0.1",
        "foo..example.com",
        " foo.example.com",
    ],
)
def test_domain_rules_reject_ambiguous_values(value: str) -> None:
    with pytest.raises(RuleInputError):
        normalize_rule(RuleKind.ALLOW_DOMAIN, value)


def test_domain_matching_uses_whole_labels() -> None:
    root = normalize_domain("example.com")
    assert domain_matches(normalize_domain("example.com"), root)
    assert domain_matches(normalize_domain("mail.example.com"), root)
    assert not domain_matches(normalize_domain("notexample.com"), root)
    assert not domain_matches(normalize_domain("example.net"), root)
    assert not domain_matches(normalize_domain("example-com.com"), root)


def test_blacklist_takes_precedence_and_config_deduplicates() -> None:
    rules = normalize_rules(
        RulesConfig(
            allow_domains=("example.com", "EXAMPLE.COM"),
            allow_senders=("user@example.com",),
            blacklist_senders=("user@example.com",),
        )
    )
    assert len(rules.allow_domains) == 1
    result = match_sender(normalize_sender("user@example.com"), rules)
    assert result.matched and result.blacklisted


def test_sender_globs_are_not_a_rule_language() -> None:
    for value in ("*@example.com", "user?@example.com", "user[1]@example.com"):
        with pytest.raises(RuleInputError):
            normalize_rule(RuleKind.ALLOW_SENDER, value)


@pytest.mark.parametrize("value", ["user;tag@example.com", 'user"tag@example.com'])
def test_sender_uses_config_mailbox_grammar(value: str) -> None:
    with pytest.raises(RuleInputError):
        normalize_rule(RuleKind.ALLOW_SENDER, value)


def test_learn_domain_rejects_source_and_own_domains() -> None:
    sender = normalize_sender("billing@sub.vendor.com")
    assert learn_domain(sender, source_primary="me@source.net").domain is not None
    assert (
        learn_domain(sender, source_primary="me@vendor.com").reason.value
        == "source_primary_domain"
    )
    assert (
        learn_domain(
            sender,
            source_primary="me@source.net",
            own=("alias@vendor.com",),
        ).reason.value
        == "own_domain"
    )


def test_policy_is_fixed_and_offline() -> None:
    policy = load_rule_policy()
    assert policy.version.value == "psl-tldextract-5.3.2-idna-3.20"
    assert (
        normalize_domain("foo.github.io", policy=policy.suffix).registrable
        == "github.io"
    )
    with pytest.raises(RuleInputError):
        normalize_rule(RuleKind.ALLOW_DOMAIN, "io", policy=policy)


def test_rule_values_are_bounded_private_scalars() -> None:
    rule = normalize_rule(RuleKind.ALLOW_SENDER, "user@example.com")
    assert type(rule.storage_value) is RuleValue
    assert repr(rule) == "<normalized rule>"
    assert "example.com" not in repr(rule)


def test_manual_public_suffix_or_foreign_policy_values_are_rejected() -> None:
    from facet.projection.suffixes import CanonicalDomain, SuffixInputError

    with pytest.raises(SuffixInputError):
        CanonicalDomain("co.uk", "co.uk", PolicyVersion("foreign"))

    with pytest.raises(SuffixInputError):
        CanonicalDomain("co.uk", "co.uk")


def test_replacing_config_with_invalid_type_is_rejected() -> None:
    with pytest.raises(RuleInputError):
        normalize_rules(replace(RulesConfig(), allow_senders=["a@example.com"]))


def test_untrusted_authentication_mode_is_rejected() -> None:
    with pytest.raises(RuleInputError):
        normalize_rules(RulesConfig(authenticity="allow_unknown"))
