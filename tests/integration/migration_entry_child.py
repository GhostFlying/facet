"""Fixed synthetic MG07 death boundaries; no installed/product path runner."""

import os
import select
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parents[1] / "unit"))

from fakes.network import deny_network  # noqa: E402
from test_db_migration_entry import SOURCE, STEP, TARGET, Scope  # noqa: E402

from facet.db import migration_entry as engine  # noqa: E402


def wait_control():
    ready, _, _ = select.select([sys.stdin], [], [], 12)
    assert ready, "owned_child_control_timeout"
    assert sys.stdin.readline().strip() == "continue", "owned_child_wrong_control"


def run():
    assert len(sys.argv) == 3, "fixed_child_arguments"
    phase, root = sys.argv[1:]
    assert phase in ("before_commit", "after_commit"), "fixed_child_phase"
    os.umask(0o077)
    engine._CURRENT_MANIFEST = TARGET
    engine._EXISTING_STEPS = (STEP,)
    engine._MIGRATION_PROVIDER_TYPES = (Scope,)
    with deny_network(), Scope(Path(root)) as scope:
        connection = scope.open()
        assert engine._state(connection, SOURCE).schema_version == SOURCE.version
        commit_requested, handshakes = [], []

        def boundary(action, first, second, database, source):
            if action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT":
                commit_requested.append(first)
                if phase == "before_commit":
                    assert connection.in_transaction
                    scope._check_migration_connection(connection, scope.owner)
                    handshakes.append(phase)
                    print("ready_before_commit", flush=True)
                    wait_control()
            if (
                phase == "after_commit"
                and commit_requested
                and not connection.in_transaction
                and not handshakes
                and action == sqlite3.SQLITE_READ
                and first == "sqlite_master"
            ):
                # Actual native COMMIT has returned: this is its first target
                # inspection, not a boolean supplied as maintenance authority.
                scope._check_migration_connection(connection, scope.owner)
                handshakes.append(phase)
                print("ready_after_commit", flush=True)
                wait_control()
            return sqlite3.SQLITE_OK

        connection.set_authorizer(boundary)
        result = engine.migrate_existing(
            connection, scope.owner, backup=scope.receipt, provider=scope
        )
        assert result.disposition == "migrated" and handshakes == [phase]
        print("migrated", flush=True)


if __name__ == "__main__":
    try:
        run()
    except BaseException:
        # Synthetic helper failure remains a failure, with no provider message,
        # SQL text or private filesystem trace copied to the parent's output.
        print("fixed_migration_child_failure", file=sys.stderr, flush=True)
        raise SystemExit(1) from None
