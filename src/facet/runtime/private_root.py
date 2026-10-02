"""Finite Linux private-root resources, not initialized state or DB authority."""

import errno
import os
import stat
import sys
import threading
from dataclasses import dataclass, field
from functools import wraps

from facet.contracts import ErrorCode

__all__ = (
    "LockFailure",
    "HeldPrivateRoot",
    "open_existing_root",
    "create_lock_root",
    "check_root",
    "close_root",
)


class LockFailure(Exception):
    """A fixed failure code; callers must never format native tracebacks."""

    def __init__(self, code: ErrorCode = ErrorCode.INVALID_INPUT):
        if type(code) is not ErrorCode or code not in _CODES:
            code = ErrorCode.INVALID_INPUT
        self.code = code
        super().__init__("lock_failure")

    def __str__(self):
        return "lock_failure"

    def __repr__(self):
        return "LockFailure('lock_failure')"


_CODES = frozenset(
    (
        ErrorCode.INVALID_INPUT,
        ErrorCode.SCOPE_REQUIRED,
        ErrorCode.OWNER_UNAVAILABLE,
        ErrorCode.OWNER_BUSY,
        ErrorCode.PERSISTENCE_FAILURE,
    )
)


def _fail(code):
    # A caller may itself be inside an except block. Clear Python's implicit
    # context after the initial raise, then bare-reraise the same safe exception.
    try:
        raise LockFailure(code) from None
    except LockFailure as error:
        error.__context__ = None
        error.__cause__ = None
        raise


class _Fault(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("lock_failure")


def _boundary(function):
    @wraps(function)
    def controlled(*args, **kwargs):
        code = ErrorCode.OWNER_UNAVAILABLE
        try:
            return function(*args, **kwargs)
        except _Fault as error:
            code = error.code
        except OSError:
            pass
        _fail(code)

    return controlled


class HeldPrivateRoot:
    """Identity-enrolled resource; construction or copying grants nothing."""

    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        _fail(ErrorCode.INVALID_INPUT)

    def __init_subclass__(cls, **kwargs):
        _fail(ErrorCode.INVALID_INPUT)

    def __repr__(self):
        return "<held private root>"

    __str__ = __repr__

    def __reduce_ex__(self, protocol):
        _fail(ErrorCode.INVALID_INPUT)

    @_boundary
    def __enter__(self):
        with _MUTEX:
            state = _root(self)
            _check_root(state)
            if state.entered:
                raise _Fault(ErrorCode.OWNER_BUSY)
            state.entered = True
        return self

    def __exit__(self, exception_type, exception, traceback):
        close_root(self)
        return False


@dataclass(frozen=True, slots=True)
class _Identity:
    device: int
    inode: int
    uid: int
    mode: int


@dataclass(slots=True)
class _Descriptor:
    number: int
    identity: _Identity


@dataclass(slots=True)
class _Node:
    descriptor: _Descriptor
    parent: _Descriptor | None
    name: str
    policy: str


@dataclass(slots=True)
class _RootState:
    path: str
    pid: int
    thread: threading.Thread
    nodes: list[_Node] = field(default_factory=list)
    directories: dict[str, _Descriptor] = field(default_factory=dict)
    leases: set = field(default_factory=set)
    phase: str = "open"
    entered: bool = False


# These strong registries are private resource ownership, not caller assertions.
# Only the fixed factories enroll objects. No finalizer or atexit unlocks them.
_ROOTS: dict[HeldPrivateRoot, _RootState] = {}
_LEASES: dict = {}
_INODES: dict[tuple[int, int], object] = {}
_DESCRIPTORS: dict[int, _Descriptor] = {}
_MUTEX = threading.RLock()
_IMPORT_PID = os.getpid()
_HOOKS_INSTALLED = False
_FORKED = False


def _identity(info):
    return _Identity(info.st_dev, info.st_ino, info.st_uid, info.st_mode)


def _same_inode(info, descriptor):
    saved = descriptor.identity
    return (info.st_dev, info.st_ino) == (saved.device, saved.inode)


def _policy(info, policy):
    mode = stat.S_IMODE(info.st_mode)
    if policy == "ancestor":
        safe = (
            stat.S_ISDIR(info.st_mode)
            and info.st_uid in (0, os.geteuid())
            and not mode & 0o7022
        )
    elif policy == "directory":
        safe = (
            stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and mode == 0o700
        )
    else:
        safe = (
            stat.S_ISREG(info.st_mode)
            and info.st_uid == os.geteuid()
            and mode == 0o600
            and info.st_nlink == 1
            and info.st_size == 0
        )
    if not safe:
        raise _Fault(ErrorCode.SCOPE_REQUIRED)


def _before_fork():
    _MUTEX.acquire()


def _after_fork_parent():
    _MUTEX.release()


def _after_fork_child():
    global _FORKED
    _FORKED = True
    # Closing a fork copy does not LOCK_UN the parent's open-file description.
    # Never retry a failed close, nor close an integer whose inode was reused.
    for descriptor in tuple(_DESCRIPTORS.values()):
        try:
            if _same_inode(os.fstat(descriptor.number), descriptor):
                os.close(descriptor.number)
        except OSError:
            pass
    _DESCRIPTORS.clear()
    _INODES.clear()
    for state in _ROOTS.values():
        state.phase = "invalid"
    for state in _LEASES.values():
        state.phase = "invalid"
    _MUTEX.release()


def _factory_guard():
    global _HOOKS_INSTALLED
    if _FORKED or os.getpid() != _IMPORT_PID or sys.platform != "linux":
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE)
    required = (
        "O_DIRECTORY",
        "O_NOFOLLOW",
        "O_CLOEXEC",
        "O_NONBLOCK",
        "register_at_fork",
    )
    if any(not hasattr(os, name) for name in required):
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE)
    if not _HOOKS_INSTALLED:
        os.register_at_fork(
            before=_before_fork,
            after_in_parent=_after_fork_parent,
            after_in_child=_after_fork_child,
        )
        _HOOKS_INSTALLED = True


def _path_parts(path):
    if type(path) is not str or len(path) > 4096:
        raise _Fault(ErrorCode.INVALID_INPUT)
    try:
        encoded = path.encode("utf-8")
    except UnicodeError:
        raise _Fault(ErrorCode.INVALID_INPUT) from None
    parts = path.split("/")[1:]
    if (
        not path.startswith("/")
        or path == "/"
        or "\x00" in path
        or len(encoded) > 4096
        or len(parts) > 256
        or any(part in ("", ".", "..") for part in parts)
        or any(len(part.encode("utf-8")) > 255 for part in parts)
    ):
        raise _Fault(ErrorCode.INVALID_INPUT)
    if ".facet-spike" in parts:
        raise _Fault(ErrorCode.SCOPE_REQUIRED)
    return parts


def _open(name, *, parent=None, directory=False, create=False):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    if directory:
        flags |= os.O_DIRECTORY
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    number = os.open(name, flags, 0o600, dir_fd=parent)
    # Mutex covers the open-to-inventory interval, including failed fstat cleanup.
    try:
        descriptor = _Descriptor(number, _identity(os.fstat(number)))
    except BaseException:
        try:
            os.close(number)
        except OSError:
            raise _Fault(ErrorCode.PERSISTENCE_FAILURE) from None
        raise
    _DESCRIPTORS[number] = descriptor
    return descriptor


def _close(descriptor):
    number = descriptor.number
    if _DESCRIPTORS.get(number) is not descriptor:
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE)
    # Forget before close: close(EINTR/EIO) cannot safely be retried by integer.
    del _DESCRIPTORS[number]
    try:
        info = os.fstat(number)
    except OSError:
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE) from None
    if not _same_inode(info, descriptor):
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE)
    try:
        os.close(number)
    except OSError:
        raise _Fault(ErrorCode.PERSISTENCE_FAILURE) from None


def _dispose(descriptors):
    failure = None
    for descriptor in reversed(descriptors):
        if _DESCRIPTORS.get(descriptor.number) is descriptor:
            try:
                _close(descriptor)
            except _Fault as error:
                if failure is not ErrorCode.PERSISTENCE_FAILURE:
                    failure = error.code
    if failure is not None:
        raise _Fault(failure)


def _open_error(error):
    if error.errno in (errno.ELOOP, errno.ENOTDIR):
        return ErrorCode.SCOPE_REQUIRED
    return ErrorCode.OWNER_UNAVAILABLE


def _node(state, parent, name, policy, *, optional=False):
    descriptor = None
    try:
        named = os.stat(
            name,
            dir_fd=parent.number if parent is not None else None,
            follow_symlinks=False,
        )
        _policy(named, policy)
        descriptor = _open(
            name,
            parent=parent.number if parent is not None else None,
            directory=policy != "file",
        )
    except OSError as error:
        if optional and error.errno == errno.ENOENT:
            return None
        raise _Fault(_open_error(error)) from None
    node = _Node(descriptor, parent, name, policy)
    state.nodes.append(node)
    _check_node(node)
    return descriptor


def _check_node(node):
    descriptor = node.descriptor
    if _DESCRIPTORS.get(descriptor.number) is not descriptor:
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE)
    try:
        current = os.fstat(descriptor.number)
        named = os.stat(
            node.name,
            dir_fd=node.parent.number if node.parent is not None else None,
            follow_symlinks=False,
        )
    except OSError:
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE) from None
    _policy(current, node.policy)
    _policy(named, node.policy)
    if _identity(current) != descriptor.identity or _identity(named) != _identity(
        current
    ):
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE)


def _check_nodes(state):
    # Parent-first order rewalks every retained lexical component from /.
    for node in state.nodes:
        _check_node(node)


def _creator(state):
    if (
        _FORKED
        or state.pid != os.getpid()
        or state.thread is not threading.current_thread()
    ):
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE)


def _root(root):
    if type(root) is not HeldPrivateRoot:
        raise _Fault(ErrorCode.INVALID_INPUT)
    state = _ROOTS.get(root)
    if state is None:
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE)
    _creator(state)
    return state


def _check_root(state):
    if state.phase != "open":
        raise _Fault(ErrorCode.OWNER_UNAVAILABLE)
    try:
        _check_nodes(state)
    except (_Fault, OSError):
        state.phase = "invalid"
        raise


_DIRECTORIES = (
    ("root", None, None),
    ("locks", "root", "locks"),
    ("requests", "root", "requests"),
    ("keys", "requests", "locks"),
)
_ALLOWED = {
    "root": frozenset(("locks", "requests")),
    "locks": frozenset(("owner.lock", "view.lock")),
    "requests": frozenset(("locks",)),
    "keys": frozenset(),
}


def _scaffold_entries(state):
    _check_nodes(state)
    for role, descriptor in state.directories.items():
        if (
            role in _ALLOWED
            and not set(os.listdir(descriptor.number)) <= _ALLOWED[role]
        ):
            raise _Fault(ErrorCode.SCOPE_REQUIRED)


def _sync(descriptor):
    try:
        os.fsync(descriptor.number)
    except OSError:
        raise _Fault(ErrorCode.PERSISTENCE_FAILURE) from None


def _make_directory(state, role, parent, name):
    _scaffold_entries(state)
    created = False
    try:
        os.mkdir(name, 0o700, dir_fd=parent.number)
        created = True
    except OSError as error:
        if error.errno != errno.EEXIST:
            raise _Fault(ErrorCode.PERSISTENCE_FAILURE) from None
    descriptor = _node(state, parent, name, "directory")
    state.directories[role] = descriptor
    _scaffold_entries(state)
    if created:
        _sync(descriptor)
        _sync(parent)


def _stable_file(state, name, *, create):
    parent = state.directories["locks"]
    descriptor = _node(state, parent, name, "file", optional=create)
    if descriptor is not None:
        return
    _scaffold_entries(state)
    created = False
    try:
        descriptor = _open(name, parent=parent.number, create=True)
        created = True
    except OSError as error:
        if error.errno != errno.EEXIST:
            raise _Fault(ErrorCode.PERSISTENCE_FAILURE) from None
        descriptor = _open(name, parent=parent.number)
    node = _Node(descriptor, parent, name, "file")
    state.nodes.append(node)
    _check_node(node)
    _scaffold_entries(state)
    if created:
        _sync(descriptor)
        _sync(parent)


def _build(path, create):
    parts = _path_parts(path)
    with _MUTEX:
        _factory_guard()
        state = _RootState(path, os.getpid(), threading.current_thread())
        try:
            parent = _node(state, None, "/", "ancestor")
            for part in parts[:-1]:
                parent = _node(state, parent, part, "ancestor")
            state.directories["parent"] = parent
            root = _node(state, parent, parts[-1], "directory", optional=create)
            if root is not None:
                state.directories["root"] = root
                for role, parent_role, name in _DIRECTORIES[1:]:
                    if parent_role in state.directories:
                        descriptor = _node(
                            state,
                            state.directories[parent_role],
                            name,
                            "directory",
                            optional=create,
                        )
                        if descriptor is not None:
                            state.directories[role] = descriptor
                if "locks" in state.directories:
                    # Preflight ALL existing files before publishing any entry.
                    for name in ("owner.lock", "view.lock"):
                        _node(
                            state,
                            state.directories["locks"],
                            name,
                            "file",
                            optional=create,
                        )
            if create:
                _scaffold_entries(state)
                for role, parent_role, name in _DIRECTORIES:
                    if role not in state.directories:
                        _make_directory(
                            state,
                            role,
                            state.directories[parent_role or "parent"],
                            name or parts[-1],
                        )
                for name in ("owner.lock", "view.lock"):
                    if not any(
                        node.name == name
                        and node.parent is state.directories["locks"]
                        and node.policy == "file"
                        for node in state.nodes
                    ):
                        _stable_file(state, name, create=True)
                _scaffold_entries(state)
            _check_nodes(state)
            held = object.__new__(HeldPrivateRoot)
            _ROOTS[held] = state
            return held
        except BaseException:
            _dispose([node.descriptor for node in state.nodes])
            raise


@_boundary
def open_existing_root(path: str) -> HeldPrivateRoot:
    """Open only the fixed existing lock infrastructure, with zero writes."""
    return _build(path, False)


@_boundary
def create_lock_root(path: str) -> HeldPrivateRoot:
    """Explicitly publish an empty safe scaffold, never initialized Facet state."""
    return _build(path, True)


@_boundary
def check_root(root: HeldPrivateRoot) -> None:
    with _MUTEX:
        _check_root(_root(root))


@_boundary
def close_root(root: HeldPrivateRoot) -> None:
    with _MUTEX:
        state = _root(root)
        if state.phase == "closed":
            return
        if state.leases:
            raise _Fault(ErrorCode.OWNER_BUSY)
        state.phase = "closed"
        _dispose([node.descriptor for node in state.nodes])
