"""Real owner v3-to-v4 backup, rollback and reopen; no external credentials."""

import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest

from facet.config import dump_config, initial_template
from facet.contracts import ErrorCode, LocalId
from facet.db import schema
from facet.db.codecs import StorageFailure
from facet.runtime.state_owner import StateOwner


@pytest.mark.parametrize("fail_ddl", [False, True])
def test_current_action_upgrade_preserves_state_and_backs_up_before_ddl(
    monkeypatch, fail_ddl
):
    with TemporaryDirectory(
        prefix="facet-current-upgrade-", dir=f"/run/user/{os.geteuid()}"
    ) as root:
        config = initial_template("source@example.com", "target@example.com")
        raw = dump_config(config)
        state = Path(root) / "state"
        with StateOwner.create(state, config, raw) as owner:
            owner.ensure_action_label_schema(LocalId(uuid4().hex), raw)
            with owner.session.transaction() as uow:
                uow._execute(
                    "INSERT INTO action_label_mappings VALUES(?,?,?,?,?)",
                    (owner.projection_id.value, "add_sender", "Facet/AddSender", 1, 1),
                )
            before = {
                table: owner._connection.execute(f"SELECT * FROM {table}").fetchall()
                for table in ("projections", "bindings", "action_label_mappings")
            }
            request = LocalId(uuid4().hex)
            real_inspect = schema._inspect_manifest

            def inspect(connection, manifest):
                if fail_ddl and manifest.version.value == 4:
                    raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)
                return real_inspect(connection, manifest)

            monkeypatch.setattr(schema, "_inspect_manifest", inspect)
            if fail_ddl:
                with pytest.raises(StorageFailure):
                    owner.ensure_current_action_schema(request, raw)
                assert owner._connection.execute("PRAGMA user_version").fetchone() == (
                    3,
                )
                assert not owner._connection.execute(
                    "SELECT 1 FROM sqlite_schema "
                    "WHERE name='current_action_observations'"
                ).fetchone()
            else:
                owner.ensure_current_action_schema(request, raw)
                assert owner._connection.execute("PRAGMA user_version").fetchone() == (
                    4,
                )
            for table, rows in before.items():
                assert (
                    owner._connection.execute(f"SELECT * FROM {table}").fetchall()
                    == rows
                )
            bundle = state / "backups" / f"action-label-v4-{request.value}"
            assert (bundle / "config.yaml").read_bytes() == raw
            with sqlite3.connect(
                f"file:{bundle / 'facet.db'}?mode=ro", uri=True
            ) as backup:
                assert backup.execute("PRAGMA user_version").fetchone() == (3,)
                assert backup.execute(
                    "SELECT label_name FROM action_label_mappings"
                ).fetchone() == ("Facet/AddSender",)
            assert bundle.stat().st_mode & 0o077 == 0
            assert (bundle / "facet.db").stat().st_mode & 0o077 == 0
        monkeypatch.setattr(schema, "_inspect_manifest", real_inspect)
        with StateOwner.open(state, config) as reopened:
            assert reopened._connection.execute("PRAGMA user_version").fetchone() == (
                3 if fail_ddl else 4,
            )
