"""Pure no-state graph/fact validation; not a VFS/runtime allowlist."""

import sys

_MODULES = frozenset(
    [
        "__main__",
        "_abc",
        "_ast",
        "_blake2",
        "_codecs",
        "_collections",
        "_collections_abc",
        "_datetime",
        "_frozen_importlib",
        "_frozen_importlib_external",
        "_functools",
        "_hashlib",
        "_imp",
        "_io",
        "_opcode",
        "_opcode_metadata",
        "_operator",
        "_signal",
        "_sqlite3",
        "_sre",
        "_stat",
        "_thread",
        "_tokenize",
        "_typing",
        "_uuid",
        "_warnings",
        "_weakref",
        "_weakrefset",
        "abc",
        "ast",
        "builtins",
        "codecs",
        "collections",
        "collections.abc",
        "contextlib",
        "copy",
        "copyreg",
        "dataclasses",
        "datetime",
        "dis",
        "encodings",
        "encodings.aliases",
        "encodings.utf_8",
        "enum",
        "functools",
        "genericpath",
        "hashlib",
        "importlib",
        "importlib._bootstrap",
        "importlib._bootstrap_external",
        "importlib.machinery",
        "inspect",
        "io",
        "itertools",
        "keyword",
        "linecache",
        "marshal",
        "opcode",
        "operator",
        "os",
        "os.path",
        "platform",
        "posix",
        "posixpath",
        "re",
        "re._casefix",
        "re._compiler",
        "re._constants",
        "re._parser",
        "reprlib",
        "sqlite3",
        "sqlite3.dbapi2",
        "stat",
        "sys",
        "threading",
        "time",
        "token",
        "tokenize",
        "types",
        "typing",
        "typing.io",
        "typing.re",
        "unicodedata",
        "uuid",
        "warnings",
        "weakref",
        "zipimport",
        "facet",
        "facet.runtime",
        "facet.runtime.read_qualification",
        "facet.contracts",
        "facet.contracts.enums",
        "facet.contracts.primitives",
        "facet.contracts.records",
        "facet.db",
        "facet.db.codecs",
        "facet.db.read_views",
    ]
)


def _verify_foundation(facts):
    # Pure validation returns metadata only; it issues no capability or entry.
    if (
        type(facts) is not tuple
        or len(facts) != 7
        or not frozenset(sys.modules) <= _MODULES
    ):
        raise ValueError("consistency_failure")
    import hashlib

    from facet.contracts import Sha256Hex
    from facet.db.read_views import ReadRuntimeIdentity

    python, sqlite, source, options, architecture, platform, vfs = facts
    if (
        type(options) is not tuple
        or len(options) > 1000
        or any(
            type(value) is not str
            or not value
            or len(value) > 256
            or any(ord(char) < 32 or ord(char) > 126 for char in value)
            for value in options
        )
        or len(frozenset(options)) != len(options)
    ):
        raise ValueError("consistency_failure")
    encoded = ("\n".join(sorted(options)) + "\n").encode() if options else b""
    runtime = ReadRuntimeIdentity(
        python,
        sqlite,
        source,
        Sha256Hex(hashlib.sha256(encoded).hexdigest()),
        architecture,
        platform,
        vfs,
    )
    from facet.db import read_views

    if (
        not frozenset(sys.modules) <= _MODULES
        or read_views._PROVIDER_TYPES != ()
        or read_views._QUALIFIED_RUNTIMES != ()
    ):
        raise ValueError("consistency_failure")
    return runtime
