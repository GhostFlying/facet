"""Trusted ordered production migration registry; no downloaded/user SQL."""

import hashlib

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
