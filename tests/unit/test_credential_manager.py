"""Synthetic owner-only credential refresh tests."""

import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from facet.config import initial_template
from facet.contracts import ErrorCode, LocalId, ProjectionId, Revision, Role, Timestamp
from facet.db.codecs import StorageFailure
from facet.gmail import credentials as credentials_module
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
from facet.gmail.credentials import CredentialManager, ProfileEvidence
from facet.runtime.state_owner import StateOwner

FUTURE = Timestamp(datetime(2040, 1, 1, tzinfo=UTC))


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

    anchor = next(
        (
            candidate
            for candidate in (Path.cwd(), Path(f"/run/user/{os.geteuid()}"))
            if trusted(candidate)
        ),
        None,
    )
    if anchor is None:
        pytest.skip("no_verified_trusted_test_anchor")
    with TemporaryDirectory(prefix="facet-credential-", dir=anchor) as value:
        yield Path(value)


def _future_secret(token: str) -> ProviderSecret:
    return ProviderSecret(
        ClientIdText("synthetic-client"),
        SecretText("synthetic-client-secret"),
        SecretText(token),
        SecretText("synthetic-refresh-token"),
        Timestamp(FUTURE.value + timedelta(hours=1)),
    )


def _envelope(owner, role, account):
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
        LocalId(
            "00000000000040008000000000000014"
            if role is Role.SOURCE
            else "00000000000040008000000000000015"
        ),
        AccountAddress(account),
        policy,
        Revision(1),
        GrantEvidence(
            GrantEvidenceKind.AUTHORIZATION_EXPLICIT,
            scopes,
            scopes,
            FUTURE,
            None,
        ),
        FUTURE,
        ProviderSecret(
            ClientIdText("synthetic-client"),
            SecretText("synthetic-client-secret"),
            SecretText("synthetic-access-token"),
            SecretText("synthetic-refresh-token"),
            FUTURE,
        ),
    )


def _write_credentials(owner):
    source = _envelope(owner, Role.SOURCE, "source@example.invalid")
    target = _envelope(owner, Role.TARGET, "target@example.invalid")
    root = Path(owner.state_dir) / "credentials"
    (root / "source.json").write_bytes(encode_envelope(source))
    (root / "target.json").write_bytes(encode_envelope(target))
    (root / "source.json").chmod(0o600)
    (root / "target.json").chmod(0o600)
    return source, target


def _manager(trusted_state_parent, monkeypatch):
    monkeypatch.setattr(credentials_module, "_owner_now", lambda: FUTURE)
    config = initial_template("source@example.invalid", "target@example.invalid")
    owner = StateOwner.create(
        trusted_state_parent / "state", config, b"synthetic config"
    )
    source, target = _write_credentials(owner)
    manager = CredentialManager(owner.state_dir, config, owner)
    return owner, config, manager, source, target


class Profiles:
    def get_profile(self, role, secret):
        return ProfileEvidence(
            AccountAddress(
                "source@example.invalid"
                if role is Role.SOURCE
                else "target@example.invalid"
            ),
            policy_scopes(
                ScopePolicy.SOURCE_READONLY
                if role is Role.SOURCE
                else ScopePolicy.TARGET_DEFAULT,
                role,
            ),
        )


def test_refresh_serializes_and_commits_metadata_only(
    trusted_state_parent, monkeypatch
):
    owner, config, manager, source, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        manager.verify_and_publish(Profiles())
        calls = []

        def exchange(role, old):
            calls.append((role, old.access_token.value))
            return _future_secret("synthetic-refreshed-token")

        snapshot = manager.refresh(Role.SOURCE, exchange)
        assert snapshot.credential_revision == Revision(2)
        assert snapshot.access_token.value == "synthetic-refreshed-token"
        assert calls == [(Role.SOURCE, "synthetic-access-token")]
        assert owner.bindings()[Role.SOURCE].credential_revision == Revision(2)
        row = owner.session._connection.execute(
            "SELECT phase,grant_kind,envelope_digest,error FROM credential_changes"
        ).fetchone()
        assert row[0:2] == ("committed", "refresh_omitted_inherited")
        assert row[2] is not None and len(row[2]) == 64
        assert row[3] is None
        database_bytes = owner.database_path.read_bytes().decode("utf-8", "ignore")
        assert "synthetic-refreshed-token" not in database_bytes
        assert "synthetic-refreshed-token" not in repr(snapshot)
        owner.close()
        reopened = StateOwner.open(trusted_state_parent / "state", config)
        try:
            reopened_manager = CredentialManager(reopened.state_dir, config, reopened)
            assert reopened_manager.load(Role.SOURCE).credential_revision == Revision(2)
        finally:
            reopened.close()
    finally:
        owner.close()


def test_refresh_file_failure_abandons_without_binding_advance(
    trusted_state_parent, monkeypatch
):
    owner, _, manager, source, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        # Initial verification is deliberately synthetic and local.
        manager.verify_and_publish(Profiles())

        def fail_write(path, raw):
            raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)

        monkeypatch.setattr(credentials_module, "_atomic_write", fail_write)
        with pytest.raises(StorageFailure) as caught:
            manager.refresh(Role.SOURCE, lambda role, old: _future_secret("new"))
        assert caught.value.code is ErrorCode.PERSISTENCE_FAILURE
        assert owner.bindings()[Role.SOURCE].credential_revision == Revision(1)
        assert owner.session._connection.execute(
            "SELECT phase,error FROM credential_changes"
        ).fetchone() == ("abandoned", "persistence_failure")
        assert (
            encode_envelope(source)
            == (Path(owner.state_dir) / "credentials" / "source.json").read_bytes()
        )
    finally:
        owner.close()


def test_refresh_rejects_backdated_caller_clock(trusted_state_parent, monkeypatch):
    owner, _, manager, _, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        manager.verify_and_publish(Profiles())
        with pytest.raises(StorageFailure) as caught:
            manager.refresh(
                Role.SOURCE,
                lambda role, old: _future_secret("new"),
                now=Timestamp(datetime(2039, 12, 31, tzinfo=UTC)),
            )
        assert caught.value.code is ErrorCode.INVALID_INPUT
        assert owner.session._connection.execute(
            "SELECT COUNT(*) FROM credential_changes"
        ).fetchone() == (0,)
    finally:
        owner.close()


def test_refresh_commit_failure_retains_attention_state(
    trusted_state_parent, monkeypatch
):
    owner, _, manager, _, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        manager.verify_and_publish(Profiles())

        def fail_commit(*args, **kwargs):
            raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)

        monkeypatch.setattr(
            "facet.db.repositories.credentials.commit_change", fail_commit
        )
        with pytest.raises(StorageFailure) as caught:
            manager.refresh(
                Role.SOURCE, lambda role, old: _future_secret("published-token")
            )
        assert caught.value.code is ErrorCode.PERSISTENCE_FAILURE
        assert owner.bindings()[Role.SOURCE].credential_revision == Revision(1)
        row = owner.session._connection.execute(
            "SELECT phase,error FROM credential_changes"
        ).fetchone()
        assert row == ("attention", "persistence_failure")
        assert "published-token" not in owner.database_path.read_bytes().decode(
            "utf-8", "ignore"
        )
    finally:
        owner.close()
