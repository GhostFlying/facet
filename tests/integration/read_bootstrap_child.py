"""Fixed no-state controls; test-only, never installed or product-selected."""

import os
import sys
import threading
import time

SENTINEL = "synthetic_body_subject_sender@example.invalid_TOKEN_PRIVATE_PATH"


def reject_network(event, args):
    if event.startswith("socket.") or event == "subprocess.Popen":
        raise RuntimeError("test_network_denied")


def load_entry(path):
    with open(path, "rb") as stream:
        source = stream.read()
    namespace = {"__name__": "_fixed_test_bootstrap", "__file__": path}
    # Exact installed bytes, loaded only by the test before its genuine latch.
    exec(compile(source, path, "exec"), namespace)
    return namespace


def refusal(operation, code="owner_unavailable"):
    try:
        operation()
    except BaseException as error:
        assert getattr(error, "code", None) == code
        assert SENTINEL not in str(error) and SENTINEL not in repr(error)
    else:
        raise AssertionError("fixed_negative_did_not_refuse")


def snapshot(latch):
    return tuple(getattr(latch, field) for field in type(latch).__slots__)


def native_retired(native, deadline):
    assert os.path.isdir("/proc/self/task")
    while os.path.exists(f"/proc/self/task/{native}"):
        assert time.monotonic() < deadline, "native_thread_not_retired"
        time.sleep(0.001)


def held_reuse(ident, original, check):
    deadline = time.monotonic() + 4
    release, matched = threading.Event(), threading.Event()
    observations, failures, workers = [], [], []

    def candidate(ready):
        try:
            current = threading.current_thread()
            actual = threading.get_ident()
            observations.append((actual, threading.get_native_id()))
            if actual == ident:
                assert current is not original
                check()
                matched.set()
        except BaseException as error:
            failures.append(error)
        finally:
            ready.set()
        if not release.wait(max(0, deadline + 2 - time.monotonic())):
            failures.append(AssertionError("candidate_hold_timeout"))

    try:
        for _ in range(64):
            assert time.monotonic() < deadline, "candidate_allocation_timeout"
            ready = threading.Event()
            worker = threading.Thread(target=candidate, args=(ready,))
            workers.append(worker)
            worker.start()
            assert ready.wait(max(0, deadline - time.monotonic()))
            if failures:
                raise failures[0]
            assert len({entry[0] for entry in observations}) == len(observations)
            if matched.is_set():
                return
        raise AssertionError("actual_ident_reuse_not_observed")
    finally:
        release.set()
        cleanup = time.monotonic() + 2
        for worker in workers:
            if worker.ident is not None:
                worker.join(max(0, cleanup - time.monotonic()))
        assert all(not worker.is_alive() for worker in workers)
        for _, native in observations:
            native_retired(native, cleanup)
        if failures:
            raise failures[0]


def thread_control(ns, scenario):
    stored, failures = [], []
    ready, finish = threading.Event(), threading.Event()

    def creator():
        try:
            latch = ns["_begin_read_bootstrap"]()
            stored.append((latch, threading.get_ident(), threading.get_native_id()))
            if scenario == "thread_reused":
                latch.probe_runtime()
            ready.set()
            if scenario == "thread_live":
                assert finish.wait(6)
                latch.probe_runtime()
                assert ns["_stage_b"](latch) == "owner_unavailable"
        except BaseException as error:
            failures.append(error)
        finally:
            ready.set()

    original = threading.Thread(target=creator)
    try:
        original.start()
        assert ready.wait(3)
        if failures:
            raise failures[0]
        latch, ident, native = stored[0]
        before = snapshot(latch)

        def refused():
            refusal(ns["_begin_read_bootstrap"])
            refusal(latch.probe_runtime)
            refusal(lambda: ns["_stage_b"](latch))
            assert snapshot(latch) == before

        refused()
        if scenario == "thread_reused":
            original.join(2)
            assert not original.is_alive()
            native_retired(native, time.monotonic() + 2)
            held_reuse(ident, original, refused)
        else:
            assert original.is_alive()
    finally:
        finish.set()
        original.join(2)
        assert not original.is_alive()
        if stored:
            native_retired(stored[0][2], time.monotonic() + 2)
    if failures:
        raise failures[0]
    print("PASS", flush=True)


def fork_control(ns, latch):
    before = snapshot(latch)
    read, write = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read)
        try:
            refusal(ns["_begin_read_bootstrap"])
            refusal(latch.probe_runtime)
            refusal(lambda: ns["_stage_b"](latch))
            assert snapshot(latch) == before
            os.write(write, b"PASS")
        except BaseException:
            os._exit(1)
        os._exit(0)
    os.close(write)
    waited = False
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            pid, status = os.waitpid(child, os.WNOHANG)
            if pid == child:
                waited = True
                assert os.waitstatus_to_exitcode(status) == 0
                break
            time.sleep(0.001)
        assert waited, "owned_fork_timeout"
        assert os.read(read, 4) == b"PASS"
    finally:
        os.close(read)
        if not waited:
            os.kill(child, 9)
            os.waitpid(child, 0)
    assert snapshot(latch) == before
    latch.probe_runtime()
    assert ns["_stage_b"](latch) == "owner_unavailable"


def run():
    scenario, path = sys.argv[1:3]
    ns = load_entry(path)
    if scenario in ("preloaded_sqlite", "preloaded_application"):
        if scenario == "preloaded_sqlite":
            __import__("sqlite3")
        else:
            package = os.path.dirname(os.path.dirname(os.path.dirname(path)))
            sys.path.insert(0, package)
            module = __import__("facet")
            assert module.__file__ == os.path.join(package, "facet", "__init__.py")
        refusal(ns["_begin_read_bootstrap"])
        for name in tuple(sys.modules):
            if name == "_sqlite3" or name.startswith(("sqlite3", "facet")):
                del sys.modules[name]
        # Clearing imported modules cannot reconstruct fresh provenance.
        refusal(ns["_begin_read_bootstrap"])
        print("PASS")
        return
    if scenario == "hook_declined":

        def decline(event, args):
            if event == "sys.addaudithook":
                raise RuntimeError(SENTINEL)

        sys.addaudithook(decline)
        refusal(ns["_begin_read_bootstrap"], "persistence_failure")
        assert ns["_LATCH"].phase == "invalidated"
        print("PASS")
        return
    if scenario == "latch_allocation":

        class AllocationFailure:
            @staticmethod
            def __new__(cls):
                raise MemoryError(SENTINEL)

        ns["object"] = AllocationFailure  # Test-only genuine allocation fault.
        try:
            ns["_begin_read_bootstrap"]()
        except MemoryError:
            pass
        else:
            raise AssertionError("allocation_fault_not_reached")
        del ns["object"]
        assert ns["_LATCH"] is ns["_REFUSED"]
        refusal(ns["_begin_read_bootstrap"])
        print("PASS")
        return
    if scenario in ("thread_live", "thread_reused"):
        thread_control(ns, scenario)
        return
    events, state_opens, fd_before = [], [], set(os.listdir("/proc/self/fd"))

    def observe(event, args):
        events.append(event)
        if (
            event == "open"
            and type(args[0]) is str
            and args[0].endswith((".db", "-wal", "-shm", "-journal", ".json"))
        ):
            state_opens.append(args[0])

    sys.addaudithook(observe)
    latch = ns["_begin_read_bootstrap"]()
    assert latch.provider is None and latch.creator_thread is threading.current_thread()
    if scenario == "fork":
        fork_control(ns, latch)
        print("PASS")
        return
    if scenario in ("duplicate_begin", "forged_latch"):
        before = snapshot(latch)
        operation = (
            ns["_begin_read_bootstrap"]
            if scenario == "duplicate_begin"
            else object.__new__(ns["ReadBootstrapLatch"]).probe_runtime
        )
        refusal(operation)
        assert snapshot(latch) == before
    if scenario in ("direct_connection", "file_connect", "forged_handle"):
        import sqlite3

        operation = {
            "direct_connection": lambda: sqlite3.Connection(":memory:"),
            "file_connect": lambda: sqlite3.connect(sys.argv[3]),
            "forged_handle": lambda: sys.audit("sqlite3.connect/handle", object()),
        }[scenario]
        refusal(operation)
        assert latch.phase == "invalidated"
        refusal(latch.probe_runtime)
        print("PASS")
        return
    if scenario in ("connect_fault", "query_fault", "handle_fault", "close_fault"):
        import sqlite3

        original = sqlite3.connect
        owned = []

        def connect(*args, **kwargs):
            if scenario == "connect_fault":
                raise MemoryError(SENTINEL)
            connection = original(*args, **kwargs)
            owned.append(connection)
            if scenario == "query_fault":
                connection.set_authorizer(lambda *args: sqlite3.SQLITE_DENY)
            return connection

        sqlite3.connect = connect
        if scenario == "handle_fault":

            def fault(event, args):
                if event == "sqlite3.connect/handle":
                    owned.append(args[0])
                    raise RuntimeError(SENTINEL)

            sys.addaudithook(fault)
        if scenario == "close_fault":

            def close_fault(connection):
                raise OSError(SENTINEL)

            ns["_close_probe"] = close_fault
        refusal(latch.probe_runtime, "persistence_failure")
        assert latch.phase == "invalidated" and latch.runtime_facts is None
        if scenario == "close_fault":
            assert latch.probe_connection is owned[0]
            assert owned[0].execute("SELECT 1").fetchone() == (1,)
            owned[0].close()  # Only the test creator's actual enrolled handle.
        elif owned:
            try:
                owned[0].execute("SELECT 1")
            except sqlite3.ProgrammingError:
                pass
            else:
                raise AssertionError("owned_probe_not_closed")
        refusal(latch.probe_runtime)
        sqlite3.connect = original
        refusal(lambda: sqlite3.connect(":memory:"))
        print("PASS")
        return
    statements, owned = [], []
    if scenario == "normal":
        import sqlite3

        original = sqlite3.connect

        def traced(*args, **kwargs):
            connection = original(*args, **kwargs)
            owned.append(connection)
            connection.set_trace_callback(statements.append)
            return connection

        sqlite3.connect = traced
    facts = latch.probe_runtime()
    assert latch.phase == "probed" and latch.probe_connection is None
    import sqlite3

    assert (
        events.count("sqlite3.connect") == events.count("sqlite3.connect/handle") == 1
    )
    assert events.index("facet.read_bootstrap.enrolled") < events.index(
        "sqlite3.connect"
    )
    if scenario == "normal":
        assert ns["_stage_b"](latch) == "owner_unavailable"
        from facet.db import read_views

        assert read_views._PROVIDER_TYPES == read_views._QUALIFIED_RUNTIMES == ()
        assert (
            not read_views._SEALS and not read_views._LEASES and not read_views._PERMITS
        )
        assert "_wmi" not in sys.modules
        assert not state_opens and set(os.listdir("/proc/self/fd")) == fd_before
        assert (
            facts[0] == tuple(sys.version_info[:3])
            and facts[1] == sqlite3.sqlite_version_info
        )
        assert latch.provider is None and latch.phase == "probed"
        assert statements == ["SELECT sqlite_source_id()", "PRAGMA compile_options"]
        try:
            owned[0].execute("SELECT 1")
        except sqlite3.ProgrammingError:
            pass
        else:
            raise AssertionError("normal_probe_not_closed_before_stage_b")
    elif scenario in ("extra_memory", "repeated_probe"):
        operation = (
            (lambda: sqlite3.connect(":memory:"))
            if scenario == "extra_memory"
            else latch.probe_runtime
        )
        refusal(operation)
        assert latch.phase == "invalidated"
    elif scenario == "foreign_sqlite":
        failures = []

        def foreign():
            try:
                refusal(lambda: sqlite3.connect(":memory:"))
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=foreign)
        worker.start()
        worker.join(2)
        assert not worker.is_alive()
        if failures:
            raise failures[0]
        assert latch.phase == "invalidated"
        refusal(lambda: ns["_stage_b"](latch))
    elif scenario == "unexpected_import":
        refusal(lambda: __import__("ctypes"), "consistency_failure")
        assert "ctypes" not in sys.modules and latch.phase == "invalidated"
    elif scenario in ("unexpected_open", "state_write"):

        def read_state():
            with open(sys.argv[3], "rb"):
                raise AssertionError("forbidden_state_opened")

        operation = (
            read_state
            if scenario == "unexpected_open"
            else (lambda: os.open(sys.argv[3], os.O_WRONLY | os.O_CREAT, 0o600))
        )
        refusal(operation, "consistency_failure")
        assert latch.phase == "invalidated"
    elif scenario == "extension":
        refusal(lambda: sys.audit("sqlite3.load_extension", object(), SENTINEL))
        assert latch.phase == "invalidated"
    elif scenario in ("state_chmod", "state_unlink", "state_mkdir"):
        operation = {
            "state_chmod": lambda: os.chmod(sys.argv[3], 0o644),
            "state_unlink": lambda: os.unlink(sys.argv[3]),
            "state_mkdir": lambda: os.mkdir(sys.argv[3]),
        }[scenario]
        refusal(operation, "consistency_failure")
        assert latch.phase == "invalidated"
    elif scenario == "loaded_optional":
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(path))))
        module = __import__("_wmi")
        assert module.TEST_VALUE == "synthetic_unexpected_module"
        refusal(lambda: ns["_stage_b"](latch), "consistency_failure")
        assert latch.phase == "invalidated"
        refusal(lambda: ns["_stage_b"](latch))
    elif scenario == "alternate_native":
        import _imp
        import importlib.machinery

        specification = importlib.machinery.ModuleSpec(
            "_uuid", None, origin=sys.argv[3]
        )
        refusal(lambda: _imp.create_dynamic(specification), "consistency_failure")
        assert "_uuid" not in sys.modules and latch.phase == "invalidated"
    elif scenario == "optional_implementation":
        sys.path.insert(0, sys.argv[3])
        refusal(lambda: __import__("_wmi"), "consistency_failure")
        assert "_wmi" not in sys.modules and latch.phase == "invalidated"
    elif scenario.startswith("facts_"):
        index, value = {
            "facts_python": (0, (True, 12, 1)),
            "facts_sqlite": (1, (3, False, 1)),
            "facts_source": (2, SENTINEL + "\n"),
            "facts_options": (3, ("SAFE", "SAFE")),
            "facts_architecture": (4, "unknown"),
            "facts_platform": (5, "unknown"),
            "facts_vfs": (6, "unknown"),
        }[scenario]
        ns["_set"](latch, "runtime_facts", (*facts[:index], value, *facts[index + 1 :]))
        refusal(lambda: ns["_stage_b"](latch), "consistency_failure")
        assert latch.phase == "invalidated"
    elif scenario in ("main_sensitive_fault", "main_hostile_code"):

        def sensitive_fault():
            if scenario == "main_hostile_code":
                raise ns["ReadBootstrapFailure"](SENTINEL)
            raise OSError(SENTINEL)

        ns["_begin_read_bootstrap"] = sensitive_fault
        raise SystemExit(ns["_main"]())
    else:
        if scenario not in ("duplicate_begin", "forged_latch"):
            raise AssertionError("unknown_fixed_test_control")
    print("PASS", flush=True)


if __name__ == "__main__":
    sys.addaudithook(reject_network)
    run()
