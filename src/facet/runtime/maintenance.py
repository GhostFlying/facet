"""Cross-container advisory lock for foreground maintenance windows."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

MARKER_NAME = "reconcile.maintenance"
_held: dict[str, int] = {}


def marker_path(state_dir: str | os.PathLike[str]) -> Path:
    return Path(state_dir) / MARKER_NAME


def acquire_marker(state_dir: str | os.PathLike[str], run_id: str) -> Path:
    path = marker_path(state_dir)
    key = str(path)
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise RuntimeError("maintenance_active") from None
    marker_fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(marker_fd, "wb") as stream:
        stream.write(
            json.dumps(
                {"pid": os.getpid(), "run_id": run_id}, separators=(",", ":")
            ).encode("ascii")
        )
        stream.flush()
        os.fsync(stream.fileno())
    _held[key] = fd
    return path


def active(state_dir: str | os.PathLike[str]) -> bool:
    path = marker_path(state_dir)
    try:
        fd = os.open(str(path) + ".lock", os.O_RDWR)
    except FileNotFoundError:
        path.unlink(missing_ok=True)
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return True
    path.unlink(missing_ok=True)
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
    return False


def release(state_dir: str | os.PathLike[str]) -> None:
    path = marker_path(state_dir)
    fd = _held.pop(str(path), None)
    if fd is not None:
        path.unlink(missing_ok=True)
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
