"""RV bridge values/refusal controls; genuine isolated producers follow below.

Empty-inventory and malformed-identity tests are not a live-WAL qualification,
and no fabricated enrollment in this process creates a successful permit.
"""

import copy
import json
import pickle
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from test_db_repositories import state as state
from test_db_repositories import view
from test_db_schema import P

from facet.contracts import ErrorCode, LocalId, Sha256Hex
from facet.db import read_views as views
from facet.db.codecs import StorageFailure


def runtime():
    # A syntactically valid synthetic value, deliberately not a qualified entry.
    return views.ReadRuntimeIdentity(
        (3, 12, 13),
        (3, 53, 1),
        "synthetic-runtime-source",
        Sha256Hex("a" * 64),
        "x86_64",
        "linux",
        "unix",
    )


@pytest.mark.parametrize("field", ["device", "inode", "uid", "mode"])
@pytest.mark.parametrize("bad", [True, -1, "PRIVATE_RUNTIME_MARKER"])
def test_file_identity_exact_nonnegative_fields_and_safe_errors(field, bad):
    value = dict(device=1, inode=2, uid=3, mode=384)
    value[field] = bad
    with pytest.raises(StorageFailure) as failure:
        views.FileIdentity(**value)
    assert failure.value.code is ErrorCode.INVALID_INPUT
    assert str(failure.value) == "invalid_input"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("python_version", [3, 12, 13]),
        ("python_version", (3, 12)),
        ("python_version", (True, 12, 13)),
        ("sqlite_version", (3, -1, 0)),
        ("sqlite_version", (3, "53", 1)),
        ("sqlite_source_id", ""),
        ("sqlite_source_id", "x" * 257),
        ("sqlite_source_id", "PRIVATE_RUNTIME_MARKER\x00"),
        ("sqlite_source_id", "x\n"),
        ("sqlite_source_id", "xé"),
        ("compile_options_digest", "a" * 64),
        ("architecture", "unknown"),
        ("platform", "darwin"),
        ("vfs", "unix-none"),
    ],
)
def test_runtime_exact_closed_fields(field, bad):
    with pytest.raises(StorageFailure) as failure:
        replace(runtime(), **{field: bad})
    assert str(failure.value) == "invalid_input"


def test_runtime_and_file_repr_never_print_private_qualification_details():
    assert repr(runtime()) == "ReadRuntimeIdentity()"
    assert repr(views.FileIdentity(1, 2, 3, 384)) == "FileIdentity()"
    assert tuple(views.ViewMode) == (
        views.ViewMode.STOPPED_CLEAN,
        views.ViewMode.LIVE_WAL,
    )


@pytest.mark.parametrize(
    "cls", [views.ReadProcessSeal, views.ReadViewLease, views.ReadViewPermit]
)
def test_opaque_constructor_copy_pickle_and_mutation_cannot_enroll(cls):
    with pytest.raises(StorageFailure):
        cls()
    forged = object.__new__(cls)
    assert not hasattr(forged, "__dict__")
    assert repr(forged) == cls.__name__ + "()"
    for call in (
        lambda: copy.copy(forged),
        lambda: pickle.dumps(forged),
        lambda: setattr(forged, "PRIVATE_RUNTIME_MARKER", True),
    ):
        with pytest.raises(StorageFailure) as failure:
            call()
        assert str(failure.value) == "invalid_input"


def test_shipped_empty_inventories_refuse_before_provider_attributes_or_sql():
    class Foreign:
        def __getattribute__(self, name):
            raise AssertionError("foreign provider attributes must not execute")

    assert views._PROVIDER_TYPES == () and views._QUALIFIED_RUNTIMES == ()
    with pytest.raises(StorageFailure) as failure:
        views._issue_read_seal(Foreign(), runtime())
    assert failure.value.code is ErrorCode.OWNER_UNAVAILABLE
    assert not views._SEALS and not views._LEASES and not views._PERMITS


def test_forged_exact_objects_fail_enrollment_before_missing_slots_are_read():
    forged_seal = object.__new__(views.ReadProcessSeal)
    forged_lease = object.__new__(views.ReadViewLease)
    forged_permit = object.__new__(views.ReadViewPermit)
    instance = LocalId("00000000000040008000000000000001")
    connection = sqlite3.connect(":memory:", autocommit=True)
    statements = []
    connection.set_trace_callback(statements.append)
    try:
        for call in (
            lambda: views._issue_read_lease(forged_seal, views.ViewMode.LIVE_WAL),
            lambda: forged_lease.check(),
            lambda: forged_lease.close(),
            lambda: views._bind_read_view(
                connection, instance, forged_lease, forged_seal
            ),
            lambda: views._consume_permit(forged_permit, connection, instance),
            lambda: views._check_permit(forged_permit),
            lambda: views._close_permit(forged_permit),
        ):
            with pytest.raises(StorageFailure) as failure:
                call()
            assert failure.value.code is ErrorCode.OWNER_UNAVAILABLE
        assert statements == []
        # Refusal of this unclaimed foreign handle must not close/adopt it.
        assert connection.execute("SELECT 1").fetchone() == (1,)
    finally:
        connection.close()


def test_foreign_factories_reject_types_without_custom_property_repr_or_comparison():
    class Foreign:
        def __getattribute__(self, name):
            raise AssertionError("foreign attribute")

        def __eq__(self, other):
            raise AssertionError("foreign comparison")

        def __repr__(self):
            raise AssertionError("foreign repr")

    foreign = Foreign()
    for call in (
        lambda: views._issue_read_seal(foreign, foreign),
        lambda: views._issue_read_lease(foreign, foreign),
        lambda: views._bind_read_view(foreign, foreign, foreign, foreign),
        lambda: views._consume_permit(foreign, foreign, foreign),
    ):
        with pytest.raises(StorageFailure) as failure:
            call()
        assert str(failure.value) in {"invalid_input", "owner_unavailable"}


def test_runtime_str_and_tuple_subclasses_are_rejected_before_their_hooks():
    class String(str):
        def __iter__(self):
            raise AssertionError("subclass string iteration")

    class Version(tuple):
        def __len__(self):
            raise AssertionError("subclass tuple length")

    for change in (
        {"sqlite_source_id": String("PRIVATE_RUNTIME_MARKER")},
        {"python_version": Version((3, 12, 13))},
        {"architecture": String("x86_64")},
    ):
        with pytest.raises(StorageFailure) as failure:
            replace(runtime(), **change)
        assert str(failure.value) == "invalid_input"


ENTRY = Path(__file__).with_name("db_view_bootstrap.py")


def isolated(case, root):
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(ENTRY), case, str(root)],
        close_fds=True,
        capture_output=True,
        text=True,
        timeout=12,
        check=True,
    )
    assert result.stderr == ""
    assert len(result.stdout) < 4096
    return json.loads(result.stdout)


def stopped_root(tmp_path):
    root = tmp_path / "isolated-state"
    root.mkdir(mode=0o700)
    for name in ("owner.lock", "view.lock"):
        (root / name).touch(mode=0o600)
    connection = sqlite3.connect(root / "metadata.db", autocommit=True)
    connection.execute("CREATE TABLE synthetic(value INTEGER NOT NULL)")
    connection.executemany("INSERT INTO synthetic VALUES(?)", [(i,) for i in range(7)])
    connection.close()
    (root / "metadata.db").chmod(0o600)
    return root


def artifacts(root):
    return {
        name.name: (name.stat().st_ino, name.stat().st_size, name.read_bytes())
        for name in root.iterdir()
        if name.is_file()
    }


@pytest.mark.parametrize(
    "case",
    [
        "preloaded",
        "duplicate_latch",
        "before_probe_memory",
        "before_probe_file",
        "duplicate_probe",
        "after_probe_memory",
        "after_probe_constructor",
        "import_open",
        "forged_latch",
        "extra_memory",
        "reuse_claim",
    ],
)
def test_real_fresh_bootstrap_order_refusals_without_state_open(tmp_path, case):
    root = stopped_root(tmp_path)
    before = artifacts(root)
    assert isolated(case, root) == {"status": "bootstrap_refused"}
    assert artifacts(root) == before


def test_real_probe_closes_before_final_seal_and_stopped_sqlite_lifetime(tmp_path):
    root = stopped_root(tmp_path)
    before = artifacts(root)
    result = isolated("stopped_positive", root)
    assert result == {
        "status": "ok",
        "rows": 7,
        "events": [
            "claimed_bootstrap",
            "acquired",
            "claimed_connection",
            "retired",
            "released",
        ],
    }
    assert artifacts(root) == before


@pytest.mark.parametrize(
    "case,expected",
    [
        ("invalid_identities", ["claimed_bootstrap", "acquired", "released"]),
        (
            "invalid_claim_return",
            [
                "claimed_bootstrap",
                "acquired",
                "claimed_connection",
                "retired",
                "released",
            ],
        ),
        (
            "allocation_failure",
            [
                "claimed_bootstrap",
                "acquired",
                "claimed_connection",
                "retired",
                "released",
            ],
        ),
    ],
)
def test_actual_acquire_and_binding_failures_release_owned_descriptors(
    tmp_path, case, expected
):
    root = stopped_root(tmp_path)
    before = artifacts(root)
    result = isolated(case, root)
    assert result["status"] in {"invalid_input", "consistency_failure"}
    assert result["events"] == expected
    assert artifacts(root) == before


def test_actual_uncertain_retirement_invalidates_seal_without_false_release(tmp_path):
    root = stopped_root(tmp_path)
    result = isolated("uncertain_retirement", root)
    assert result == {
        "status": "owner_unavailable",
        "events": ["claimed_bootstrap", "acquired", "claimed_connection"],
    }
    # The child has exited; the OS, not a claimed successful retirement, releases
    # its resources. A new independent process can now acquire the real locks.
    assert isolated("stopped_positive", root)["status"] == "ok"


def test_real_second_attachment_refuses_and_normal_owned_close_still_succeeds(tmp_path):
    root = stopped_root(tmp_path)
    assert isolated("double_attach", root)["status"] == "ok"


@pytest.mark.parametrize("case", ["foreign_thread", "inherited_fork"])
def test_actual_foreign_creator_cannot_adopt_or_invalidate_correct_owner(
    tmp_path, case
):
    root = stopped_root(tmp_path)
    before = artifacts(root)
    assert isolated(case, root)["status"] == "ok"
    assert artifacts(root) == before


def test_actual_altered_probe_facts_refuse_before_state_connection(tmp_path):
    root = stopped_root(tmp_path)
    before = artifacts(root)
    assert isolated("altered_runtime", root) == {
        "status": "consistency_failure",
        "events": [],
    }
    assert artifacts(root) == before


@pytest.mark.parametrize("entry", ["-wal", "-shm", "-journal"])
def test_stopped_zero_length_sidecar_is_not_clean_admission(tmp_path, entry):
    root = stopped_root(tmp_path)
    (root / ("metadata.db" + entry)).touch(mode=0o600)
    before = artifacts(root)
    result = isolated("stopped_positive", root)
    assert result == {"status": "owner_unavailable", "events": ["claimed_bootstrap"]}
    assert artifacts(root) == before
    (root / ("metadata.db" + entry)).unlink()
    assert isolated("stopped_positive", root)["status"] == "ok"


def test_actual_symlink_and_unsafe_permission_refuse_before_sqlite_open(tmp_path):
    root = stopped_root(tmp_path)
    (root / "metadata.db").chmod(0o644)
    before = artifacts(root)
    assert isolated("stopped_positive", root)["status"] == "owner_unavailable"
    assert artifacts(root) == before
    (root / "metadata.db").chmod(0o600)
    (root / "metadata.db").rename(root / "saved.db")
    (root / "metadata.db").symlink_to(root / "saved.db")
    before = artifacts(root)
    assert isolated("stopped_positive", root)["status"] == "consistency_failure"
    assert artifacts(root) == before


WRITER = """
import fcntl, os, select, socket, sqlite3, sys
from pathlib import Path
os.umask(0o077)
root = Path(sys.argv[1])
owner = os.open(root / 'owner.lock', os.O_RDONLY)
view = os.open(root / 'view.lock', os.O_RDONLY)
fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
db = sqlite3.connect(root / 'metadata.db', autocommit=True)
db.execute('PRAGMA journal_mode=WAL')
db.execute('PRAGMA wal_autocheckpoint=0')
db.execute('CREATE TABLE synthetic(value INTEGER NOT NULL)')
db.executemany('INSERT INTO synthetic VALUES(?)', [(i,) for i in range(7)])
server = socket.socket(socket.AF_UNIX)
server.bind(str(root / 'owner.sock'))
server.listen(4)
peers = []
print('ready', flush=True)
try:
    while True:
        ready, _, _ = select.select([server, sys.stdin], [], [], 10)
        if sys.stdin in ready:
            command = sys.stdin.readline().strip()
            if command != 'commit':
                break
            db.execute('INSERT INTO synthetic VALUES(7)')
            print('committed', flush=True)
        if server in ready:
            peer, _ = server.accept()
            peer.sendall(b'ready')
            peers.append(peer)
finally:
    fcntl.flock(view, fcntl.LOCK_EX)
    db.close()
    for peer in peers:
        peer.close()
    server.close()
    os.close(view)
    os.close(owner)
"""


@contextmanager
def live_root(tmp_path):
    import select

    root = tmp_path / "isolated-live"
    root.mkdir(mode=0o700)
    for name in ("owner.lock", "view.lock"):
        (root / name).touch(mode=0o600)
    child = subprocess.Popen(
        [sys.executable, "-I", "-S", "-c", WRITER, str(root)],
        close_fds=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([child.stdout], [], [], 8)[0]
        assert child.stdout.readline() == "ready\n"
        yield root, child
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
        assert stderr == "" and stdout == "" and child.returncode == 0


def test_actual_virgin_runtime_pair_detects_ordinary_ro_shm_write(tmp_path):
    with live_root(tmp_path) as (root, _):
        before = artifacts(root)
        assert isolated("control_readonly", root) == {
            "status": "diagnostic_only",
            "rows": 7,
        }
        assert artifacts(root) == before
        assert isolated("control_ordinary", root) == {
            "status": "diagnostic_only",
            "rows": 7,
        }
        after = artifacts(root)
        assert before.keys() == after.keys()
        assert after["metadata.db-shm"] != before["metadata.db-shm"]
        for name in before.keys() - {"metadata.db-shm"}:
            assert after[name] == before[name]


@pytest.mark.parametrize("row", [2, 3])
def test_actual_admitted_reader_step_failure_rolls_back_and_remains_usable(state, row):
    with view(state) as probe:
        assert probe.call("read_step_fault", P, row=row) == {
            "actual_child_assertions": True
        }


def test_actual_admitted_getters_reject_cursor_bounds_and_registered_family(state):
    with view(state) as probe:
        assert probe.call("guard_read_cursor", P) == {"actual_child_assertions": True}


@pytest.mark.parametrize("variant", ["foreign", "instance", "schema", "sql"])
def test_actual_admitted_attachment_refusal_preserves_or_closes_only_owned_handle(
    state, variant
):
    with view(state) as probe:
        assert probe.call("read_attach_failure", P, variant=variant) == (
            {"actual_child_assertions": True}
            if variant == "foreign"
            else {"ordered_cleanup": True}
        )


@pytest.mark.parametrize("case", ["live_positive", "live_two_readers"])
def test_real_live_leases_peer_pidfd_and_registered_readers_without_shm_writes(
    tmp_path, case
):
    # The detecting pair qualifies this actual binary's unix readonly_shm
    # behavior; it is test-only and not a shipped production runtime entry.
    with live_root(tmp_path) as (root, _):
        before = artifacts(root)
        assert isolated("control_readonly", root)["rows"] == 7
        assert artifacts(root) == before
        assert isolated("control_ordinary", root)["rows"] == 7
        baseline = artifacts(root)
        assert baseline["metadata.db-shm"] != before["metadata.db-shm"]
        result = isolated(case, root)
        assert result["status"] == "ok" and result["rows"] == 7
        assert artifacts(root) == baseline
