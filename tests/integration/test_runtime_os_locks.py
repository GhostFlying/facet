"""OL01–10: real Linux files, flocks, processes and detecting fault controls."""

import errno
import gc
import os
import select
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import weakref
from contextlib import contextmanager, suppress
from pathlib import Path

import pytest

from facet.contracts import ErrorCode, LocalId
from facet.runtime import locks, private_root

NAMESPACE = LocalId("123456781234423482341234567890ab")
NONCE = LocalId("8765432187654321a321876543210abc")
OTHER = LocalId("aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa")
CHILD = Path(__file__).with_name("runtime_lock_child.py")
SENTINEL = "SYNTHETIC_PRIVATE_LOCK_ERROR"


def assert_failure(operation, code, *args, **kwargs):
    with pytest.raises(private_root.LockFailure) as captured:
        operation(*args, **kwargs)
    error = captured.value
    assert error.code is code
    assert error.args == ("lock_failure",)
    assert str(error) == "lock_failure"
    assert repr(error) == "LockFailure('lock_failure')"
    assert error.__context__ is None and error.__cause__ is None
    assert SENTINEL not in repr(vars(error))
    return error


def _trusted(path):
    for entry in (path, *path.parents):
        try:
            info = entry.lstat()
        except OSError:
            return False
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in (0, os.geteuid())
            or stat.S_IMODE(info.st_mode) & 0o7022
        ):
            return False
    return True


@contextmanager
def trusted_sandbox():
    # CI uses its trusted workspace; this host's foreign-UID /data00 is rejected.
    # No pytest-/tmp exception exists in production or in this verification.
    candidates = (Path.cwd(), Path(f"/run/user/{os.geteuid()}"))
    anchor = next((path for path in candidates if _trusted(path)), None)
    assert anchor is not None, "no_verified_trusted_test_anchor"
    with tempfile.TemporaryDirectory(prefix="facet-os-test-", dir=anchor) as directory:
        yield Path(directory)


@pytest.fixture
def sandbox(deny_external_network):
    with trusted_sandbox() as path:
        yield path


def make_root(sandbox, name="state"):
    path = sandbox / name
    with private_root.create_lock_root(str(path)):
        pass
    return path


def tree(path):
    result = {}
    for entry in (path, *sorted(path.rglob("*"))):
        info = entry.lstat()
        result[str(entry.relative_to(path))] = (
            info.st_dev,
            info.st_ino,
            info.st_uid,
            info.st_mode,
            info.st_nlink,
            info.st_size,
            info.st_mtime_ns,
            entry.read_bytes() if stat.S_ISREG(info.st_mode) else None,
        )
    return result


def live_fds():
    result = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            info = os.fstat(int(name))
        except OSError as error:
            # The list operation's own short-lived descriptor is already closed.
            assert error.errno == errno.EBADF
            continue
        result[int(name)] = (info.st_dev, info.st_ino, info.st_mode)
    return result


class Child:
    def __init__(self, scenario, path, *args):
        self.handshake_timeout = 14 if scenario.startswith("thread_") else 8
        self.process = subprocess.Popen(
            [sys.executable, "-B", str(CHILD), scenario, str(path), *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.stderr = b""

    def line(self):
        ready, _, _ = select.select(
            [self.process.stdout], [], [], self.handshake_timeout
        )
        assert ready, "test_child_handshake_timeout"
        value = self.process.stdout.readline()
        assert value, "test_child_missing_handshake"
        return value.decode().strip()

    def send(self, value):
        self.process.stdin.write((value + "\n").encode())
        self.process.stdin.flush()

    def finish(self):
        if self.process.poll() is None:
            with suppress(BrokenPipeError):
                self.send("quit")
        try:
            _, self.stderr = self.process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            # Only this freshly spawned test process is ever signalled.
            self.process.kill()
            _, self.stderr = self.process.communicate(timeout=8)
            pytest.fail("test_child_cleanup_timeout")


@contextmanager
def child(scenario, path, *args):
    participant = Child(scenario, path, *args)
    try:
        yield participant
    finally:
        participant.finish()
        assert participant.stderr == b""


def probe(scenario, path):
    with child(scenario, path) as participant:
        result = participant.line()
    assert participant.process.returncode == 0
    return result


def test_ol01_existing_zero_writes_and_trusted_0755_ancestors(sandbox, monkeypatch):
    parent = sandbox / "trusted-parent"
    parent.mkdir(mode=0o755)
    path = make_root(parent)
    (path / "config.yaml").write_text("synthetic_private_configuration")
    before = tree(sandbox)

    def forbidden(*args, **kwargs):
        raise AssertionError("read_path_mutation")

    with (
        monkeypatch.context() as guard,
    ):
        for name in ("mkdir", "chmod", "chown", "unlink", "fsync"):
            guard.setattr(os, name, forbidden)
        with private_root.open_existing_root(str(path)) as root:
            private_root.check_root(root)
            with locks.acquire_owner(root) as owner:
                locks.check_lock(owner)
                with locks.acquire_view(root, locks.LockMode.EXCLUSIVE, owner=owner):
                    locks.check_lock(owner)
    assert tree(sandbox) == before


@pytest.mark.parametrize(
    "missing", ["root", "owner", "view", "locks", "requests", "keys"]
)
def test_ol01_missing_infrastructure_never_creates(sandbox, missing):
    path = make_root(sandbox)
    entries = {
        "root": path,
        "owner": path / "locks/owner.lock",
        "view": path / "locks/view.lock",
        "locks": path / "locks",
        "requests": path / "requests",
        "keys": path / "requests/locks",
    }
    entries[missing].rename(sandbox / "removed")
    before = tree(sandbox)
    assert_failure(
        private_root.open_existing_root, ErrorCode.OWNER_UNAVAILABLE, str(path)
    )
    assert tree(sandbox) == before


def test_ol02_fresh_partial_and_concurrent_creator_convergence(sandbox):
    path = sandbox / "state"
    with child("create", path) as first, child("create", path) as second:
        assert first.line() == second.line() == "ready"
        first.send("go")
        second.send("go")
        assert first.line() == second.line() == "created"
    assert first.process.returncode == second.process.returncode == 0
    before = tree(sandbox)
    with private_root.create_lock_root(str(path)):
        pass
    assert tree(sandbox) == before
    assert set(entry.name for entry in path.iterdir()) == {"locks", "requests"}
    for entry in path.rglob("*"):
        assert stat.S_IMODE(entry.stat().st_mode) == (
            0o700 if entry.is_dir() else 0o600
        )
        if entry.is_file():
            assert entry.stat().st_size == 0 and entry.stat().st_nlink == 1
    partial = sandbox / "partial"
    partial.mkdir(mode=0o700)
    (partial / "locks").mkdir(mode=0o700)
    original = (partial / "locks").stat().st_ino
    with private_root.create_lock_root(str(partial)):
        pass
    assert (partial / "locks").stat().st_ino == original


@pytest.mark.parametrize(
    "entry", ["config.yaml", "metadata.db", "bootstrap.json", "extra"]
)
def test_ol02_unknown_existing_entries_refuse_before_creation(sandbox, entry):
    path = sandbox / "state"
    path.mkdir(mode=0o700)
    (path / entry).touch(mode=0o600)
    before = tree(sandbox)
    assert_failure(private_root.create_lock_root, ErrorCode.SCOPE_REQUIRED, str(path))
    assert tree(sandbox) == before


@pytest.mark.parametrize("name", ["owner.lock", "view.lock"])
@pytest.mark.parametrize("as_parent", [False, True])
def test_ol02_ancestor_or_root_name_does_not_skip_fixed_lock_files(
    sandbox, name, as_parent
):
    if as_parent:
        parent = sandbox / name
        parent.mkdir(mode=0o700)
        path = parent / "state"
    else:
        path = sandbox / name
    with private_root.create_lock_root(str(path)) as root:
        private_root.check_root(root)
        assert (path / "locks/owner.lock").is_file()
        assert (path / "locks/view.lock").is_file()
        with locks.acquire_owner(root):
            assert probe("try_owner", path) == "owner_busy"
    assert probe("try_owner", path) == "held"


def test_ol02_preflight_checks_unsafe_file_before_any_missing_publication(sandbox):
    path = make_root(sandbox)
    (path / "requests/locks").rmdir()
    (path / "locks/view.lock").chmod(0o644)
    before = tree(sandbox)
    assert_failure(private_root.create_lock_root, ErrorCode.SCOPE_REQUIRED, str(path))
    assert tree(sandbox) == before


def test_ol02_restrictive_umask_is_refused_without_permission_repair(sandbox):
    previous = os.umask(0o777)
    try:
        assert_failure(
            private_root.create_lock_root,
            ErrorCode.SCOPE_REQUIRED,
            str(sandbox / "state"),
        )
    finally:
        os.umask(previous)
    assert stat.S_IMODE((sandbox / "state").stat().st_mode) == 0
    with pytest.raises(PermissionError):
        list((sandbox / "state").iterdir())
    # Only the test restores its own synthetic fixture for inspection/cleanup.
    (sandbox / "state").chmod(0o700)
    assert list((sandbox / "state").iterdir()) == []


def test_ol03_actual_owner_contention_context_exit_and_sigkill(sandbox):
    path = make_root(sandbox)
    before = tree(sandbox)
    with child("owner", path) as owner:
        assert owner.line() == "held"
        assert probe("try_owner", path) == "owner_busy"
    assert probe("try_owner", path) == "held"
    with child("owner", path) as victim:
        assert victim.line() == "held"
        assert probe("try_owner", path) == "owner_busy"
        victim.process.send_signal(signal.SIGKILL)
        victim.process.wait(timeout=8)
        assert victim.process.returncode == -signal.SIGKILL
        assert probe("try_owner", path) == "held"
    assert tree(sandbox) == before


def test_ol04_actual_shared_readers_and_owner_exclusive_freeze(sandbox):
    path = make_root(sandbox)
    with private_root.open_existing_root(str(path)) as root:
        with locks.acquire_owner(root) as owner:
            with child("view", path) as first, child("view", path) as second:
                assert first.line() == second.line() == "held"
                assert_failure(
                    locks.acquire_view,
                    ErrorCode.OWNER_BUSY,
                    root,
                    locks.LockMode.EXCLUSIVE,
                    owner=owner,
                )
                locks.check_lock(owner)
            with locks.acquire_view(root, locks.LockMode.EXCLUSIVE, owner=owner):
                assert probe("try_view", path) == "owner_busy"
        with locks.acquire_view(root, locks.LockMode.SHARED) as view:
            for mode in locks.LockMode:
                assert_failure(
                    locks.acquire_view, ErrorCode.OWNER_BUSY, root, mode, owner=None
                )
            assert_failure(locks.acquire_owner, ErrorCode.OWNER_BUSY, root)
            locks.check_lock(view)


def test_ol04_same_process_overlap_across_roots_and_threads(sandbox):
    path = make_root(sandbox)
    with private_root.open_existing_root(str(path)) as first:
        private_root.check_root(first)
        with locks.acquire_view(first, locks.LockMode.SHARED) as view:
            with private_root.open_existing_root(str(path)) as other:
                assert_failure(
                    locks.acquire_view,
                    ErrorCode.OWNER_BUSY,
                    other,
                    locks.LockMode.SHARED,
                )
            results = []

            def foreign_root():
                with private_root.open_existing_root(str(path)) as root:
                    results.append(
                        assert_failure(
                            locks.acquire_view,
                            ErrorCode.OWNER_BUSY,
                            root,
                            locks.LockMode.SHARED,
                        ).code
                    )

            thread = threading.Thread(target=foreign_root)
            thread.start()
            thread.join(timeout=8)
            assert not thread.is_alive() and results == [ErrorCode.OWNER_BUSY]
            locks.check_lock(view)


def test_ol04_physical_root_order_and_owner_dependency_across_distinct_handles(sandbox):
    path = make_root(sandbox)
    with (
        private_root.open_existing_root(str(path)) as first,
        private_root.open_existing_root(str(path)) as second,
    ):
        with locks.acquire_view(first, locks.LockMode.SHARED) as view:
            before = live_fds()
            assert_failure(locks.acquire_owner, ErrorCode.OWNER_BUSY, second)
            assert before == live_fds()
            locks.check_lock(view)
            assert probe("try_owner", path) == "held"
            assert probe("try_view", path) == "held"
        with locks.acquire_owner(second) as owner:
            locks.check_lock(owner)
            with locks.acquire_view(first, locks.LockMode.SHARED) as view:
                before = live_fds()
                assert_failure(locks.release_lock, ErrorCode.OWNER_BUSY, owner)
                assert before == live_fds()
                locks.check_lock(owner)
                locks.check_lock(view)
                assert probe("try_owner", path) == "owner_busy"
            locks.check_lock(owner)
    assert probe("exclusive", path) == "held"


@pytest.mark.parametrize("owner_first", [False, True])
def test_ol04_physical_root_order_and_dependency_across_actual_creator_threads(
    sandbox, owner_first
):
    path = make_root(sandbox)
    ready, finish = threading.Event(), threading.Event()
    errors = []

    def view_creator():
        try:
            with private_root.open_existing_root(str(path)) as first:
                private_root.check_root(first)
                with locks.acquire_view(first, locks.LockMode.SHARED) as view:
                    ready.set()
                    assert finish.wait(timeout=8), "test_view_control_timeout"
                    locks.check_lock(view)
        except BaseException as error:
            errors.append(error)

    with private_root.open_existing_root(str(path)) as second:
        owner = locks.acquire_owner(second) if owner_first else None
        creator = threading.Thread(target=view_creator)
        creator.start()
        try:
            assert ready.wait(timeout=8), "test_view_missing_handshake"
            before = live_fds()
            if owner_first:
                assert_failure(locks.release_lock, ErrorCode.OWNER_BUSY, owner)
                locks.check_lock(owner)
                assert probe("try_owner", path) == "owner_busy"
            else:
                assert_failure(locks.acquire_owner, ErrorCode.OWNER_BUSY, second)
                assert probe("try_owner", path) == "held"
            assert before == live_fds()
            assert probe("try_view", path) == "held"
            private_root.check_root(second)
        finally:
            finish.set()
            creator.join(timeout=8)
            if owner is not None:
                locks.release_lock(owner)
        assert not creator.is_alive() and not errors
        with locks.acquire_owner(second):
            assert probe("try_owner", path) == "owner_busy"
    assert probe("exclusive", path) == "held"


def test_ol05_same_key_contention_caller_finally_release_and_ipc_order(sandbox):
    path = make_root(sandbox)
    with child("key", path, NAMESPACE.value, NONCE.value) as peer:
        assert peer.line() == "held"
        with private_root.open_existing_root(str(path)) as root:
            with locks.acquire_view(root, locks.LockMode.SHARED) as view:
                assert_failure(
                    locks.acquire_key,
                    ErrorCode.OWNER_BUSY,
                    root,
                    NAMESPACE,
                    NONCE,
                    view=view,
                )
                # Failure does not silently release caller-owned SH.
                locks.check_lock(view)
                with locks.acquire_key(
                    root, NAMESPACE, OTHER, view=view, create=True
                ) as key:
                    assert_failure(
                        locks.acquire_key,
                        ErrorCode.OWNER_BUSY,
                        root,
                        OTHER,
                        NONCE,
                        view=view,
                    )
                    locks.check_lock(key)
            assert_failure(locks.check_lock, ErrorCode.OWNER_UNAVAILABLE, view)
    # Both same-key participants have now released SH; real owner EX succeeds.
    assert probe("exclusive", path) == "held"
    with private_root.open_existing_root(str(path)) as root:
        with locks.acquire_view(root, locks.LockMode.SHARED) as view:
            locks.check_lock(view)
            with locks.acquire_key(root, NAMESPACE, NONCE, view=view) as key:
                locks.check_lock(key)
        # The simulated IPC barrier can run only after key and SH are released.
        assert probe("exclusive", path) == "held"
    assert sorted(
        entry.name for entry in (path / "requests/locks").iterdir()
    ) == sorted(
        [
            f"rq1_{NAMESPACE.value}_{NONCE.value}.lock",
            f"rq1_{NAMESPACE.value}_{OTHER.value}.lock",
        ]
    )


def test_ol05_missing_key_read_is_zero_create(sandbox):
    path = make_root(sandbox)
    before = tree(sandbox)
    with private_root.open_existing_root(str(path)) as root:
        private_root.check_root(root)
        with locks.acquire_view(root, locks.LockMode.SHARED) as view:
            assert_failure(
                locks.acquire_key,
                ErrorCode.OWNER_UNAVAILABLE,
                root,
                NAMESPACE,
                NONCE,
                view=view,
            )
            locks.check_lock(view)
    assert tree(sandbox) == before


@pytest.mark.parametrize(
    "entry",
    [
        "state",
        "state/locks",
        "state/requests",
        "state/requests/locks",
        "state/locks/owner.lock",
    ],
)
def test_ol06_named_inode_replacement_invalidates_and_old_descriptors_close(
    sandbox, entry
):
    path = make_root(sandbox)
    root = private_root.open_existing_root(str(path))
    original = set(private_root._DESCRIPTORS)
    target = sandbox / entry
    directory = target.is_dir()
    target.rename(sandbox / "displaced")
    if directory:
        target.mkdir(mode=0o700)
    else:
        target.touch(mode=0o600)
    assert_failure(private_root.check_root, ErrorCode.OWNER_UNAVAILABLE, root)
    private_root.close_root(root)
    assert not original & set(private_root._DESCRIPTORS)
    assert target.exists()


def test_ol06_retained_ancestor_replacement_refuses(sandbox):
    parent = sandbox / "parent"
    parent.mkdir(mode=0o700)
    path = make_root(parent)
    root = private_root.open_existing_root(str(path))
    parent.rename(sandbox / "displaced")
    parent.mkdir(mode=0o700)
    assert_failure(private_root.check_root, ErrorCode.OWNER_UNAVAILABLE, root)
    private_root.close_root(root)


def test_ol06_key_inode_replacement_checks_actual_parent_and_cleans_old_fd(sandbox):
    path = make_root(sandbox)
    root = private_root.open_existing_root(str(path))
    view = locks.acquire_view(root, locks.LockMode.SHARED)
    key = locks.acquire_key(root, NAMESPACE, NONCE, view=view, create=True)
    target = path / f"requests/locks/rq1_{NAMESPACE.value}_{NONCE.value}.lock"
    original = private_root._LEASES[key].node.descriptor.number
    target.rename(sandbox / "displaced-key")
    target.touch(mode=0o600)
    assert_failure(locks.check_lock, ErrorCode.OWNER_UNAVAILABLE, key)
    locks.release_lock(key)
    with pytest.raises(OSError) as captured:
        os.fstat(original)
    assert captured.value.errno == errno.EBADF
    locks.release_lock(view)
    private_root.close_root(root)
    assert target.exists() and target.stat().st_size == 0
    assert probe("exclusive", path) == "held"


def test_ol06_key_checks_real_view_file_not_only_saved_key_tuple(sandbox):
    path = make_root(sandbox)
    root = private_root.open_existing_root(str(path))
    owner = locks.acquire_owner(root)
    view = locks.acquire_view(root, locks.LockMode.EXCLUSIVE, owner=owner)
    key = locks.acquire_key(root, NAMESPACE, NONCE, view=view, create=True)
    (path / "locks/view.lock").rename(sandbox / "displaced-view")
    (path / "locks/view.lock").touch(mode=0o600)
    assert_failure(locks.check_lock, ErrorCode.OWNER_UNAVAILABLE, key)
    locks.release_lock(key)
    locks.release_lock(view)
    locks.release_lock(owner)
    private_root.close_root(root)
    assert probe("try_owner", path) == "held"


def test_ol06_parent_is_actual_same_root_live_kind_not_constructed_proof(sandbox):
    path = make_root(sandbox)
    other_path = make_root(sandbox, "other")
    with (
        private_root.open_existing_root(str(path)) as root,
        private_root.open_existing_root(str(other_path)) as other,
        locks.acquire_owner(other) as foreign_owner,
        locks.acquire_view(root, locks.LockMode.SHARED) as view,
    ):
        assert_failure(
            locks.acquire_key,
            ErrorCode.INVALID_INPUT,
            root,
            NAMESPACE,
            NONCE,
            view=foreign_owner,
            create=True,
        )
        locks.check_lock(view)
        locks.check_lock(foreign_owner)
    with (
        private_root.open_existing_root(str(path)) as root,
        private_root.open_existing_root(str(other_path)) as other,
        locks.acquire_owner(other) as foreign_owner,
    ):
        assert_failure(
            locks.acquire_view,
            ErrorCode.INVALID_INPUT,
            root,
            locks.LockMode.EXCLUSIVE,
            owner=foreign_owner,
        )
        locks.release_lock(foreign_owner)
        assert_failure(
            locks.acquire_view,
            ErrorCode.OWNER_UNAVAILABLE,
            other,
            locks.LockMode.EXCLUSIVE,
            owner=foreign_owner,
        )


@pytest.mark.parametrize(
    "problem", ["symlink", "hardlink", "fifo", "directory", "content", "mode"]
)
def test_ol06_unsafe_lock_type_links_content_mode_zero_repair(sandbox, problem):
    path = make_root(sandbox)
    target = path / "locks/owner.lock"
    if problem in {"symlink", "fifo", "directory"}:
        target.unlink()
    if problem == "symlink":
        target.symlink_to(path / "locks/view.lock")
    elif problem == "hardlink":
        os.link(target, sandbox / "extra-link")
    elif problem == "fifo":
        os.mkfifo(target, 0o600)
    elif problem == "directory":
        target.mkdir(mode=0o600)
    elif problem == "content":
        target.write_bytes(b"synthetic_nonzero")
    else:
        target.chmod(0o640)
    before = tree(sandbox)
    assert_failure(private_root.open_existing_root, ErrorCode.SCOPE_REQUIRED, str(path))
    assert tree(sandbox) == before


@pytest.mark.parametrize(
    "entry,mode",
    [
        ("state", 0o750),
        ("state/locks", 0o770),
        ("state/requests", 0o1700),
        ("state/requests/locks", 0o755),
        ("", 0o722),
    ],
)
def test_ol06_unsafe_private_or_writable_ancestor_refuses(sandbox, entry, mode):
    path = make_root(sandbox)
    target = sandbox / entry
    target.chmod(mode)
    try:
        before = tree(sandbox)
        assert_failure(
            private_root.open_existing_root, ErrorCode.SCOPE_REQUIRED, str(path)
        )
        assert tree(sandbox) == before
    finally:
        target.chmod(0o700)


def test_ol06_actual_wrong_uid_directory_and_sticky_tmp_refuse():
    # The actual root-owned /usr cannot be an eUID-owned private state root.
    assert os.stat("/usr").st_uid == 0 and os.geteuid() != 0
    assert_failure(private_root.open_existing_root, ErrorCode.SCOPE_REQUIRED, "/usr")
    assert_failure(
        private_root.open_existing_root, ErrorCode.SCOPE_REQUIRED, "/tmp/state"
    )


def test_ol06_reused_fd_never_closes_unrelated_replacement(sandbox):
    path = make_root(sandbox)
    root = private_root.open_existing_root(str(path))
    lease = locks.acquire_owner(root)
    number = private_root._LEASES[lease].node.descriptor.number
    os.close(number)
    replacement = os.open(
        sandbox / "unrelated", os.O_CREAT | os.O_EXCL | os.O_RDONLY, 0o600
    )
    assert replacement == number
    try:
        assert_failure(locks.check_lock, ErrorCode.OWNER_UNAVAILABLE, lease)
        assert_failure(locks.release_lock, ErrorCode.OWNER_UNAVAILABLE, lease)
        os.fstat(replacement)
        private_root.close_root(root)
        os.fstat(replacement)
        with private_root.open_existing_root(str(path)) as fresh:
            private_root.check_root(fresh)
            with locks.acquire_owner(fresh):
                locks.release_lock(lease)
                assert probe("try_owner", path) == "owner_busy"
    finally:
        os.close(replacement)


def test_ol07_foreign_live_thread_cannot_poison_genuine_owner(sandbox):
    path = make_root(sandbox)
    with private_root.open_existing_root(str(path)) as root:
        private_root.check_root(root)
        with locks.acquire_owner(root) as lease:
            errors = []

            def foreign():
                for operation, resource in (
                    (private_root.check_root, root),
                    (private_root.close_root, root),
                    (locks.check_lock, lease),
                    (locks.release_lock, lease),
                ):
                    errors.append(
                        assert_failure(
                            operation, ErrorCode.OWNER_UNAVAILABLE, resource
                        ).code
                    )

            thread = threading.Thread(target=foreign)
            thread.start()
            thread.join(timeout=8)
            assert not thread.is_alive() and len(errors) == 4
            private_root.check_root(root)
            locks.check_lock(lease)
            assert probe("try_owner", path) == "owner_busy"


def test_ol07_real_recycled_thread_ident_refuses_with_original_lock_alive(sandbox):
    path = make_root(sandbox)
    with child("thread_exit", path) as participant:
        assert participant.line() == "recycled_refused"
        assert probe("try_owner", path) == "owner_busy"
    assert participant.process.returncode == 0
    assert probe("try_owner", path) == "held"


def test_ol08_actual_fork_copy_closes_without_unlocking_parent(sandbox):
    path = make_root(sandbox)
    with child("fork_release", path) as participant:
        assert participant.line() == "held"
        assert participant.line() == "fork_ready"
        assert probe("try_owner", path) == "owner_busy"
        participant.send("release")
        assert participant.line() == "released_child_alive"
        assert probe("try_owner", path) == "held"
    assert participant.process.returncode == 0


@pytest.mark.parametrize(
    "scenario,expected", [("fork_exit", "held"), ("duplicate_control", "owner_busy")]
)
def test_ol08_parent_exits_while_fork_child_alive_detecting_negative(
    sandbox, scenario, expected
):
    path = make_root(sandbox)
    with child(scenario, path) as participant:
        assert participant.line() == "held"
        participant.send("exit")
        assert participant.line() == "copy_alive"
        participant.process.wait(timeout=8)
        assert participant.process.returncode == 0
        assert probe("try_owner", path) == expected
    assert probe("try_owner", path) == "held"


def test_ol08_exec_inherits_no_owned_descriptor(sandbox):
    path = make_root(sandbox)
    assert probe("exec", path) == "exec_ok"
    assert probe("try_owner", path) == "held"


@pytest.mark.parametrize(
    "boundary", ["open", "fstat", "flock_busy", "flock_io", "post_lock_drift"]
)
def test_ol09_acquisition_faults_fixed_safe_errors_cleanup_only_new_fd(
    sandbox, monkeypatch, boundary
):
    path = make_root(sandbox)
    root = private_root.open_existing_root(str(path))
    descriptors = dict(private_root._DESCRIPTORS)
    kernel_descriptors = live_fds()
    before = tree(sandbox)
    real_open, real_fstat, real_flock = os.open, os.fstat, locks.fcntl.flock

    def injected_open(name, *args, **kwargs):
        if name == "owner.lock":
            raise OSError(errno.EIO, SENTINEL)
        return real_open(name, *args, **kwargs)

    def injected_fstat(number):
        if number not in descriptors:
            raise OSError(errno.EIO, SENTINEL)
        return real_fstat(number)

    def injected_flock(number, operation):
        if boundary == "flock_busy":
            raise OSError(errno.EAGAIN, SENTINEL)
        if boundary == "flock_io":
            raise OSError(errno.EIO, SENTINEL)
        real_flock(number, operation)
        (path / "locks/owner.lock").rename(sandbox / "displaced-lock")
        (path / "locks/owner.lock").touch(mode=0o600)

    with monkeypatch.context() as fault:
        if boundary == "open":
            fault.setattr(os, "open", injected_open)
        elif boundary == "fstat":
            fault.setattr(os, "fstat", injected_fstat)
        else:
            fault.setattr(locks.fcntl, "flock", injected_flock)
        expected = (
            ErrorCode.OWNER_BUSY
            if boundary == "flock_busy"
            else ErrorCode.OWNER_UNAVAILABLE
        )
        try:
            raise RuntimeError(SENTINEL)
        except RuntimeError:
            assert_failure(locks.acquire_owner, expected, root)
    assert descriptors == private_root._DESCRIPTORS
    assert kernel_descriptors == live_fds()
    assert not private_root._ROOTS[root].leases
    if boundary != "post_lock_drift":
        assert tree(sandbox) == before
    private_root.close_root(root)
    assert probe("try_owner", path) == "held"


def test_ol09_creation_fsync_failure_preserves_partial_for_explicit_retry(
    sandbox, monkeypatch
):
    path = sandbox / "state"
    before = dict(private_root._DESCRIPTORS)
    kernel_descriptors = live_fds()

    def failure(number):
        raise OSError(errno.EIO, SENTINEL)

    with monkeypatch.context() as fault:
        fault.setattr(os, "fsync", failure)
        assert_failure(
            private_root.create_lock_root, ErrorCode.PERSISTENCE_FAILURE, str(path)
        )
    assert before == private_root._DESCRIPTORS
    assert kernel_descriptors == live_fds()
    assert path.exists()
    with private_root.create_lock_root(str(path)):
        pass


@pytest.mark.parametrize("boundary", ["mkdir", "file_create", "key_fsync"])
def test_ol09_explicit_publication_failures_and_caller_owned_view(
    sandbox, monkeypatch, boundary
):
    path = sandbox / "state"
    original = dict(private_root._DESCRIPTORS)

    def failure(*args, **kwargs):
        raise OSError(errno.EIO, SENTINEL)

    if boundary != "key_fsync":
        with monkeypatch.context() as fault:
            if boundary == "mkdir":
                fault.setattr(os, "mkdir", failure)
            else:
                real_open = os.open

                def failed_file(name, flags, *args, **kwargs):
                    if flags & os.O_CREAT:
                        return failure()
                    return real_open(name, flags, *args, **kwargs)

                fault.setattr(os, "open", failed_file)
            assert_failure(
                private_root.create_lock_root,
                ErrorCode.PERSISTENCE_FAILURE,
                str(path),
            )
        assert original == private_root._DESCRIPTORS
        with private_root.create_lock_root(str(path)):
            pass
    else:
        path = make_root(sandbox)
        root = private_root.open_existing_root(str(path))
        view = locks.acquire_view(root, locks.LockMode.SHARED)
        owned = dict(private_root._DESCRIPTORS)
        with monkeypatch.context() as fault:
            fault.setattr(os, "fsync", failure)
            assert_failure(
                locks.acquire_key,
                ErrorCode.PERSISTENCE_FAILURE,
                root,
                NAMESPACE,
                NONCE,
                view=view,
                create=True,
            )
        assert owned == private_root._DESCRIPTORS
        assert private_root._ROOTS[root].leases == {view}
        assert probe("exclusive", path) == "owner_busy"
        locks.release_lock(view)
        private_root.close_root(root)
        assert probe("exclusive", path) == "held"
        assert original == private_root._DESCRIPTORS


@pytest.mark.parametrize("actually_closed", [True, False])
def test_ol09_uncertain_close_never_retries_integer(
    sandbox, monkeypatch, actually_closed
):
    path = make_root(sandbox)
    root = private_root.open_existing_root(str(path))
    lease = locks.acquire_owner(root)
    number = private_root._LEASES[lease].node.descriptor.number
    close = os.close
    calls = []

    def uncertain(candidate):
        calls.append(candidate)
        if actually_closed:
            close(candidate)
        raise OSError(errno.EIO, SENTINEL)

    with monkeypatch.context() as fault:
        fault.setattr(os, "close", uncertain)
        assert_failure(locks.release_lock, ErrorCode.PERSISTENCE_FAILURE, lease)
        locks.release_lock(lease)
    assert calls == [number] and number not in private_root._DESCRIPTORS
    assert_failure(private_root.check_root, ErrorCode.OWNER_UNAVAILABLE, root)
    private_root.close_root(root)
    if not actually_closed:
        # Test owns the deliberately unclosed raw FD; product must never retry it.
        assert probe("try_owner", path) == "owner_busy"
        close(number)
    assert probe("try_owner", path) == "held"


def test_ol10_dependency_close_refusal_and_reverse_nested_lifecycle(sandbox):
    path = make_root(sandbox)
    with private_root.open_existing_root(str(path)) as root:
        with locks.acquire_owner(root) as owner:
            with (
                locks.acquire_view(root, locks.LockMode.EXCLUSIVE, owner=owner) as view,
                locks.acquire_key(
                    root, NAMESPACE, NONCE, view=view, create=True
                ) as key,
            ):
                assert_failure(private_root.close_root, ErrorCode.OWNER_BUSY, root)
                assert_failure(locks.release_lock, ErrorCode.OWNER_BUSY, owner)
                assert_failure(locks.release_lock, ErrorCode.OWNER_BUSY, view)
                locks.check_lock(key)
                assert_failure(key.__enter__, ErrorCode.OWNER_BUSY)
            assert_failure(locks.check_lock, ErrorCode.OWNER_UNAVAILABLE, view)
            locks.check_lock(owner)
        locks.release_lock(owner)
    private_root.close_root(root)
    assert_failure(private_root.check_root, ErrorCode.OWNER_UNAVAILABLE, root)
    assert probe("try_owner", path) == "held"


def test_ol10_body_exception_not_suppressed_and_invalid_own_cleanup(sandbox):
    path = make_root(sandbox)
    with (
        pytest.raises(RuntimeError, match="synthetic_body"),
        private_root.open_existing_root(str(path)) as root,
        locks.acquire_owner(root),
    ):
        raise RuntimeError("synthetic_body")
    assert probe("try_owner", path) == "held"
    root = private_root.open_existing_root(str(path))
    owner = locks.acquire_owner(root)
    (path / "locks/owner.lock").rename(sandbox / "displaced-lock")
    (path / "locks/owner.lock").touch(mode=0o600)
    assert_failure(locks.check_lock, ErrorCode.OWNER_UNAVAILABLE, owner)
    locks.release_lock(owner)
    private_root.close_root(root)
    assert probe("try_owner", path) == "held"


def test_ol10_closed_metadata_is_bounded_by_live_terminal_handles(sandbox):
    path = make_root(sandbox)
    before = tree(sandbox)
    active = (len(private_root._ROOTS), len(private_root._LEASES))
    terminal = (len(private_root._CLOSED_ROOTS), len(private_root._RELEASED_LEASES))
    descriptors = live_fds()
    references = []
    for _ in range(256):
        with private_root.open_existing_root(str(path)) as root:
            private_root.check_root(root)
            with locks.acquire_owner(root) as owner:
                references.extend((weakref.ref(root), weakref.ref(owner)))
                locks.check_lock(owner)
        assert root not in private_root._ROOTS
        assert owner not in private_root._LEASES
    assert (len(private_root._ROOTS), len(private_root._LEASES)) == active
    assert len(private_root._CLOSED_ROOTS) <= terminal[0] + 1
    assert len(private_root._RELEASED_LEASES) <= terminal[1] + 1
    del root, owner
    gc.collect()
    assert all(reference() is None for reference in references)
    assert len(private_root._CLOSED_ROOTS) <= terminal[0]
    assert len(private_root._RELEASED_LEASES) <= terminal[1]
    assert live_fds() == descriptors and tree(sandbox) == before


def test_ol10_dropped_live_references_retain_actual_kernel_owner(sandbox):
    path = make_root(sandbox)
    root = private_root.open_existing_root(str(path))
    owner = locks.acquire_owner(root)
    root_reference, owner_reference = weakref.ref(root), weakref.ref(owner)
    del root, owner
    gc.collect()
    assert root_reference() is not None and owner_reference() is not None
    assert probe("try_owner", path) == "owner_busy"
    root, owner = root_reference(), owner_reference()
    locks.check_lock(owner)
    locks.release_lock(owner)
    private_root.close_root(root)
    del root, owner
    gc.collect()
    assert root_reference() is None and owner_reference() is None
    assert probe("try_owner", path) == "held"


def test_ol10_retained_terminal_proofs_repeat_without_resource_effects(
    sandbox, monkeypatch
):
    path = make_root(sandbox)
    root = private_root.open_existing_root(str(path))
    owner = locks.acquire_owner(root)
    locks.release_lock(owner)
    private_root.close_root(root)
    for value in (
        private_root._CLOSED_ROOTS[root],
        private_root._RELEASED_LEASES[owner],
    ):
        assert type(value) is private_root._TerminalProof
        assert tuple(value.__slots__) == ("pid", "thread", "phase")
        assert value.pid == os.getpid() and value.thread is threading.current_thread()

    def forbidden(*args, **kwargs):
        raise AssertionError("terminal_resource_effect")

    with monkeypatch.context() as guard:
        for name in ("open", "close", "stat", "fstat", "fsync", "mkdir", "unlink"):
            guard.setattr(os, name, forbidden)
        guard.setattr(locks.fcntl, "flock", forbidden)
        for _ in range(32):
            locks.release_lock(owner)
            private_root.close_root(root)
        assert_failure(locks.check_lock, ErrorCode.OWNER_UNAVAILABLE, owner)
        assert_failure(private_root.check_root, ErrorCode.OWNER_UNAVAILABLE, root)
        assert_failure(
            locks.release_lock,
            ErrorCode.OWNER_UNAVAILABLE,
            object.__new__(locks.LockLease),
        )
        assert_failure(
            private_root.close_root,
            ErrorCode.OWNER_UNAVAILABLE,
            object.__new__(private_root.HeldPrivateRoot),
        )
        failures = []

        def foreign():
            for operation, resource in (
                (locks.release_lock, owner),
                (private_root.close_root, root),
            ):
                failures.append(
                    assert_failure(
                        operation, ErrorCode.OWNER_UNAVAILABLE, resource
                    ).code
                )

        creator = threading.Thread(target=foreign)
        creator.start()
        creator.join(timeout=8)
        assert not creator.is_alive() and len(failures) == 2
    assert probe("try_owner", path) == "held"


@pytest.mark.parametrize("resource", ["root", "lease"])
def test_ol09_terminal_proof_allocation_failure_preserves_live_authority(
    sandbox, monkeypatch, resource
):
    path = make_root(sandbox)
    root = private_root.open_existing_root(str(path))
    owner = locks.acquire_owner(root) if resource == "lease" else None
    before = live_fds()

    def failure(*args, **kwargs):
        raise MemoryError(SENTINEL)

    with monkeypatch.context() as fault:
        fault.setattr(private_root, "_TerminalProof", failure)
        if owner is not None:
            assert_failure(locks.release_lock, ErrorCode.PERSISTENCE_FAILURE, owner)
            locks.check_lock(owner)
            assert probe("try_owner", path) == "owner_busy"
        else:
            assert_failure(private_root.close_root, ErrorCode.PERSISTENCE_FAILURE, root)
        private_root.check_root(root)
        assert before == live_fds()
    if owner is not None:
        locks.release_lock(owner)
    private_root.close_root(root)
    assert probe("try_owner", path) == "held"


def test_ol08_retained_terminal_fork_copies_cannot_act(sandbox):
    path = make_root(sandbox)
    assert probe("fork_terminal", path) == "terminal_fork_refused"
    assert probe("try_owner", path) == "held"


def test_ol07_terminal_original_thread_identity_survives_actual_id_recycling(sandbox):
    path = make_root(sandbox)
    with child("thread_terminal", path) as participant:
        assert participant.line() == "recycled_refused"
        assert probe("try_owner", path) == "held"
    assert participant.process.returncode == 0


THREAD_CONTROLS = (
    ("thread_exit", "recycled_refused", "owner_busy", 1),
    ("thread_terminal", "recycled_refused", "held", 1),
    ("thread_native_live", "native_live_refused", "owner_busy", 2),
    ("thread_allocation_live", "allocation_live_refused", "owner_busy", 2),
    ("thread_start_fault", "start_fault_cleaned", "owner_busy", 2),
    ("thread_timeout_fault", "timeout_fault_cleaned", "owner_busy", 2),
    ("thread_check_fault", "check_fault_cleaned", "owner_busy", 1),
)


def thread_control(path, scenario, handshake, kernel, task_count):
    before = tree(path), live_fds()
    with child(scenario, path) as participant:
        assert participant.line() == handshake
        # Native retirement and finally-joined candidates are visible from the
        # parent too. Only the deliberately held creator may accompany main.
        assert (
            len(list(Path(f"/proc/{participant.process.pid}/task").iterdir()))
            == task_count
        )
        assert probe("try_owner", path) == kernel
        assert tree(path) == before[0]
    assert participant.process.returncode == 0
    assert probe("try_owner", path) == "held"
    assert (tree(path), live_fds()) == before


@pytest.mark.parametrize("scenario,handshake,kernel,task_count", THREAD_CONTROLS[2:])
def test_th02_th03_actual_thread_negative_and_fault_cleanup_controls(
    sandbox, scenario, handshake, kernel, task_count
):
    thread_control(make_root(sandbox), scenario, handshake, kernel, task_count)


@pytest.mark.parametrize("batch", range(20))
def test_th04_twenty_complete_real_thread_child_control_batches(sandbox, batch):
    path = make_root(sandbox, f"state-{batch}")
    for scenario, handshake, kernel, task_count in THREAD_CONTROLS:
        thread_control(path, scenario, handshake, kernel, task_count)
