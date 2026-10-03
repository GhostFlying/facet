"""Typed source-path authenticity evidence; provider parsing lives elsewhere."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from facet.contracts import PolicyVersion, ProviderId, Revision, Role, Timestamp
from facet.db.codecs import PrivateAddress


class SourcePathStatus(StrEnum):
    TRUSTED = "trusted"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class FromAlignment(StrEnum):
    ALIGNED = "aligned"
    MISALIGNED = "misaligned"
    UNKNOWN = "unknown"


class EvidenceReason(StrEnum):
    TRUSTED = "trusted"
    MISSING = "missing"
    ROLE_MISMATCH = "role_mismatch"
    ACCOUNT_MISMATCH = "account_mismatch"
    MESSAGE_MISMATCH = "message_mismatch"
    LINEAGE_MISMATCH = "lineage_mismatch"
    NOT_CURRENT = "not_current"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    SOURCE_PATH_REJECTED = "source_path_rejected"
    SOURCE_PATH_UNKNOWN = "source_path_unknown"
    FROM_MISALIGNED = "from_misaligned"
    FROM_UNKNOWN = "from_unknown"


@dataclass(frozen=True, slots=True, repr=False, init=False)
class VerifiedSourceEvidence:
    source_role: Role
    source_account: PrivateAddress
    source_message_id: ProviderId
    source_path: SourcePathStatus
    from_alignment: FromAlignment
    binding_revision: Revision
    credential_revision: Revision
    observed_at: Timestamp
    expires_at: Timestamp
    policy_version: PolicyVersion

    def __init__(
        self,
        source_role: Role,
        source_account: PrivateAddress,
        source_message_id: ProviderId,
        source_path: SourcePathStatus,
        from_alignment: FromAlignment,
        binding_revision: Revision,
        credential_revision: Revision,
        observed_at: Timestamp,
        expires_at: Timestamp,
        policy_version: PolicyVersion,
        *,
        _token: object,
    ) -> None:
        if _token is not _EVIDENCE_TOKEN:
            raise ValueError("invalid_input")
        values = (
            source_role,
            source_account,
            source_message_id,
            source_path,
            from_alignment,
            binding_revision,
            credential_revision,
            observed_at,
            expires_at,
            policy_version,
        )
        if (
            type(source_role) is not Role
            or type(source_account) is not PrivateAddress
            or type(source_message_id) is not ProviderId
            or type(source_path) is not SourcePathStatus
            or type(from_alignment) is not FromAlignment
            or type(binding_revision) is not Revision
            or type(credential_revision) is not Revision
            or type(observed_at) is not Timestamp
            or type(expires_at) is not Timestamp
            or type(policy_version) is not PolicyVersion
            or source_role is not Role.SOURCE
            or binding_revision.value < 1
            or credential_revision.value < 1
            or expires_at.value <= observed_at.value
            or expires_at.value - observed_at.value > timedelta(days=7)
        ):
            raise ValueError("invalid_input")
        for field, value in zip(self.__dataclass_fields__, values, strict=True):
            object.__setattr__(self, field, value)

    def __repr__(self) -> str:
        return "<verified source evidence>"

    __str__ = __repr__


_EVIDENCE_TOKEN = object()


@dataclass(frozen=True, slots=True, repr=False)
class SourcePathEvidenceIssuer:
    """Owner-bound constructor for producer-issued evidence."""

    _token: object

    def __post_init__(self) -> None:
        if self._token is not _EVIDENCE_TOKEN:
            raise ValueError("invalid_input")

    def issue(self, **kwargs: object) -> VerifiedSourceEvidence:
        return VerifiedSourceEvidence(**kwargs, _token=_EVIDENCE_TOKEN)

    def __repr__(self) -> str:
        return "<source evidence issuer>"

    __str__ = __repr__


def _issuer_for_tests() -> SourcePathEvidenceIssuer:
    """Synthetic producer hook; the real M1-06 owner supplies its own issuer."""

    return SourcePathEvidenceIssuer(_EVIDENCE_TOKEN)


@dataclass(frozen=True, slots=True, repr=False)
class TrustAssessment:
    trusted: bool
    reason: EvidenceReason

    def __post_init__(self) -> None:
        if type(self.trusted) is not bool or type(self.reason) is not EvidenceReason:
            raise ValueError("invalid_input")

    def __repr__(self) -> str:
        return "<trust assessment>"

    __str__ = __repr__


def assess_evidence(
    evidence: VerifiedSourceEvidence | None,
    *,
    source_account: PrivateAddress,
    message_id: ProviderId,
    now: Timestamp,
    binding_revision: Revision,
    credential_revision: Revision,
) -> TrustAssessment:
    if evidence is None:
        return TrustAssessment(False, EvidenceReason.MISSING)
    if (
        type(source_account) is not PrivateAddress
        or type(message_id) is not ProviderId
        or type(now) is not Timestamp
        or type(binding_revision) is not Revision
        or type(credential_revision) is not Revision
    ):
        raise ValueError("invalid_input")
    if evidence.source_role is not Role.SOURCE:
        return TrustAssessment(False, EvidenceReason.ROLE_MISMATCH)
    if evidence.source_account != source_account:
        return TrustAssessment(False, EvidenceReason.ACCOUNT_MISMATCH)
    if evidence.source_message_id != message_id:
        return TrustAssessment(False, EvidenceReason.MESSAGE_MISMATCH)
    if (
        evidence.binding_revision != binding_revision
        or evidence.credential_revision != credential_revision
    ):
        return TrustAssessment(False, EvidenceReason.LINEAGE_MISMATCH)
    if now.value < evidence.observed_at.value:
        return TrustAssessment(False, EvidenceReason.NOT_YET_VALID)
    if now.value > evidence.expires_at.value:
        return TrustAssessment(False, EvidenceReason.EXPIRED)
    if evidence.source_path is SourcePathStatus.REJECTED:
        return TrustAssessment(False, EvidenceReason.SOURCE_PATH_REJECTED)
    if evidence.source_path is SourcePathStatus.UNKNOWN:
        return TrustAssessment(False, EvidenceReason.SOURCE_PATH_UNKNOWN)
    if evidence.from_alignment is FromAlignment.MISALIGNED:
        return TrustAssessment(False, EvidenceReason.FROM_MISALIGNED)
    if evidence.from_alignment is FromAlignment.UNKNOWN:
        return TrustAssessment(False, EvidenceReason.FROM_UNKNOWN)
    return TrustAssessment(True, EvidenceReason.TRUSTED)


__all__ = (
    "EvidenceReason",
    "FromAlignment",
    "SourcePathEvidenceIssuer",
    "SourcePathStatus",
    "TrustAssessment",
    "VerifiedSourceEvidence",
    "_issuer_for_tests",
    "assess_evidence",
)
