"""Trusted ordered production migration registry; no downloaded/user SQL."""

import hashlib
import re
from dataclasses import dataclass

from facet.contracts import Sha256Hex

from ..codecs import SchemaVersion, invalid
from . import v0001

# Only an explicit pristine bootstrap can create v1. There is no production v0.
REGISTRY = ((1, "v0001", v0001.STATEMENTS),)
CHECKSUMS = tuple(
    hashlib.sha256("\n".join(statements).encode("utf-8")).hexdigest()
    for _, _, statements in REGISTRY
)
REGISTRY_DIGEST = hashlib.sha256(
    "\n".join(
        f"{version}:{name}:{checksum}"
        for (version, name, _), checksum in zip(REGISTRY, CHECKSUMS, strict=True)
    ).encode("ascii")
).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class _SchemaManifest:
    version: SchemaVersion
    catalogue: tuple[tuple[str, str, str], ...]
    ledger: tuple[tuple[int, str, str], ...]
    registry_digest: Sha256Hex

    def __post_init__(self):
        if (
            type(self.version) is not SchemaVersion
            or type(self.registry_digest) is not Sha256Hex
            or type(self.catalogue) is not tuple
            or not self.catalogue
            or type(self.ledger) is not tuple
            or not self.ledger
        ):
            invalid()
        for row in self.catalogue:
            if (
                type(row) is not tuple
                or len(row) != 3
                or any(type(value) is not str or not value for value in row)
                or row[0] not in {"table", "index", "trigger"}
            ):
                invalid()
        if len({row[:2] for row in self.catalogue}) != len(self.catalogue):
            invalid()
        previous = 0
        for row in self.ledger:
            if (
                type(row) is not tuple
                or len(row) != 3
                or type(row[0]) is not int
                or not previous < row[0] <= self.version.value
                or type(row[1]) is not str
                or re.fullmatch(r"v[0-9]{4}", row[1]) is None
                or type(row[2]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", row[2]) is None
            ):
                invalid()
            previous = row[0]
        digest = hashlib.sha256(
            "\n".join(
                f"{v}:{name}:{checksum}" for v, name, checksum in self.ledger
            ).encode("ascii")
        ).hexdigest()
        if previous != self.version.value or digest != self.registry_digest.value:
            invalid()


@dataclass(frozen=True, slots=True, repr=False)
class _ExistingStep:
    source: _SchemaManifest
    target: _SchemaManifest
    statements: tuple[str, ...]
    checksum: Sha256Hex

    def __post_init__(self):
        if (
            type(self.source) is not _SchemaManifest
            or type(self.target) is not _SchemaManifest
            or type(self.checksum) is not Sha256Hex
            or self.source.version.value >= self.target.version.value
            or type(self.statements) is not tuple
            or not self.statements
            or any(type(sql) is not str or not sql for sql in self.statements)
            or hashlib.sha256("\n".join(self.statements).encode("utf-8")).hexdigest()
            != self.checksum.value
            or self.target.ledger[:-1] != self.source.ledger
            or self.target.ledger[-1][0] != self.target.version.value
            or self.target.ledger[-1][2] != self.checksum.value
        ):
            invalid()


def _current_catalogue():
    rows = []
    for sql in v0001.STATEMENTS:
        match = re.match(r"CREATE (?:UNIQUE )?(TABLE|INDEX|TRIGGER) (\w+)", sql)
        assert match is not None
        kind, name = match.groups()
        rows.append((kind.lower(), name, sql))
    return tuple(rows)


_CURRENT_MANIFEST = _SchemaManifest(
    SchemaVersion(v0001.VERSION),
    _current_catalogue(),
    tuple(
        (version, name, checksum)
        for (version, name, _), checksum in zip(REGISTRY, CHECKSUMS, strict=True)
    ),
    Sha256Hex(REGISTRY_DIGEST),
)
# Existing-state migration is deliberately unavailable in the shipping registry.
_EXISTING_STEPS: tuple[_ExistingStep, ...] = ()
