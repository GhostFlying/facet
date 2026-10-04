"""Strict structural configuration, not binding verification or admission policy."""

import ipaddress
import re
import unicodedata
from dataclasses import dataclass

import yaml
from yaml.events import AliasEvent

from facet.contracts import ErrorCode, ProjectionId, SourceMode

MAX_CONFIG_BYTES = 1024 * 1024
MAX_DEPTH = 16
MAX_COLLECTION_ITEMS = 1000
# Registration requires a reviewed per-field extension and M1-03's executor.
MUTABLE_CONFIG_FIELDS: tuple[str, ...] = ()


class ConfigError(Exception):
    """Fixed code only: never retains configuration or parser exception text."""

    def __init__(self, code: ErrorCode = ErrorCode.INVALID_INPUT) -> None:
        self.code = code
        super().__init__(code.value)


class _StrictLoader(yaml.SafeLoader):
    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._depth = 0
        self._items = 0

    def compose_node(self, parent: object, index: object) -> object:
        event = self.peek_event()
        if isinstance(event, AliasEvent) or getattr(event, "anchor", None) is not None:
            raise ConfigError()
        self._depth += 1
        if self._depth > MAX_DEPTH:
            raise ConfigError()
        try:
            node = super().compose_node(parent, index)
            if isinstance(node, (yaml.MappingNode, yaml.SequenceNode)):
                self._items += len(node.value)
                if self._items > MAX_COLLECTION_ITEMS:
                    raise ConfigError()
            return node
        finally:
            self._depth -= 1

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        result = {}
        for key_node, value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise ConfigError()
            key = self.construct_object(key_node, deep=deep)
            if type(key) is not str or key in result:
                raise ConfigError()
            result[key] = self.construct_object(value_node, deep=deep)
        return result


# Do not mutate SafeLoader's process-global resolver table or accept YAML 1.1's
# implicit yes/on/off booleans. The model accepts exact scalar types only.
_StrictLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in rules if tag != "tag:yaml.org,2002:bool"]
    for key, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), ["t", "f"]
)


@dataclass(frozen=True, slots=True, repr=False)
class ProjectionConfig:
    id: ProjectionId
    source_email: str
    target_email: str
    source_mode: SourceMode
    own_addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class SyncConfig:
    poll_interval_seconds: int = 30
    backfill_lookback_months: int = 6
    thread_concurrency: int = 4
    source_reconcile_interval_hours: int = 24
    target_audit_interval_hours: int = 168


@dataclass(frozen=True, slots=True, repr=False)
class RulesConfig:
    allow_domains: tuple[str, ...] = ()
    allow_senders: tuple[str, ...] = ()
    blacklist_senders: tuple[str, ...] = ()
    authenticity: str = "require_trusted_auth"


@dataclass(frozen=True, slots=True, repr=False)
class TargetConfig:
    inbox: bool = False
    projected_label: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class WebConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    refresh_interval_seconds: int = 10


@dataclass(frozen=True, slots=True, repr=False)
class Config:
    projection: ProjectionConfig
    sync: SyncConfig
    rules: RulesConfig
    target: TargetConfig
    web: WebConfig


def _mapping(value: object, keys: set[str]) -> dict:
    if type(value) is not dict or any(
        type(k) is not str or k not in keys for k in value
    ):
        raise ConfigError()
    return value


def _string(value: object) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value)
    ):
        raise ConfigError()
    return value


def _mailbox(value: object) -> str:
    address = _string(value)
    if (
        address.count("@") != 1
        or any(c.isspace() or c in '<>(),;:"\\' for c in address)
        or any(not part for part in address.split("@"))
    ):
        raise ConfigError()
    return address


def _strings(value: object, *, mailboxes: bool = False) -> tuple[str, ...]:
    if type(value) is not list:
        raise ConfigError()
    validator = _mailbox if mailboxes else _string
    return tuple(validator(v) for v in value)


def _positive(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ConfigError()
    return value


def _bool(value: object) -> bool:
    if type(value) is not bool:
        raise ConfigError()
    return value


def _model(document: object) -> Config:
    top = _mapping(document, {"projection", "sync", "rules", "target", "web"})
    projection = _mapping(
        top.get("projection"),
        {"id", "source_email", "target_email", "source_mode", "own_addresses"},
    )
    source = _mailbox(projection.get("source_email"))
    target = _mailbox(projection.get("target_email"))
    if source.casefold() == target.casefold():
        raise ConfigError(ErrorCode.BINDING_MISMATCH)
    try:
        selector = ProjectionId(projection.get("id"))
        mode = SourceMode(projection.get("source_mode", "readonly"))
    except (ValueError, TypeError):
        raise ConfigError() from None
    own = _strings(projection.get("own_addresses", [source]), mailboxes=True)
    sync = _mapping(
        top.get("sync", {}),
        {
            "poll_interval_seconds",
            "backfill_lookback_months",
            "thread_concurrency",
            "source_reconcile_interval_hours",
            "target_audit_interval_hours",
        },
    )
    sync_model = SyncConfig(
        **{
            key: _positive(sync.get(key, getattr(SyncConfig(), key)))
            for key in SyncConfig.__dataclass_fields__
        }
    )
    if sync_model.backfill_lookback_months != 6:
        raise ConfigError()
    rules = _mapping(
        top.get("rules", {}),
        {"allow_domains", "allow_senders", "blacklist_senders", "authenticity"},
    )
    if rules.get("authenticity", "require_trusted_auth") != "require_trusted_auth":
        raise ConfigError()
    rules_model = RulesConfig(
        _strings(rules.get("allow_domains", [])),
        _strings(rules.get("allow_senders", []), mailboxes=True),
        _strings(rules.get("blacklist_senders", []), mailboxes=True),
    )
    target_options = _mapping(top.get("target", {}), {"inbox", "projected_label"})
    label = target_options.get("projected_label")
    if label is not None:
        label = _string(label)
    target_model = TargetConfig(_bool(target_options.get("inbox", False)), label)
    web = _mapping(
        top.get("web", {}), {"enabled", "host", "port", "refresh_interval_seconds"}
    )
    host = _string(web.get("host", "0.0.0.0"))
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise ConfigError() from None
    port = _positive(web.get("port", 8080))
    if port > 65535:
        raise ConfigError()
    return Config(
        ProjectionConfig(selector, source, target, mode, own),
        sync_model,
        rules_model,
        target_model,
        WebConfig(
            _bool(web.get("enabled", True)),
            host,
            port,
            _positive(web.get("refresh_interval_seconds", 10)),
        ),
    )


def load_config(raw: bytes) -> Config:
    """Parse exactly one bounded document; errors never expose the input."""
    if type(raw) is not bytes or len(raw) > MAX_CONFIG_BYTES:
        raise ConfigError()
    try:
        text = raw.decode("utf-8", errors="strict")
        loader = _StrictLoader(text)
        try:
            document = loader.get_single_data()
        finally:
            loader.dispose()
        return _model(document)
    except ConfigError:
        raise
    except (UnicodeError, yaml.YAMLError, ValueError, TypeError, RecursionError):
        raise ConfigError() from None


def initial_template(
    source_email: str, target_email: str, projection_id: str = "gmail-default"
) -> Config:
    """Construct in memory only. The future ownership handler writes the file."""
    return _model(
        {
            "projection": {
                "id": projection_id,
                "source_email": source_email,
                "target_email": target_email,
            }
        }
    )


def dump_config(config: Config) -> bytes:
    """Serialize the closed configuration schema to deterministic YAML bytes."""
    if type(config) is not Config:
        raise ConfigError()
    document = {
        "projection": {
            "id": config.projection.id.value,
            "source_email": config.projection.source_email,
            "target_email": config.projection.target_email,
            "source_mode": config.projection.source_mode.value,
            "own_addresses": list(config.projection.own_addresses),
        },
        "sync": {
            "poll_interval_seconds": config.sync.poll_interval_seconds,
            "backfill_lookback_months": config.sync.backfill_lookback_months,
            "thread_concurrency": config.sync.thread_concurrency,
            "source_reconcile_interval_hours": (
                config.sync.source_reconcile_interval_hours
            ),
            "target_audit_interval_hours": config.sync.target_audit_interval_hours,
        },
        "rules": {
            "allow_domains": list(config.rules.allow_domains),
            "allow_senders": list(config.rules.allow_senders),
            "blacklist_senders": list(config.rules.blacklist_senders),
            "authenticity": config.rules.authenticity,
        },
        "target": {
            "inbox": config.target.inbox,
            "projected_label": config.target.projected_label,
        },
        "web": {
            "enabled": config.web.enabled,
            "host": config.web.host,
            "port": config.web.port,
            "refresh_interval_seconds": config.web.refresh_interval_seconds,
        },
    }
    try:
        raw = yaml.safe_dump(
            document,
            allow_unicode=False,
            default_flow_style=False,
            sort_keys=False,
        ).encode("utf-8")
    except (UnicodeError, TypeError, yaml.YAMLError):
        raise ConfigError() from None
    if len(raw) > MAX_CONFIG_BYTES or load_config(raw) != config:
        raise ConfigError()
    return raw


def config_warnings(config: Config) -> tuple[str, ...]:
    warnings = ["binding_verification_pending", "managed_state_check_pending"]
    if (
        config.rules.allow_domains
        or config.rules.allow_senders
        or config.rules.blacklist_senders
    ):
        warnings.append("rule_validation_pending")
    return tuple(warnings)
