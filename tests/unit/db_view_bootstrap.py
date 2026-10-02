"""Test-only fresh -I -S entry, never a shipped launcher or provider.

The audit guard is installed before SQLite/application imports. Its only
pre-admission connection is the fixed, successfully closed memory probe.
"""

import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from threading import current_thread

_ENROLLED = None


class BootstrapFailure(Exception):
    def __str__(self):
        return "bootstrap_refused"


class ReadBootstrapLatch:
    __slots__ = (
        "creator_pid",
        "creator_thread",
        "phase",
        "probe_connection",
        "runtime_facts",
        "provider",
    )

    def _check(self):
        if (
            self is not _ENROLLED
            or self.creator_pid != os.getpid()
            or self.creator_thread is not current_thread()
            or self.phase == "invalidated"
        ):
            self.phase = "invalidated"
            raise BootstrapFailure()

    def probe_runtime(self):
        self._check()
        if self.phase != "installed":
            self.phase = "invalidated"
            raise BootstrapFailure()
        self.phase = "probing"
        connection = None
        try:
            import sqlite3

            connection = sqlite3.connect(":memory:", autocommit=True)
            if connection is not self.probe_connection:
                raise BootstrapFailure()
            source = connection.execute("SELECT sqlite_source_id()").fetchone()[0]
            options = tuple(
                sorted(row[0] for row in connection.execute("PRAGMA compile_options"))
            )
            facts = (
                tuple(sys.version_info[:3]),
                tuple(sqlite3.sqlite_version_info),
                source,
                options,
                platform.machine(),
                sys.platform,
                "unix",
            )
            connection.close()
            self.probe_connection = None
            self.runtime_facts = facts
            self.phase = "probed"
            return facts
        except Exception:
            self.phase = "invalidated"
            if connection is not None:
                connection.close()
            raise BootstrapFailure() from None

    def claim(self, provider, runtime):
        self._check()
        if self.phase != "probed":
            self.phase = "invalidated"
            raise BootstrapFailure()
        facts = self.runtime_facts
        options = ("\n".join(facts[3]) + "\n").encode() if facts[3] else b""
        actual = (
            runtime.python_version,
            runtime.sqlite_version,
            runtime.sqlite_source_id,
            runtime.compile_options_digest.value,
            runtime.architecture,
            runtime.platform,
            runtime.vfs,
        )
        expected = facts[:3] + (hashlib.sha256(options).hexdigest(),) + facts[4:]
        if actual != expected:
            self.phase = "invalidated"
            raise BootstrapFailure()
        self.provider = provider
        self.phase = "claimed"


def _begin_read_bootstrap():
    global _ENROLLED
    if _ENROLLED is not None or any(
        name == "sqlite3"
        or name == "_sqlite3"
        or name == "db_view_adapter"
        or name == "facet"
        or name.startswith("facet.")
        for name in sys.modules
    ):
        raise BootstrapFailure()
    latch = object.__new__(ReadBootstrapLatch)
    latch.creator_pid = os.getpid()
    latch.creator_thread = current_thread()
    latch.phase = "installed"
    latch.probe_connection = None
    latch.runtime_facts = None
    latch.provider = None
    _ENROLLED = latch
    awaiting_probe_handle = False

    def audit(event, args):
        nonlocal awaiting_probe_handle
        if event not in {"sqlite3.connect", "sqlite3.connect/handle"}:
            return
        latch._check()
        if latch.phase == "probing":
            if event == "sqlite3.connect":
                if (
                    awaiting_probe_handle
                    or latch.probe_connection is not None
                    or len(args) != 1
                    or type(args[0]) is not str
                    or args[0] != ":memory:"
                ):
                    latch.phase = "invalidated"
                    raise BootstrapFailure()
                awaiting_probe_handle = True
                return
            if not awaiting_probe_handle or latch.probe_connection is not None:
                latch.phase = "invalidated"
                raise BootstrapFailure()
            import sqlite3

            if len(args) != 1 or type(args[0]) is not sqlite3.Connection:
                latch.phase = "invalidated"
                raise BootstrapFailure()
            latch.probe_connection = args[0]
            awaiting_probe_handle = False
            return
        if latch.phase != "claimed":
            latch.phase = "invalidated"
            raise BootstrapFailure()
        # These fixed test-class methods are not caller-supplied callbacks.
        try:
            provider = latch.provider
            method = (
                type(provider)._audit_connect
                if event == "sqlite3.connect"
                else type(provider)._audit_handle
            )
            method(provider, args[0])
        except Exception:
            latch.phase = "invalidated"
            raise BootstrapFailure() from None

    sys.addaudithook(audit)
    return latch


def main():
    # The case selector is a finite synthetic-test instruction, not a product
    # config/provider/URI selector. The repository path is this reviewed entry.
    case = sys.argv[1]
    root = sys.argv[2]
    if case in {"control_ordinary", "control_readonly"}:
        # Deliberately unqualified virgin diagnostics for the detecting pair.
        # Neither process may issue a seal or open an application ReadSession.
        import sqlite3

        flag = "" if case == "control_ordinary" else "readonly_shm=1&"
        uri = Path(root, "metadata.db").as_uri() + (
            "?mode=ro&" + flag + "cache=private&vfs=unix"
        )
        connection = sqlite3.connect(uri, uri=True, autocommit=True)
        rows = connection.execute("SELECT count(*) FROM synthetic").fetchone()[0]
        connection.close()
        print(json.dumps({"status": "diagnostic_only", "rows": rows}))
        return
    if case == "preloaded":
        import sqlite3  # noqa: F401

    try:
        latch = _begin_read_bootstrap()
        if case == "duplicate_latch":
            _begin_read_bootstrap()
        if case in {"before_probe_memory", "before_probe_file"}:
            import sqlite3

            sqlite3.connect(":memory:" if case.endswith("memory") else root)
        facts = latch.probe_runtime()
        if case == "duplicate_probe":
            latch.probe_runtime()
        if case in {"after_probe_memory", "after_probe_constructor"}:
            import sqlite3

            method = sqlite3.connect if case.endswith("memory") else sqlite3.Connection
            method(":memory:", autocommit=True)
        if case == "forged_latch":
            forged = object.__new__(ReadBootstrapLatch)
            for name in ReadBootstrapLatch.__slots__:
                setattr(forged, name, getattr(latch, name))
            forged.probe_runtime()
        # Paths are fixed from this file, added only after the closed probe.
        location = Path(__file__).resolve()
        sys.path[:0] = [str(location.parent), str(location.parents[2] / "src")]
        from db_view_adapter import (
            GETTERS,
            PHYSICAL_CASES,
            getter_case,
            physical_case,
            run_case,
        )

        if (
            case not in GETTERS
            and case not in PHYSICAL_CASES
            and case
            not in {
                "stopped_positive",
                "live_positive",
                "live_two_readers",
                "double_attach",
                "invalid_identities",
                "invalid_claim_return",
                "uncertain_retirement",
                "allocation_failure",
                "foreign_thread",
                "inherited_fork",
                "altered_runtime",
                "extra_memory",
                "reuse_claim",
            }
        ):
            raise BootstrapFailure()

        if case in GETTERS or case in PHYSICAL_CASES:
            request = sys.stdin.buffer.read(32769)
            if len(request) > 32768:
                raise BootstrapFailure()
            method = getter_case if case in GETTERS else physical_case
            result = method(case, root, latch, facts, json.loads(request))
        else:
            result = run_case(case, root, latch, facts)
        encoded = json.dumps(result, sort_keys=True)
        if len(encoded.encode()) > 2 * 1024 * 1024:
            raise BootstrapFailure()
        print(encoded)
    except BootstrapFailure:
        print('{"status":"bootstrap_refused"}')
    except Exception as error:
        # Even a fixture protocol/parse failure does not export raw exceptions.
        from facet.db.codecs import StorageFailure

        if type(error) is StorageFailure:
            print(json.dumps({"status": error.code.value}))
        elif type(error) in {ValueError, TypeError, KeyError}:
            print('{"status":"invalid_input"}')
        else:
            print('{"status":"test_failure"}')
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
