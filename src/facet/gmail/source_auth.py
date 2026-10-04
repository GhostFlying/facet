"""Source-path attestation providers for the Gmail candidate adapter.

The metadata adapter never treats provider response headers as authentication
evidence.  Production uses the cryptographic DKIM provider below, which
verifies the exact raw message fetched for a Gmail message ID.  Unknown and
synthetic providers remain available for fail-closed seams and offline tests;
the synthetic implementation cannot manufacture evidence from headers or
provider response data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from email import message_from_bytes
from email.message import Message
from email.policy import default
from email.utils import getaddresses
from typing import Protocol

import dkim

from facet.contracts import PolicyVersion, ProviderId, Revision, Role, Timestamp
from facet.db.codecs import PrivateAddress
from facet.projection.authenticity import (
    FromAlignment,
    SourcePathStatus,
    VerifiedSourceEvidence,
    _issuer_for_provider,
    assess_evidence,
)
from facet.projection.rules import normalize_sender
from facet.projection.suffixes import normalize_domain

_AUTH_POLICY = PolicyVersion("auth-v1")


class _SilentLogger:
    """Prevent third-party verifier diagnostics from crossing our boundary."""

    def isEnabledFor(self, _level):
        return False

    def debug(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None


_SILENT_LOGGER = _SilentLogger()


class SourceAuthProvider(Protocol):
    """Producer-owned source-path attestation boundary."""

    def attest(
        self,
        *,
        source_account: PrivateAddress,
        message_id: ProviderId,
        observed_at: Timestamp,
        binding_revision: Revision,
        credential_revision: Revision,
        raw: bytes | None = None,
    ) -> VerifiedSourceEvidence | None:
        """Return evidence for this exact message, or unknown (``None``)."""


@dataclass(frozen=True, slots=True, repr=False)
class UnknownSourceAuthProvider:
    """The production-safe default: no independently verified attestation."""

    def attest(
        self,
        *,
        source_account: PrivateAddress,
        message_id: ProviderId,
        observed_at: Timestamp,
        binding_revision: Revision,
        credential_revision: Revision,
        raw: bytes | None = None,
    ) -> None:
        if (
            type(source_account) is not PrivateAddress
            or type(message_id) is not ProviderId
            or type(observed_at) is not Timestamp
            or type(binding_revision) is not Revision
            or type(credential_revision) is not Revision
        ):
            raise ValueError("invalid_input")
        return None

    def __repr__(self) -> str:
        return "<unknown source auth provider>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticSourceAuthProvider:
    """Offline-only provider for a previously issued synthetic attestation.

    The evidence is still checked against every call's account, message,
    binding/credential lineage and freshness.  No caller-provided boolean,
    header text or policy value is accepted as evidence.
    """

    evidence: VerifiedSourceEvidence

    def __post_init__(self) -> None:
        if type(self.evidence) is not VerifiedSourceEvidence:
            raise ValueError("invalid_input")

    def attest(
        self,
        *,
        source_account: PrivateAddress,
        message_id: ProviderId,
        observed_at: Timestamp,
        binding_revision: Revision,
        credential_revision: Revision,
        raw: bytes | None = None,
    ) -> VerifiedSourceEvidence | None:
        if (
            type(source_account) is not PrivateAddress
            or type(message_id) is not ProviderId
            or type(observed_at) is not Timestamp
            or type(binding_revision) is not Revision
            or type(credential_revision) is not Revision
        ):
            raise ValueError("invalid_input")
        assessment = assess_evidence(
            self.evidence,
            source_account=source_account,
            message_id=message_id,
            now=observed_at,
            binding_revision=binding_revision,
            credential_revision=credential_revision,
            policy_version=_AUTH_POLICY,
        )
        return self.evidence if assessment.trusted else None

    def __repr__(self) -> str:
        return "<synthetic source auth provider>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class DkimSourceAuthProvider:
    """Cryptographically verify one Gmail message's sender authentication.

    The provider accepts only a raw message fetched for the exact Gmail
    message ID.  It does not consume provider authentication headers as
    evidence.  DNS and parse failures intentionally collapse to unknown.
    """

    dnsfunc: object = dkim.get_txt
    timeout: int = 5
    max_raw_bytes: int = 25 * 1024 * 1024

    # SourceAdapter uses this to avoid fetching raw content for the safe
    # unknown/synthetic providers.
    requires_raw = True

    def __post_init__(self) -> None:
        if (
            not callable(self.dnsfunc)
            or type(self.timeout) is not int
            or not 1 <= self.timeout <= 30
            or type(self.max_raw_bytes) is not int
            or not 1 <= self.max_raw_bytes <= 50 * 1024 * 1024
        ):
            raise ValueError("invalid_input")

    def attest(
        self,
        *,
        source_account: PrivateAddress,
        message_id: ProviderId,
        observed_at: Timestamp,
        binding_revision: Revision,
        credential_revision: Revision,
        raw: bytes | None = None,
    ) -> VerifiedSourceEvidence | None:
        if (
            type(source_account) is not PrivateAddress
            or type(message_id) is not ProviderId
            or type(observed_at) is not Timestamp
            or type(binding_revision) is not Revision
            or type(credential_revision) is not Revision
            or type(raw) is not bytes
            or not raw
            or len(raw) > self.max_raw_bytes
        ):
            return None
        try:
            from_domain, signing_domains = self._verified_domains(raw)
        except Exception:
            # The exception may contain provider/raw data.  It must not cross
            # the provider boundary or enter logs/diagnostics.
            return None
        aligned = {
            domain
            for domain in signing_domains
            if domain == from_domain or domain.registrable == from_domain.registrable
        }
        if len(aligned) != 1:
            return None
        return _issuer_for_provider().issue(
            source_role=Role.SOURCE,
            source_account=source_account,
            source_message_id=message_id,
            source_path=SourcePathStatus.TRUSTED,
            from_alignment=FromAlignment.ALIGNED,
            binding_revision=binding_revision,
            credential_revision=credential_revision,
            observed_at=observed_at,
            expires_at=Timestamp(observed_at.value + timedelta(hours=1)),
            policy_version=_AUTH_POLICY,
        )

    def _verified_domains(self, raw: bytes):
        message: Message = message_from_bytes(raw, policy=default)
        names = {name.casefold() for name in message}
        if names & {
            "arc-seal",
            "arc-message-signature",
            "arc-authentication-results",
            "resent-from",
            "resent-sender",
        }:
            # A valid signature may survive forwarding.  Without an explicit
            # original-delivery attestation, forwarding/ARC is ambiguous.
            raise ValueError("forwarding_ambiguous")
        from_values = message.get_all("From", [])
        addresses = getaddresses(from_values)
        if len(addresses) != 1 or not addresses[0][1]:
            raise ValueError("from_ambiguous")
        from_domain = normalize_sender(addresses[0][1]).domain

        verifier = dkim.DKIM(raw, logger=_SILENT_LOGGER, timeout=self.timeout)
        signatures = [
            value
            for name, value in verifier.headers
            if name.lower() == b"dkim-signature"
        ]
        if not signatures:
            return from_domain, ()
        signing_domains = []
        for index, signature in enumerate(signatures):
            try:
                tags = dkim.parse_tag_value(signature)
                signing_domain = normalize_domain(tags[b"d"].decode("ascii"))
                valid = verifier.verify(index, dnsfunc=self.dnsfunc)
            except (UnicodeError, KeyError, TypeError, ValueError, OSError):
                raise ValueError("signature_invalid") from None
            if not valid:
                raise ValueError("signature_invalid")
            signing_domains.append(signing_domain)
        return from_domain, tuple(signing_domains)


__all__ = (
    "SourceAuthProvider",
    "DkimSourceAuthProvider",
    "SyntheticSourceAuthProvider",
    "UnknownSourceAuthProvider",
)
