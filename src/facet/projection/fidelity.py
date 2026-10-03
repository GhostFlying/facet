"""In-memory MIME facts used to verify a Gmail projection."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

from facet.contracts import DatePolicy, PolicyVersion, Sha256Hex
from facet.db.codecs import RfcMessageId, StorageFailure

_SEMANTIC_VERSION = PolicyVersion("mime-v1")
_TRANSPORT_HEADERS = {
    "authentication-results",
    "delivered-to",
    "received",
    "received-spf",
    "return-path",
    "x-google-smtp-source",
    "x-received",
}


@dataclass(frozen=True, slots=True, repr=False)
class FidelityFacts:
    """Digests and bounded header facts; no MIME payload is retained."""

    raw_digest: Sha256Hex
    semantic_digest: Sha256Hex
    semantic_version: PolicyVersion
    rfc_message_id: RfcMessageId | None
    date_policy: DatePolicy

    def __repr__(self) -> str:
        return "<fidelity facts>"


def _frame(digest: hashlib._Hash, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _header_value(message, name: str) -> str | None:
    values = message.get_all(name, [])
    if len(values) != 1 or not isinstance(values[0], str):
        return None
    return values[0].strip()


def _message_id(message) -> RfcMessageId | None:
    value = _header_value(message, "Message-ID")
    if value is None or not (value.startswith("<") and value.endswith(">")):
        return None
    if len(value) <= 2 or any(char.isspace() for char in value[1:-1]):
        return None
    try:
        return RfcMessageId(value)
    except (ValueError, StorageFailure):
        return None


def _date_policy(message) -> DatePolicy:
    value = _header_value(message, "Date")
    if value is None:
        return DatePolicy.FALLBACK_RECEIVED_TIME
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return DatePolicy.FALLBACK_RECEIVED_TIME
    if parsed is None or parsed.tzinfo is None:
        return DatePolicy.FALLBACK_RECEIVED_TIME
    try:
        parsed.astimezone(UTC)
    except (OverflowError, ValueError):
        return DatePolicy.FALLBACK_RECEIVED_TIME
    return DatePolicy.VALID_DATE_HEADER


def _is_transport(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered in _TRANSPORT_HEADERS
        or lowered.startswith("arc-")
        or lowered.startswith("x-gm-")
    )


def _part_digest(message, digest: hashlib._Hash) -> None:
    _frame(digest, message.get_content_type().lower().encode("utf-8"))
    disposition = message.get_content_disposition() or ""
    _frame(digest, disposition.lower().encode("utf-8"))
    filename = message.get_filename() or ""
    _frame(digest, filename.encode("utf-8", "surrogateescape"))
    content_id = message.get("Content-ID", "")
    _frame(digest, content_id.encode("utf-8", "surrogateescape"))
    for name, value in message.raw_items():
        if _is_transport(name):
            continue
        _frame(digest, name.lower().encode("utf-8", "surrogateescape"))
        _frame(digest, value.encode("utf-8", "surrogateescape"))
    if message.is_multipart():
        _frame(digest, b"multipart")
        for child in message.iter_parts():
            _part_digest(child, digest)
        return
    payload = message.get_payload(decode=True)
    if payload is None:
        value = message.get_payload(decode=False)
        payload = (
            value.encode("utf-8", "surrogateescape") if isinstance(value, str) else b""
        )
    _frame(digest, b"payload")
    _frame(digest, payload)


def inspect(raw: bytes) -> FidelityFacts:
    """Parse one raw message and return only non-content verification facts."""
    if type(raw) is not bytes or not raw:
        raise ValueError("invalid_input")
    raw_hash = hashlib.sha256(raw).hexdigest()
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        semantic = hashlib.sha256()
        _part_digest(message, semantic)
    except (LookupError, UnicodeError, ValueError):
        raise ValueError("invalid_input") from None
    return FidelityFacts(
        Sha256Hex(raw_hash),
        Sha256Hex(semantic.hexdigest()),
        _SEMANTIC_VERSION,
        _message_id(message),
        _date_policy(message),
    )


__all__ = ("FidelityFacts", "inspect")
