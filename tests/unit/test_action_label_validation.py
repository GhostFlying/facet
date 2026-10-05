"""Closed action-label mapping validation and unknown-event safety."""

import os
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
