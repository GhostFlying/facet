"""Fixed synthetic OS scenarios; never packaged or a product execution route."""

import errno
import fcntl
import os
import select
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fakes.network import deny_network  # noqa: E402


def say(value):
    print(value, flush=True)


def wait():
    value = sys.stdin.readline().strip()
    if value not in ("quit", "release", "exit", "go"):
        raise RuntimeError("invalid_test_control")
    return value


def read_control(number, count):
    ready, _, _ = select.select([number], [], [], 5)
    assert ready, "fork_test_control_timeout"
    return os.read(number, count)


def reap_owned_fork(pid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        waited, status = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            assert os.waitstatus_to_exitcode(status) == 0
            return
        time.sleep(0.01)
    # This PID came only from this helper's own fresh os.fork call.
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    raise AssertionError("fork_test_cleanup_timeout")


def native_retired(native_id, deadline):
    tasks = Path("/proc/self/task")
    assert tasks.is_dir() and (tasks / str(threading.get_native_id())).is_dir(), (
        "test_native_task_visibility_missing"
    )
    while (tasks / str(native_id)).exists():
        assert time.monotonic() < deadline, "test_native_thread_not_retired"
        time.sleep(0.001)


def inventories(roots):
    # Copy primitive phases, not mutable state objects whose later changes could
    # otherwise make a before/after comparison falsely equal.
    with roots._MUTEX:
        return (
            tuple(
                (
                    id(key),
                    id(state),
                    state.pid,
                    id(state.thread),
                    state.phase,
                    state.entered,
                    frozenset(map(id, state.leases)),
                )
                for key, state in roots._ROOTS.items()
            ),
            tuple(
                (
                    id(key),
                    id(state),
                    state.pid,
                    id(state.thread),
                    id(state.root),
                    id(state.parent),
                    state.kind,
                    state.mode,
                    state.phase,
                    state.entered,
                )
                for key, state in roots._LEASES.items()
            ),
            tuple(
                (id(key), state.pid, id(state.thread), state.phase)
                for key, state in roots._CLOSED_ROOTS.items()
            ),
            tuple(
                (id(key), state.pid, id(state.thread), state.phase)
                for key, state in roots._RELEASED_LEASES.items()
            ),
            tuple((key, id(state)) for key, state in roots._INODES.items()),
            tuple(
                (number, id(descriptor), descriptor.identity, os.fstat(number))
                for number, descriptor in roots._DESCRIPTORS.items()
            ),
        )


def held_candidates(ident, original, check, *, limit=64, timeout=4, fault=None):
    """Require actual identity reuse; hold every other allocation until cleanup."""
    deadline = time.monotonic() + timeout
    release = threading.Event()
    matched = threading.Event()
    observations = []
    failures = []
    candidates = []

    def candidate(ready, arrived):
        try:
            current = threading.current_thread()
            actual = threading.get_ident()
            observations.append((actual, current, threading.get_native_id()))
            arrived.set()
            if fault == "timeout":
                assert release.wait(max(0, deadline + 2 - time.monotonic())), (
                    "test_candidate_hold_timeout"
                )
            if actual == ident:
                assert current is not original, "test_original_thread_substituted"
                check()
                if fault == "check":
                    raise AssertionError("test_candidate_check_fault")
                matched.set()
        except BaseException as error:
            failures.append(error)
        finally:
            arrived.set()
            ready.set()
        if not release.wait(max(0, deadline + 2 - time.monotonic())):
            failures.append(AssertionError("test_candidate_hold_timeout"))

    try:
        for index in range(limit):
            assert time.monotonic() < deadline, "test_candidate_allocation_timeout"
            ready = threading.Event()
            arrived = threading.Event()
            current = threading.Thread(target=candidate, args=(ready, arrived))
            # Register before start, so every actually started Thread is joined,
            # including an exceptional start path. Never join an unstarted one.
            candidates.append(current)
            if fault == "start" and index == 1:
                assert len(observations) == 1 and candidates[0].is_alive()
                raise AssertionError("test_candidate_start_fault")
            current.start()
            if fault == "timeout":
                # First prove a real worker is running and held. Its readiness
                # cannot complete before finally releases the controlled gate.
                assert arrived.wait(max(0, deadline - time.monotonic()))
                assert observations and current.is_alive() and not failures
            readiness = (
                min(deadline, time.monotonic() + 0.03)
                if fault == "timeout"
                else deadline
            )
            assert ready.wait(max(0, readiness - time.monotonic())), (
                "test_candidate_readiness_timeout"
            )
            if failures:
                raise failures[0]
            assert len({entry[0] for entry in observations}) == len(observations)
            if matched.is_set():
                return len(observations)
        raise AssertionError("real_thread_ident_reuse_not_observed")
    finally:
        release.set()
        cleanup = time.monotonic() + 2
        for current in candidates:
            if current.ident is not None:
                current.join(max(0, cleanup - time.monotonic()))
        assert all(not current.is_alive() for current in candidates), (
            "test_candidate_cleanup_timeout"
        )
        for _, _, native_id in observations:
            native_retired(native_id, cleanup)
        # The explicit timeout control intentionally holds its readiness until
        # finally releases it. Other late worker errors must never pass quietly.
        if failures:
            raise failures[0]


def thread_scenario(scenario, path, roots, locks):
    stored = []
    failures = []
    ready = threading.Event()
    finish = threading.Event()
    live_control = scenario in (
        "thread_native_live",
        "thread_allocation_live",
        "thread_start_fault",
        "thread_timeout_fault",
    )

    def creator():
        try:
            root = roots.open_existing_root(path)
            lease = locks.acquire_owner(root)
            roots.check_root(root)
            locks.check_lock(lease)
            stored.append(
                (
                    root,
                    lease,
                    threading.get_ident(),
                    threading.current_thread(),
                    threading.get_native_id(),
                )
            )
            if scenario == "thread_terminal":
                locks.release_lock(lease)
                roots.close_root(root)
            ready.set()
            if live_control:
                try:
                    assert finish.wait(14), "test_creator_finish_timeout"
                    roots.check_root(root)
                    locks.check_lock(lease)
                finally:
                    locks.release_lock(lease)
                    roots.close_root(root)
        except BaseException as error:
            failures.append(error)
        finally:
            ready.set()

    original = threading.Thread(target=creator)
    try:
        original.start()
        assert ready.wait(2), "test_creator_readiness_timeout"
        if failures:
            raise failures[0]
        root, lease, ident, thread, native_id = stored[0]
        assert thread is original
        if live_control:
            assert original.is_alive()
            assert Path(f"/proc/self/task/{native_id}").is_dir()
        else:
            original.join(2)
            assert not original.is_alive(), "test_creator_join_timeout"
            native_retired(native_id, time.monotonic() + 2)
        before = inventories(roots)

        def refused():
            for operation, resource in (
                (roots.check_root, root),
                (roots.close_root, root),
                (locks.check_lock, lease),
                (locks.release_lock, lease),
            ):
                try:
                    operation(resource)
                except roots.LockFailure as error:
                    assert error.code.value == "owner_unavailable"
                    assert error.__context__ is None and error.__cause__ is None
                else:
                    raise AssertionError("foreign_thread_accepted")
            assert inventories(roots) == before, "test_original_inventory_changed"

        controls = {
            "thread_native_live": (
                "test_native_thread_not_retired",
                "native_live_refused",
            ),
            "thread_allocation_live": (
                "real_thread_ident_reuse_not_observed",
                "allocation_live_refused",
            ),
            "thread_start_fault": ("test_candidate_start_fault", "start_fault_cleaned"),
            "thread_timeout_fault": (
                "test_candidate_readiness_timeout",
                "timeout_fault_cleaned",
            ),
            "thread_check_fault": ("test_candidate_check_fault", "check_fault_cleaned"),
        }
        if scenario in controls:
            expected, handshake = controls[scenario]
            try:
                if scenario == "thread_native_live":
                    native_retired(native_id, time.monotonic() + 0.03)
                else:
                    fault = scenario.removeprefix("thread_").removesuffix("_fault")
                    count = held_candidates(
                        ident,
                        thread,
                        refused,
                        limit=4 if live_control else 64,
                        fault=fault if scenario.endswith("_fault") else None,
                    )
                    raise AssertionError("test_negative_control_accepted")
            except AssertionError as error:
                assert str(error) == expected, "test_wrong_detecting_failure"
        else:
            count = held_candidates(ident, thread, refused)
            assert 1 <= count <= 64
            handshake = "recycled_refused"
        assert inventories(roots) == before, "test_original_inventory_changed"
        # No candidate remains alive at the handshake. The watched creator is
        # deliberately still alive only in the fixed negative controls.
        assert set(threading.enumerate()) == (
            {threading.main_thread(), original}
            if live_control
            else {threading.main_thread()}
        )
        say(handshake)
        wait()
    finally:
        finish.set()
        if original.ident is not None:
            original.join(2)
        assert not original.is_alive(), "test_creator_cleanup_timeout"
        if stored:
            native_retired(stored[0][4], time.monotonic() + 2)
        if failures:
            raise failures[0]
    # Live retired-owner and check-fault resources stay strongly enrolled until
    # this fresh process exits: no transfer or GC unlock is a cleanup shortcut.


def run():
    scenario, path = sys.argv[1:3]
    if scenario == "duplicate_control":
        # Deliberate no-library/no-hook negative: a fork copy prolongs flock.
        fd = os.open(path + "/locks/owner.lock", os.O_RDONLY | os.O_CLOEXEC)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        say("held")
        wait()
        pid = os.fork()
        if pid == 0:
            say("copy_alive")
            time.sleep(2)
            os._exit(0)
        os.close(fd)
        os._exit(0)

    from facet.contracts import LocalId
    from facet.runtime import locks, private_root

    if scenario == "create":
        say("ready")
        wait()
        with private_root.create_lock_root(path):
            say("created")
        return

    if scenario.startswith("thread_"):
        thread_scenario(scenario, path, private_root, locks)
        return

    if scenario == "fork_terminal":
        root = private_root.open_existing_root(path)
        lease = locks.acquire_owner(root)
        locks.release_lock(lease)
        private_root.close_root(root)
        pid = os.fork()
        if pid == 0:
            assert not private_root._DESCRIPTORS
            for operation, resource in (
                (locks.release_lock, lease),
                (private_root.close_root, root),
                (locks.check_lock, lease),
                (private_root.check_root, root),
            ):
                try:
                    operation(resource)
                except private_root.LockFailure as error:
                    assert error.code.value == "owner_unavailable"
                else:
                    raise AssertionError("terminal_fork_copy_accepted")
            os._exit(0)
        reap_owned_fork(pid)
        locks.release_lock(lease)
        private_root.close_root(root)
        say("terminal_fork_refused")
        return

    with private_root.open_existing_root(path) as root:
        try:
            if scenario in ("owner", "try_owner", "fork_release", "fork_exit", "exec"):
                lease = locks.acquire_owner(root)
            elif scenario in ("view", "try_view"):
                lease = locks.acquire_view(root, locks.LockMode.SHARED)
            elif scenario == "exclusive":
                with locks.acquire_owner(root) as owner:
                    locks.check_lock(owner)
                    with locks.acquire_view(
                        root, locks.LockMode.EXCLUSIVE, owner=owner
                    ):
                        say("held")
                return
            elif scenario == "key":
                with locks.acquire_view(root, locks.LockMode.SHARED) as view:
                    locks.check_lock(view)
                    with locks.acquire_key(
                        root,
                        LocalId(sys.argv[3]),
                        LocalId(sys.argv[4]),
                        view=view,
                        create=True,
                    ):
                        say("held")
                        wait()
                return
            else:
                raise AssertionError("unknown_test_scenario")
        except private_root.LockFailure as error:
            assert error.__context__ is None and error.__cause__ is None
            say(error.code.value)
            return

        with lease:
            if scenario == "exec":
                numbers = tuple(private_root._DESCRIPTORS)
                code = (
                    "import os, errno\n"
                    f"numbers={numbers!r}\n"
                    "for number in numbers:\n"
                    " try: os.fstat(number)\n"
                    " except OSError as error: assert error.errno == errno.EBADF\n"
                    " else: raise AssertionError('inherited_owned_descriptor')\n"
                    "print('exec_ok', flush=True)\n"
                )
                os.execv(sys.executable, [sys.executable, "-B", "-c", code])
            say("held")
            if scenario.startswith("try_"):
                return
            if scenario == "fork_exit":
                wait()
                pid = os.fork()
                if pid == 0:
                    assert private_root._DESCRIPTORS == {}
                    say("copy_alive")
                    time.sleep(2)
                    os._exit(0)
                os._exit(0)
            if scenario == "fork_release":
                read_fd, write_fd = os.pipe()
                reply_read, reply_write = os.pipe()
                original = tuple(private_root._DESCRIPTORS)
                pid = os.fork()
                if pid == 0:
                    os.close(write_fd)
                    os.close(reply_read)
                    for number in original:
                        try:
                            os.fstat(number)
                        except OSError as error:
                            assert error.errno == errno.EBADF
                        else:
                            raise AssertionError("fork_owned_descriptor_survived")
                    for operation, resource in (
                        (private_root.check_root, root),
                        (private_root.close_root, root),
                        (locks.check_lock, lease),
                        (locks.release_lock, lease),
                        (private_root.open_existing_root, path),
                        (private_root.create_lock_root, path),
                    ):
                        try:
                            operation(resource)
                        except private_root.LockFailure as error:
                            assert error.code.value == "owner_unavailable"
                        else:
                            raise AssertionError("fork_copy_accepted")
                    os.write(reply_write, b"ready")
                    read_control(read_fd, 1)
                    os._exit(0)
                os.close(read_fd)
                os.close(reply_write)
                try:
                    assert read_control(reply_read, 5) == b"ready"
                    say("fork_ready")
                    assert wait() == "release"
                    locks.release_lock(lease)
                    say("released_child_alive")
                    wait()
                finally:
                    os.close(write_fd)
                    os.close(reply_read)
                    reap_owned_fork(pid)
                return
            wait()


if __name__ == "__main__":
    with deny_network():
        run()
