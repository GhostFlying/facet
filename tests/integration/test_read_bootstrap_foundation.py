"""RB01–10: actual installed no-state subprocess and detecting controls."""

import ast
import hashlib
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = Path(__file__).with_name("read_bootstrap_child.py")
SENTINEL = "synthetic_body_subject_sender@example.invalid_TOKEN_PRIVATE_PATH"
ENV = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


@pytest.fixture(scope="session")
def installed_read_foundation(tmp_path_factory):
    sandbox = tmp_path_factory.mktemp("installed-read-foundation")
    uv = shutil.which("uv")
    assert uv is not None
    for command in (
        [uv, "build", "--offline", "--wheel", "--out-dir", str(sandbox / "dist")],
        [uv, "venv", "--offline", "--python", sys.executable, str(sandbox / "venv")],
    ):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=30)
        assert result.returncode == 0, "offline_wheel_environment_failed"
    wheel = next((sandbox / "dist").glob("*.whl"))
    python = sandbox / "venv/bin/python"
    result = subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--offline",
            "--no-deps",
            "--link-mode",
            "copy",
            "--python",
            str(python),
            str(wheel),
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, "offline_noneditable_install_failed"
    site = (
        sandbox
        / "venv/lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    return python, site, wheel


def child(installed, scenario, *arguments):
    python, site, _ = installed
    result = subprocess.run(
        [
            str(python),
            "-I",
            "-S",
            "-B",
            "-X",
            "utf8",
            str(HELPER),
            scenario,
            str(site / "facet/runtime/read_bootstrap.py"),
            *map(str, arguments),
        ],
        cwd="/",
        env=ENV,
        capture_output=True,
        timeout=12,
    )
    assert result.returncode == 0, (
        "fixed_installed_control_failed: "
        + scenario
        + " "
        + result.stderr.decode(errors="replace")
    )
    assert result.stdout == b"PASS\n" and result.stderr == b""


def launcher(installed, *, script=None, env=None, timeout=15):
    python, _, _ = installed
    script = (
        script
        or "from facet.runtime.read_launcher import "
        "_launch_no_state_read_bootstrap as launch; print(launch().value)"
    )
    return subprocess.run(
        [str(python), "-I", "-B", "-c", script],
        cwd="/",
        env=env or ENV,
        capture_output=True,
        timeout=timeout,
    )


def assert_launch(result, code="owner_unavailable"):
    assert result.returncode == 0 and result.stdout == (code + "\n").encode()
    assert result.stderr == b"" and SENTINEL.encode() not in result.stdout


def test_rb01_actual_guard_probe_close_stage_b_unavailable(installed_read_foundation):
    child(installed_read_foundation, "normal")
    python, site, _ = installed_read_foundation
    direct = subprocess.run(
        [
            str(python),
            "-I",
            "-S",
            "-B",
            "-X",
            "utf8",
            str(site / "facet/runtime/read_bootstrap.py"),
        ],
        env=ENV,
        capture_output=True,
        timeout=10,
    )
    assert direct.returncode == 4 and direct.stdout == b""
    assert direct.stderr == b"facet: owner_unavailable\n"
    assert_launch(launcher(installed_read_foundation))


@pytest.mark.parametrize(
    "scenario",
    [
        "preloaded_sqlite",
        "preloaded_application",
        "hook_declined",
        "latch_allocation",
        "duplicate_begin",
        "forged_latch",
        "direct_connection",
        "forged_handle",
        "extra_memory",
        "repeated_probe",
        "foreign_sqlite",
    ],
)
def test_rb02_actual_provenance_and_audit_negatives(
    installed_read_foundation, scenario
):
    child(installed_read_foundation, scenario)


@pytest.mark.parametrize("scenario", ["thread_live", "thread_reused", "fork"])
def test_rb03_actual_creator_native_retirement_reuse_and_fork(
    installed_read_foundation, scenario
):
    child(installed_read_foundation, scenario)


@pytest.mark.parametrize(
    "scenario", ["connect_fault", "query_fault", "handle_fault", "close_fault"]
)
def test_rb05_actual_probe_faults_owned_cleanup(installed_read_foundation, scenario):
    child(installed_read_foundation, scenario)


@pytest.mark.parametrize("scenario", ["unexpected_import", "extension"])
def test_rb06_fixed_import_and_native_binding_negatives(
    installed_read_foundation, scenario
):
    child(installed_read_foundation, scenario)


def test_rb06_optional_missing_vs_actual_hostile_implementation(
    installed_read_foundation, tmp_path
):
    # The positive genuinely attempts the absent Windows extension while the
    # negative supplies real hostile Python code outside the fixed graph.
    child(installed_read_foundation, "normal")
    marker = tmp_path / "unexpected-state-created"
    (tmp_path / "_wmi.py").write_text(
        f"open({str(marker)!r}, 'w').write({SENTINEL!r})\n"
    )
    child(installed_read_foundation, "optional_implementation", tmp_path)
    assert not marker.exists()
    _, site, _ = installed_read_foundation
    alternate = site / "_wmi.py"
    assert not alternate.exists()
    try:
        alternate.write_text("TEST_VALUE = 'synthetic_unexpected_module'\n")
        child(installed_read_foundation, "loaded_optional")
        # Same fixed import name, actual hostile implementation in the installed
        # path: the state-open audit refuses before marker creation.
        alternate.write_text(f"open({str(marker)!r}, 'w').write({SENTINEL!r})\n")
        child(installed_read_foundation, "optional_implementation", site)
        assert not marker.exists()
    finally:
        alternate.unlink(missing_ok=True)


def test_rb06_actual_alternate_native_binding_refuses_before_load(
    installed_read_foundation, tmp_path
):
    specification = importlib.util.find_spec("_uuid")
    assert specification is not None and specification.origin is not None
    native = Path(specification.origin)
    if specification.origin == "built-in":
        # The locked standalone CPython compiles _uuid into the interpreter.
        # Its actual shared libpython still exercises the real dynamic-loader
        # audit before dlopen, under the otherwise permitted extension name.
        native = Path(sysconfig.get_config_var("LIBDIR")) / sysconfig.get_config_var(
            "LDLIBRARY"
        )
    assert native.is_file()
    alternate = tmp_path / "alternate.so"
    shutil.copyfile(native, alternate)
    child(installed_read_foundation, "alternate_native", alternate)


def test_rb04_rb08_actual_site_poison_and_inherited_fd_not_admitted(
    installed_read_foundation,
):
    script = f"""
import os
from pathlib import Path
from facet.runtime import read_launcher as module
site = Path(module.__file__).parents[2]
injected = site / 'test-owned-bootstrap.pth'
marker = site / 'test-owned-bootstrap-marker'
descriptor = os.open('/dev/null', os.O_RDONLY)
os.dup2(descriptor, 100, inheritable=True)
os.close(descriptor)
real = module.subprocess.Popen
children = []
def captured(argv, **kwargs):
    assert kwargs['env'] == {{'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}}
    process = real(argv, **kwargs)
    children.append(process)
    return process
module.subprocess.Popen = captured
try:
    assert not injected.exists() and not marker.exists()
    payload = "import pathlib; pathlib.Path(" + repr(str(marker)) + ").touch()\\n"
    injected.write_text(payload)
    os.environ.update(PYTHONPATH={SENTINEL!r}, PYTHONHOME={SENTINEL!r},
        LD_PRELOAD={SENTINEL!r}, LD_LIBRARY_PATH={SENTINEL!r},
        HTTPS_PROXY={SENTINEL!r}, FACET_READ_PROVIDER={SENTINEL!r})
    assert module._launch_no_state_read_bootstrap().value == 'owner_unavailable'
    assert not marker.exists() and len(children) == 1
    assert children[0].poll() is not None
    # A separate real controlled child proves kernel-level close_fds, not only
    # the observed keyword, with the same launcher and bounded collection.
    def fd_child(argv, **kwargs):
        code = ("import os,sys\\ntry: os.fstat(100)\\nexcept OSError: pass\\n"
            "else: os._exit(1)\\n"
            "sys.stderr.write('facet: owner_unavailable\\\\n');sys.exit(4)")
        process = real([argv[0], '-I', '-S', '-B', '-X', 'utf8', '-c', code], **kwargs)
        children.append(process)
        return process
    module.subprocess.Popen = fd_child
    print(module._launch_no_state_read_bootstrap().value)
    assert len(children) == 2 and all(child.poll() is not None for child in children)
finally:
    injected.unlink(missing_ok=True)
    marker.unlink(missing_ok=True)
    os.close(100)
"""
    assert_launch(launcher(installed_read_foundation, script=script))


@pytest.mark.parametrize(
    "field",
    ["python", "sqlite", "source", "options", "architecture", "platform", "vfs"],
)
def test_rb06_actual_probed_primitive_bounds(installed_read_foundation, field):
    child(installed_read_foundation, "facts_" + field)


def inventory(path):
    return {
        str(entry.relative_to(path)): (
            entry.stat().st_dev,
            entry.stat().st_ino,
            entry.stat().st_uid,
            entry.stat().st_mode,
            entry.stat().st_nlink,
            entry.read_bytes(),
        )
        for entry in path.rglob("*")
        if entry.is_file()
    }


def test_rb04_rb07_poisoned_environment_real_wal_and_state_unchanged(
    installed_read_foundation, tmp_path
):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    connection = sqlite3.connect(state / "facet.db", autocommit=True)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("CREATE TABLE synthetic(value TEXT)")
        connection.execute("INSERT INTO synthetic VALUES (?)", (SENTINEL,))
        assert (state / "facet.db-wal").exists() and (state / "facet.db-shm").exists()
        for name in (
            "config.json",
            "token.json",
            "facet.db-journal",
            "owner.lock",
            "binding.json",
        ):
            entry = state / name
            entry.write_text(SENTINEL)
            entry.chmod(0o600)
        injected = tmp_path / "injected"
        injected.mkdir()
        marker = tmp_path / "poison-executed"
        payload = f"open({str(marker)!r}, 'w').write({SENTINEL!r})\n"
        (injected / "sitecustomize.py").write_text(payload)
        (injected / "usercustomize.py").write_text(payload)
        (injected / "hostile.pth").write_text("import sitecustomize\n")
        poisoned = dict(
            ENV,
            PYTHONPATH=str(injected),
            PYTHONHOME=str(injected),
            LD_LIBRARY_PATH=str(injected),
            HTTPS_PROXY=SENTINEL,
            FACET_STATE_DIR=str(state),
            FACET_READ_PROVIDER=SENTINEL,
        )
        before = inventory(state)
        # -I protects this installed parent; production launches its own child
        # with only the fixed locale environment, without inheriting selectors.
        assert_launch(launcher(installed_read_foundation, env=poisoned))
        child(installed_read_foundation, "normal")
        for scenario, argument in (
            ("file_connect", state / "facet.db"),
            ("unexpected_open", state / "token.json"),
            ("state_write", state / "not-created.db"),
            ("state_chmod", state / "token.json"),
            ("state_unlink", state / "token.json"),
            ("state_mkdir", state / "not-created-directory"),
        ):
            child(installed_read_foundation, scenario, argument)
        assert inventory(state) == before and not marker.exists()
        assert connection.execute("SELECT value FROM synthetic").fetchall() == [
            (SENTINEL,)
        ]
    finally:
        connection.close()


@pytest.mark.parametrize(
    "scenario,code",
    [
        ("main_sensitive_fault", "persistence_failure"),
        ("main_hostile_code", "consistency_failure"),
    ],
)
def test_rb08_child_errors_never_forward_sensitive_input(
    installed_read_foundation, scenario, code
):
    python, site, _ = installed_read_foundation
    result = subprocess.run(
        [
            str(python),
            "-I",
            "-S",
            "-B",
            "-X",
            "utf8",
            str(HELPER),
            scenario,
            str(site / "facet/runtime/read_bootstrap.py"),
        ],
        env=ENV,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 7 and result.stdout == b""
    assert result.stderr == ("facet: " + code + "\n").encode()
    assert SENTINEL.encode() not in result.stderr


@pytest.mark.parametrize(
    "behavior,code",
    [
        ("print('x' * 400, flush=True)", "consistency_failure"),
        (f"print({SENTINEL!r}, flush=True)", "consistency_failure"),
        ("import os; os._exit(9)", "consistency_failure"),
        ("import time; time.sleep(30)", "owner_unavailable"),
    ],
)
def test_rb08_real_bounded_pipe_timeout_death_reaped(
    installed_read_foundation, behavior, code
):
    # Test-only Popen replacement still executes a genuine newly owned process.
    # Product has no behavior/script selector or alternate entry.
    script = f"""
import os, sys, time
from facet.runtime import read_launcher as module
real = module.subprocess.Popen
children = []
before = set(os.listdir('/proc/self/fd'))
def controlled(argv, **kwargs):
    assert argv[1:6] == ['-I', '-S', '-B', '-X', 'utf8']
    assert kwargs['close_fds'] is True and kwargs['env'] == module._ENV
    controlled = [sys.executable, '-I', '-S', '-B', '-X', 'utf8', '-c']
    process = real([*controlled, {behavior!r}], **kwargs)
    children.append(process)
    return process
module.subprocess.Popen = controlled
start = time.monotonic()
result = module._launch_no_state_read_bootstrap()
assert time.monotonic() - start < 10
assert len(children) == 1 and children[0].poll() is not None
assert not os.path.exists('/proc/' + str(children[0].pid))
assert set(os.listdir('/proc/self/fd')) == before
print(result.value)
"""
    assert_launch(launcher(installed_read_foundation, script=script), code)


def test_rb08_actual_launch_failure_fixed_unavailable(installed_read_foundation):
    script = f"""
from facet.runtime import read_launcher as module
def fault(*args, **kwargs):
    raise FileNotFoundError({SENTINEL!r})
module.subprocess.Popen = fault
print(module._launch_no_state_read_bootstrap().value)
"""
    assert_launch(launcher(installed_read_foundation, script=script))


@pytest.mark.parametrize(
    "kind", ["missing", "symlink", "hardlink", "writable", "replacement"]
)
def test_rb04_actual_missing_replaced_or_unsafe_installed_entry_no_fallback(
    installed_read_foundation, kind
):
    _, site, _ = installed_read_foundation
    bootstrap = site / "facet/runtime/read_bootstrap.py"
    saved = bootstrap.with_name("test-owned-bootstrap-saved.py")
    assert not saved.exists()
    original = bootstrap.read_bytes()
    mode = bootstrap.stat().st_mode & 0o777
    try:
        if kind in ("missing", "symlink", "hardlink"):
            bootstrap.rename(saved)
            if kind == "symlink":
                bootstrap.symlink_to(saved)
            elif kind == "hardlink":
                os.link(saved, bootstrap)
        elif kind == "writable":
            bootstrap.chmod(0o666)
        else:
            bootstrap.write_text(f"print({SENTINEL!r})\n")
        assert_launch(launcher(installed_read_foundation))
    finally:
        if saved.exists():
            bootstrap.unlink(missing_ok=True)
            saved.rename(bootstrap)
        else:
            bootstrap.write_bytes(original)
            bootstrap.chmod(mode)
    assert bootstrap.read_bytes() == original


def test_rb08_uncertain_pipe_close_still_reaps_and_sanitizes(installed_read_foundation):
    script = """
import os
from facet.runtime import read_launcher as module
original = module._collect
children = []
def closed_descriptor(process, deadline):
    result = original(process, deadline)
    children.append(process)
    os.close(process.stdout.fileno())
    return result
module._collect = closed_descriptor
print(module._launch_no_state_read_bootstrap().value)
assert len(children) == 1 and children[0].poll() is not None
assert children[0].stderr.closed
"""
    assert_launch(launcher(installed_read_foundation, script=script))


def test_rb03_repeated_actual_held_reuse_never_skips(installed_read_foundation):
    for _ in range(10):
        child(installed_read_foundation, "thread_reused")


def test_rb09_fresh_wheel_exact_bytes_no_helpers_or_private_assets(
    installed_read_foundation,
):
    _, site, wheel = installed_read_foundation
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any(
            name.startswith(("tests/", "docs/", ".facet", "data/", "credentials/"))
            for name in names
        )
        assert not any(name.endswith((".db", ".eml", ".mbox")) for name in names)
        for name in ("read_bootstrap.py", "read_launcher.py", "read_qualification.py"):
            relative = "facet/runtime/" + name
            source = (ROOT / "src" / relative).read_bytes()
            assert archive.read(relative) == source == (site / relative).read_bytes()
        assert (
            archive.read("facet/runtime/__init__.py")
            == (ROOT / "src/facet/runtime/__init__.py").read_bytes()
            == b""
        )
    assert len(hashlib.sha256(wheel.read_bytes()).hexdigest()) == 64


def test_rb09_installed_imports_have_no_hook_connection_child_or_network(
    installed_read_foundation,
):
    script = """
import sys
events = []
def observer(event, args):
    guarded = event.startswith(('sqlite3.', 'socket.'))
    if event in ('sys.addaudithook', 'subprocess.Popen') or guarded:
        events.append(event)
sys.addaudithook(observer)
before = len(events)
from facet.runtime import read_bootstrap, read_launcher, read_qualification
assert len(events) == before
assert 'sqlite3' not in sys.modules and '_sqlite3' not in sys.modules
assert read_bootstrap._LATCH is None
assert not hasattr(read_bootstrap.ReadBootstrapLatch, 'claim')
print('PASS')
"""
    result = launcher(installed_read_foundation, script=script)
    assert (
        result.returncode == 0 and result.stdout == b"PASS\n" and result.stderr == b""
    )


def test_rb09_product_has_no_test_selector_opener_or_dynamic_graph():
    for name in ("read_bootstrap.py", "read_launcher.py", "read_qualification.py"):
        tree = ast.parse((ROOT / "src/facet/runtime" / name).read_text())
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("eval", "exec", "compile")
            for node in ast.walk(tree)
        )
        imported = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert not imported.intersection(
            {"ctypes", "cffi", "facet.cli", "facet.config", "facet.db.connection"}
        )
