"""DB-01/02/06/18/20/21: real file-backed trusted schema/owner-supplied sessions."""

import os
import select
import sqlite3
import subprocess
import sys
from contextlib import contextmanager, suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread

import pytest

from facet.contracts import (
    BindingState,
    Count,
    ErrorCode,
    LocalId,
    ProjectionId,
    RestoreState,
    Revision,
    Role,
    SourceMode,
    Timestamp,
)
from facet.db.codecs import PrivateAddress, StorageFailure
from facet.db.connection import _attach_writer, _initialize_database
from facet.db.migrations import CHECKSUMS, REGISTRY_DIGEST, v0001
from facet.db.models import (
    BindingRow,
    BootstrapInitContext,
    OwnerSessionInfo,
    ProjectionRow,
    RulesetRow,
)
from facet.db.schema import TRUSTED_CATALOGUE, _inspect

P = ProjectionId("synthetic-projection")
NOW = Timestamp(datetime(2026, 10, 2, tzinfo=UTC))


def lid(n: int) -> LocalId:
    return LocalId(f"00000000000040008000{n:012x}")


def bootstrap_rows():
    info = OwnerSessionInfo(lid(1), lid(2), lid(3))
    projection = ProjectionRow(
        P,
        Count(1),
        info.state_instance_id,
        info.request_namespace,
        Revision(0),
        Revision(0),
        SourceMode.READONLY,
        BindingState.VERIFICATION_PENDING,
        RestoreState.NORMAL,
        True,
        info.owner_run_id,
        NOW,
    )
    bindings = tuple(
        BindingRow(
            P,
            role,
            PrivateAddress(role.value + "@example.invalid"),
            None,
            Revision(0),
            Revision(1),
            BindingState.VERIFICATION_PENDING,
            None,
        )
        for role in Role
    )
    return info, projection, bindings, RulesetRow(P, Revision(0), NOW, True)


def create_state(path, *, factory=sqlite3.Connection):
    # Test-owned newly-created connection, not an exported production factory.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(fd)
    connection = sqlite3.connect(path, autocommit=True, factory=factory)
    info, projection, bindings, ruleset = bootstrap_rows()
    session = _initialize_database(
        connection,
        bootstrap=BootstrapInitContext(info, lid(4)),
        initial_projection=projection,
        source_binding=bindings[0],
        target_binding=bindings[1],
        initial_ruleset=ruleset,
    )
    return connection, session, info


@pytest.fixture
def state(tmp_path):
    connection, session, info = create_state(tmp_path / "metadata.db")
    yield connection, session, info
    if not session._closed:
        session.close()


def test_pristine_initialize_real_file_wal_exact_catalogue_and_pending_rows(state):
    connection, _, _ = state
    assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    assert connection.execute("PRAGMA application_id").fetchone() == (
        v0001.APPLICATION_ID,
    )
    assert connection.execute("PRAGMA user_version").fetchone() == (1,)
    assert connection.execute(
        "SELECT registry_digest FROM schema_metadata"
    ).fetchone() == (REGISTRY_DIGEST,)
    assert connection.execute("SELECT checksum FROM schema_migrations").fetchone() == (
        CHECKSUMS[0],
    )
    assert (
        len(
            connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ).fetchall()
        )
        == 32
    )
    assert len(TRUSTED_CATALOGUE) == len(v0001.STATEMENTS)
    assert all(
        row[-1] == 1
        for row in connection.execute("PRAGMA table_list")
        if row[1] in {t.name for t in v0001.TABLES}
    )
    assert connection.execute(
        "SELECT cursor,reliable_coverage_at,revision FROM history_checkpoints"
    ).fetchone() == (None, None, 0)
    assert connection.execute(
        "SELECT daemon_paused,binding_state FROM projections"
    ).fetchone() == (1, "verification_pending")
    assert connection.execute("SELECT COUNT(*) FROM bindings").fetchone() == (2,)
    assert connection.execute("SELECT COUNT(*) FROM binding_revisions").fetchone() == (
        2,
    )
    assert connection.execute("SELECT revision,sealed FROM rulesets").fetchone() == (
        0,
        1,
    )
    assert not connection.in_transaction
    _inspect(connection)


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE unrelated(secret TEXT)",
        "CREATE VIEW unrelated AS SELECT 1",
        "PRAGMA application_id=1",
        "PRAGMA user_version=1",
    ],
)
def test_initializer_refuses_existing_unrelated_state_without_empty_recreation(
    tmp_path, statement
):
    path = tmp_path / "existing.db"
    connection = sqlite3.connect(path, autocommit=True)
    connection.execute(statement)
    info, projection, bindings, ruleset = bootstrap_rows()
    with pytest.raises(StorageFailure, match="^maintenance_required$"):
        _initialize_database(
            connection,
            bootstrap=BootstrapInitContext(info, lid(4)),
            initial_projection=projection,
            source_binding=bindings[0],
            target_binding=bindings[1],
            initial_ruleset=ruleset,
        )
    with sqlite3.connect(path) as reopened:
        assert (
            reopened.execute(
                "SELECT name FROM sqlite_schema WHERE name='projections'"
            ).fetchall()
            == []
        )


@pytest.mark.parametrize(
    "change", ["ready", "unpaused", "namespace", "same_account", "verified"]
)
def test_bootstrap_identity_and_pending_guards_precede_any_sql(tmp_path, change):
    connection = sqlite3.connect(tmp_path / "fresh.db", autocommit=True)
    info, projection, bindings, ruleset = bootstrap_rows()
    source, target = bindings
    if change == "ready":
        projection = replace(projection, binding_state=BindingState.VERIFIED)
    elif change == "unpaused":
        projection = replace(projection, daemon_paused=False)
    elif change == "namespace":
        projection = replace(projection, request_namespace=lid(99))
    elif change == "same_account":
        target = replace(target, declared_address=source.declared_address)
    else:
        source = replace(
            source,
            verified_address=source.declared_address,
            verified_at=NOW,
            state=BindingState.VERIFIED,
        )
    with pytest.raises(StorageFailure, match="^invalid_input$"):
        _initialize_database(
            connection,
            bootstrap=BootstrapInitContext(info, lid(4)),
            initial_projection=projection,
            source_binding=source,
            target_binding=target,
            initial_ruleset=ruleset,
        )
    assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []
    assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    connection.close()


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE unreviewed(x INTEGER) STRICT",
        "CREATE INDEX unreviewed ON bindings(role)",
        "DROP INDEX events_pending",
        "DROP TRIGGER schema_migrations_immutable_update",
        "PRAGMA user_version=2",
        "PRAGMA application_id=0",
    ],
)
def test_schema_tamper_newer_and_unrelated_fail_closed(state, statement):
    connection, _, _ = state
    connection.execute(statement)
    with pytest.raises(StorageFailure):
        _inspect(connection)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE schema_migrations SET checksum='" + "a" * 64 + "'",
        "DELETE FROM schema_migrations",
        "UPDATE rulesets SET sealed=0",
        "UPDATE bindings SET declared_address='other@example.invalid'",
        "UPDATE binding_revisions SET state='auth_required'",
    ],
)
def test_immutable_history_identity_and_sealed_snapshot_sql_guards(state, statement):
    connection, _, _ = state
    with pytest.raises(sqlite3.IntegrityError, match="^consistency_failure$"):
        connection.execute(statement)


def test_direct_sql_scalars_cross_projection_and_same_account_are_refused(state):
    connection, _, _ = state
    bad = (
        ("UPDATE projections SET config_revision=?", (-1,)),
        ("UPDATE projections SET daemon_paused=?", (2,)),
        ("UPDATE projections SET source_mode=?", ("secret arbitrary value",)),
        ("INSERT INTO rulesets VALUES(?,1,0,1)", ("different-projection",)),
        (
            "INSERT INTO binding_revisions VALUES(?,?,?,?,?,?,?)",
            (
                P.value,
                "target",
                2,
                "source@example.invalid",
                None,
                "verification_pending",
                None,
            ),
        ),
        (
            "INSERT INTO rules VALUES(?,?,?,?,?)",
            (P.value, "not-uuid4", "allow_sender", "synthetic@example.invalid", 0),
        ),
        (
            "INSERT INTO rules VALUES(?,?,?,?,?)",
            (P.value, lid(9).value, "allow_sender", "sentinel\x85content", 0),
        ),
    )
    for sql, params in bad:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(sql, params)


def test_short_transaction_rolls_back_and_caught_sql_failure_cannot_commit(state):
    connection, session, _ = state
    with (
        pytest.raises(StorageFailure, match="^consistency_failure$"),
        session.transaction() as uow,
    ):
        uow._execute("UPDATE projections SET config_revision=1")
        uow._execute("UPDATE projections SET daemon_paused=7")
    assert connection.execute("SELECT config_revision FROM projections").fetchone() == (
        0,
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        uow._execute("UPDATE projections SET config_revision=2")
        with suppress(StorageFailure):
            uow._execute("UPDATE projections SET daemon_paused=7")
    assert connection.execute("SELECT config_revision FROM projections").fetchone() == (
        0,
    )
    assert not connection.in_transaction


def test_nested_reused_wrong_thread_closed_uow_refused(state):
    connection, session, _ = state
    transaction = session.transaction()
    with transaction, pytest.raises(StorageFailure), session.transaction():
        pass
    with pytest.raises(StorageFailure), transaction:
        pass
    codes = []

    def wrong_thread():
        try:
            session.transaction()
        except StorageFailure as failure:
            codes.append(failure.code)

    thread = Thread(target=wrong_thread)
    thread.start()
    thread.join(5)
    assert not thread.is_alive()
    assert codes == [ErrorCode.OWNER_UNAVAILABLE]
    connection.close()
    with pytest.raises(StorageFailure, match="^owner_unavailable$"):
        session.transaction()


METADATA_WRITER = """
import fcntl, os, select, socket, sqlite3, sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from facet.contracts import LocalId
from facet.db.connection import _attach_writer
from facet.db.models import OwnerSessionInfo
os.umask(0o077)
root = Path(sys.argv[1])
owner = os.open(root / 'owner.lock', os.O_RDONLY)
view = os.open(root / 'view.lock', os.O_RDONLY)
fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
connection = sqlite3.connect(root / 'metadata.db', autocommit=True)
info = OwnerSessionInfo(*(LocalId(f'00000000000040008000{n:012x}') for n in (1,2,3)))
session = _attach_writer(connection, info)
connection.execute('PRAGMA wal_autocheckpoint=0')
# Preserve the supplied test-owned owner lineage, not a M103 new-owner claim.
with session.transaction() as uow:
    uow._execute('UPDATE projections SET config_revision=0')
server = socket.socket(socket.AF_UNIX)
server.bind(str(root / 'owner.sock'))
server.listen(4)
peers = []
print('ready', flush=True)
try:
    while True:
        selected, _, _ = select.select([server, sys.stdin, *peers], [], [], 10)
        if sys.stdin in selected:
            break
        if server in selected:
            peer, _ = server.accept()
            peer.sendall(b'ready')
            peers.append(peer)
        for peer in tuple(peers):
            if peer in selected:
                command = peer.recv(6)
                if not command:
                    peers.remove(peer)
                    peer.close()
                elif command == b'commit':
                    with session.transaction() as uow:
                        uow._execute('UPDATE projections SET config_revision=1')
                    peer.sendall(b'committed')
                else:
                    raise AssertionError('unknown fixed metadata writer command')
finally:
    fcntl.flock(view, fcntl.LOCK_EX)
    session.close()
    for peer in peers:
        peer.close()
    server.close()
    os.close(view)
    os.close(owner)
"""


@contextmanager
def live_metadata_writer(root):
    # A fixed test-only actor: existing supplied-lineage metadata, one update,
    # real writer ownership and shutdown coordination. No product IPC/runtime.
    for name in ("owner.lock", "view.lock"):
        (root / name).touch(mode=0o600)
    child = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            METADATA_WRITER,
            str(root),
            str(Path(__file__).resolve().parents[2] / "src"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
        text=True,
    )
    try:
        assert select.select([child.stdout], [], [], 8)[0]
        assert child.stdout.readline() == "ready\n"
        yield child
    finally:
        if child.poll() is None:
            child.stdin.write("exit\n")
            child.stdin.flush()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        stdout, stderr = child.communicate()
        assert stdout == "" and stderr == "" and child.returncode == 0


def test_reader_existing_wal_does_not_write_or_create_and_releases_snapshot(
    state, tmp_path
):
    from test_db_repositories import SnapshotProbe

    _, session, info = state
    session.close()
    path = tmp_path / "metadata.db"
    inode = path.stat().st_ino
    with live_metadata_writer(tmp_path):
        before = {p.name for p in tmp_path.iterdir()}
        probe = SnapshotProbe(tmp_path, info.state_instance_id)
        assert probe.call("live_schema_revision", P) == {
            "actual_child_assertions": True
        }
        assert path.stat().st_ino == inode
        assert set(p.name for p in tmp_path.iterdir()) == before
    connection = sqlite3.connect(path, autocommit=True)
    try:
        assert connection.execute(
            "SELECT config_revision FROM projections"
        ).fetchone() == (1,)
    finally:
        connection.close()


def test_writer_reattach_requires_exact_instance_namespace_owner(state, tmp_path):
    _, session, info = state
    session.close()
    for field in ("state_instance_id", "request_namespace", "owner_run_id"):
        connection = sqlite3.connect(tmp_path / "metadata.db", autocommit=True)
        with pytest.raises(StorageFailure, match="^request_lineage_mismatch$"):
            _attach_writer(connection, replace(info, **{field: lid(99)}))
    connection = sqlite3.connect(tmp_path / "metadata.db", autocommit=True)
    restored = _attach_writer(connection, info)
    with restored.transaction():
        assert connection.in_transaction
    assert not connection.in_transaction
    restored.close()


def test_all_foreign_key_lookup_columns_have_nonpartial_prefix_indexes(state):
    connection, _, _ = state
    for table in v0001.TABLES:
        keys = []
        for _, index, _, _, partial in connection.execute(
            f"PRAGMA index_list({table.name})"
        ):
            if not partial:
                keys.append(
                    tuple(
                        row[2]
                        for row in connection.execute(f"PRAGMA index_info({index})")
                    )
                )
        for columns, _, _, _ in v0001._relations(table):
            assert any(key[: len(columns)] == columns for key in keys), (
                table.name,
                columns,
            )


def test_sealed_ruleset_members_check_old_and_new_parent_for_every_mutation(state):
    connection, _, _ = state
    connection.execute("BEGIN IMMEDIATE")
    connection.execute(
        "INSERT INTO rules VALUES(?,?,?,?,?)",
        (P.value, lid(10).value, "allow_sender", "synthetic@example.invalid", 1),
    )
    connection.execute(
        "INSERT INTO rule_revisions VALUES(?,?,?,?,?,?,?)",
        (P.value, lid(10).value, 1, 1, 0, "cli", "synthetic-v1"),
    )
    connection.execute("INSERT INTO rulesets VALUES(?,1,0,0)", (P.value,))
    connection.execute("INSERT INTO rulesets VALUES(?,2,0,0)", (P.value,))
    connection.execute(
        "INSERT INTO ruleset_members VALUES(?,1,?,1)", (P.value, lid(10).value)
    )
    connection.execute(
        "UPDATE ruleset_members SET ruleset_revision=2 WHERE ruleset_revision=1"
    )
    with pytest.raises(sqlite3.IntegrityError, match="^consistency_failure$"):
        connection.execute(
            "UPDATE ruleset_members SET ruleset_revision=0 WHERE ruleset_revision=2"
        )
    with pytest.raises(sqlite3.IntegrityError, match="^consistency_failure$"):
        connection.execute(
            "INSERT INTO ruleset_members VALUES(?,0,?,1)", (P.value, lid(10).value)
        )
    connection.execute("UPDATE rulesets SET sealed=1 WHERE revision=2")
    for sql in (
        "UPDATE ruleset_members SET ruleset_revision=1 WHERE ruleset_revision=2",
        "UPDATE ruleset_members SET rule_revision=rule_revision "
        "WHERE ruleset_revision=2",
        "DELETE FROM ruleset_members WHERE ruleset_revision=2",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="^consistency_failure$"):
            connection.execute(sql)
    assert connection.execute(
        "SELECT COUNT(*) FROM ruleset_members WHERE ruleset_revision=0"
    ).fetchone() == (0,)
    connection.execute("COMMIT")


@pytest.mark.parametrize(
    "kind,legal",
    [
        ("L", lid(55).value),
        ("H", "a" * 64),
        ("P", "synthetic-projection"),
        ("K", "synthetic-policy.v1"),
        ("MigrationName", "v0001"),
    ],
)
def test_full_sql_text_scalar_rejects_nul_suffix_and_interior(
    kind, legal, state, tmp_path
):
    connection, _, _ = state
    sqltype, predicate = v0001._scalar("value", kind)
    connection.execute(
        f"CREATE TABLE test_scalar(value {sqltype} NOT NULL CHECK({predicate})) STRICT"
    )
    connection.execute("INSERT INTO test_scalar VALUES(?)", (legal,))
    sentinel = "PRIVATE_CONTENT_SENTINEL"
    for illegal in (
        legal + "\x00" + sentinel,
        legal[:1] + "\x00" + legal[2:],
        legal + "é",
    ):
        assert connection.execute(
            f"SELECT ({predicate}) FROM (SELECT ? AS value)", (illegal,)
        ).fetchone() == (0,)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            connection.execute("INSERT INTO test_scalar VALUES(?)", (illegal,))
    audit = (
        P.value,
        lid(55).value + "\x00" + sentinel,
        "initialized",
        "projection",
        *([None] * 8),
        0,
    )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        connection.execute(
            "INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", audit
        )
    assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone() == (0,)
    assert connection.execute("SELECT value FROM test_scalar").fetchall() == [(legal,)]
    for artifact in tmp_path.iterdir():
        if artifact.is_file():
            assert sentinel.encode() not in artifact.read_bytes()


@pytest.mark.parametrize(
    "kind,legal,bad",
    [
        ("L", lid(8).value, "f" * 32),
        ("H", "a" * 64, "A" * 64),
        ("P", "p" * 64, "p" * 65),
        ("K", "k" * 64, "k" * 65),
        ("MigrationName", "v9999", "v99999"),
    ],
)
def test_sql_scalar_legal_boundaries_and_precise_invalid_forms(state, kind, legal, bad):
    connection, _, _ = state
    _, predicate = v0001._scalar("value", kind)
    assert connection.execute(
        f"SELECT ({predicate}) FROM (SELECT ? AS value)", (legal,)
    ).fetchone() == (1,)
    assert connection.execute(
        f"SELECT ({predicate}) FROM (SELECT ? AS value)", (bad,)
    ).fetchone() == (0,)
