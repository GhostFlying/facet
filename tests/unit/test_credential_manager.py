"""Synthetic owner-only credential refresh tests."""

import os
import stat
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from facet.config import initial_template
from facet.contracts import (
    ErrorCode,
    LocalId,
    ProjectionId,
    Revision,
    Role,
    Sha256Hex,
    Timestamp,
)
from facet.db.codecs import StorageFailure
from facet.db.models import CredentialChangeRow
from facet.db.repositories import credentials as credential_repository
from facet.gmail import credentials as credentials_module
from facet.gmail.credential_codec import encode_envelope
from facet.gmail.credential_models import (
    AccountAddress,
    ClientIdText,
    CredentialEnvelope,
    GrantEvidence,
    GrantEvidenceKind,
    ProviderSecret,
    RefreshResult,
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
        assert manager.load(Role.SOURCE).change_id != source.change_id
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


def test_refresh_uses_only_the_owner_clock(trusted_state_parent, monkeypatch):
    owner, _, manager, _, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        manager.verify_and_publish(Profiles())
        monkeypatch.setattr(
            credentials_module,
            "_owner_now",
            lambda: Timestamp(FUTURE.value + timedelta(days=1)),
        )
        with pytest.raises(StorageFailure) as caught:
            manager.refresh(Role.SOURCE, lambda role, old: _future_secret("new"))
        assert caught.value.code is ErrorCode.SOURCE_AUTH_REQUIRED
        assert "now" not in str(__import__("inspect").signature(manager.refresh))
    finally:
        owner.close()


def test_refresh_preserves_typed_exchange_failure(trusted_state_parent, monkeypatch):
    owner, _, manager, _, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        manager.verify_and_publish(Profiles())

        def exchange(role, old):
            raise StorageFailure(ErrorCode.NETWORK_UNAVAILABLE)

        with pytest.raises(StorageFailure) as caught:
            manager.refresh(Role.SOURCE, exchange)
        assert caught.value.code is ErrorCode.NETWORK_UNAVAILABLE
        assert owner.session._connection.execute(
            "SELECT phase,error FROM credential_changes"
        ).fetchone() == ("abandoned", "network_unavailable")
    finally:
        owner.close()


def test_refresh_records_explicit_scope_evidence(trusted_state_parent, monkeypatch):
    owner, _, manager, _, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        manager.verify_and_publish(Profiles())
        result = manager.refresh(
            Role.SOURCE,
            lambda role, old: RefreshResult(
                _future_secret("explicit-scope"),
                policy_scopes(ScopePolicy.SOURCE_READONLY, Role.SOURCE),
            ),
        )
        assert result.credential_revision == Revision(2)
        assert owner.session._connection.execute(
            "SELECT phase,grant_kind,granted_scopes FROM credential_changes"
        ).fetchone() == ("committed", "refresh_explicit", "gmail_readonly")
    finally:
        owner.close()


def test_refresh_rejects_reduced_explicit_scope_evidence(
    trusted_state_parent, monkeypatch
):
    owner, _, manager, _, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        manager.verify_and_publish(Profiles())
        with pytest.raises(StorageFailure) as caught:
            manager.refresh(
                Role.SOURCE,
                lambda role, old: RefreshResult(
                    _future_secret("reduced-scope"),
                    policy_scopes(ScopePolicy.TARGET_DEFAULT, Role.TARGET),
                ),
            )
        assert caught.value.code is ErrorCode.SCOPE_REQUIRED
        assert owner.session._connection.execute(
            "SELECT phase,error FROM credential_changes"
        ).fetchone() == ("abandoned", "scope_required")
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
        change_id = owner.session._connection.execute(
            "SELECT change_id FROM credential_changes"
        ).fetchone()[0]
        with (
            pytest.raises(StorageFailure) as abandon,
            owner.session.transaction() as uow,
        ):
            credential_repository.abandon_change(
                uow,
                owner.projection_id,
                Role.SOURCE,
                LocalId(change_id),
                ErrorCode.PERSISTENCE_FAILURE,
            )
        assert abandon.value.code is ErrorCode.REQUEST_CONFLICT
        assert "published-token" not in owner.database_path.read_bytes().decode(
            "utf-8", "ignore"
        )
    finally:
        owner.close()


@pytest.mark.parametrize("boundary", ["fsync", "replace"])
def test_refresh_replace_boundary_failure_retains_attention(
    trusted_state_parent, monkeypatch, boundary
):
    owner, _, manager, source, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        manager.verify_and_publish(Profiles())
        original_fsync = credentials_module.os.fsync
        original_replace = credentials_module.os.replace
        calls = 0

        def fail_directory_fsync(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic directory fsync failure")
            return original_fsync(descriptor)

        def replace_then_fail(source_path, target_path):
            original_replace(source_path, target_path)
            raise OSError("synthetic replace acknowledgement failure")

        if boundary == "fsync":
            monkeypatch.setattr(credentials_module.os, "fsync", fail_directory_fsync)
        else:
            monkeypatch.setattr(credentials_module.os, "replace", replace_then_fail)
        with pytest.raises(StorageFailure) as caught:
            manager.refresh(Role.SOURCE, lambda role, old: _future_secret("boundary"))
        assert caught.value.code is ErrorCode.PERSISTENCE_FAILURE
        assert owner.bindings()[Role.SOURCE].credential_revision == Revision(1)
        assert owner.session._connection.execute(
            "SELECT phase,error FROM credential_changes"
        ).fetchone() == ("attention", "persistence_failure")
        assert (Path(owner.state_dir) / "credentials" / "source.json").read_bytes() != (
            encode_envelope(source)
        )
    finally:
        owner.close()


def test_same_role_refresh_is_single_flight(trusted_state_parent, monkeypatch):
    owner, _, manager, _, _ = _manager(trusted_state_parent, monkeypatch)
    release = threading.Event()
    calls = []
    try:
        manager.verify_and_publish(Profiles())

        def exchange(role, old):
            calls.append(old.access_token.value)
            assert release.wait(5)
            return _future_secret("single-flight")

        def duplicate_exchange(role, old):
            raise AssertionError("duplicate exchange")

        with ThreadPoolExecutor(max_workers=1) as pool:
            holder = {}

            def submit_duplicate(role, old):
                holder["future"] = pool.submit(
                    manager.refresh, Role.SOURCE, duplicate_exchange
                )

            def first_exchange(role, old):
                submit_duplicate(role, old)
                calls.append(old.access_token.value)
                for _ in range(100):
                    with manager._flight_condition:
                        if manager._flights[Role.SOURCE].waiters == 1:
                            break
                        manager._flight_condition.wait(0.01)
                else:
                    raise AssertionError("duplicate_refresh_did_not_join")
                release.set()
                assert release.wait(5)
                return _future_secret("single-flight")

            result = manager.refresh(Role.SOURCE, first_exchange)
            release.set()
            duplicate = holder["future"].result(timeout=5)
        assert result == duplicate
        assert calls == ["synthetic-access-token"]
    finally:
        owner.close()


@pytest.mark.parametrize("stage", ["requesting", "published"])
def test_subprocess_termination_leaves_restart_attention_boundary(
    trusted_state_parent, monkeypatch, stage
):
    owner, config, manager, _, _ = _manager(trusted_state_parent, monkeypatch)
    state = str(owner.state_dir)
    try:
        manager.verify_and_publish(Profiles())
    finally:
        owner.close()
    script = """
import os
import sys
from facet.config import initial_template
from facet.contracts import Role
from facet.gmail import credentials as credentials_module
from facet.gmail.credential_models import SecretText
from facet.gmail.credentials import CredentialManager
from facet.runtime.state_owner import StateOwner

config = initial_template('source@example.invalid', 'target@example.invalid')
owner = StateOwner.open(sys.argv[1], config)
manager = CredentialManager(owner.state_dir, config, owner)
if sys.argv[2] == 'requesting':
    manager.refresh(Role.SOURCE, lambda role, old: os._exit(17))
else:
    original_write = credentials_module._atomic_write
    def exchange(role, old):
        return type(
            old
        )(old.client_id, old.client_secret, SecretText('child-token'),
           old.refresh_token, old.expires_at)
    def replace_then_exit(path, raw):
        original_write(path, raw)
        os._exit(17)
    credentials_module._atomic_write = replace_then_exit
    manager.refresh(Role.SOURCE, exchange)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, state, stage],
        check=False,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 17
    reopened = StateOwner.open(state, config)
    try:
        reopened_manager = CredentialManager(reopened.state_dir, config, reopened)
        with pytest.raises(StorageFailure) as caught:
            reopened_manager.snapshot(Role.SOURCE)
        assert caught.value.code is ErrorCode.MAINTENANCE_REQUIRED
    finally:
        reopened.close()


def test_repository_rejects_noncanonical_granted_scope_text(
    trusted_state_parent, monkeypatch
):
    owner, config, manager, source, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        manager.verify_and_publish(Profiles())
        row = CredentialChangeRow(
            config.projection.id,
            source.state_instance_id,
            LocalId("000000000000400080000000000000aa"),
            Role.SOURCE,
            "refresh",
            "validated",
            Revision(1),
            Revision(2),
            source.binding_revision,
            source.scope_policy_revision,
            None,
            None,
            Sha256Hex("a" * 64),
            source.scope_policy.value,
            "refresh_omitted_inherited",
            "gmail_readonly,provider-secret",
            source.credential_revision,
            FUTURE,
            source.profile_verified_at,
            source.secret.expires_at,
            FUTURE,
            FUTURE,
            None,
        )
        with (
            pytest.raises(StorageFailure) as caught,
            owner.session.transaction() as uow,
        ):
            credential_repository.mark_validated(uow, config.projection.id, row)
        assert caught.value.code is ErrorCode.INVALID_INPUT
    finally:
        owner.close()
