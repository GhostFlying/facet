"""Fixed isolated test producer, excluded from the Facet package/wheel.

This owns actual descriptors, advisory locks, peer lifetime and every SQLite
handle in its fresh reader. It is not a capability mock or a product opener.
"""

import fcntl
import hashlib
import os
import select
import socket
import sqlite3
import stat
import struct
import sys
from dataclasses import replace
from pathlib import Path
from threading import Thread, current_thread

from facet.contracts import ErrorCode, LocalId, Sha256Hex
from facet.db import read_views as views
from facet.db.codecs import StorageFailure

INSTANCE = LocalId("00000000000040008000000000000001")

if sys.argv[1] == "import_open":
    # Deliberately forbidden import-time open in the fixed negative fixture.
    sqlite3.connect(":memory:", autocommit=True)


def refuse():
    raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)


class FixedReadProvider:
    def __init__(self, latch, root, *, fault=None):
        self.latch = latch
        self.root = Path(root)
        self.seal = None
        self.resources = {}
        self.inventory = {}
        self.opening = None
        self.events = []
        self.fault = fault
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
            permit = views._bind_read_view(connection, INSTANCE, lease, self.seal)
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
