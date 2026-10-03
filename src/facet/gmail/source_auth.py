"""Closed source-path attestation seam for the Gmail candidate adapter.

The Gmail metadata adapter is deliberately not an authentication parser.  A
separate, owner-controlled producer may attest to a source-path result, while
the default implementation remains unknown.  The synthetic implementation is
only useful for offline tests and cannot manufacture evidence from headers or
provider response data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from facet.contracts import PolicyVersion, ProviderId, Revision, Timestamp
from facet.db.codecs import PrivateAddress
from facet.projection.authenticity import (
    VerifiedSourceEvidence,
    assess_evidence,
)

_AUTH_POLICY = PolicyVersion("auth-v1")


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


__all__ = (
    "SourceAuthProvider",
    "SyntheticSourceAuthProvider",
    "UnknownSourceAuthProvider",
)
