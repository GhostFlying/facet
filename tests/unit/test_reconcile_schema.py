"""Source reconcile schema upgrade keeps the owner backup contract."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from facet.config import dump_config, initial_template
from facet.contracts import LocalId
from facet.runtime.state_owner import StateOwner


def test_reconcile_schema_upgrade_creates_private_run_tables_and_backup():
    with TemporaryDirectory(
        prefix="facet-reconcile-schema-", dir=f"/run/user/{os.geteuid()}"
    ) as root:
        config = initial_template("source@example.com", "target@example.com")
        raw = dump_config(config)
        state = Path(root) / "state"
        with StateOwner.create(state, config, raw) as owner:
            request = LocalId(uuid4().hex)
            owner.ensure_reconcile_schema(request, raw)
            assert owner._connection.execute("PRAGMA user_version").fetchone() == (7,)
            for table in ("reconcile_runs", "reconcile_candidates"):
                assert owner._connection.execute(
                    "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",
                    (table,),
                ).fetchone() == (1,)
        backup = state / "backups" / f"reconcile-v6-{request.value}" / "facet.db"
        assert backup.exists()
