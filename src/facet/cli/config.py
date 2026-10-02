"""Working structural-only config commands with explicit private output."""

from facet.config import Config, ConfigError, config_warnings, load_config
from facet.contracts import ErrorCode, ProjectionId
from facet.private_paths import (
    filesystem_warning,
    inspect_state_root,
    read_standalone_config,
    select_paths,
)


def _summary(config: Config) -> dict:
    # An explicit local allowlist, not dataclasses.asdict or a public DTO.
    return {
        "source_mode": config.projection.source_mode.value,
        "own_address_count": len(config.projection.own_addresses),
        "allow_domain_count": len(config.rules.allow_domains),
        "allow_sender_count": len(config.rules.allow_senders),
        "blacklist_sender_count": len(config.rules.blacklist_senders),
        "authenticity": config.rules.authenticity,
        "poll_interval_seconds": config.sync.poll_interval_seconds,
        "backfill_lookback_months": config.sync.backfill_lookback_months,
        "thread_concurrency": config.sync.thread_concurrency,
        "source_reconcile_interval_hours": config.sync.source_reconcile_interval_hours,
        "target_audit_interval_hours": config.sync.target_audit_interval_hours,
        "target_inbox": config.target.inbox,
        "projected_label_configured": config.target.projected_label is not None,
        "web_enabled": config.web.enabled,
        "web_host": config.web.host,
        "web_port": config.web.port,
        "web_refresh_interval_seconds": config.web.refresh_interval_seconds,
    }


def config_read(options: object, *, show: bool) -> tuple[dict, tuple[str, ...]]:
    if getattr(options, "public", False):
        raise ConfigError(ErrorCode.SCOPE_REQUIRED)
    paths = select_paths(
        getattr(options, "state_dir", None), getattr(options, "config_path", None)
    )
    inspect_state_root(paths.root)
    fs_warning = filesystem_warning(paths.root)
    config = load_config(
        read_standalone_config(
            paths,
            explicit=getattr(options, "config_path", None) is not None,
        )
    )
    selector = getattr(options, "projection", None)
    if selector is not None and ProjectionId(selector) != config.projection.id:
        raise ConfigError(ErrorCode.BINDING_MISMATCH)
    data = {"validation_scope": "structural_only"}
    if show:
        data.update(_summary(config))
        if getattr(options, "private_metadata", False):
            data["private_metadata"] = {
                "projection": config.projection.id.value,
                "source_email": config.projection.source_email,
                "target_email": config.projection.target_email,
                "own_addresses": list(config.projection.own_addresses),
                "allow_domains": list(config.rules.allow_domains),
                "allow_senders": list(config.rules.allow_senders),
                "blacklist_senders": list(config.rules.blacklist_senders),
                "projected_label": config.target.projected_label,
                "state_dir": str(paths.root),
                "config": str(paths.config),
            }
    return data, (*config_warnings(config), fs_warning)
