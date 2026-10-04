"""Non-mutating path inspection. This is NOT the managed-bundle view protocol."""

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from facet.config import MAX_CONFIG_BYTES, ConfigError
from facet.contracts import ErrorCode


@dataclass(frozen=True, slots=True, repr=False)
class PrivatePaths:
    root: Path
    config: Path
    db: Path
    credentials: Path


def select_paths(
    state_dir: str | None = None, config: str | None = None
) -> PrivatePaths:
    # abspath is lexical: never follow a symlink into another ownership domain.
    root = Path(os.path.abspath(os.path.expanduser(state_dir or ".facet")))
    config_path = (
        Path(os.path.abspath(os.path.expanduser(config)))
        if config
        else root / "config.yaml"
    )
    if ".facet-spike" in root.parts or ".facet-spike" in config_path.parts:
        raise ConfigError(ErrorCode.SCOPE_REQUIRED)
    return PrivatePaths(root, config_path, root / "facet.db", root / "credentials")


def _open_parent(path: Path) -> int:
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in path.parts[1:-1]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _owner_only(info: os.stat_result, *, directory: bool = False) -> None:
    if (
        info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
        or (directory and not stat.S_ISDIR(info.st_mode))
        or (not directory and not stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise ConfigError(ErrorCode.SCOPE_REQUIRED)


def inspect_state_root(root: Path) -> bool:
    """True means a private directory exists, not a verified bundle or WAL FS."""
    parent = None
    descriptor = None
    try:
        parent = _open_parent(root)
        descriptor = os.open(
            root.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent,
        )
        _owner_only(os.fstat(descriptor), directory=True)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        raise ConfigError(ErrorCode.SCOPE_REQUIRED) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)


def read_standalone_config(paths: PrivatePaths, *, explicit: bool) -> bytes:
    # Refuse every managed route, including an absent/unresponsive owner and an
    # apparently uninitialized root. Absence checks are never consistency proof.
    if ".facet-spike" in paths.config.parts:
        raise ConfigError(ErrorCode.SCOPE_REQUIRED)
    if not explicit or paths.config.is_relative_to(paths.root):
        raise ConfigError(ErrorCode.OWNER_UNAVAILABLE)
    parent = None
    descriptor = None
    try:
        parent = _open_parent(paths.config)
        descriptor = os.open(
            paths.config.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
        before = os.fstat(descriptor)
        _owner_only(before)
        if before.st_size > MAX_CONFIG_BYTES:
            raise ConfigError()
        chunks = []
        remaining = MAX_CONFIG_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        named = os.stat(paths.config.name, dir_fd=parent, follow_symlinks=False)
        current_parent = _open_parent(paths.config)
        try:
            original_parent = os.fstat(parent)
            current_parent_info = os.fstat(current_parent)
            if (original_parent.st_dev, original_parent.st_ino) != (
                current_parent_info.st_dev,
                current_parent_info.st_ino,
            ):
                raise ConfigError(ErrorCode.OWNER_BUSY)
        finally:
            os.close(current_parent)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or (after.st_dev, after.st_ino) != (named.st_dev, named.st_ino):
            raise ConfigError(ErrorCode.OWNER_BUSY)
        raw = b"".join(chunks)
        if len(raw) > MAX_CONFIG_BYTES:
            raise ConfigError()
        return raw
    except OSError:
        raise ConfigError(ErrorCode.SCOPE_REQUIRED) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)


def read_managed_config(paths: PrivatePaths) -> bytes:
    """Read the fixed root/config.yaml inode without following a path race."""
    if paths.config != paths.root / "config.yaml":
        raise ConfigError(ErrorCode.INVALID_INPUT)
    parent = descriptor = None
    try:
        parent = _open_parent(paths.root)
        root_info = os.stat(paths.root.name, dir_fd=parent, follow_symlinks=False)
        _owner_only(root_info, directory=True)
        root = os.open(
            paths.root.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent,
        )
        os.close(parent)
        parent = root
        before_parent = os.fstat(parent)
        descriptor = os.open(
            "config.yaml",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            dir_fd=parent,
        )
        before = os.fstat(descriptor)
        _owner_only(before)
        if before.st_size > MAX_CONFIG_BYTES:
            raise ConfigError()
        chunks = []
        remaining = MAX_CONFIG_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        named = os.stat("config.yaml", dir_fd=parent, follow_symlinks=False)
        current_parent = os.fstat(parent)
        if (
            (
                before_parent.st_dev,
                before_parent.st_ino,
            )
            != (current_parent.st_dev, current_parent.st_ino)
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            or (after.st_dev, after.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise ConfigError(ErrorCode.OWNER_BUSY)
        raw = b"".join(chunks)
        if len(raw) > MAX_CONFIG_BYTES:
            raise ConfigError()
        return raw
    except ConfigError:
        raise
    except OSError:
        raise ConfigError(ErrorCode.SCOPE_REQUIRED) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)


def filesystem_warning(root: Path) -> str:
    """Reject known remote filesystems; unknown detection never proves WAL safety."""
    try:
        entries = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return "filesystem_verification_pending"
    matches = []
    for entry in entries:
        parts = entry.split()
        try:
            separator = parts.index("-")
            mount = Path(parts[4].replace("\\040", " ").replace("\\134", "\\"))
            if root.is_relative_to(mount):
                matches.append((len(mount.parts), parts[separator + 1]))
        except (ValueError, IndexError):
            continue
    if not matches:
        return "filesystem_verification_pending"
    fs_type = max(matches)[1].casefold()
    if fs_type in {"nfs", "nfs4", "cifs", "smb", "smb3", "smbfs"}:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    # File-system detection alone does not establish lock/WAL behavior.
    return "filesystem_verification_pending"
