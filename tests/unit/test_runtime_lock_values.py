"""OL11: exact finite values, opaque enrollment, safe errors and pure imports."""

import copy
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest
from integration.test_runtime_os_locks import (
    NAMESPACE,
    NONCE,
    SENTINEL,
    assert_failure,
    make_root,
    trusted_sandbox,
)

from facet.contracts import ErrorCode, LocalId
from facet.runtime import locks, private_root


@pytest.fixture
def sandbox(deny_external_network):
    with trusted_sandbox() as path:
        yield path


class Trap:
    def __fspath__(self):
        raise AssertionError("hostile_path_hook")

    def __str__(self):
        raise AssertionError("hostile_string_hook")

    def __repr__(self):
        raise AssertionError("hostile_repr_hook")

    def __eq__(self, other):
        raise AssertionError("hostile_comparison_hook")

    def __bool__(self):
        raise AssertionError("hostile_bool_hook")


class StrTrap(str):
    def encode(self, *args, **kwargs):
        raise AssertionError("subclass_encode_hook")


class IdTrap(LocalId):
    def __getattribute__(self, name):
        raise AssertionError("subclass_id_hook")


@pytest.mark.parametrize(
    "value",
    [
        Trap(),
        StrTrap("/synthetic"),
        Path("/synthetic"),
        None,
        True,
        b"/synthetic",
        "",
        "/",
        "relative",
        "/a/",
        "/a//b",
        "/a/./b",
        "/a/../b",
        "/a\x00b",
        "/" + "a" * 256,
        "/" + "a/" * 256 + "a",
        "/" + "a" * 255 + "/b" * 2048,
        "/a/\ud800",
    ],
    ids=lambda _: "invalid-path",
)
def test_ol11_exact_path_bounds_refuse_before_os_or_hooks(monkeypatch, value):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid_input_reached_os")

    with monkeypatch.context() as guard:
        for name in ("open", "stat", "mkdir", "register_at_fork"):
            guard.setattr(os, name, forbidden)
        for factory in (private_root.open_existing_root, private_root.create_lock_root):
            assert_failure(factory, ErrorCode.INVALID_INPUT, value)


def test_ol11_spike_component_is_scope_refusal_before_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("spike_scope_reached_os")

    monkeypatch.setattr(os, "open", forbidden)
    assert_failure(
        private_root.open_existing_root,
        ErrorCode.SCOPE_REQUIRED,
        "/synthetic/.facet-spike/state",
    )


@pytest.mark.parametrize("primitive", ["platform", "O_NONBLOCK", "register_at_fork"])
def test_ol11_unavailable_primitives_refuse_before_any_descriptor(
    monkeypatch, primitive
):
    def forbidden(*args, **kwargs):
        raise AssertionError("unavailable_platform_opened_state")

    monkeypatch.setattr(os, "open", forbidden)
    if primitive == "platform":
        monkeypatch.setattr(sys, "platform", "unavailable")
    else:
        monkeypatch.delattr(os, primitive)
    assert_failure(
        private_root.open_existing_root, ErrorCode.OWNER_UNAVAILABLE, "/synthetic/state"
    )


@pytest.mark.parametrize(
    "value",
    [Trap(), StrTrap("shared"), "shared", "exclusive", 1, True, None],
    ids=lambda _: "invalid-mode",
)
def test_ol11_exact_lock_mode_before_root_io(monkeypatch, value):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid_mode_reached_os")

    monkeypatch.setattr(os, "fstat", forbidden)
    assert_failure(locks.acquire_view, ErrorCode.INVALID_INPUT, object(), value)


@pytest.mark.parametrize(
    "value",
    [
        Trap(),
        "123456781234423482341234567890ab",
        object.__new__(LocalId),
        pytest.param(object.__new__(IdTrap), id="hostile-subclass"),
        None,
        True,
    ],
    ids=lambda _: "invalid-id",
)
def test_ol11_exact_key_ids_before_root_or_path_hooks(monkeypatch, value):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid_key_reached_os")

    monkeypatch.setattr(os, "open", forbidden)
    assert_failure(
        locks.acquire_key,
        ErrorCode.INVALID_INPUT,
        object(),
        value,
        NONCE,
        view=object(),
    )
    assert_failure(
        locks.acquire_key,
        ErrorCode.INVALID_INPUT,
        object(),
        NAMESPACE,
        value,
        view=object(),
    )


@pytest.mark.parametrize(
    "text",
    [
        "0" * 32,
        "123456781234123482341234567890ab",
        "123456781234423412341234567890ab",
        "AAAAAAAAAAAA4AAA8AAAAAAAAAAAAAAA",
        "../synthetic",
        SENTINEL,
    ],
)
def test_ol11_forged_actual_local_id_revalidates_uuid4(text):
    value = object.__new__(LocalId)
    object.__setattr__(value, "value", text)
    assert_failure(
        locks.acquire_key,
        ErrorCode.INVALID_INPUT,
        object(),
        value,
        NONCE,
        view=object(),
    )


@pytest.mark.parametrize(
    "value", [Trap(), 0, 1, None, "true"], ids=lambda _: "invalid-flag"
)
def test_ol11_create_flag_is_exact_bool_before_root_io(value):
    assert_failure(
        locks.acquire_key,
        ErrorCode.INVALID_INPUT,
        object(),
        NAMESPACE,
        NONCE,
        view=object(),
        create=value,
    )


def test_ol11_opaque_classes_construction_enrollment_copy_and_no_exports(sandbox):
    for kind in (private_root.HeldPrivateRoot, locks.LockLease):
        assert_failure(kind, ErrorCode.INVALID_INPUT)
        with pytest.raises(private_root.LockFailure) as captured:
            type("BadSubclass", (kind,), {})
        assert captured.value.code is ErrorCode.INVALID_INPUT
        forged = object.__new__(kind)
        check = (
            private_root.check_root
            if kind is private_root.HeldPrivateRoot
            else locks.check_lock
        )
        assert_failure(check, ErrorCode.OWNER_UNAVAILABLE, forged)
    path = make_root(sandbox)
    with private_root.open_existing_root(str(path)) as root:
        private_root.check_root(root)
        with locks.acquire_owner(root) as lease:
            for value in (root, lease):
                for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                    assert_failure(operation, ErrorCode.INVALID_INPUT, value)
                for name in (
                    "fd",
                    "fileno",
                    "path",
                    "descriptors",
                    "inventory",
                    "pid",
                    "thread",
                    "__dict__",
                ):
                    assert not hasattr(value, name)
                assert str(path) not in str(value) + repr(value)
            assert_failure(
                private_root.HeldPrivateRoot.__enter__,
                ErrorCode.OWNER_UNAVAILABLE,
                object.__new__(private_root.HeldPrivateRoot),
            )
            locks.check_lock(lease)


def test_ol11_error_code_is_closed_and_constant_even_inside_caller_handler():
    for invalid in (Trap(), "owner_busy", ErrorCode.BINDING_MISMATCH, None):
        error = private_root.LockFailure(invalid)
        assert error.code is ErrorCode.INVALID_INPUT and error.args == ("lock_failure",)
        assert (
            str(error) == "lock_failure"
            and repr(error) == "LockFailure('lock_failure')"
        )
    try:
        raise ValueError(SENTINEL)
    except ValueError:
        assert_failure(private_root.check_root, ErrorCode.INVALID_INPUT, object())


def test_ol11_imports_install_no_hooks_open_no_state_or_logging(tmp_path):
    code = """
import logging, os, socket, sys
from unittest.mock import patch
before = (tuple(logging.root.handlers), logging.getLogRecordFactory(), sys.excepthook)
def forbidden(*args, **kwargs):
    raise AssertionError('import_effect')
with (
    patch.object(os, 'open', forbidden),
    patch.object(os, 'register_at_fork', forbidden),
    patch.object(socket, 'socket', forbidden),
):
    import facet.runtime
    assert 'facet.runtime.private_root' not in sys.modules
    assert 'facet.runtime.locks' not in sys.modules
    from facet.runtime import private_root, locks
    assert private_root._DESCRIPTORS == {} and private_root._ROOTS == {}
    assert not private_root._HOOKS_INSTALLED
    assert len(private_root.__all__) == 6 and len(locks.__all__) == 7
    assert before == (
        tuple(logging.root.handlers), logging.getLogRecordFactory(), sys.excepthook
    )
    forbidden_prefixes = (
        'sqlite3', '_sqlite3', 'facet.db', 'facet.cli', 'facet_spike', 'google.',
        'googleapiclient', 'google_auth_oauthlib',
    )
    assert not any(name.startswith(forbidden_prefixes) for name in sys.modules)
    assert str(private_root.LockFailure()) == 'lock_failure'
print('controlled_ok')
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout == b"controlled_ok\n" and result.stderr == b""
    assert list(tmp_path.iterdir()) == []
