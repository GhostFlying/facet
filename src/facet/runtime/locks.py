"""Nonblocking stable owner/view/key flock leases with no descriptor export."""

import errno
import fcntl
import os
import threading
from dataclasses import dataclass
from enum import StrEnum

from facet.contracts import ErrorCode, LocalId
from facet.runtime import private_root as _roots

__all__ = (
    "LockMode",
    "LockLease",
    "acquire_owner",
    "acquire_view",
    "acquire_key",
    "check_lock",
    "release_lock",
)


class LockMode(StrEnum):
    SHARED = "shared"
    EXCLUSIVE = "exclusive"


class LockLease:
    """Only an enrolled, retained kernel lock is an ownership proof."""

    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        _roots._fail(ErrorCode.INVALID_INPUT)

    def __init_subclass__(cls, **kwargs):
        _roots._fail(ErrorCode.INVALID_INPUT)

    def __repr__(self):
        return "<held lock lease>"

    __str__ = __repr__

    def __reduce_ex__(self, protocol):
        _roots._fail(ErrorCode.INVALID_INPUT)

    @_roots._boundary
    def __enter__(self):
        with _roots._MUTEX:
            state = _lease(self)
            _check(state)
            if state.entered:
                raise _roots._Fault(ErrorCode.OWNER_BUSY)
            state.entered = True
        return self

    def __exit__(self, exception_type, exception, traceback):
        release_lock(self)
        return False


@dataclass(slots=True)
class _LeaseState:
    root: _roots.HeldPrivateRoot
    pid: int
    thread: threading.Thread
    kind: str
    mode: LockMode
    node: _roots._Node
    parent: LockLease | None
    key: tuple[LocalId, LocalId] | None
    phase: str = "held"
    entered: bool = False


def _lease(lease):
    if type(lease) is not LockLease:
        raise _roots._Fault(ErrorCode.INVALID_INPUT)
    state = _roots._LEASES.get(lease)
    if state is None:
        raise _roots._Fault(ErrorCode.OWNER_UNAVAILABLE)
    _roots._creator(state)
    return state


def _check(state):
    if state.phase != "held":
        raise _roots._Fault(ErrorCode.OWNER_UNAVAILABLE)
    root = _roots._root(state.root)
    try:
        _roots._check_root(root)
        if state.parent is not None:
            parent = _lease(state.parent)
            if parent.root is not state.root:
                raise _roots._Fault(ErrorCode.OWNER_UNAVAILABLE)
            _check(parent)
        _roots._check_node(state.node)
        identity = state.node.descriptor.identity
        if _roots._INODES.get((identity.device, identity.inode)) is not state:
            raise _roots._Fault(ErrorCode.OWNER_UNAVAILABLE)
    except (_roots._Fault, OSError):
        state.phase = "invalid"
        root.phase = "invalid"
        raise


def _parent(root, lease, kind):
    state = _lease(lease)
    if state.root is not root or state.kind != kind:
        raise _roots._Fault(ErrorCode.INVALID_INPUT)
    _check(state)
    return state


def _kinds(state):
    return {_roots._LEASES[lease].kind for lease in state.leases}


def _acquire(root, kind, mode, parent, name, key=None, create=False):
    state = _roots._root(root)
    _roots._check_root(state)
    directory = state.directories["keys" if kind == "key" else "locks"]
    descriptor = None
    created = False
    try:
        if create:
            try:
                descriptor = _roots._open(name, parent=directory.number, create=True)
                created = True
            except OSError as error:
                if error.errno != errno.EEXIST:
                    raise _roots._Fault(ErrorCode.PERSISTENCE_FAILURE) from None
        if descriptor is None:
            try:
                descriptor = _roots._open(name, parent=directory.number)
            except OSError as error:
                raise _roots._Fault(_roots._open_error(error)) from None
        node = _roots._Node(descriptor, directory, name, "file")
        _roots._check_node(node)
        if created:
            _roots._sync(descriptor)
            _roots._sync(directory)
            _roots._check_root(state)
            _roots._check_node(node)
        identity = descriptor.identity
        if (identity.device, identity.inode) in _roots._INODES:
            raise _roots._Fault(ErrorCode.OWNER_BUSY)
        operation = fcntl.LOCK_SH if mode is LockMode.SHARED else fcntl.LOCK_EX
        try:
            fcntl.flock(descriptor.number, operation | fcntl.LOCK_NB)
        except OSError as error:
            code = (
                ErrorCode.OWNER_BUSY
                if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK)
                else ErrorCode.OWNER_UNAVAILABLE
            )
            if code is not ErrorCode.OWNER_BUSY:
                state.phase = "invalid"
            raise _roots._Fault(code) from None
        _roots._check_root(state)
        _roots._check_node(node)
        if parent is not None:
            _check(_lease(parent))
        lease = object.__new__(LockLease)
        leased = _LeaseState(
            root, os.getpid(), threading.current_thread(), kind, mode, node, parent, key
        )
        _roots._LEASES[lease] = leased
        _roots._INODES[(identity.device, identity.inode)] = leased
        state.leases.add(lease)
        return lease
    except BaseException as error:
        if descriptor is not None and not (
            type(error) is _roots._Fault and error.code is ErrorCode.OWNER_BUSY
        ):
            state.phase = "invalid"
        if descriptor is not None:
            _roots._dispose([descriptor])
        raise


@_roots._boundary
def acquire_owner(root: _roots.HeldPrivateRoot) -> LockLease:
    with _roots._MUTEX:
        state = _roots._root(root)
        _roots._check_root(state)
        if state.leases:
            raise _roots._Fault(ErrorCode.OWNER_BUSY)
        return _acquire(root, "owner", LockMode.EXCLUSIVE, None, "owner.lock")


@_roots._boundary
def acquire_view(
    root: _roots.HeldPrivateRoot,
    mode: LockMode,
    *,
    owner: LockLease | None = None,
) -> LockLease:
    if type(mode) is not LockMode:
        raise _roots._Fault(ErrorCode.INVALID_INPUT)
    with _roots._MUTEX:
        state = _roots._root(root)
        _roots._check_root(state)
        if _kinds(state) & {"view", "key"}:
            raise _roots._Fault(ErrorCode.OWNER_BUSY)
        if owner is not None:
            _parent(root, owner, "owner")
        elif mode is LockMode.EXCLUSIVE:
            raise _roots._Fault(ErrorCode.INVALID_INPUT)
        return _acquire(root, "view", mode, owner, "view.lock")


def _local_id(value):
    if type(value) is not LocalId:
        raise _roots._Fault(ErrorCode.INVALID_INPUT)
    try:
        LocalId(value.value)
    except (AttributeError, ValueError, TypeError):
        raise _roots._Fault(ErrorCode.INVALID_INPUT) from None
    return value.value


@_roots._boundary
def acquire_key(
    root: _roots.HeldPrivateRoot,
    namespace: LocalId,
    nonce: LocalId,
    *,
    view: LockLease,
    create: bool = False,
) -> LockLease:
    namespace_text = _local_id(namespace)
    nonce_text = _local_id(nonce)
    if type(create) is not bool:
        raise _roots._Fault(ErrorCode.INVALID_INPUT)
    with _roots._MUTEX:
        state = _roots._root(root)
        _roots._check_root(state)
        _parent(root, view, "view")
        if "key" in _kinds(state):
            raise _roots._Fault(ErrorCode.OWNER_BUSY)
        name = f"rq1_{namespace_text}_{nonce_text}.lock"
        return _acquire(
            root,
            "key",
            LockMode.EXCLUSIVE,
            view,
            name,
            (namespace, nonce),
            create,
        )


@_roots._boundary
def check_lock(lease: LockLease) -> None:
    with _roots._MUTEX:
        _check(_lease(lease))


@_roots._boundary
def release_lock(lease: LockLease) -> None:
    with _roots._MUTEX:
        state = _lease(lease)
        if state.phase == "released":
            return
        root = _roots._root(state.root)
        others = [_roots._LEASES[item] for item in root.leases if item is not lease]
        if any(item.parent is lease for item in others) or (
            state.kind == "owner" and others
        ):
            raise _roots._Fault(ErrorCode.OWNER_BUSY)
        descriptor = state.node.descriptor
        identity = descriptor.identity
        # Remove authority on every close outcome; an uncertain integer is never
        # retained for cleanup and can never unlock a later unrelated descriptor.
        state.phase = "released"
        root.leases.discard(lease)
        if _roots._INODES.get((identity.device, identity.inode)) is state:
            del _roots._INODES[(identity.device, identity.inode)]
        try:
            _roots._close(descriptor)
        except (_roots._Fault, OSError):
            root.phase = "invalid"
            raise
