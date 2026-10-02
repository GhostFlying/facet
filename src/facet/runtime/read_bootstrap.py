"""Installed no-state bootstrap. Import alone installs no hook or connection.

This is an ordering/provenance foundation, NOT a provider or malicious-code
sandbox. The only admitted connection is one creator-owned memory probe.
"""

import os
import stat
import sys
import threading

_LATCH = None
_REFUSED = object()
_OPENING = object()
_PACKAGE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STDLIB = os.path.join(
    sys.base_prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}"
)
_CODES = frozenset(
    (
        "invalid_input",
        "owner_unavailable",
        "unsupported_version",
        "consistency_failure",
        "persistence_failure",
    )
)
# CPython platform tries this Windows-only extension even on Linux. Its failed
# import is permitted, but a loaded module is never in the qualified graph.
_ABSENT_IMPORTS = frozenset(("_wmi",))
# Fixed reviewed dependency graph; never filled from observed runtime modules.
# These CPython stdlib/native names permit no alternative SQLite binding.
_MODULES = frozenset(
    [
        "__main__",
        "_abc",
        "_ast",
        "_blake2",
        "_codecs",
        "_collections",
        "_collections_abc",
        "_datetime",
        "_frozen_importlib",
        "_frozen_importlib_external",
        "_functools",
        "_hashlib",
        "_imp",
        "_io",
        "_opcode",
        "_opcode_metadata",
        "_operator",
        "_signal",
        "_sqlite3",
        "_sre",
        "_stat",
        "_thread",
        "_tokenize",
        "_typing",
        "_uuid",
        "_warnings",
        "_weakref",
        "_weakrefset",
        "abc",
        "ast",
        "builtins",
        "codecs",
        "collections",
        "collections.abc",
        "contextlib",
        "copy",
        "copyreg",
        "dataclasses",
        "datetime",
        "dis",
        "encodings",
        "encodings.aliases",
        "encodings.utf_8",
        "enum",
        "functools",
        "genericpath",
        "hashlib",
        "importlib",
        "importlib._bootstrap",
        "importlib._bootstrap_external",
        "importlib.machinery",
        "inspect",
        "io",
        "itertools",
        "keyword",
        "linecache",
        "marshal",
        "opcode",
        "operator",
        "os",
        "os.path",
        "platform",
        "posix",
        "posixpath",
        "re",
        "re._casefix",
        "re._compiler",
        "re._constants",
        "re._parser",
        "reprlib",
        "sqlite3",
        "sqlite3.dbapi2",
        "stat",
        "sys",
        "threading",
        "time",
        "token",
        "tokenize",
        "types",
        "typing",
        "typing.io",
        "typing.re",
        "unicodedata",
        "uuid",
        "warnings",
        "weakref",
        "zipimport",
        "facet",
        "facet.runtime",
        "facet.runtime.read_qualification",
        "facet.contracts",
        "facet.contracts.enums",
        "facet.contracts.primitives",
        "facet.contracts.records",
        "facet.db",
        "facet.db.codecs",
        "facet.db.read_views",
    ]
)


class ReadBootstrapFailure(Exception):
    """Only a fixed literal code, never the rejected input or native error."""

    def __init__(self, code="consistency_failure"):
        self.code = (
            code if type(code) is str and code in _CODES else "consistency_failure"
        )
        super().__init__(self.code)

    def __repr__(self):
        return "ReadBootstrapFailure('controlled_failure')"


def _fail(code="owner_unavailable"):
    raise ReadBootstrapFailure(code)


def _set(latch, name, value):
    object.__setattr__(latch, name, value)


def _creator(latch):
    if (
        type(latch) is not ReadBootstrapLatch
        or latch is not _LATCH
        or latch.creator_pid != os.getpid()
        or latch.creator_thread is not threading.current_thread()
    ):
        _fail()


class ReadBootstrapLatch:
    __slots__ = (
        "creator_pid",
        "creator_thread",
        "phase",
        "probe_connection",
        "runtime_facts",
        "provider",
    )

    def __new__(cls, *args, **kwargs):
        _fail("invalid_input")

    def __init_subclass__(cls, **kwargs):
        _fail("invalid_input")

    def __setattr__(self, name, value):
        _fail("invalid_input")

    def __reduce_ex__(self, protocol):
        _fail("invalid_input")

    def __repr__(self):
        return "ReadBootstrapLatch()"

    def probe_runtime(self):
        # Foreign lifecycle callers never mutate or close the creator's probe.
        _creator(self)
        if self.phase != "installed":
            _set(self, "phase", "invalidated")
            _fail()
        _set(self, "phase", "probing")
        failed = None
        connection = None
        facts = None
        try:
            import sqlite3

            connection = sqlite3.connect(":memory:", autocommit=True)
            if (
                connection is not self.probe_connection
                or type(connection) is not sqlite3.Connection
            ):
                _fail("consistency_failure")
            source = connection.execute("SELECT sqlite_source_id()").fetchone()[0]
            options = tuple(
                row[0] for row in connection.execute("PRAGMA compile_options")
            )
            architecture = os.uname().machine
            facts = (
                tuple(sys.version_info[:3]),
                sqlite3.sqlite_version_info,
                source,
                options,
                architecture,
                sys.platform,
                "unix",
            )
        except BaseException as error:
            failed = (
                error.code
                if type(error) is ReadBootstrapFailure
                else "persistence_failure"
            )
        # An uncertain close never clears this handle or permits another probe.
        owned = self.probe_connection
        if owned is not None and owned is not _OPENING:
            try:
                _creator(self)
                _close_probe(owned)
            except BaseException:
                failed = "persistence_failure"
            else:
                _set(self, "probe_connection", None)
        elif connection is not None:
            failed = "consistency_failure"
        if failed is not None or self.phase != "probing":
            _set(self, "phase", "invalidated")
            _fail(failed or "consistency_failure")
        _set(self, "runtime_facts", facts)
        _set(self, "phase", "probed")
        return facts


def _close_probe(connection):
    # Fixed compiled cleanup, not an injected/user-selected callback.
    connection.close()


def _audit(latch, event, arguments):
    if event.startswith("sqlite3.connect"):
        valid = (
            latch.creator_pid == os.getpid()
            and latch.creator_thread is threading.current_thread()
            and latch.phase == "probing"
        )
        if valid and event == "sqlite3.connect":
            valid = arguments == (":memory:",) and latch.probe_connection is None
            if valid:
                _set(latch, "probe_connection", _OPENING)
                return
        elif valid and event == "sqlite3.connect/handle":
            import sqlite3

            valid = (
                latch.probe_connection is _OPENING
                and len(arguments) == 1
                and type(arguments[0]) is sqlite3.Connection
            )
            if valid:
                _set(latch, "probe_connection", arguments[0])
                return
        _set(latch, "phase", "invalidated")
        _fail()
    if event.startswith("sqlite3."):
        _set(latch, "phase", "invalidated")
        _fail()
    if (
        event == "import"
        and arguments[0] not in _MODULES
        and arguments[0] not in _ABSENT_IMPORTS
    ):
        _set(latch, "phase", "invalidated")
        _fail("consistency_failure")
    if event == "import" and arguments[1] is not None:
        # CPython emits the filename before loading a native extension. An
        # allowed name is not permission for an alternate installed binding.
        filename = arguments[1]
        allowed = False
        if type(filename) is str and arguments[0] not in _ABSENT_IMPORTS:
            absolute = os.path.abspath(filename)
            if (
                absolute.endswith(".so")
                and os.path.commonpath((absolute, _STDLIB)) == _STDLIB
            ):
                info = os.lstat(absolute)
                allowed = (
                    stat.S_ISREG(info.st_mode)
                    and info.st_uid in (0, os.geteuid())
                    and not stat.S_IMODE(info.st_mode) & 0o022
                )
        if not allowed:
            _set(latch, "phase", "invalidated")
            _fail("consistency_failure")
    if event == "open":
        path, _, flags = arguments
        allowed = False
        if type(path) is str and type(flags) is int:
            absolute = os.path.abspath(path)
            allowed = (
                not flags
                & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
                and absolute.endswith((".py", ".pyc", ".so"))
                and any(
                    os.path.commonpath((absolute, root)) == root
                    for root in (_PACKAGE, _STDLIB)
                )
            )
        if not allowed:
            _set(latch, "phase", "invalidated")
            _fail("consistency_failure")
    if event.startswith("socket.") or event in (
        "subprocess.Popen",
        "os.system",
        "os.posix_spawn",
        "os.exec",
        "os.mkdir",
        "os.rmdir",
        "os.remove",
        "os.rename",
        "os.chmod",
        "os.chown",
        "os.truncate",
        "os.link",
        "os.symlink",
        "os.utime",
    ):
        _set(latch, "phase", "invalidated")
        _fail("consistency_failure")


def _begin_read_bootstrap():
    global _LATCH
    if _LATCH is not None:
        _fail()
    # Absence after sys.modules clearing is not fresh provenance. Even an
    # initial validation/allocation failure permanently consumes this attempt.
    _LATCH = _REFUSED
    if (
        not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.dont_write_bytecode
        or not sys.flags.utf8_mode
        or not frozenset(sys.modules) <= _MODULES
        or any(
            name == "sqlite3" or name == "_sqlite3" or name.startswith("facet")
            for name in sys.modules
        )
    ):
        _fail()
    latch = object.__new__(ReadBootstrapLatch)
    _set(latch, "creator_pid", os.getpid())
    _set(latch, "creator_thread", threading.current_thread())
    _set(latch, "phase", "installed")
    _set(latch, "probe_connection", None)
    _set(latch, "runtime_facts", None)
    _set(latch, "provider", None)
    _LATCH = latch
    failed = False
    enrolled = [False]

    def guard(event, arguments):
        _audit(latch, event, arguments)
        if event == "facet.read_bootstrap.enrolled" and arguments == (latch,):
            enrolled[0] = True

    try:
        # The closure retains the exact enrolled identity for process lifetime.
        sys.addaudithook(guard)
        # CPython may silently decline hook addition when an existing hook
        # refuses it. Actual delivery, not addaudithook's return, is the proof.
        sys.audit("facet.read_bootstrap.enrolled", latch)
        if not enrolled[0]:
            failed = True
    except BaseException:
        failed = True
    if failed:
        _set(latch, "phase", "invalidated")
        _fail("persistence_failure")
    return latch


def _stage_b(latch):
    _creator(latch)
    if latch.phase != "probed" or latch.probe_connection is not None:
        _fail()
    package = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if os.path.basename(package) != "site-packages":
        _set(latch, "phase", "invalidated")
        _fail()
    sys.path.insert(0, package)
    verified = False
    try:
        from facet.runtime.read_qualification import _verify_foundation

        _verify_foundation(latch.runtime_facts)
        verified = True
    except BaseException:
        pass
    if not verified:
        _set(latch, "phase", "invalidated")
        _fail("consistency_failure")
    # Qualification constructs metadata only; no claim/seal/provider exists.
    _creator(latch)
    if latch.phase != "probed":
        _fail()
    return "owner_unavailable"


def _main():
    code = "consistency_failure"
    try:
        latch = _begin_read_bootstrap()
        latch.probe_runtime()
        code = _stage_b(latch)
    except ReadBootstrapFailure as error:
        code = error.code
    except BaseException:
        code = "persistence_failure"
    if type(code) is not str or code not in _CODES:
        code = "consistency_failure"
    # No raw traceback, runtime facts, paths or underlying exceptions.
    sys.stderr.write("facet: " + code + "\n")
    return 4 if code in ("owner_unavailable", "unsupported_version") else 7


if __name__ == "__main__":
    raise SystemExit(_main())
