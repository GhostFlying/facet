"""Raw Gmail message parsing without MIME reserialization."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import Any

from facet_spike.errors import SpikeError
from facet_spike.privacy import fingerprint

_AUTH_RESULT = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-zA-Z0-9_-]+)", re.I)


@dataclass(frozen=True)
class PartDigest:
    content_type: str
    disposition: str | None
    size: int
    sha256: str


@dataclass(frozen=True)
class MessageAnalysis:
    raw_bytes: bytes
    raw_sha256: str
    rfc_message_id: str | None
    date_header: str | None
    parsed_date: str | None
    parts: tuple[PartDigest, ...]
    auth_results: dict[str, Any]

    def redacted_summary(self) -> dict[str, Any]:
        return {
            "raw_size": len(self.raw_bytes),
            "raw_sha256": self.raw_sha256,
            "rfc_message_id": fingerprint(
                self.rfc_message_id,
                prefix="rfc-message-id",
            ),
            "date_present": self.date_header is not None,
            "parsed_date": self.parsed_date,
            "parts": [
                {
                    "content_type": part.content_type,
                    "disposition": part.disposition,
                    "size": part.size,
                    "sha256": part.sha256,
                }
                for part in self.parts
            ],
            "authentication": self.auth_results,
        }


def decode_raw(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw + padding)
    except (ValueError, TypeError) as error:
        raise SpikeError("Gmail returned invalid base64url raw content") from error


def parse_raw(raw: str) -> MessageAnalysis:
    raw_bytes = decode_raw(raw)
    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    message_id = _single_line_header(message.get("Message-ID"))
    date_header = _single_line_header(message.get("Date"))
    parsed_date = _parse_date(date_header)
    parts = tuple(
        _part_digest(part) for part in message.walk() if not part.is_multipart()
    )
    return MessageAnalysis(
        raw_bytes=raw_bytes,
        raw_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        rfc_message_id=message_id,
        date_header=date_header,
        parsed_date=parsed_date,
        parts=parts,
        auth_results=_authentication_summary(message),
    )


def compare_messages(
    source: MessageAnalysis,
    target: MessageAnalysis,
) -> dict[str, Any]:
    source_parts = [
        (part.content_type, part.disposition, part.size, part.sha256)
        for part in source.parts
    ]
    target_parts = [
        (part.content_type, part.disposition, part.size, part.sha256)
        for part in target.parts
    ]
    return {
        "raw_equal": source.raw_sha256 == target.raw_sha256,
        "rfc_message_id_equal": source.rfc_message_id == target.rfc_message_id,
        "date_header_equal": source.date_header == target.date_header,
        "mime_payloads_equal": source_parts == target_parts,
        "source_part_count": len(source_parts),
        "target_part_count": len(target_parts),
    }


def rfc822_query(message_id: str) -> str:
    if "\r" in message_id or "\n" in message_id:
        raise SpikeError("unsafe newline in RFC Message-ID")
    return f"rfc822msgid:{message_id.strip()}"


def _single_line_header(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if "\r" in normalized or "\n" in normalized:
        return None
    return normalized or None


def _parse_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.isoformat()


def _part_digest(part: Message) -> PartDigest:
    payload = part.get_payload(decode=True)
    if payload is None:
        undecoded = part.get_payload()
        payload = undecoded.encode("utf-8", errors="replace") if undecoded else b""
    return PartDigest(
        content_type=part.get_content_type(),
        disposition=part.get_content_disposition(),
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _authentication_summary(message: Message) -> dict[str, Any]:
    headers = message.get_all("Authentication-Results", [])
    headers += message.get_all("ARC-Authentication-Results", [])
    results: dict[str, set[str]] = {"spf": set(), "dkim": set(), "dmarc": set()}
    for header in headers:
        for mechanism, result in _AUTH_RESULT.findall(str(header)):
            results[mechanism.lower()].add(result.lower())
    return {
        "header_count": len(headers),
        "spf": sorted(results["spf"]),
        "dkim": sorted(results["dkim"]),
        "dmarc": sorted(results["dmarc"]),
    }
