"""Small owner-independent marker for foreground maintenance windows."""

from __future__ import annotations

import json
import os
from pathlib import Path

MARKER_NAME = "reconcile.maintenance"


def marker_path(state_dir: str | os.PathLike[str]) -> Path:
    return Path(state_dir) / MARKER_NAME


def acquire_marker(state_dir: str | os.PathLike[str], run_id: str) -> Path:
    path = marker_path(state_dir)
    payload = json.dumps(
        {"pid": os.getpid(), "run_id": run_id},
        separators=(",", ":"),
    ).encode("ascii")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if active(state_dir):
            raise RuntimeError("maintenance_active") from None
        path.unlink(missing_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
    return path


def active(state_dir: str | os.PathLike[str]) -> bool:
    path = marker_path(state_dir)
    try:
        data = json.loads(path.read_text(encoding="ascii"))
        pid = data.get("pid")
        if type(pid) is not int or pid <= 0:
            return True
        os.kill(pid, 0)
        return True
    except FileNotFoundError:
        return False
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return False


def release(state_dir: str | os.PathLike[str]) -> None:
    marker_path(state_dir).unlink(missing_ok=True)
