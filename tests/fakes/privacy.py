"""Bounded sentinel regression probes with explicit sink classifications."""

import base64
import json
import sqlite3
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import quote


class MarkerKind(Enum):
    CONTENT = "content"
    CREDENTIAL = "credential"
    METADATA = "metadata"
    OUTPUT_ONLY = "output_only"  # E.g. attachment name / unfiltered error text.


class Profile(Enum):
    METADATA = "metadata"
    PUBLIC = "public"
    PRIVATE_CLI = "private_cli"
    LOG = "log"
    CREDENTIAL_FILE = "credential_file"


@dataclass(frozen=True)
class Marker:
    kind: MarkerKind
    value: str


def markers() -> tuple[Marker, ...]:
    return tuple(
        Marker(kind, "FACET_SYNTHETIC_" + kind.value.upper() + "_8c0e7a_é/<x>")
        for kind in MarkerKind
    )


def _forms(value: str) -> set[bytes]:
    raw = value.encode()
    return {
        raw,
        json.dumps(value, ensure_ascii=True)[1:-1].encode(),
        quote(value, safe="").encode(),
        base64.b64encode(raw),
        base64.b64encode(raw).rstrip(b"="),
        base64.urlsafe_b64encode(raw),
        base64.urlsafe_b64encode(raw).rstrip(b"="),
    }


def assert_private_boundary(
    value: str | bytes,
    sentinels: tuple[Marker, ...],
    profile: Profile,
) -> None:
    if not isinstance(profile, Profile) or not isinstance(value, str | bytes):
        raise ValueError("invalid privacy inspection input")
    raw = value.encode() if isinstance(value, str) else value
    if len(raw) > 8 * 1024 * 1024 or len(sentinels) > 64:
        raise AssertionError("privacy inspection budget exceeded")
    for marker in sentinels:
        if (
            not isinstance(marker.kind, MarkerKind)
            or not 16 <= len(marker.value) <= 512
        ):
            raise ValueError("invalid sentinel")
        allowed = (
            marker.kind == MarkerKind.METADATA
            and profile
            in {Profile.METADATA, Profile.PRIVATE_CLI, Profile.CREDENTIAL_FILE}
        ) or (
            marker.kind == MarkerKind.CREDENTIAL and profile == Profile.CREDENTIAL_FILE
        )
        if not allowed and any(form in raw for form in _forms(marker.value)):
            raise AssertionError("privacy sentinel detected: " + marker.kind.value)


def inspect_files(
    root: Path,
    paths: list[Path],
    sentinels: tuple[Marker, ...],
    *,
    credential_files: tuple[Path, ...] = (),
) -> None:
    """Only explicit test-owned paths; no host scan or directory exclusions."""
    if root.is_symlink() or not root.is_dir() or len(paths) > 512:
        raise ValueError("invalid test inspection root")
    root = root.absolute()
    allowed = set(credential_files)
    if not allowed.issubset(set(paths)):
        raise ValueError("credential exception outside explicit scan")
    total = 0
    for path in paths:
        path = path.absolute()
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            raise ValueError("inspection outside test root") from None
        if not parts or ".." in parts:
            raise ValueError("invalid inspection path")
        cursor = root
        for part in parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError("inspection symlink refused")
        if not path.is_file():
            raise ValueError("inspection requires regular test file")
        if path in allowed and stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ValueError("credential fixture must be owner-only")
        size = path.stat().st_size
        total += size
        if total > 8 * 1024 * 1024:
            raise AssertionError("privacy inspection budget exceeded")
        with path.open("rb") as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        profile = Profile.CREDENTIAL_FILE if path in allowed else Profile.METADATA
        assert_private_boundary(raw, sentinels, profile)


def inspect_sqlite(
    connection: sqlite3.Connection, sentinels: tuple[Marker, ...]
) -> None:
    """Logical values on a supplied test connection; does not commit/checkpoint."""
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchmany(101)
    if len(tables) > 100:
        raise AssertionError("privacy table budget exceeded")
    total = 0
    for (table,) in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        rows = connection.execute("SELECT * FROM " + quoted).fetchmany(1001)
        if len(rows) > 1000:
            raise AssertionError("privacy row budget exceeded")
        for row in rows:
            for value in row:
                if isinstance(value, str | bytes):
                    total += len(value)
                    if total > 8 * 1024 * 1024:
                        raise AssertionError("privacy inspection budget exceeded")
                    assert_private_boundary(value, sentinels, Profile.METADATA)
