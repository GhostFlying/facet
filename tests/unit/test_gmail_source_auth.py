import base64
from datetime import UTC, datetime, timedelta

import pytest

from facet.contracts import PolicyVersion, ProviderId, Revision, Role, Timestamp
from facet.db.codecs import PrivateAddress
from facet.gmail.source_auth import (
    DkimSourceAuthProvider,
    SyntheticSourceAuthProvider,
    UnknownSourceAuthProvider,
)
from facet.projection.authenticity import (
    FromAlignment,
    SourcePathStatus,
    _issuer_for_tests,
)
from facet.projection.rules import normalize_sender

NOW = datetime(2026, 10, 4, 1, 2, 3, tzinfo=UTC)
ACCOUNT = PrivateAddress("source@example.invalid")
MESSAGE = ProviderId("m-1")
EXPECTED_SENDER = normalize_sender("sender@example.com")
_SIGNED_RAW = base64.b64decode(
    "REtJTS1TaWduYXR1cmU6IHY9MTsgYT1yc2Etc2hhMjU2OyBjPXJlbGF4ZWQvc2ltcGxlOyBkPWV4YW1wbGUuY29tOw0KIGk9QGV4YW1wbGUuY29tOyBxPWRucy90eHQ7IHM9c2VsOyB0PTE3OTExNTAwNDA7IGg9ZnJvbSA6IHRvIDogc3ViamVjdDsNCiBiaD14L044L2l2UmZHTXhGNTZwOC92a3JUYUhsUGFkR2lqSFJXejBNQjg3OFdrPTsNCiBiPVBGS01ZdEsxaUU0TXhJRWJrMlFwNzkxcDlmdUVTUEd2bmZJeGlzWmg0K1dKWmNaNDdPZmprcy93QkdkT2crcEdIdE5YSQ0KIDVoa2cwdnRkc3h4akh2QVhKVi85c1hzbjgySENYcXN1WTR5b1ozV0ZwZVhKNmpEaTYxeFUrRGphMDgzeXNYY01lTmNIZVkvDQogd2xZOGFQTk5MUitTalpaZCtOUFF4R2xBVmpwVUU1ND0NCkZyb206IHNlbmRlckBleGFtcGxlLmNvbQ0KVG86IHRhcmdldEBleGFtcGxlLmludmFsaWQNClN1YmplY3Q6IFN5bnRoZXRpYw0KDQpCb2R5DQo="
)
_PUBLIC_KEY = base64.b64decode(
    "MIGJAoGBALX2wl5pVUuagVvXrWCnjlANv8ngaInMYNn9gbsEsQmUdxea4W7MkPUi9C3baE9w1mRnisoW2f96LnqHrahD2OcJ41DAhttJlmV4wfWzPK24c330Is2EbDNcScuAEAR3xHhsw0LplEFTNpjX8XRtsN4YSYVzjBw392kFGzISxTbXAgMBAAE="
)


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


def _signed_raw(*, sender="sender@example.com", dkim_domain=b"example.com", extra=b""):
    assert dkim_domain == b"example.com"
    raw = _SIGNED_RAW.replace(b"sender@example.com", sender.encode(), 1)
    if extra:
        raw = raw.replace(b"\r\n\r\nBody\r\n", b"\r\n" + extra + b"\r\nBody\r\n")
    return raw


def _dns(name, timeout=5):
    assert timeout == 5
    assert name == b"sel._domainkey.example.com."
    return b"v=DKIM1; k=rsa; p=" + base64.b64encode(_PUBLIC_KEY)


def _dkim_provider():
    return DkimSourceAuthProvider(dnsfunc=_dns)


def test_dkim_provider_issues_bound_evidence_for_aligned_signature():
    evidence = _dkim_provider().attest(
        source_account=ACCOUNT,
        message_id=MESSAGE,
        observed_at=Timestamp(NOW),
        binding_revision=Revision(1),
        credential_revision=Revision(1),
        expected_sender=EXPECTED_SENDER,
        raw=_signed_raw(),
    )
    assert evidence is not None
    assert evidence.source_message_id == MESSAGE
    assert evidence.from_alignment is FromAlignment.ALIGNED


@pytest.mark.parametrize(
    "raw",
    [
        _signed_raw(sender="sender@other.example.net"),
        b"From: sender@example.com\r\n"
        b"Authentication-Results: dkim=pass\r\n\r\nunsigned\r\n",
        _signed_raw(extra=b"ARC-Authentication-Results: dkim=pass\r\n"),
        _signed_raw(extra=b"Resent-From: forwarder@example.invalid\r\n"),
        b"From: sender@example.com\r\n\r\nunsigned\r\n",
    ],
)
def test_dkim_provider_fails_closed_for_untrusted_delivery(raw):
    assert (
        _dkim_provider().attest(
            source_account=ACCOUNT,
            message_id=MESSAGE,
            observed_at=Timestamp(NOW),
            binding_revision=Revision(1),
            credential_revision=Revision(1),
            expected_sender=EXPECTED_SENDER,
            raw=raw,
        )
        is None
    )


def test_dkim_provider_does_not_use_bounded_or_missing_raw():
    provider = DkimSourceAuthProvider(dnsfunc=_dns, max_raw_bytes=32)
    assert (
        provider.attest(
            source_account=ACCOUNT,
            message_id=MESSAGE,
            observed_at=Timestamp(NOW),
            binding_revision=Revision(1),
            credential_revision=Revision(1),
            expected_sender=EXPECTED_SENDER,
        )
        is None
    )
    assert (
        provider.attest(
            source_account=ACCOUNT,
            message_id=MESSAGE,
            observed_at=Timestamp(NOW),
            binding_revision=Revision(1),
            credential_revision=Revision(1),
            expected_sender=EXPECTED_SENDER,
            raw=_signed_raw(),
        )
        is None
    )


def test_dkim_provider_rejects_metadata_raw_sender_mismatch():
    assert (
        _dkim_provider().attest(
            source_account=ACCOUNT,
            message_id=MESSAGE,
            observed_at=Timestamp(NOW),
            binding_revision=Revision(1),
            credential_revision=Revision(1),
            expected_sender=normalize_sender("other@example.com"),
            raw=_signed_raw(),
        )
        is None
    )
