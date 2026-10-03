from datetime import UTC, datetime, timedelta

from facet.contracts import PolicyVersion, ProviderId, Revision, Role, Timestamp
from facet.db.codecs import PrivateAddress
from facet.gmail.source_auth import (
    SyntheticSourceAuthProvider,
    UnknownSourceAuthProvider,
)
from facet.projection.authenticity import (
    FromAlignment,
    SourcePathStatus,
    _issuer_for_tests,
)

NOW = datetime(2026, 10, 4, 1, 2, 3, tzinfo=UTC)
ACCOUNT = PrivateAddress("source@example.invalid")
MESSAGE = ProviderId("m-1")


def _evidence(*, account=ACCOUNT, message=MESSAGE, observed=NOW):
    return _issuer_for_tests().issue(
        source_role=Role.SOURCE,
        source_account=account,
        source_message_id=message,
        source_path=SourcePathStatus.TRUSTED,
        from_alignment=FromAlignment.ALIGNED,
        binding_revision=Revision(1),
        credential_revision=Revision(1),
        observed_at=Timestamp(observed - timedelta(minutes=1)),
        expires_at=Timestamp(observed + timedelta(hours=1)),
        policy_version=PolicyVersion("auth-v1"),
    )


def test_unknown_provider_never_attests():
    result = UnknownSourceAuthProvider().attest(
        source_account=ACCOUNT,
        message_id=MESSAGE,
        observed_at=Timestamp(NOW),
        binding_revision=Revision(1),
        credential_revision=Revision(1),
    )
    assert result is None


def test_synthetic_provider_requires_exact_binding_and_freshness():
    provider = SyntheticSourceAuthProvider(_evidence())
    assert (
        provider.attest(
            source_account=ACCOUNT,
            message_id=MESSAGE,
            observed_at=Timestamp(NOW),
            binding_revision=Revision(1),
            credential_revision=Revision(1),
        )
        is not None
    )
    assert (
        provider.attest(
            source_account=ACCOUNT,
            message_id=ProviderId("other"),
            observed_at=Timestamp(NOW),
            binding_revision=Revision(1),
            credential_revision=Revision(1),
        )
        is None
    )
    assert (
        provider.attest(
            source_account=ACCOUNT,
            message_id=MESSAGE,
            observed_at=Timestamp(NOW),
            binding_revision=Revision(2),
            credential_revision=Revision(1),
        )
        is None
    )


def test_provider_repr_does_not_expose_evidence():
    provider = SyntheticSourceAuthProvider(_evidence())
    assert "source@example.invalid" not in repr(provider)
    assert "m-1" not in repr(provider)
