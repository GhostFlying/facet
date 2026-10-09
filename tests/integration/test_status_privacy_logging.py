"""Real isolated process lifecycle controls; not production entrypoint evidence."""

import json
import os
import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fakes.privacy import (
    Marker,
    MarkerKind,
    Profile,
    assert_private_boundary,
    markers,
)

SENTINEL = "SYNTHETIC_PRIVATE_TOKEN_SUBJECT_87"
TESTS = str(Path(__file__).resolve().parents[1])


def run_code(code, *, network_guard=True):
    prelude = "import sys\nsys.path.insert(0, " + repr(TESTS) + ")\n"
    if network_guard:
        prelude += "from fakes.network import deny_network\nwith deny_network():\n"
        code = textwrap.indent(textwrap.dedent(code), "    ")
    result = subprocess.run(
        [sys.executable, "-c", prelude + code],
        capture_output=True,
        timeout=15,
        check=False,
        env=dict(os.environ),
    )
    return result


BUFFER = f"""
import logging, logging.handlers, sys
target = logging.StreamHandler(sys.stderr)
buffer = logging.handlers.MemoryHandler(100, target=target)
buffer.handle(logging.LogRecord('google.auth', logging.WARNING, '', 0,
                                {SENTINEL!r}, (), None))
logging.getLogger('google.auth').addHandler(buffer)
"""


def test_detecting_uncontained_atexit_buffer_negative_control():
    result = run_code(BUFFER)
    assert result.returncode == 0
    assert SENTINEL.encode() in result.stderr


@pytest.mark.parametrize(
    "ending", ["", "logging.shutdown()", "configure_production_logging()"]
)
def test_prebuffered_handler_records_discard_before_shutdown(ending):
    result = run_code(
        BUFFER
        + """
from facet.status import configure_production_logging
configure_production_logging()
assert buffer.buffer == [] and buffer.target is None
"""
        + ending
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == b""


@pytest.mark.parametrize(
    "unsupported",
    [
        "logging.setLogRecordFactory(lambda *a, **k: None)",
        "import http.client; http.client.HTTPConnection.debuglevel = 1",
        "class Unsafe(logging.Handler):\n    def close(self):\n        print('"
        + SENTINEL
        + "', file=sys.stderr)\nlogging.getLogger('other').addHandler(Unsafe())",
    ],
)
def test_startup_refusal_never_flushes_buffers_or_calls_custom_close(unsupported):
    result = run_code(
        BUFFER
        + unsupported
        + """
from facet.status import configure_production_logging
from facet.status.errors import OutputBoundaryError
try:
    configure_production_logging()
except OutputBoundaryError:
    print('controlled_refusal')
else:
    raise AssertionError('must refuse')
logging.shutdown()
"""
    )
    assert result.returncode == 0
    assert result.stdout == b"controlled_refusal\n"
    assert result.stderr == b""


def test_changed_runtime_policy_refuses_and_discards_new_buffer():
    result = run_code(
        """
from facet.status import configure_production_logging
from facet.status.errors import OutputBoundaryError
configure_production_logging()
"""
        + BUFFER
        + """
try:
    configure_production_logging()
except OutputBoundaryError:
    print('refused')
else:
    raise AssertionError('changed policy accepted')
"""
    )
    assert result.returncode == 0
    assert result.stdout == b"refused\n"
    assert result.stderr == b""


def test_standard_library_records_and_unsafe_objects_never_formatted():
    result = run_code("""
import logging, warnings
from facet.status import configure_production_logging
configure_production_logging()
class Unsafe:
    def __str__(self):
        raise AssertionError('format invoked')
    __repr__ = __str__
for name in ('google_auth_oauthlib', 'oauthlib', 'requests_oauthlib',
             'google.auth', 'google.oauth2', 'googleapiclient', 'requests',
             'urllib3', 'httplib2', 'asyncio', 'py.warnings'):
    logger = logging.getLogger(name)
    for level in (10,20,30,40,50):
        logger.log(level, Unsafe(), exc_info=True)
warnings.warn('SYNTHETIC_PRIVATE_TOKEN_SUBJECT_87')
configure_production_logging()
""")
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b"facet: consistency_failure\n"


def test_main_exception_sealed_and_exits_seven():
    result = run_code("""
from facet.status import configure_production_logging
configure_production_logging()
raise RuntimeError('SYNTHETIC_PRIVATE_TOKEN_SUBJECT_87')
""")
    assert result.returncode == 7
    assert result.stdout == b""
    assert result.stderr == b"facet: consistency_failure\n"


@pytest.mark.parametrize(
    "failure",
    [
        "import threading\ndef fail():\n"
        "    raise RuntimeError('SYNTHETIC_PRIVATE_TOKEN_SUBJECT_87')\n"
        "t=threading.Thread(target=fail); t.start(); t.join()",
        "class Bad:\n    def __del__(self):\n"
        "        raise RuntimeError('SYNTHETIC_PRIVATE_TOKEN_SUBJECT_87')\n"
        "b=Bad(); del b",
        "import asyncio\n"
        "from facet.status.logging import sealed_asyncio_exception_handler\n"
        "loop=asyncio.new_event_loop(); "
        "loop.set_exception_handler(sealed_asyncio_exception_handler); "
        "loop.call_exception_handler("
        "{'message':'SYNTHETIC_PRIVATE_TOKEN_SUBJECT_87'}); "
        "loop.close()",
    ],
)
def test_background_failure_sealed_and_next_admission_refuses(failure):
    result = run_code(
        """
from facet.status import configure_production_logging
from facet.status.errors import OutputBoundaryError
configure_production_logging()
"""
        + failure
        + """
try:
    configure_production_logging()
except OutputBoundaryError:
    print('refused')
"""
    )
    assert result.returncode == 0
    assert result.stdout == b"refused\n"
    assert result.stderr == b"facet: consistency_failure\n"


def test_module_import_does_not_change_spike_logging_policy():
    result = run_code("""
import logging, sys, warnings
before=(logging.root.manager.disable, logging.root.handlers[:], sys.excepthook,
        warnings.showwarning, logging.lastResort)
import facet.status
assert before == (logging.root.manager.disable, logging.root.handlers[:],
                  sys.excepthook, warnings.showwarning, logging.lastResort)
logging.warning('synthetic-visible-control')
""")
    assert result.returncode == 0
    assert b"synthetic-visible-control" in result.stderr


def test_typed_log_sink_real_json_and_invalid_event_fixed_only():
    result = run_code("""
from datetime import UTC, datetime
from facet.contracts import Timestamp
from facet.status import configure_production_logging, emit_safe
from facet.status.models import Component
from facet.status.logging import SafeLogEvent, LogEventKind, SafeLogLevel
configure_production_logging()
emit_safe(SafeLogEvent(LogEventKind.WORK_SUMMARY, SafeLogLevel.DEBUG,
          Timestamp(datetime(2026,10,2,tzinfo=UTC)), Component.RUNTIME,
          None, None, 12))
class Unsafe:
    def __str__(self): raise AssertionError('formatted')
    __repr__=__str__
emit_safe(Unsafe())
""")
    assert result.returncode == 0
    first, second = result.stderr.splitlines()
    output = json.loads(first)
    assert output == {
        "kind": "work_summary",
        "level": "debug",
        "at": datetime(2026, 10, 2, tzinfo=UTC)
        .astimezone()
        .isoformat(timespec="microseconds"),
        "component": "runtime",
        "role": None,
        "code": None,
        "count": 12,
        "error_class": None,
    }
    assert second == b"facet: consistency_failure"
    assert result.stdout == b""


def test_sink_oserror_is_swallowed_without_recursive_error():
    result = run_code("""
import os
from facet.status import emit_safe
os.close(2)
emit_safe(object())
print('survived')
""")
    assert result.returncode == 0
    assert result.stdout == b"survived\n" and result.stderr == b""


def test_real_file_buffer_and_public_error_sinks_with_detecting_controls(tmp_path):
    private = markers()
    path = tmp_path / "synthetic.log"
    setup = f"""
import logging, logging.handlers
target = logging.FileHandler({str(path)!r})
buffer = logging.handlers.MemoryHandler(100, target=target)
for text in {tuple(marker.value for marker in private)!r}:
    buffer.handle(logging.LogRecord('google.auth', 30, '', 0, text, (), None))
logging.getLogger('google.auth').addHandler(buffer)
"""
    negative = run_code(setup)
    assert negative.returncode == 0
    with pytest.raises(AssertionError, match="privacy sentinel detected"):
        assert_private_boundary(path.read_bytes(), private, Profile.LOG)
    # A distinct file proves containment, not deletion of previously leaked bytes.
    safe_path = tmp_path / "contained.log"
    safe_setup = setup.replace(repr(str(path)), repr(str(safe_path)))
    result = run_code(
        safe_setup
        + f"""
import json
from facet.status import configure_production_logging, public_json, present_error
from facet.status.errors import OutputBoundaryError
configure_production_logging()
for text in {tuple(marker.value for marker in private)!r}:
    try:
        public_json(text)
    except OutputBoundaryError as error:
        assert error.args == ('consistency_failure',)
    assert present_error(RuntimeError(text)).code.value == 'consistency_failure'
print(json.dumps({{'controlled_failures': 4}}))
"""
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"controlled_failures": 4}
    for output in (result.stdout, result.stderr, safe_path.read_bytes()):
        assert_private_boundary(output, private, Profile.PUBLIC)
    assert safe_path.read_bytes() == b""


def test_child_process_network_guard_is_real():
    result = run_code("""
import socket
from fakes.network import NetworkDenied
try:
    socket.create_connection(('synthetic.invalid',443))
except NetworkDenied:
    print('denied')
else:
    raise AssertionError('network guard absent')
""")
    assert result.returncode == 0
    assert result.stdout == b"denied\n"


def test_containment_does_not_close_explicit_terminal_channel():
    # Not an OAuth flow/consumer gate: synthetic PTY demonstrates the logging
    # primitive leaves the independently owned explicit terminal channel intact.
    result = run_code("""
import os, pty
from facet.status import configure_production_logging
master, slave = pty.openpty()
configure_production_logging()
os.write(slave, b'https://example.invalid/synthetic-authorization-only')
assert b'synthetic-authorization-only' in os.read(master, 4096)
os.close(slave); os.close(master)
print('{"terminal_channel_preserved":true}')
""")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"terminal_channel_preserved": True}
    marker = Marker(
        MarkerKind.CREDENTIAL, "https://example.invalid/synthetic-authorization-only"
    )
    assert_private_boundary(result.stdout + result.stderr, (marker,), Profile.PUBLIC)


HOSTILE_CONFIGURATIONS = [
    """
class Custom(logging.Handler):
    @property
    def __dict__(self):
        print('SYNTHETIC_HANDLER_PROPERTY_CALLED')
        raise RuntimeError('SYNTHETIC_PRIVATE_HANDLER_VALUE')
handler = Custom()
logging.getLogger('google.auth').addHandler(handler)
""",
    """
class Custom(logging.Logger):
    def __getattribute__(self, name):
        if name == '_cache':
            print('SYNTHETIC_LOGGER_PROPERTY_CALLED')
            raise RuntimeError('SYNTHETIC_PRIVATE_LOGGER_CACHE')
        return super().__getattribute__(name)
logging.setLoggerClass(Custom)
logger = logging.getLogger('synthetic.custom.new.logger')
""",
    """
class Custom(logging.RootLogger):
    def __getattribute__(self, name):
        if name in ('handlers', 'manager', '_cache'):
            print('SYNTHETIC_ROOT_PROPERTY_CALLED')
            raise RuntimeError('SYNTHETIC_PRIVATE_ROOT_VALUE')
        return super().__getattribute__(name)
logging.root = Custom(30)
""",
    """
class Custom(logging.Handler):
    __hash__ = object.__hash__
    def __eq__(self, other):
        print('SYNTHETIC_EQ_CALLED')
        raise RuntimeError('SYNTHETIC_PRIVATE_EQ_VALUE')
handler = Custom()
# Populate the pre-existing unsupported state without addHandler invoking __eq__
# during fixture construction, before the boundary under test has been called.
logging.getLogger('google.auth').handlers.append(handler)
""",
    """
class Custom(logging.Formatter):
    def format(self, record):
        print('SYNTHETIC_FORMATTER_CALLED')
        raise RuntimeError('SYNTHETIC_PRIVATE_FORMATTER_VALUE')
target.setFormatter(Custom())
""",
    """
class CustomFactory:
    def __call__(self, *args, **kwargs):
        print('SYNTHETIC_FACTORY_CALLED')
        raise RuntimeError('SYNTHETIC_PRIVATE_FACTORY_VALUE')
logging.setLogRecordFactory(CustomFactory())
""",
]


@pytest.mark.parametrize("configuration", HOSTILE_CONFIGURATIONS)
@pytest.mark.parametrize("after_initial_setup", [False, True])
def test_hostile_config_refuses_without_descriptor_eq_or_formatter_calls(
    configuration, after_initial_setup
):
    begin = "from facet.status import configure_production_logging\n"
    if after_initial_setup:
        begin += "configure_production_logging()\n"
    result = run_code(
        begin
        + BUFFER
        + configuration
        + """
from facet.status.errors import OutputBoundaryError
try:
    configure_production_logging()
except OutputBoundaryError:
    print('controlled_refusal')
else:
    raise AssertionError('hostile configuration accepted')
assert buffer.buffer == [] and buffer.target is None
logging.shutdown()
"""
    )
    assert result.returncode == 0
    assert result.stdout == b"controlled_refusal\n"
    assert result.stderr == b""


def test_handler_descriptor_negative_control_really_executes():
    result = run_code(
        BUFFER
        + HOSTILE_CONFIGURATIONS[0]
        + """
object.__getattribute__(handler, '__dict__')
"""
    )
    assert result.returncode != 0
    assert b"SYNTHETIC_HANDLER_PROPERTY_CALLED" in result.stdout
    assert b"SYNTHETIC_PRIVATE_HANDLER_VALUE" in result.stderr


def test_disable_negative_control_really_traverses_custom_logger():
    result = run_code(
        BUFFER
        + HOSTILE_CONFIGURATIONS[1]
        + """
logging.disable(50)
"""
    )
    assert result.returncode != 0
    assert b"SYNTHETIC_LOGGER_PROPERTY_CALLED" in result.stdout
    assert b"SYNTHETIC_PRIVATE_LOGGER_CACHE" in result.stderr
