"""Opaque and fixed-error values; no ordinary-process bootstrap enrollment."""

import copy
import pickle
import sys

import pytest

from facet.contracts import ErrorCode
from facet.runtime import read_bootstrap, read_launcher, read_qualification


class Trap:
    def __str__(self):
        raise AssertionError("hostile_string_hook")

    def __repr__(self):
        raise AssertionError("hostile_repr_hook")

    def __eq__(self, other):
        raise AssertionError("hostile_equality_hook")

    def __hash__(self):
        raise AssertionError("hostile_hash_hook")


@pytest.mark.parametrize(
    "value",
    [
        Trap(),
        None,
        True,
        1,
        b"invalid_input",
        "private-sentinel",
        "consistency_failure",
    ],
)
def test_rb08_failure_catalog_never_coerces_hostile_input(value):
    failure = read_bootstrap.ReadBootstrapFailure(value)
    assert failure.code == "consistency_failure"
    assert str(failure) == "consistency_failure"
    assert repr(failure) == "ReadBootstrapFailure('controlled_failure')"


@pytest.mark.parametrize(
    "operation",
    [
        lambda: read_bootstrap.ReadBootstrapLatch(),
        lambda: type("Forged", (read_bootstrap.ReadBootstrapLatch,), {}),
        lambda: object.__new__(read_bootstrap.ReadBootstrapLatch).probe_runtime(),
        lambda: copy.copy(object.__new__(read_bootstrap.ReadBootstrapLatch)),
        lambda: pickle.dumps(object.__new__(read_bootstrap.ReadBootstrapLatch)),
        lambda: setattr(
            object.__new__(read_bootstrap.ReadBootstrapLatch), "phase", "probed"
        ),
    ],
)
def test_rb02_opaque_unenrolled_values_refuse(operation):
    before = read_bootstrap._LATCH
    with pytest.raises(read_bootstrap.ReadBootstrapFailure) as error:
        operation()
    assert error.value.code in ("invalid_input", "owner_unavailable")
    assert read_bootstrap._LATCH is before


def test_rb02_ordinary_source_entry_and_launcher_refuse_without_connection():
    with pytest.raises(read_bootstrap.ReadBootstrapFailure) as error:
        read_bootstrap._begin_read_bootstrap()
    assert error.value.code == "owner_unavailable"
    assert (
        read_launcher._launch_no_state_read_bootstrap() is ErrorCode.OWNER_UNAVAILABLE
    )
    assert read_bootstrap._LATCH is read_bootstrap._REFUSED


def test_rb06_compiled_graph_not_provider_or_runtime_registration():
    assert read_bootstrap._MODULES == read_qualification._MODULES
    assert frozenset(("_wmi",)) == read_bootstrap._ABSENT_IMPORTS
    assert "_wmi" not in read_qualification._MODULES
    assert type(read_bootstrap._MODULES) is frozenset
    assert "errno" in read_bootstrap._MODULES
    assert read_bootstrap._builtin_errno() and read_qualification._builtin_errno()
    assert not hasattr(read_bootstrap.ReadBootstrapLatch, "claim")
    assert read_bootstrap.ReadBootstrapLatch.__slots__ == (
        "creator_pid",
        "creator_thread",
        "phase",
        "probe_connection",
        "runtime_facts",
        "provider",
    )
    assert read_launcher._ENV == {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    assert read_launcher._SECONDS == 10 and read_launcher._BYTES == 256


@pytest.mark.parametrize("value", [Trap(), type(sys)("errno"), None])
def test_rb06_builtin_errno_does_not_admit_foreign_module(monkeypatch, value):
    if value is None:
        # Absence is supported on3.12; it grants only the compiled builtin name.
        monkeypatch.delitem(sys.modules, "errno", raising=False)
        assert read_bootstrap._builtin_errno() and read_qualification._builtin_errno()
    else:
        monkeypatch.setitem(sys.modules, "errno", value)
        assert not read_bootstrap._builtin_errno()
        assert not read_qualification._builtin_errno()


def test_rb06_errno_failed_import_entry_is_not_an_absent_builtin(monkeypatch):
    monkeypatch.setitem(sys.modules, "errno", None)
    assert not read_bootstrap._builtin_errno()
    assert not read_qualification._builtin_errno()
