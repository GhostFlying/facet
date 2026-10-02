"""Stable redaction helpers for experiment evidence."""

from __future__ import annotations

import hashlib


def fingerprint(value: str | None, *, prefix: str = "id") -> str | None:
    if value is None:
        return None
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def mask_email(address: str) -> str:
    local, separator, domain = address.partition("@")
    if not separator:
        return "***"
    visible = local[:1]
    return f"{visible}***@{domain}"
