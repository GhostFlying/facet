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
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise RuntimeError("maintenance_active") from None
    os.ftruncate(fd, 0)
    os.write(
        fd,
        json.dumps(
            {"pid": os.getpid(), "run_id": run_id}, separators=(",", ":")
        ).encode("ascii"),
    )
    os.fsync(fd)
    _held[key] = fd
    return path


def active(state_dir: str | os.PathLike[str]) -> bool:
    path = marker_path(state_dir)
    try:
        fd = os.open(path, os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return True
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
    path.unlink(missing_ok=True)
    return False


def release(state_dir: str | os.PathLike[str]) -> None:
    path = marker_path(state_dir)
    fd = _held.pop(str(path), None)
    if fd is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    path.unlink(missing_ok=True)
