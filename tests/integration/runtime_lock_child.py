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

    if scenario in ("thread_exit", "thread_terminal"):
        stored = []

        def creator():
            root = private_root.open_existing_root(path)
            lease = locks.acquire_owner(root)
            if scenario == "thread_terminal":
                locks.release_lock(lease)
                private_root.close_root(root)
            stored.append(
                (root, lease, threading.get_ident(), threading.current_thread())
            )

        first = threading.Thread(target=creator)
        first.start()
        first.join()
        root, lease, ident, thread = stored[0]
        recycled = []

        def foreign():
            if threading.get_ident() == ident:
                assert threading.current_thread() is not thread
                for operation, resource in (
                    (private_root.check_root, root),
                    (private_root.close_root, root),
                    (locks.check_lock, lease),
                    (locks.release_lock, lease),
                ):
                    try:
                        operation(resource)
                    except private_root.LockFailure as error:
                        assert error.code.value == "owner_unavailable"
                    else:
                        raise AssertionError("foreign_thread_accepted")
                recycled.append(True)

        for _ in range(64):
            candidate = threading.Thread(target=foreign)
            candidate.start()
            candidate.join()
            if recycled:
                break
        assert recycled, "real_thread_ident_reuse_not_observed"
        say("recycled_refused")
        wait()
        # Neither live nor terminal resources transfer to a recycled Thread ID.
        # In the live case only this test process exit releases its kernel lock.
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
