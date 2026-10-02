from __future__ import annotations

import base64

import pytest

from facet_spike.errors import SpikeError
from facet_spike.message import compare_messages, parse_raw, rfc822_query

RAW_MESSAGE = b"""From: Hyatt <offers@mail.hyatt.com>\r
To: user@example.com\r
Subject: Reservation\r
Date: Tue, 01 Sep 2026 10:00:00 +0800\r
Message-ID: <reservation-1@example.com>\r
Authentication-Results: mx.google.com; spf=pass; dkim=pass; dmarc=pass\r
MIME-Version: 1.0\r
Content-Type: multipart/mixed; boundary=facet\r
\r
--facet\r
Content-Type: text/plain; charset=utf-8\r
\r
hello\r
--facet\r
Content-Type: application/octet-stream\r
Content-Disposition: attachment; filename=receipt.bin\r
Content-Transfer-Encoding: base64\r
\r
AAEC\r
--facet--\r
"""


def encoded(raw: bytes = RAW_MESSAGE) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def test_parse_raw_records_payload_digests_and_authentication() -> None:
    analysis = parse_raw(encoded())

    assert analysis.rfc_message_id == "<reservation-1@example.com>"
    assert analysis.parsed_date == "2026-09-01T10:00:00+08:00"
    assert [part.content_type for part in analysis.parts] == [
        "text/plain",
        "application/octet-stream",
    ]
    assert analysis.parts[1].size == 3
    assert analysis.auth_results == {
        "header_count": 1,
        "spf": ["pass"],
        "dkim": ["pass"],
        "dmarc": ["pass"],
    }


def test_compare_detects_equal_mime_payloads() -> None:
    first = parse_raw(encoded())
    second = parse_raw(encoded())

    comparison = compare_messages(first, second)

    assert comparison["raw_equal"] is True
    assert comparison["mime_payloads_equal"] is True
    assert comparison["rfc_message_id_equal"] is True


def test_rfc822_query_rejects_header_injection() -> None:
    with pytest.raises(SpikeError):
        rfc822_query("<safe@example.com>\nfrom:attacker@example.com")
