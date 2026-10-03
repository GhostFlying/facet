"""OP01/02/06: structural values cannot attest grants or create capabilities."""

from dataclasses import fields, replace
from datetime import UTC, datetime, tzinfo

import pytest

from facet.contracts import ErrorCode, LocalId, ProjectionId, Revision, Role, Timestamp
from facet.gmail import credential_models as models
from facet.gmail.credential_models import (
    AccountAddress,
    ClientIdText,
    CredentialCodecError,
    CredentialEnvelope,
    GrantEvidence,
    GrantEvidenceKind,
    ProviderSecret,
    ScopeName,
    ScopePolicy,
    ScopeSet,
    SecretText,
    policy_scopes,
)

NOW = Timestamp(datetime(2026, 10, 2, 1, 2, 3, 123456, tzinfo=UTC))
SENTINEL = "SYNTHETIC_PRIVATE_CREDENTIAL"


def envelope():
    scopes = policy_scopes(ScopePolicy.TARGET_DEFAULT, Role.TARGET)
    return CredentialEnvelope(
        1,
        ProjectionId("synthetic"),
        LocalId("00000000000040008000000000000001"),
        Role.TARGET,
        Revision(1),
        Revision(1),
        LocalId("00000000000040008000000000000002"),
        AccountAddress("target@example.invalid"),
        ScopePolicy.TARGET_DEFAULT,
        Revision(1),
        GrantEvidence(
            GrantEvidenceKind.AUTHORIZATION_EXPLICIT, scopes, scopes, NOW, None
        ),
        NOW,
        ProviderSecret(
            ClientIdText("synthetic-client"),
            SecretText(SENTINEL),
            SecretText(SENTINEL + "_access"),
            SecretText(SENTINEL + "_refresh"),
            NOW,
        ),
    )


class Trap:
    def _called(self, *args, **kwargs):
        raise AssertionError("unsupported hook called")

    __str__ = __repr__ = __eq__ = __iter__ = __getattribute__ = _called


def assert_controlled(call):
    with pytest.raises(CredentialCodecError) as caught:
        call()
    error = caught.value
    assert error.args == (error.code.value,)
    assert error.__context__ is None and error.__cause__ is None
    assert SENTINEL not in str(error) + repr(error)
    return error


def test_exact_inventory_and_required_fields():
    assert set(models.__all__) == {
        "SecretText",
        "ClientIdText",
        "AccountAddress",
        "ScopeName",
        "ScopeSet",
        "ScopePolicy",
        "GrantEvidenceKind",
        "GrantEvidence",
        "ProviderSecret",
        "CredentialEnvelope",
        "AccessSnapshot",
        "CredentialCodecError",
        "policy_scopes",
    }
    assert tuple(f.name for f in fields(CredentialEnvelope)) == (
        "version",
        "projection_id",
        "state_instance_id",
        "role",
        "binding_revision",
        "credential_revision",
        "change_id",
        "account",
        "scope_policy",
        "scope_policy_revision",
        "grant",
        "profile_verified_at",
        "secret",
    )
    assert tuple(f.name for f in fields(GrantEvidence)) == (
        "kind",
        "granted",
        "requested",
        "observed_at",
        "parent_credential_revision",
    )
    assert tuple(f.name for f in fields(ProviderSecret)) == (
        "client_id",
        "client_secret",
        "access_token",
        "refresh_token",
        "expires_at",
    )
    for deferred in ("VerifiedProfile", "CredentialChange"):
        assert not hasattr(models, deferred)
    value = envelope()
    assert SENTINEL not in str(value) + repr(value) + repr(value.secret)
    with pytest.raises(AttributeError):
        value.version = 2


@pytest.mark.parametrize(
    "policy,role,expected",
    [
        (ScopePolicy.SOURCE_READONLY, Role.SOURCE, {"gmail_readonly"}),
        (ScopePolicy.SOURCE_CONVENIENCE, Role.SOURCE, {"gmail_modify"}),
        (ScopePolicy.TARGET_DEFAULT, Role.TARGET, {"gmail_insert", "gmail_readonly"}),
        (
            ScopePolicy.TARGET_LABELS,
            Role.TARGET,
            {"gmail_insert", "gmail_readonly", "gmail_labels"},
        ),
    ],
)
def test_exact_policies_do_not_authorize_modes(policy, role, expected):
    assert {v.value for v in policy_scopes(policy, role).value} == expected
    other = Role.TARGET if role is Role.SOURCE else Role.SOURCE
    assert_controlled(lambda: policy_scopes(policy, other))


@pytest.mark.parametrize(
    "cls,bad",
    [
        (SecretText, ""),
        (SecretText, "x\x00"),
        (SecretText, "x\x7f"),
        (SecretText, "x" * 16385),
        (SecretText, "\ud800"),
        (ClientIdText, "x y"),
        (ClientIdText, "é"),
        (ClientIdText, "x" * 1025),
        (AccountAddress, "not-an-address"),
        (AccountAddress, "a@b\n"),
        (AccountAddress, "a" * 1024 + "@b"),
        (ScopeSet, frozenset()),
        (ScopeSet, {ScopeName.GMAIL_READONLY}),
        (ScopeSet, frozenset({"gmail_readonly"})),
    ],
)
def test_invalid_scalars_are_fixed_errors(cls, bad):
    assert_controlled(lambda: cls(bad))


@pytest.mark.parametrize("cls", [SecretText, ClientIdText, AccountAddress, ScopeSet])
def test_scalar_hostile_objects_never_run_hooks(cls):
    assert_controlled(lambda: cls(Trap()))


def test_resource_boundary_and_account_spelling():
    assert len(SecretText("é" * 8192).value.encode()) == 16384
    assert ClientIdText("x" * 1024).value == "x" * 1024
    assert (
        AccountAddress("User+tag@Example.invalid").value == "User+tag@Example.invalid"
    )
    assert_controlled(lambda: SecretText("é" * 8193))


def test_refresh_lineage_and_expired_value_remain_only_structural():
    value = envelope()
    grant = replace(
        value.grant,
        kind=GrantEvidenceKind.REFRESH_OMITTED_INHERITED,
        parent_credential_revision=Revision(1),
    )
    refreshed = replace(value, credential_revision=Revision(2), grant=grant)
    assert refreshed.secret.expires_at == NOW
    assert_controlled(lambda: replace(value, grant=grant))
    assert_controlled(lambda: replace(grant, parent_credential_revision=None))
    assert_controlled(
        lambda: replace(value.grant, parent_credential_revision=Revision(1))
    )
    assert_controlled(lambda: replace(value, role=Role.SOURCE))
    assert_controlled(lambda: replace(value, binding_revision=Revision(0)))
    assert_controlled(lambda: replace(value, version=True))
    assert (
        assert_controlled(lambda: replace(value, version=2)).code
        is ErrorCode.UNSUPPORTED_VERSION
    )


def test_uninitialized_and_corrupted_exact_payloads_are_revalidated():
    from facet.gmail.credential_codec import encode_envelope

    assert_controlled(lambda: encode_envelope(object.__new__(CredentialEnvelope)))
    value = envelope()
    object.__setattr__(value.secret.access_token, "value", Trap())
    assert_controlled(lambda: encode_envelope(value))
    value = envelope()
    object.__setattr__(value.credential_revision, "value", True)
    assert_controlled(lambda: encode_envelope(value))


def test_custom_timezone_is_rejected_before_its_callback():
    class TimeTrap(tzinfo):
        def utcoffset(self, dt):
            raise AssertionError("timezone hook called")

    timestamp = object.__new__(Timestamp)
    object.__setattr__(timestamp, "value", datetime(2026, 1, 1, tzinfo=TimeTrap()))
    assert_controlled(lambda: replace(envelope(), profile_verified_at=timestamp))


def test_error_constructor_never_uses_unknown_hook():
    error = CredentialCodecError(Trap())
    assert error.args == ("invalid_input",)
