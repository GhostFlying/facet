from dataclasses import FrozenInstanceError

import pytest
import yaml

from facet.config import (
    MAX_CONFIG_BYTES,
    MUTABLE_CONFIG_FIELDS,
    ConfigError,
    config_warnings,
    initial_template,
    load_config,
)
from facet.contracts import SourceMode

MINIMAL = b"""projection:
  id: gmail-default
  source_email: source@synthetic.example
  target_email: target@synthetic.example
"""


def test_defaults_are_conservative_and_immutable():
    config = load_config(MINIMAL)
    assert config == initial_template(
        "source@synthetic.example", "target@synthetic.example"
    )
    assert config.projection.source_mode is SourceMode.READONLY
    assert config.projection.own_addresses == ("source@synthetic.example",)
    assert config.sync.backfill_lookback_months == 6
    assert config.sync.thread_concurrency == 4
    assert config.sync.poll_interval_seconds == 60
    assert config.sync.source_reconcile_interval_hours == 24
    assert config.sync.target_audit_interval_hours == 168
    assert config.target.inbox is False
    assert config.target.projected_label is None
    assert config.web.enabled is True and config.web.host == "0.0.0.0"
    assert config.web.port == 8080 and config.web.refresh_interval_seconds == 10
    assert config.rules.allow_domains == config.rules.allow_senders == ()
    assert MUTABLE_CONFIG_FIELDS == ()
    assert "rule_validation_pending" not in config_warnings(config)
    with pytest.raises(FrozenInstanceError):
        config.web.port = 1
    assert "synthetic.example" not in repr(config)


@pytest.mark.parametrize(
    "suffix",
    [
        "projection: {}",
        "extra: true",
        "sync: {typo: 1}",
        "sync: {backfill_lookback_months: 5}",
        "sync: {thread_concurrency: true}",
        "sync: {poll_interval_seconds: '30'}",
        "sync: {poll_interval_seconds: 0}",
        "sync: {poll_interval_seconds: 1.0}",
        "web: {port: 65536}",
        "web: {port: -1}",
        "web: {host: private-hostname}",
        "web: {enabled: yes}",
        "target: {inbox: on}",
        "target: {projected_label: ''}",
        "rules: {authenticity: ignore}",
        "rules: {allow_domains: synthetic.example}",
        "rules: {allow_domains: ['']}",
        "web: {unknown: 1}",
        "target: {unknown: 1}",
    ],
)
def test_unknown_fields_coercions_and_forbidden_changes(suffix):
    with pytest.raises(ConfigError):
        load_config(MINIMAL + suffix.encode())


@pytest.mark.parametrize(
    "raw",
    [
        b"!!python/object/apply:os.system ['never executed']",
        MINIMAL + b"web: &alias {port: 8080}\ntarget: *alias",
        MINIMAL + b"web: {<<: {port: 8080}}",
        MINIMAL + b"---\n{}",
        MINIMAL + b"web: {port: 1, port: 2}",
        MINIMAL + b"web: {1: 8080}",
        MINIMAL + b"web: !!set {port: null}",
        b"\xff",
        b"",
        b"[]",
        b"null",
        b"a" * (MAX_CONFIG_BYTES + 1),
        MINIMAL + ("web: " + "[" * 20 + "0" + "]" * 20).encode(),
        MINIMAL
        + (
            "rules: {allow_domains: [" + ",".join("a" for _ in range(1001)) + "]}"
        ).encode(),
    ],
)
def test_unsafe_yaml_and_resource_limits(raw):
    with pytest.raises(ConfigError, match="^invalid_input$"):
        load_config(raw)


@pytest.mark.parametrize(
    "address", ["", " ", "display <a@b>", "a@b,c@d", "a", "@b", "a@", "a\nb@c"]
)
def test_mailbox_shape(address):
    with pytest.raises(ConfigError):
        initial_template(address, "target@synthetic.example")


def test_roles_own_addresses_and_rules_remain_pending():
    with pytest.raises(ConfigError, match="^binding_mismatch$"):
        initial_template("Same@synthetic.example", "same@synthetic.example")
    # No Gmail dot/plus/alias equivalence or settings access is inferred.
    config = initial_template("s.ource@synthetic.example", "source@synthetic.example")
    assert config.projection.source_email != config.projection.target_email
    config = load_config(MINIMAL + b"rules: {allow_domains: [com]}\n")
    assert "rule_validation_pending" in config_warnings(config)
    assert config.rules.allow_domains == ("com",)  # structural, NOT PSL/admission pass


def test_legacy_authenticity_setting_is_ignored_and_not_serialized():
    config = load_config(MINIMAL + b"rules: {authenticity: require_trusted_auth}\n")
    assert config.rules.allow_domains == ()
    from facet.config import dump_config

    assert b"authenticity" not in dump_config(config)


def test_safe_loader_global_rules_are_not_modified():
    assert yaml.safe_load("enabled: yes") == {"enabled": True}


def test_errors_cannot_echo_private_yaml_sentinel():
    sentinel = "PRIVATE_BODY_CREDENTIAL_SENTINEL"
    with pytest.raises(ConfigError) as raised:
        load_config(MINIMAL + f"{sentinel}: [invalid".encode())
    assert sentinel not in str(raised.value)
