"""Closed action-label mapping validation and unknown-event safety."""

import os
import sqlite3
import stat
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from facet.config import dump_config, initial_template
from facet.contracts import ErrorCode, LocalId
from facet.db.action_labels import _valid_name
from facet.db.codecs import StorageFailure
from facet.runtime import state_owner as state_owner_module
from facet.runtime.state_owner import StateOwner


@pytest.mark.parametrize("name", ["", "   ", "\t", "\n", "\r\n"])
def test_action_label_name_rejects_empty_or_whitespace(name):
    with pytest.raises(StorageFailure) as caught:
        _valid_name(name)
    assert caught.value.code is ErrorCode.INVALID_INPUT


def test_action_label_name_accepts_bounded_synthetic_exact_name():
    _valid_name("Facet/AddSender")
    _valid_name("Facet/发件人")


def test_action_label_v2_upgrade_writes_private_sqlite_backup_bundle():
    anchor = Path(f"/run/user/{os.geteuid()}")
    if not anchor.is_dir() or stat.S_IMODE(anchor.stat().st_mode) & 0o77:
        pytest.skip("no_verified_trusted_test_anchor")
    with TemporaryDirectory(prefix="facet-label-", dir=anchor) as root:
        config = initial_template(
            "source@synthetic.example", "target@synthetic.example"
        )
        raw = dump_config(config)
        owner = StateOwner.create(Path(root) / "state", config, raw)
        try:
            request = LocalId("123e4567e89b42d3a456426614174001")
            owner.ensure_action_label_schema(request, raw)
            assert owner._connection.execute("PRAGMA user_version").fetchone() == (3,)
            bundle = (
                Path(owner.state_dir) / "backups" / f"action-label-v3-{request.value}"
            )
            assert (bundle / "config.yaml").read_bytes() == raw
            assert (bundle / "facet.db").is_file()
        finally:
            owner.close()
        reopened = StateOwner.open(Path(root) / "state", config)
        try:
            assert reopened._connection.execute("PRAGMA user_version").fetchone() == (
                3,
            )
        finally:
            reopened.close()


def test_action_label_upgrade_ignores_credential_atime_change(monkeypatch):
    anchor = Path(f"/run/user/{os.geteuid()}")
    if not anchor.is_dir() or stat.S_IMODE(anchor.stat().st_mode) & 0o77:
        pytest.skip("no_verified_trusted_test_anchor")
    with TemporaryDirectory(prefix="facet-label-atime-", dir=anchor) as root:
        config = initial_template(
            "source@synthetic.example", "target@synthetic.example"
        )
        raw = dump_config(config)
        state_path = Path(root) / "state"
        owner = StateOwner.create(state_path, config, raw)
        source = state_path / "credentials" / "source.json"
        source.write_bytes(b"synthetic credential envelope")
        source.chmod(0o600)
        # An old atime makes a normal read update it on relatime filesystems.
        os.utime(source, ns=(1_000_000_000, 2_000_000_000))
        real_fstat = state_owner_module.os.fstat
        observed_fd = None
        fstat_calls = 0

        class AtimeOnlyStat:
            def __init__(self, wrapped):
                self._wrapped = wrapped

            def __getattr__(self, name):
                return getattr(self._wrapped, name)

            @property
            def st_atime(self):
                return self._wrapped.st_atime + 1

            @property
            def st_atime_ns(self):
                return self._wrapped.st_atime_ns + 1

        def fstat_with_atime(fd):
            nonlocal observed_fd, fstat_calls
            value = real_fstat(fd)
            if observed_fd is None:
                observed_fd = fd
            if fd == observed_fd:
                fstat_calls += 1
                if fstat_calls == 2:
                    return AtimeOnlyStat(value)
            return value

        monkeypatch.setattr(state_owner_module.os, "fstat", fstat_with_atime)
        try:
            owner.ensure_action_label_schema(
                LocalId("523e4567e89b42d3a456426614174001"), raw
            )
            assert fstat_calls >= 2
            assert owner._connection.execute("PRAGMA user_version").fetchone() == (3,)
            bundle = (
                state_path
                / "backups"
                / "action-label-v3-523e4567e89b42d3a456426614174001"
            )
            assert (bundle / "source.json").read_bytes() == source.read_bytes()
        finally:
            owner.close()


def test_action_label_upgrade_rejects_config_digest_mismatch_without_migration():
    anchor = Path(f"/run/user/{os.geteuid()}")
    if not anchor.is_dir() or stat.S_IMODE(anchor.stat().st_mode) & 0o77:
        pytest.skip("no_verified_trusted_test_anchor")
    with TemporaryDirectory(prefix="facet-label-digest-", dir=anchor) as root:
        config = initial_template(
            "source@synthetic.example", "target@synthetic.example"
        )
        raw = dump_config(config)
        owner = StateOwner.create(Path(root) / "state", config, raw)
        try:
            request = LocalId("223e4567e89b42d3a456426614174001")
            with pytest.raises(StorageFailure) as caught:
                owner.ensure_action_label_schema(request, raw + b"\n")
            assert caught.value.code is ErrorCode.REQUEST_CONFLICT
            assert owner._connection.execute("PRAGMA user_version").fetchone() == (2,)
        finally:
            owner.close()


def test_action_label_upgrade_backup_failure_blocks_schema_mutation(monkeypatch):
    anchor = Path(f"/run/user/{os.geteuid()}")
    if not anchor.is_dir() or stat.S_IMODE(anchor.stat().st_mode) & 0o77:
        pytest.skip("no_verified_trusted_test_anchor")
    with TemporaryDirectory(prefix="facet-label-backup-", dir=anchor) as root:
        config = initial_template(
            "source@synthetic.example", "target@synthetic.example"
        )
        raw = dump_config(config)
        owner = StateOwner.create(Path(root) / "state", config, raw)
        try:
            request = LocalId("323e4567e89b42d3a456426614174001")
            original = state_owner_module._backup_write

            def fail_facet_db(path, content):
                if path.name == "facet.db":
                    raise OSError("synthetic backup failure")
                return original(path, content)

            monkeypatch.setattr(state_owner_module, "_backup_write", fail_facet_db)
            with pytest.raises(OSError, match="synthetic backup failure"):
                owner.ensure_action_label_schema(request, raw)
            assert owner._connection.execute("PRAGMA user_version").fetchone() == (2,)
            backups = Path(owner.state_dir) / "backups"
            assert not (backups / f"action-label-v3-{request.value}").exists()
        finally:
            owner.close()


def test_action_label_upgrade_ddl_failure_reopens_exact_v2(monkeypatch):
    anchor = Path(f"/run/user/{os.geteuid()}")
    if not anchor.is_dir() or stat.S_IMODE(anchor.stat().st_mode) & 0o77:
        pytest.skip("no_verified_trusted_test_anchor")
    with TemporaryDirectory(prefix="facet-label-ddl-", dir=anchor) as root:
        config = initial_template(
            "source@synthetic.example", "target@synthetic.example"
        )
        raw = dump_config(config)
        state_path = Path(root) / "state"
        owner = StateOwner.create(state_path, config, raw)
        request = LocalId("423e4567e89b42d3a456426614174001")

        def deny_create(action, *_):
            if action == sqlite3.SQLITE_CREATE_TABLE:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        owner._connection.set_authorizer(deny_create)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                owner.ensure_action_label_schema(request, raw)
            assert owner._connection.execute("PRAGMA user_version").fetchone() == (2,)
        finally:
            owner._connection.set_authorizer(None)
            owner.close()
        reopened = StateOwner.open(state_path, config)
        try:
            assert reopened._connection.execute("PRAGMA user_version").fetchone() == (
                2,
            )
        finally:
            reopened.close()
