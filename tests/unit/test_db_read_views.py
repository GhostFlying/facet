"""RV bridge values/refusal controls; genuine isolated producers follow below.

Empty-inventory and malformed-identity tests are not a live-WAL qualification,
and no fabricated enrollment in this process creates a successful permit.
"""

import copy
import pickle
import sqlite3
from dataclasses import replace

import pytest

from facet.contracts import ErrorCode, LocalId, Sha256Hex
from facet.db import read_views as views
from facet.db.codecs import StorageFailure


def runtime():
    # A syntactically valid synthetic value, deliberately not a qualified entry.
    return views.ReadRuntimeIdentity(
        (3, 12, 13),
        (3, 53, 1),
        "synthetic-runtime-source",
        Sha256Hex("a" * 64),
        "x86_64",
        "linux",
        "unix",
    )


@pytest.mark.parametrize("field", ["device", "inode", "uid", "mode"])
@pytest.mark.parametrize("bad", [True, -1, "PRIVATE_RUNTIME_MARKER"])
def test_file_identity_exact_nonnegative_fields_and_safe_errors(field, bad):
    value = dict(device=1, inode=2, uid=3, mode=384)
    value[field] = bad
    with pytest.raises(StorageFailure) as failure:
        views.FileIdentity(**value)
    assert failure.value.code is ErrorCode.INVALID_INPUT
    assert str(failure.value) == "invalid_input"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("python_version", [3, 12, 13]),
        ("python_version", (3, 12)),
        ("python_version", (True, 12, 13)),
        ("sqlite_version", (3, -1, 0)),
        ("sqlite_version", (3, "53", 1)),
        ("sqlite_source_id", ""),
        ("sqlite_source_id", "x" * 257),
        ("sqlite_source_id", "PRIVATE_RUNTIME_MARKER\x00"),
        ("sqlite_source_id", "x\n"),
        ("sqlite_source_id", "xé"),
        ("compile_options_digest", "a" * 64),
        ("architecture", "unknown"),
        ("platform", "darwin"),
        ("vfs", "unix-none"),
    ],
)
def test_runtime_exact_closed_fields(field, bad):
    with pytest.raises(StorageFailure) as failure:
        replace(runtime(), **{field: bad})
    assert str(failure.value) == "invalid_input"


def test_runtime_and_file_repr_never_print_private_qualification_details():
    assert repr(runtime()) == "ReadRuntimeIdentity()"
    assert repr(views.FileIdentity(1, 2, 3, 384)) == "FileIdentity()"
    assert tuple(views.ViewMode) == (
        views.ViewMode.STOPPED_CLEAN,
        views.ViewMode.LIVE_WAL,
    )


@pytest.mark.parametrize(
    "cls", [views.ReadProcessSeal, views.ReadViewLease, views.ReadViewPermit]
)
def test_opaque_constructor_copy_pickle_and_mutation_cannot_enroll(cls):
    with pytest.raises(StorageFailure):
        cls()
    forged = object.__new__(cls)
    assert not hasattr(forged, "__dict__")
    assert repr(forged) == cls.__name__ + "()"
    for call in (
        lambda: copy.copy(forged),
        lambda: pickle.dumps(forged),
        lambda: setattr(forged, "PRIVATE_RUNTIME_MARKER", True),
    ):
        with pytest.raises(StorageFailure) as failure:
            call()
        assert str(failure.value) == "invalid_input"


def test_shipped_empty_inventories_refuse_before_provider_attributes_or_sql():
    class Foreign:
        def __getattribute__(self, name):
            raise AssertionError("foreign provider attributes must not execute")

    assert views._PROVIDER_TYPES == () and views._QUALIFIED_RUNTIMES == ()
    with pytest.raises(StorageFailure) as failure:
        views._issue_read_seal(Foreign(), runtime())
    assert failure.value.code is ErrorCode.OWNER_UNAVAILABLE
    assert not views._SEALS and not views._LEASES and not views._PERMITS


def test_forged_exact_objects_fail_enrollment_before_missing_slots_are_read():
    forged_seal = object.__new__(views.ReadProcessSeal)
    forged_lease = object.__new__(views.ReadViewLease)
    forged_permit = object.__new__(views.ReadViewPermit)
    instance = LocalId("00000000000040008000000000000001")
    connection = sqlite3.connect(":memory:", autocommit=True)
    statements = []
    connection.set_trace_callback(statements.append)
    try:
        for call in (
            lambda: views._issue_read_lease(forged_seal, views.ViewMode.LIVE_WAL),
            lambda: forged_lease.check(),
            lambda: forged_lease.close(),
            lambda: views._bind_read_view(
                connection, instance, forged_lease, forged_seal
            ),
            lambda: views._consume_permit(forged_permit, connection, instance),
            lambda: views._check_permit(forged_permit),
            lambda: views._close_permit(forged_permit),
        ):
            with pytest.raises(StorageFailure) as failure:
                call()
            assert failure.value.code is ErrorCode.OWNER_UNAVAILABLE
        assert statements == []
        # Refusal of this unclaimed foreign handle must not close/adopt it.
        assert connection.execute("SELECT 1").fetchone() == (1,)
    finally:
        connection.close()


def test_foreign_factories_reject_types_without_custom_property_repr_or_comparison():
    class Foreign:
        def __getattribute__(self, name):
            raise AssertionError("foreign attribute")

        def __eq__(self, other):
            raise AssertionError("foreign comparison")

        def __repr__(self):
            raise AssertionError("foreign repr")

    foreign = Foreign()
    for call in (
        lambda: views._issue_read_seal(foreign, foreign),
        lambda: views._issue_read_lease(foreign, foreign),
        lambda: views._bind_read_view(foreign, foreign, foreign, foreign),
        lambda: views._consume_permit(foreign, foreign, foreign),
    ):
        with pytest.raises(StorageFailure) as failure:
            call()
        assert str(failure.value) in {"invalid_input", "owner_unavailable"}


def test_runtime_str_and_tuple_subclasses_are_rejected_before_their_hooks():
    class String(str):
        def __iter__(self):
            raise AssertionError("subclass string iteration")

    class Version(tuple):
        def __len__(self):
            raise AssertionError("subclass tuple length")

    for change in (
        {"sqlite_source_id": String("PRIVATE_RUNTIME_MARKER")},
        {"python_version": Version((3, 12, 13))},
        {"architecture": String("x86_64")},
    ):
        with pytest.raises(StorageFailure) as failure:
            replace(runtime(), **change)
        assert str(failure.value) == "invalid_input"
