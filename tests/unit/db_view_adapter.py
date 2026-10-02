"""Fixed isolated test producer, excluded from the Facet package/wheel.

This owns actual descriptors, advisory locks, peer lifetime and every SQLite
handle in its fresh reader. It is not a capability mock or a product opener.
"""

import copy
import fcntl
import hashlib
import os
import pickle
import select
import socket
import sqlite3
import stat
import struct
import sys
from dataclasses import replace
from pathlib import Path
from threading import Thread, current_thread

from db_view_job_values import pack_job

from facet.contracts import (
    Count,
    ErrorCode,
    JobState,
    LocalId,
    ProjectionId,
    ProviderId,
    Revision,
    Role,
    Sha256Hex,
)
from facet.db import connection as sessions
from facet.db import read_views as views
from facet.db.codecs import PageLimit, StorageFailure
from facet.db.connection import ReadSession, _attach_view
from facet.db.migration_backup import snapshot_database
from facet.db.repositories import reads
from facet.db.repositories.serialization import _encode_row

INSTANCE = LocalId("00000000000040008000000000000001")

if sys.argv[1] == "import_open":
    # Deliberately forbidden import-time open in the fixed negative fixture.
    sqlite3.connect(":memory:", autocommit=True)


def refuse():
    raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)


class FixedReadProvider:
    def __init__(self, latch, root, *, fault=None, instance=INSTANCE):
        self.latch = latch
        self.root = Path(root)
        self.seal = None
        self.resources = {}
        self.inventory = {}
        self.opening = None
        self.events = []
        self.fault = fault
        self.instance = instance
        self.creator_pid = os.getpid()
        self.creator_thread = current_thread()

    def _owner(self):
        if (
            os.getpid() != self.creator_pid
            or current_thread() is not self.creator_thread
        ):
            refuse()

    def _ready(self):
        self._owner()
        if (
            self.seal not in views._SEALS
            or self.seal.provider is not self
            or self.seal.invalidated
            or self.latch.phase != "claimed"
            or self.latch.provider is not self
        ):
            refuse()

    def _check_bootstrap(self, runtime):
        self._owner()
        self.latch.claim(self, runtime)
        self.events.append("claimed_bootstrap")

    @staticmethod
    def _identity(fd, *, directory=False):
        info = os.fstat(fd)
        expected = stat.S_ISDIR if directory else stat.S_ISREG
        if (
            not expected(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or not directory
            and info.st_nlink != 1
        ):
            refuse()
        return views.FileIdentity(info.st_dev, info.st_ino, info.st_uid, info.st_mode)

    @staticmethod
    def _close_resources(resource):
        # Close just this acquisition's resources, never any foreign owner.
        for key in ("peer", "pidfd"):
            value = resource.get(key)
            if value is not None:
                value.close() if key == "peer" else os.close(value)
        for fd in reversed(resource["fds"]):
            os.close(fd)

    def _acquire_lease(self, lease, mode):
        self._ready()
        if lease in self.resources:
            refuse()
        resource = {"fds": [], "mode": mode, "identities": {}}
        try:
            rootfd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            resource["fds"].append(rootfd)
            resource["root_identity"] = self._identity(rootfd, directory=True)

            def opened(name):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=rootfd)
                resource["fds"].append(fd)
                identity = self._identity(fd)
                resource["identities"][name] = (fd, identity)
                return fd

            ownerfd = opened("owner.lock")
            viewfd = opened("view.lock")
            if mode is views.ViewMode.STOPPED_CLEAN:
                fcntl.flock(ownerfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(viewfd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                for name in (
                    "metadata.db-wal",
                    "metadata.db-shm",
                    "metadata.db-journal",
                ):
                    try:
                        os.stat(name, dir_fd=rootfd, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    refuse()
            else:
                fcntl.flock(viewfd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                # An independent descriptor must observe a genuinely held owner
                # lock; successful acquisition is not a live ready owner.
                try:
                    fcntl.flock(ownerfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    fcntl.flock(ownerfd, fcntl.LOCK_UN)
                    refuse()
                if os.path.lexists(self.root / "metadata.db-journal"):
                    refuse()
                peer = socket.socket(socket.AF_UNIX)
                resource["peer"] = peer
                peer.settimeout(2)
                peer.connect(str(self.root / "owner.sock"))
                pid, uid, _ = struct.unpack(
                    "3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                )
                if pid == os.getpid() or uid != os.getuid():
                    refuse()
                resource["pidfd"] = os.pidfd_open(pid)
                if peer.recv(5) != b"ready":
                    refuse()
                opened("metadata.db-wal")
                opened("metadata.db-shm")
            opened("metadata.db")
            self.resources[lease] = resource
            self.events.append("acquired")
            if self.fault == "invalid_identities":
                return (object(), None, None)
            ids = resource["identities"]
            return (
                ids["metadata.db"][1],
                ids["metadata.db-wal"][1] if mode is views.ViewMode.LIVE_WAL else None,
                ids["metadata.db-shm"][1] if mode is views.ViewMode.LIVE_WAL else None,
            )
        except Exception:
            self._close_resources(resource)
            raise

    def _check_lease(self, lease):
        self._ready()
        resource = self.resources.get(lease)
        if resource is None:
            refuse()
        rootfd = resource["fds"][0]
        current_root = os.stat(self.root, follow_symlinks=False)
        if (
            views.FileIdentity(
                current_root.st_dev,
                current_root.st_ino,
                current_root.st_uid,
                current_root.st_mode,
            )
            != resource["root_identity"]
        ):
            refuse()
        for name, (fd, identity) in resource["identities"].items():
            current = os.stat(name, dir_fd=rootfd, follow_symlinks=False)
            if (
                self._identity(fd) != identity
                or views.FileIdentity(
                    current.st_dev, current.st_ino, current.st_uid, current.st_mode
                )
                != identity
            ):
                refuse()
        if resource["mode"] is views.ViewMode.LIVE_WAL:
            poll = select.poll()
            poll.register(resource["pidfd"], select.POLLIN)
            if poll.poll(0):
                refuse()
        else:
            for suffix in ("-wal", "-shm", "-journal"):
                if os.path.lexists(self.root / ("metadata.db" + suffix)):
                    refuse()

    def _audit_connect(self, database):
        self._ready()
        if (
            self.opening is None
            or self.opening["connected"]
            or type(database) is not str
            or database != self.opening["uri"]
        ):
            refuse()
        self._check_lease(self.opening["lease"])
        self.opening["connected"] = True

    def _audit_handle(self, connection):
        self._ready()
        if (
            self.opening is None
            or not self.opening["connected"]
            or self.opening["handle"] is not None
            or type(connection) is not sqlite3.Connection
            or connection in self.inventory
        ):
            refuse()
        self.opening["handle"] = connection
        self.inventory[connection] = (self.opening["lease"], "fresh")

    def _claim_connection(self, connection, lease):
        self._check_lease(lease)
        if self.inventory.get(connection) != (lease, "fresh"):
            refuse()
        self.inventory[connection] = (lease, "claimed")
        self.events.append("claimed_connection")
        if self.fault == "invalid_claim_return":
            return object()

    def _closed_connection(self, connection, lease):
        self._owner()
        if self.inventory.get(connection) not in {(lease, "fresh"), (lease, "claimed")}:
            refuse()
        try:
            connection.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            pass
        else:
            refuse()
        if self.fault == "uncertain_retirement":
            refuse()
        del self.inventory[connection]
        self.events.append("retired")

    def _release_lease(self, lease):
        self._owner()
        if lease not in self.resources or any(
            value[0] is lease for value in self.inventory.values()
        ):
            refuse()
        self._close_resources(self.resources.pop(lease))
        self.events.append("released")

    def open_bound(self, lease):
        self._check_lease(lease)
        if self.opening is not None:
            refuse()
        flags = (
            "immutable=1"
            if lease.mode is views.ViewMode.STOPPED_CLEAN
            else "readonly_shm=1"
        )
        uri = (self.root / "metadata.db").as_uri() + (
            "?mode=ro&" + flags + "&cache=private&vfs=unix"
        )
        self.opening = {"lease": lease, "uri": uri, "connected": False, "handle": None}
        try:
            connection = sqlite3.connect(uri, uri=True, autocommit=True)
            if connection is not self.opening["handle"]:
                refuse()
            self._check_lease(lease)
            permit = views._bind_read_view(connection, self.instance, lease, self.seal)
            return connection, permit
        except Exception:
            # Until _bind returns a permit, this opener owns its fresh handle.
            # A protocol-error return after registration does not transfer it.
            connection = self.opening["handle"]
            if connection in self.inventory:
                connection.close()
                self._closed_connection(connection, lease)
            if lease in self.resources:
                if lease in views._LEASES:
                    lease.close()
                else:
                    self._release_lease(lease)
            raise
        finally:
            self.opening = None


def _runtime(facts):
    options = ("\n".join(facts[3]) + "\n").encode() if facts[3] else b""
    return views.ReadRuntimeIdentity(
        *facts[:3], Sha256Hex(hashlib.sha256(options).hexdigest()), *facts[4:]
    )


def _lock_available(root, name):
    fd = os.open(Path(root) / name, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True
    finally:
        os.close(fd)


# This finite test inventory contains actual imported functions and their one
# result family. A request never selects a table, model, import, SQL or callback.
GETTERS = {
    "row_projection": (reads.get_projection, "projections", ()),
    "schema": (reads.inspect_schema, None, ()),
    "row_binding": (reads.get_binding, "bindings", (("role", Role),)),
    "row_binding_revision": (
        reads.get_binding_revision,
        "binding_revisions",
        (("role", Role), ("revision", Revision)),
    ),
    "row_rule": (reads.get_rule, "rules", (("id", LocalId),)),
    "row_epoch": (reads.get_epoch, "epochs", (("id", LocalId),)),
    "row_event": (reads.get_event, "source_events", (("id", LocalId),)),
    "row_job": (reads.get_job, "sync_jobs", (("id", LocalId),)),
    "row_attempt": (reads.get_attempt, "insert_attempts", (("id", LocalId),)),
    "row_action": (reads.get_action, "action_commands", (("id", LocalId),)),
    "row_thread": (reads.get_thread, "tracked_threads", (("id", ProviderId),)),
    "row_mapping": (reads.get_mapping, "message_mappings", (("id", ProviderId),)),
    "row_thread_target": (
        reads.get_thread_target,
        "thread_targets",
        (("source", ProviderId), ("target", ProviderId)),
    ),
    "row_thread_anchor": (
        reads.get_thread_anchor,
        "thread_targets",
        (("source", ProviderId),),
    ),
    "row_checkpoint": (reads.get_checkpoint, "history_checkpoints", ()),
    "row_history_poll": (reads.get_history_poll, "history_polls", (("id", LocalId),)),
    "row_history_page": (
        reads.get_history_page,
        "history_pages",
        (("id", LocalId), ("ordinal", Count)),
    ),
    "page_jobs": (reads.list_jobs, "sync_jobs", (("limit", PageLimit),)),
    "page_attempts": (reads.list_attempts, "insert_attempts", (("limit", PageLimit),)),
    "page_events": (reads.list_events, "source_events", (("limit", PageLimit),)),
    "page_audit": (reads.list_audit, "audit_events", (("limit", PageLimit),)),
    "counts": (reads.counts, None, ()),
}

PHYSICAL_CASES = {
    "guard_history_types": {"variant"},
    "guard_history_lifetime": set(),
    "guard_thread_reads": {"source", "target"},
    "guard_binding_role": set(),
    "read_zero_write": {"id", "ordinal"},
    "keyset_501": set(),
    "guard_read_cursor": set(),
    "read_step_fault": {"row"},
    "read_attach_failure": {"variant"},
    "snapshot_reject_read_source": set(),
    "live_schema_revision": set(),
}


def _expect_failure(function, *, code=None):
    try:
        function()
    except StorageFailure as error:
        if code is not None:
            assert error.code is code
        assert str(error) == error.code.value
        return
    raise AssertionError("fixed actual guard accepted")


def physical_case(case, root, latch, facts, request):
    assert type(request) is dict
    assert request.keys() == {"instance", "projection"} | PHYSICAL_CASES[case]
    instance = LocalId(request["instance"])
    projection = ProjectionId(request["projection"])
    runtime = _runtime(facts)
    views._PROVIDER_TYPES = (FixedReadProvider,)
    views._QUALIFIED_RUNTIMES = (runtime,)
    provider = FixedReadProvider(latch, root, instance=instance)
    provider.seal = views._issue_read_seal(provider, runtime)
    mode = (
        views.ViewMode.LIVE_WAL
        if case == "live_schema_revision"
        else views.ViewMode.STOPPED_CLEAN
    )
    lease = views._issue_read_lease(provider.seal, mode)

    def live_artifacts():
        return {
            name: (path.stat().st_ino, path.read_bytes())
            for name in ("metadata.db", "metadata.db-wal", "metadata.db-shm")
            for path in (Path(root) / name,)
        }

    live_before = live_artifacts() if case == "live_schema_revision" else None
    connection, permit = provider.open_bound(lease)
    if case == "read_attach_failure":
        variant = request["variant"]
        assert variant in {
            "foreign",
            "single_owner",
            "late_loss",
            "instance",
            "schema",
            "sql",
            "allocation",
        }
        trace = []
        connection.set_trace_callback(trace.append)
        if variant == "foreign":
            _expect_failure(
                lambda: _attach_view(
                    connection, instance, permit=object.__new__(views.ReadViewPermit)
                ),
                code=ErrorCode.OWNER_UNAVAILABLE,
            )
            assert trace == [] and not connection.in_transaction
            errors = []

            def foreign_creator():
                try:
                    _attach_view(connection, instance, permit=permit)
                except StorageFailure as error:
                    errors.append(error.code)

            thread = Thread(target=foreign_creator)
            thread.start()
            thread.join(2)
            assert not thread.is_alive() and errors == [ErrorCode.OWNER_UNAVAILABLE]
            assert trace == [] and not provider.seal.invalidated
        elif variant in {"single_owner", "late_loss"}:
            # The paired assertions below need the first, successful attachment.
            pass
        elif variant == "instance":
            # Genuine bound ownership, but mismatching expected identity, must
            # close rather than leave the adopted source handle alive.
            wrong = LocalId("00000000000040008000000000000063")
            _expect_failure(lambda: _attach_view(connection, wrong, permit=permit))
        elif variant == "allocation":
            original = sessions._Session.__init__

            def failed_allocation(*args):
                assert permit.phase == "attached"
                assert provider.inventory[connection] == (lease, "claimed")
                raise MemoryError("SYNTHETIC_PRIVATE_ALLOCATION_EXCEPTION")

            sessions._Session.__init__ = failed_allocation
            try:
                _expect_failure(
                    lambda: _attach_view(connection, instance, permit=permit),
                    code=ErrorCode.PERSISTENCE_FAILURE,
                )
            finally:
                sessions._Session.__init__ = original
        else:
            action = (
                sqlite3.SQLITE_READ if variant == "schema" else sqlite3.SQLITE_PRAGMA
            )
            connection.set_authorizer(
                lambda current, *args: (
                    sqlite3.SQLITE_DENY if current == action else sqlite3.SQLITE_OK
                )
            )
            _expect_failure(lambda: _attach_view(connection, instance, permit=permit))
        if variant not in {"foreign", "single_owner", "late_loss"}:
            assert not provider.resources and not provider.inventory
            assert provider.events[-2:] == ["retired", "released"]
            return {"status": "ok", "result": {"ordered_cleanup": True}}
    reader = _attach_view(connection, instance, permit=permit)
    try:
        if case == "read_attach_failure" and request["variant"] == "single_owner":
            trace.clear()
            inventory, resources, events = (
                provider.inventory.copy(),
                provider.resources.copy(),
                tuple(provider.events),
            )
            for duplicate in (
                lambda: ReadSession(connection, instance, permit),
                lambda: ReadSession.__init__(reader, connection, instance, permit),
                lambda: _attach_view(connection, instance, permit=permit),
                lambda: copy.copy(reader),
                lambda: copy.deepcopy(reader),
                lambda: pickle.dumps(reader),
            ):
                _expect_failure(duplicate, code=ErrorCode.OWNER_UNAVAILABLE)
                assert trace == []
                assert provider.inventory == inventory
                assert provider.resources == resources
                assert tuple(provider.events) == events
                assert permit.phase == "attached" and not reader._closed

            failures = []

            def other_owner():
                for function in (
                    lambda: reader._read("SELECT 1"),
                    lambda: _attach_view(connection, instance, permit=permit),
                ):
                    try:
                        function()
                    except StorageFailure as error:
                        failures.append(error.code)

            thread = Thread(target=other_owner)
            thread.start()
            thread.join(2)
            assert not thread.is_alive()
            assert failures == [ErrorCode.OWNER_UNAVAILABLE] * 2
            assert trace == [] and not reader._closed
            assert tuple(provider.events) == events
            assert provider.inventory == inventory and provider.resources == resources

            readfd, writefd = os.pipe()
            pid = os.fork()
            if pid == 0:
                os.close(readfd)
                try:
                    for function in (
                        lambda: reader._read("SELECT 1"),
                        lambda: _attach_view(connection, instance, permit=permit),
                    ):
                        _expect_failure(function, code=ErrorCode.OWNER_UNAVAILABLE)
                    assert trace == [] and tuple(provider.events) == events
                    assert provider.inventory == inventory
                    assert provider.resources == resources
                    os.write(writefd, b"ok")
                except Exception:
                    os.write(writefd, b"no")
                finally:
                    os._exit(0)
            os.close(writefd)
            try:
                assert select.select([readfd], [], [], 2)[0]
                assert os.read(readfd, 2) == b"ok"
                assert os.waitpid(pid, 0)[1] == 0
            finally:
                os.close(readfd)

            assert reader._read("SELECT 1") == ((1,),)
            assert provider.inventory == inventory and provider.resources == resources
            assert tuple(provider.events) == events
            reader.close()
            assert provider.events == list(events) + ["retired", "released"]
            assert permit.phase == "closed"
            _expect_failure(reader.close, code=ErrorCode.OWNER_UNAVAILABLE)
            assert provider.events == list(events) + ["retired", "released"]
        elif case == "read_attach_failure" and request["variant"] == "late_loss":
            # A real inode metadata change invalidates the acquired OS identity;
            # only the actual holder may then close its own admitted resources.
            path = Path(root) / "metadata.db"
            before = (path.stat().st_ino, path.read_bytes())
            path.chmod(0o400)
            trace.clear()
            try:
                _expect_failure(
                    lambda: reader._read("SELECT 1"),
                    code=ErrorCode.OWNER_UNAVAILABLE,
                )
            finally:
                path.chmod(0o600)
            assert trace == [] and reader._closed and provider.seal.invalidated
            assert permit.phase == "closed"
            assert not provider.inventory and not provider.resources
            assert provider.events[-2:] == ["retired", "released"]
            assert (path.stat().st_ino, path.read_bytes()) == before
            after = tuple(provider.events)
            _expect_failure(reader.close, code=ErrorCode.OWNER_UNAVAILABLE)
            assert tuple(provider.events) == after
        elif case == "guard_history_types":
            variant = request["variant"]
            assert variant in {"view", "projection", "poll", "ordinal", "zero"}

            class Trap:
                @property
                def value(self):
                    raise AssertionError("foreign property executed")

            arguments = [
                reader,
                projection,
                LocalId("000000000000400080000000000003e8"),
                Count(1),
            ]
            if variant == "zero":
                arguments[3] = Count(0)
            else:
                arguments[
                    {"view": 0, "projection": 1, "poll": 2, "ordinal": 3}[variant]
                ] = Trap()
            _expect_failure(
                lambda: reads.get_history_page(*arguments), code=ErrorCode.INVALID_INPUT
            )
            if variant not in {"ordinal", "zero"}:
                _expect_failure(
                    lambda: reads.get_history_poll(*arguments[:3]),
                    code=ErrorCode.INVALID_INPUT,
                )
            reads.get_history_poll(
                reader, projection, LocalId("000000000000400080000000000003e8")
            )
        elif case == "guard_history_lifetime":
            id = LocalId("000000000000400080000000000003e8")
            before = reads.get_history_poll(reader, projection, id)
            failures = []

            def other():
                for function in (
                    lambda: reads.get_history_poll(reader, projection, id),
                    lambda: reads.get_history_page(reader, projection, id, Count(1)),
                ):
                    try:
                        function()
                    except StorageFailure as error:
                        failures.append(error.code)

            thread = Thread(target=other)
            thread.start()
            thread.join(2)
            assert (
                not thread.is_alive() and failures == [ErrorCode.OWNER_UNAVAILABLE] * 2
            )
            assert reads.get_history_poll(reader, projection, id) == before
            reader.close()
            _expect_failure(
                lambda: reads.get_history_poll(reader, projection, id),
                code=ErrorCode.OWNER_UNAVAILABLE,
            )
            _expect_failure(
                lambda: reads.get_history_page(reader, projection, id, Count(1)),
                code=ErrorCode.OWNER_UNAVAILABLE,
            )
        elif case == "guard_thread_reads":
            source, target = (
                ProviderId(request["source"]),
                ProviderId(request["target"]),
            )
            assert (
                reads.get_thread_anchor(
                    reader, ProjectionId("missing-projection"), source
                )
                is None
            )
            for first, second in (("thread", target), (source, "target")):
                _expect_failure(
                    lambda first=first, second=second: reads.get_thread_target(
                        reader, projection, first, second
                    ),
                    code=ErrorCode.INVALID_INPUT,
                )
            before = reads.get_thread_anchor(reader, projection, source)
            failures = []

            def other_thread():
                try:
                    reads.get_thread_anchor(reader, projection, source)
                except StorageFailure as error:
                    failures.append(error.code)

            thread = Thread(target=other_thread)
            thread.start()
            thread.join(2)
            assert not thread.is_alive() and failures == [ErrorCode.OWNER_UNAVAILABLE]
            assert reads.get_thread_anchor(reader, projection, source) == before
            reader.close()
            _expect_failure(
                lambda: reads.get_thread_target(reader, projection, source, target),
                code=ErrorCode.OWNER_UNAVAILABLE,
            )
        elif case == "guard_binding_role":
            _expect_failure(
                lambda: reads.get_binding(reader, projection, "source"),
                code=ErrorCode.INVALID_INPUT,
            )
            assert reads.get_binding(reader, projection, Role.SOURCE) is not None
        elif case == "read_zero_write":
            id, ordinal = LocalId(request["id"]), Count(request["ordinal"])
            before = connection.total_changes
            assert (
                reads.get_history_poll(reader, projection, id).projection_id
                == projection
            )
            assert reads.get_history_page(reader, projection, id, ordinal) is not None
            assert (
                reads.get_history_poll(
                    reader, projection, LocalId("0000000000004000800000000000270f")
                )
                is None
            )
            assert reads.get_history_page(reader, projection, id, Count(2)) is None
            foreign = ProjectionId("foreign-projection")
            assert reads.get_history_poll(reader, foreign, id) is None
            assert reads.get_history_page(reader, foreign, id, ordinal) is None
            assert connection.total_changes == before and not connection.in_transaction
        elif case == "keyset_501":
            first = reads.list_jobs(reader, projection, PageLimit(500), None)
            assert len(first.items) == 500 and first.next_key is not None
            assert not connection.in_transaction
            second = reads.list_jobs(reader, projection, PageLimit(500), first.next_key)
            assert len(second.items) == 1 and second.next_key is None
            assert not connection.in_transaction
            assert connection.execute("PRAGMA query_only").fetchone() == (1,)
        elif case == "guard_read_cursor":
            from facet.db.keys import _frame, _read_key

            for raw in (
                b"",
                b"private",
                b"x" * 8193,
                _frame(("read.unregistered", projection.value, "0", instance.value)),
            ):
                for function in (
                    reads.list_jobs,
                    reads.list_attempts,
                    reads.list_events,
                    reads.list_audit,
                ):
                    _expect_failure(
                        lambda function=function, raw=raw: function(
                            reader, projection, PageLimit(2), raw
                        ),
                        code=ErrorCode.INVALID_INPUT,
                    )
            raw = _read_key("sync_jobs", projection, 0, instance)
            _expect_failure(
                lambda: reads.list_audit(reader, projection, PageLimit(2), raw),
                code=ErrorCode.INVALID_INPUT,
            )
            _expect_failure(
                lambda: reads.list_jobs(
                    reader, ProjectionId("other"), PageLimit(2), raw
                ),
                code=ErrorCode.INVALID_INPUT,
            )
            reads.get_projection(reader, projection)
        elif case == "read_step_fault":
            fail_row = request["row"]
            assert type(fail_row) is int and fail_row in {2, 3}
            called = []

            def step(value):
                called.append(value)
                if value == fail_row:
                    raise ValueError("SYNTHETIC_PRIVATE_FETCH_EXCEPTION")
                return value

            connection.create_function("test_only_fetch_fault", 1, step)
            _expect_failure(
                lambda: reader._read(
                    "SELECT test_only_fetch_fault(v) FROM "
                    "(SELECT 1 AS v UNION ALL SELECT 2 UNION ALL SELECT 3)"
                ),
                code=ErrorCode.PERSISTENCE_FAILURE,
            )
            assert (
                called == list(range(1, fail_row + 1)) and not connection.in_transaction
            )
            assert reader._read("SELECT 1") == ((1,),)
        elif case == "snapshot_reject_read_source":
            trace = []
            connection.set_trace_callback(trace.append)
            _expect_failure(
                lambda: snapshot_database(reader, connection),
                code=ErrorCode.INVALID_INPUT,
            )
            assert trace == []
            assert reader._read("SELECT 1") == ((1,),)
        elif case == "live_schema_revision":
            assert reader._read("SELECT config_revision FROM projections") == ((0,),)
            assert not connection.in_transaction
            assert live_artifacts() == live_before
            peer = provider.resources[lease]["peer"]
            peer.sendall(b"commit")
            assert peer.recv(9) == b"committed"
            live_committed = live_artifacts()
            assert reader._read("SELECT config_revision FROM projections") == ((1,),)
            assert not connection.in_transaction
            _expect_failure(
                lambda: reader._read("UPDATE projections SET config_revision=2")
            )
            assert reader._read("SELECT config_revision FROM projections") == ((1,),)
            assert live_artifacts() == live_committed
            reader.close()
            assert live_artifacts() == live_committed
        # read_attach_failure / foreign rejection rejoins here after proving the
        # fresh actual owner was untouched and attaches its real permit.
        return {"status": "ok", "result": {"actual_child_assertions": True}}
    finally:
        if not reader._closed:
            reader.close()
        assert not provider.inventory and not provider.resources


def _read_request(case, request):
    function, table, selectors = GETTERS[case]
    fields = {"instance", "projection"} | {name for name, _ in selectors}
    if case.startswith("page_"):
        fields.add("cursor")
    if case == "counts":
        fields.add("epoch")
    if type(request) is not dict or request.keys() != fields:
        refuse()
    instance = LocalId(request["instance"])
    projection = ProjectionId(request["projection"])
    arguments = tuple(cls(request[name]) for name, cls in selectors)
    if case.startswith("page_"):
        cursor = request["cursor"]
        if cursor is not None:
            if type(cursor) is not str or len(cursor) > 16384:
                refuse()
            cursor = bytes.fromhex(cursor)
        arguments += (cursor,)
    elif case == "counts":
        arguments += (
            LocalId(request["epoch"]) if request["epoch"] is not None else None,
        )
    return instance, projection, function, table, arguments


def packed_row(table, row):
    if row is None:
        return None
    cells = _encode_row(table, row)
    result = []
    for cell in cells:
        if cell is None or type(cell) in {bool, int, str}:
            result.append(cell)
        elif type(cell) is bytes and len(cell) <= 8192:
            result.append({"hex": cell.hex()})
        else:
            raise AssertionError("nonfinite test materialization")
    return result


def getter_case(case, root, latch, facts, request):
    instance, projection, function, table, arguments = _read_request(case, request)
    runtime = _runtime(facts)
    views._PROVIDER_TYPES = (FixedReadProvider,)
    views._QUALIFIED_RUNTIMES = (runtime,)
    provider = FixedReadProvider(latch, root, instance=instance)
    provider.seal = views._issue_read_seal(provider, runtime)
    lease = views._issue_read_lease(provider.seal, views.ViewMode.STOPPED_CLEAN)
    connection, permit = provider.open_bound(lease)
    reader = _attach_view(connection, instance, permit=permit)
    before = connection.total_changes
    try:
        value = function(reader, projection, *arguments)
        assert connection.total_changes == before and not connection.in_transaction
        assert connection.execute("PRAGMA query_only").fetchone() == (1,)
        if case.startswith("page_"):
            assert len(value.items) <= min(arguments[0].value, 500)
            result = {
                "items": [
                    pack_job(row) if case == "page_jobs" else packed_row(table, row)
                    for row in value.items
                ],
                "next": value.next_key.hex() if value.next_key is not None else None,
            }
        elif case == "schema":
            assert len(value[1]) <= 500
            result = {
                "metadata": packed_row("schema_metadata", value[0]),
                "ledger": [packed_row("schema_migrations", row) for row in value[1]],
            }
        elif case == "counts":
            assert tuple(row.state for row in value.by_job_state) == tuple(JobState)
            result = {
                "confirmed": value.confirmed_mappings.value,
                "states": [
                    [row.state.value, row.count.value] for row in value.by_job_state
                ],
                "uncertain": value.unresolved_attempts.value,
                "complete": value.discovery_complete,
                "total": value.known_total.value
                if value.known_total is not None
                else None,
            }
        elif case == "row_job":
            result = pack_job(value) if value is not None else None
        else:
            result = packed_row(table, value)
        return {"status": "ok", "result": result}
    except StorageFailure as error:
        return {"status": error.code.value}
    finally:
        reader.close()
        assert not provider.inventory and not provider.resources


def run_case(case, root, latch, facts):
    runtime = _runtime(facts)
    views._PROVIDER_TYPES = (FixedReadProvider,)
    views._QUALIFIED_RUNTIMES = (runtime,)
    provider = FixedReadProvider(latch, root)
    if case == "altered_runtime":
        runtime = replace(runtime, sqlite_source_id="altered-synthetic-facts")
        views._QUALIFIED_RUNTIMES = (runtime,)
    try:
        provider.seal = views._issue_read_seal(provider, runtime)
        if case == "extra_memory":
            sqlite3.connect(":memory:", autocommit=True)
        if case == "reuse_claim":
            latch.claim(provider, runtime)
        if case in {
            "invalid_identities",
            "invalid_claim_return",
            "uncertain_retirement",
        }:
            provider.fault = case
        mode = (
            views.ViewMode.LIVE_WAL
            if case.startswith("live_")
            else views.ViewMode.STOPPED_CLEAN
        )
        lease = views._issue_read_lease(provider.seal, mode)
        if case == "allocation_failure":
            original = views._allocate

            def allocate(cls, **values):
                if cls is views.ReadViewPermit:
                    raise MemoryError("synthetic-private-error")
                return original(cls, **values)

            views._allocate = allocate
        connection, permit = provider.open_bound(lease)
        views._consume_permit(permit, connection, INSTANCE)
        views._check_permit(permit)
        if case == "foreign_thread":
            rejected = []

            def foreign():
                try:
                    views._check_permit(permit)
                except StorageFailure as error:
                    rejected.append(error.code)

            thread = Thread(target=foreign)
            thread.start()
            thread.join(timeout=2)
            assert not thread.is_alive()
            assert rejected == [ErrorCode.OWNER_UNAVAILABLE]
            views._check_permit(permit)
        if case == "inherited_fork":
            readfd, writefd = os.pipe()
            pid = os.fork()
            if pid == 0:
                os.close(readfd)
                try:
                    views._check_permit(permit)
                except StorageFailure as error:
                    os.write(
                        writefd,
                        b"ok" if error.code is ErrorCode.OWNER_UNAVAILABLE else b"no",
                    )
                os._exit(0)
            os.close(writefd)
            try:
                assert os.read(readfd, 2) == b"ok"
                assert os.waitpid(pid, 0)[1] == 0
            finally:
                os.close(readfd)
            views._check_permit(permit)
        # This fixed query is only an admission/OS diagnostic, not a claimed
        # substitute for the later actual ReadSession/repository test matrix.
        rows = connection.execute("SELECT count(*) FROM synthetic").fetchone()[0]
        views._check_permit(permit)
        if case == "double_attach":
            try:
                views._consume_permit(permit, connection, INSTANCE)
            except StorageFailure:
                pass
            else:
                raise AssertionError("second attachment accepted")
        if case == "live_two_readers":
            other_lease = views._issue_read_lease(provider.seal, mode)
            other, other_permit = provider.open_bound(other_lease)
            views._consume_permit(other_permit, other, INSTANCE)
            assert other.execute("SELECT count(*) FROM synthetic").fetchone()[0] == rows
            views._close_permit(other_permit)
            views._check_permit(permit)
        views._close_permit(permit)
        assert not provider.resources and not provider.inventory
        return {"status": "ok", "rows": rows, "events": provider.events}
    except StorageFailure as error:
        if case in {"invalid_identities", "invalid_claim_return", "allocation_failure"}:
            assert not provider.resources and not provider.inventory
            assert _lock_available(root, "owner.lock")
            assert _lock_available(root, "view.lock")
            assert provider.events[-1] == "released"
        if case == "uncertain_retirement":
            assert provider.seal.invalidated
            assert provider.resources and provider.inventory
            assert not _lock_available(root, "owner.lock")
        return {"status": error.code.value, "events": provider.events}
