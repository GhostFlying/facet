"""Offline consumer seam: initialized owner, profile verification and actions."""

import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from facet.config import initial_template
from facet.contracts import (
    ErrorCode,
    LabelChange,
    LocalId,
    ProjectionId,
    ProviderId,
    Revision,
    Role,
    Timestamp,
)
from facet.contracts.records import SourceEventKeyLabelChanged
from facet.db.codecs import ActionKind, PrivateAddress, StorageFailure
from facet.gmail.credential_codec import encode_envelope
from facet.gmail.credential_models import (
    AccountAddress,
    ClientIdText,
    CredentialEnvelope,
    GrantEvidence,
    GrantEvidenceKind,
    ProviderSecret,
    ScopePolicy,
    SecretText,
    policy_scopes,
)
from facet.gmail.credentials import (
    CredentialManager,
    ProfileEvidence,
)
from facet.projection.actions import (
    ActionAttention,
    ActionAttentionReason,
    ActionLabelProducer,
    ActionMessageFact,
    PrivateActionLabelMap,
)
from facet.runtime.private_root import LockFailure
from facet.runtime.state_owner import StateOwner

NOW = Timestamp(datetime(2026, 10, 3, 1, 2, 3, tzinfo=UTC))


@pytest.fixture
def trusted_state_parent():
    def trusted(path):
        for entry in (path, *path.parents):
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                return False
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in (0, os.geteuid())
                or stat.S_IMODE(info.st_mode) & 0o7022
            ):
                return False
        return True

    candidates = (Path.cwd(), Path(f"/run/user/{os.geteuid()}"))
    anchor = next(
        (candidate for candidate in candidates if trusted(candidate)),
        None,
    )
    if anchor is None:
        pytest.skip("no_verified_trusted_test_anchor")
    with TemporaryDirectory(prefix="facet-consumer-", dir=anchor) as value:
        yield Path(value)


def lid(number: int) -> LocalId:
    return LocalId(f"00000000000040008000{number:012x}")


def pid(value: str) -> ProviderId:
    return ProviderId(value)


def event(label: ProviderId, *, change=LabelChange.ADDED):
    return SourceEventKeyLabelChanged(
        "label_changed",
        ProjectionId("gmail-default"),
        pid("history-1"),
        pid("message-1"),
        label,
        change,
    )


def envelope(owner, role, account):
    policy = (
        ScopePolicy.SOURCE_READONLY
        if role is Role.SOURCE
        else ScopePolicy.TARGET_DEFAULT
    )
    scopes = policy_scopes(policy, role)
    return CredentialEnvelope(
        1,
        ProjectionId("gmail-default"),
        owner.owner_info.state_instance_id,
        role,
        Revision(1),
        Revision(1),
        lid(20 if role is Role.SOURCE else 21),
        AccountAddress(account),
        policy,
        Revision(1),
        GrantEvidence(
            GrantEvidenceKind.AUTHORIZATION_EXPLICIT,
            scopes,
            scopes,
            NOW,
            None,
        ),
        NOW,
        ProviderSecret(
            ClientIdText("synthetic-client"),
            SecretText("synthetic-client-secret"),
            SecretText("synthetic-access-token"),
            SecretText("synthetic-refresh-token"),
            NOW,
        ),
    )


class Profiles:
    def __init__(self, source_scopes, target_scopes):
        self.calls = []
        self._profiles = {
            Role.SOURCE: ProfileEvidence(
                AccountAddress("source@example.invalid"), source_scopes
            ),
            Role.TARGET: ProfileEvidence(
                AccountAddress("target@example.invalid"), target_scopes
            ),
        }

    def get_profile(self, role, secret):
        self.calls.append((role, secret))
        return self._profiles[role]


def write_credentials(owner, *, source_scopes=None, target_scopes=None):
    source = envelope(owner, Role.SOURCE, "source@example.invalid")
    target = envelope(owner, Role.TARGET, "target@example.invalid")
    root = Path(owner.state_dir) / "credentials"
    (root / "source.json").write_bytes(encode_envelope(source))
    (root / "target.json").write_bytes(encode_envelope(target))
    (root / "source.json").chmod(0o600)
    (root / "target.json").chmod(0o600)
    return source, target


def test_state_owner_initializes_and_reopens_shipping_v2(trusted_state_parent):
    config = initial_template("source@example.invalid", "target@example.invalid")
    state = StateOwner.create(
        trusted_state_parent / "state", config, b"synthetic config"
    )
    first_run = state.owner_info.owner_run_id
    assert state.database_path.exists()
    assert state.bindings()[Role.SOURCE].state.value == "verification_pending"
    with pytest.raises(LockFailure) as busy:
        StateOwner.open(trusted_state_parent / "state", config)
    assert busy.value.code is ErrorCode.OWNER_BUSY
    state.close()

    wrong_config = initial_template("other@example.invalid", "target@example.invalid")
    with pytest.raises(StorageFailure) as mismatch:
        StateOwner.open(trusted_state_parent / "state", wrong_config)
    assert mismatch.value.code is ErrorCode.BINDING_MISMATCH

    reopened = StateOwner.open(trusted_state_parent / "state", config)
    assert reopened.owner_info.owner_run_id != first_run
    assert reopened.owner_info.state_instance_id == state.owner_info.state_instance_id
    reopened.close()


def test_profile_verification_publishes_distinct_bindings(trusted_state_parent):
    config = initial_template("source@example.invalid", "target@example.invalid")
    owner = StateOwner.create(
        trusted_state_parent / "state", config, b"synthetic config"
    )
    write_credentials(owner)
    manager = CredentialManager(owner.state_dir, config, owner)
    source_scopes = policy_scopes(ScopePolicy.SOURCE_READONLY, Role.SOURCE)
    target_scopes = policy_scopes(ScopePolicy.TARGET_DEFAULT, Role.TARGET)
    reader = Profiles(source_scopes, target_scopes)
    verified = manager.verify_and_publish(reader)
    assert {profile.role for profile in verified.profiles} == {Role.SOURCE, Role.TARGET}
    assert all(
        profile.account.value.endswith("example.invalid")
        for profile in verified.profiles
    )
    bindings = owner.bindings()
    assert all(binding.state.value == "verified" for binding in bindings.values())
    assert owner.session._connection.execute(
        "SELECT binding_state FROM projections"
    ).fetchone() == ("verified",)
    assert all(type(secret).__name__ == "ProviderSecret" for _, secret in reader.calls)
    assert b"synthetic-access-token" not in owner.database_path.read_bytes()
    assert "synthetic-access-token" not in repr(verified)
    owner.close()


@pytest.mark.parametrize("failure", ["account", "scope", "role"])
def test_profile_verification_fails_closed_without_publishing(
    trusted_state_parent, failure
):
    config = initial_template("source@example.invalid", "target@example.invalid")
    owner = StateOwner.create(
        trusted_state_parent / "state", config, b"synthetic config"
    )
    write_credentials(owner)
    manager = CredentialManager(owner.state_dir, config, owner)
    source_scopes = policy_scopes(ScopePolicy.SOURCE_READONLY, Role.SOURCE)
    target_scopes = policy_scopes(ScopePolicy.TARGET_DEFAULT, Role.TARGET)
    reader = Profiles(source_scopes, target_scopes)
    if failure == "account":
        reader._profiles[Role.SOURCE] = ProfileEvidence(
            AccountAddress("other@example.invalid"), source_scopes
        )
    elif failure == "scope":
        reader._profiles[Role.TARGET] = ProfileEvidence(
            AccountAddress("target@example.invalid"), source_scopes
        )
    else:
        target = manager._path(Role.TARGET)
        target.write_bytes(
            encode_envelope(envelope(owner, Role.SOURCE, "target@example.invalid"))
        )
        target.chmod(0o600)
    with pytest.raises(StorageFailure) as caught:
        manager.verify(reader)
    assert caught.value.code in {
        ErrorCode.BINDING_MISMATCH,
        ErrorCode.SCOPE_REQUIRED,
    }
    assert owner.bindings()[Role.SOURCE].state.value == "verification_pending"
    assert owner.bindings()[Role.TARGET].state.value == "verification_pending"
    owner.close()


def test_action_producer_is_typed_readonly_and_selects_latest_external_sender():
    labels = PrivateActionLabelMap(
        pid("add-sender"), pid("add-domain"), pid("blacklist")
    )
    facts = (
        ActionMessageFact(
            pid("old"), pid("thread"), PrivateAddress("source@example.invalid"), NOW
        ),
        ActionMessageFact(
            pid("new"),
            pid("thread"),
            PrivateAddress("bank@example.invalid"),
            Timestamp(datetime(2026, 10, 3, 1, 2, 4, tzinfo=UTC)),
        ),
    )

    class Source:
        def get_thread_facts(self, source_message_id):
            assert source_message_id == pid("message-1")
            return facts

    activation = ActionLabelProducer().consume(
        event(labels.add_sender_label_id),
        labels,
        Source(),
        (AccountAddress("source@example.invalid"),),
    )
    assert activation.kind is ActionKind.ADD_SENDER
    assert activation.sender.value == "bank@example.invalid"
    removed = ActionLabelProducer().consume(
        event(labels.add_sender_label_id, change=LabelChange.REMOVED),
        labels,
        Source(),
        (AccountAddress("source@example.invalid"),),
    )
    assert isinstance(removed, ActionAttention)
    assert removed.reason is ActionAttentionReason.REMOVED_LABEL
    unknown = ActionLabelProducer().consume(
        event(pid("unconfigured")),
        labels,
        Source(),
        (AccountAddress("source@example.invalid"),),
    )
    assert unknown.reason is ActionAttentionReason.UNKNOWN_LABEL


def test_action_producer_does_not_emit_private_values_in_repr():
    labels = PrivateActionLabelMap(
        pid("add-sender"), pid("add-domain"), pid("blacklist")
    )
    value = ActionLabelProducer().consume(
        event(labels.blacklist_label_id),
        labels,
        type("Source", (), {"get_thread_facts": lambda self, _: ()})(),
        (AccountAddress("source@example.invalid"),),
    )
    assert isinstance(value, ActionAttention)
    assert "example.invalid" not in repr(value)


def test_action_producer_attention_on_duplicate_typed_fact():
    labels = PrivateActionLabelMap(
        pid("add-sender"), pid("add-domain"), pid("blacklist")
    )
    fact = ActionMessageFact(
        pid("message"),
        pid("thread"),
        PrivateAddress("bank@example.invalid"),
        NOW,
    )

    class Source:
        def get_thread_facts(self, source_message_id):
            return (fact, fact)

    attention = ActionLabelProducer().consume(
        event(labels.add_sender_label_id),
        labels,
        Source(),
        (AccountAddress("source@example.invalid"),),
    )
    assert attention.reason is ActionAttentionReason.DUPLICATE_EVENT
