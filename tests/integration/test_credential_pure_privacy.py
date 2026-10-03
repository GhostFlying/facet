"""OP07/08: real process sinks, explicit memory positive controls, no OAuth."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from fakes.privacy import Marker, MarkerKind, Profile, assert_private_boundary

SENTINEL = "SYNTHETIC_PRIVATE_CREDENTIAL"
TESTS = Path(__file__).resolve().parents[1]
MARKERS = (Marker(MarkerKind.CREDENTIAL, SENTINEL),)


def run_code(code, tmp_path):
    prelude = (
        "import sys\n"
        f"sys.path[:0] = [{str(TESTS)!r}, {str(TESTS / 'unit')!r}]\n"
        "from fakes.network import deny_network\n"
        "with deny_network():\n"
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            prelude + textwrap.indent(textwrap.dedent(code), "    "),
        ],
        capture_output=True,
        timeout=15,
        cwd=tmp_path,
        check=False,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
    )


@pytest.mark.parametrize("sealed", [False, True])
@pytest.mark.parametrize("mode", ["roundtrip", "malformed", "hostile", "uninitialized"])
def test_process_success_refusal_sinks_and_no_function_file_io(tmp_path, sealed, mode):
    result = run_code(
        f"""
        import builtins, io, os, logging
        from unittest.mock import patch
        from test_credential_models import envelope, Trap
        from facet.gmail.credential_models import (
            CredentialCodecError, CredentialEnvelope,
        )
        from facet.gmail.credential_codec import encode_envelope, decode_envelope
        from facet.gmail.client_config import parse_desktop_client
        if {sealed!r}:
            from facet.status import configure_production_logging
            configure_production_logging()
        def forbidden(*args, **kwargs):
            raise AssertionError('pure function attempted file I/O')
        with (
            patch.object(builtins, 'open', forbidden),
            patch.object(io, 'open', forbidden),
            patch.object(os, 'open', forbidden),
        ):
            mode = {mode!r}
            if mode == 'roundtrip':
                value = envelope()
                raw = encode_envelope(value)
                assert {SENTINEL.encode()!r} in raw
                assert decode_envelope(raw) == value
                assert {SENTINEL!r} not in repr(value) + str(value.secret)
            else:
                try:
                    if mode == 'malformed':
                        decode_envelope(b'{{"secret":"SYNTHETIC_PRIVATE_CREDENTIAL",}}')
                    elif mode == 'hostile':
                        parse_desktop_client(Trap())
                    else:
                        encode_envelope(object.__new__(CredentialEnvelope))
                except CredentialCodecError as error:
                    assert error.args == ('invalid_input',)
                    assert error.__cause__ is None and error.__context__ is None
                else:
                    raise AssertionError('expected refusal')
        print('controlled_ok')
        logging.shutdown()
    """,
        tmp_path,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout == b"controlled_ok\n" and result.stderr == b""
    assert_private_boundary(result.stdout + result.stderr, MARKERS, Profile.LOG)
    assert list(tmp_path.iterdir()) == []


def test_real_sealed_buffer_exit_and_explicit_secret_memory_positive(tmp_path):
    result = run_code(
        f"""
        import logging, logging.handlers, sys
        target = logging.StreamHandler(sys.stderr)
        buffer = logging.handlers.MemoryHandler(100, target=target)
        buffer.handle(logging.LogRecord(
            'google.auth', 30, '', 0, {SENTINEL!r}, (), None,
        ))
        logging.getLogger('google.auth').addHandler(buffer)
        from facet.status import configure_production_logging
        configure_production_logging()
        from test_credential_models import envelope
        from facet.gmail.credential_codec import encode_envelope
        assert {SENTINEL.encode()!r} in encode_envelope(envelope())
        logging.getLogger('google.auth').error({SENTINEL!r})
        assert buffer.buffer == [] and buffer.target is None
    """,
        tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == b""


def test_privacy_oracle_detects_deliberate_output_negative_control(tmp_path):
    result = run_code(f"print({SENTINEL!r})", tmp_path)
    assert result.returncode == 0
    with pytest.raises(AssertionError):
        assert_private_boundary(result.stdout, MARKERS, Profile.PUBLIC)


def test_imports_keep_logging_environment_and_capability_surfaces_unchanged(tmp_path):
    result = run_code(
        """
        import logging, sys
        def logging_state():
            return (logging.root, tuple(logging.root.handlers),
                    logging.getLogRecordFactory(), sys.excepthook)
        before = logging_state()
        import facet.gmail
        assert facet.gmail.__all__ == ()
        assert 'facet.gmail.credential_models' not in sys.modules
        from facet.gmail import credential_models, credential_codec, client_config
        assert before == logging_state()
        assert credential_codec.__all__ == ('encode_envelope', 'decode_envelope')
        assert client_config.__all__ == ('DesktopClientConfig', 'parse_desktop_client')
        assert len(credential_models.__all__) == 14
        forbidden = ('facet.db', 'facet.cli', 'facet_spike', 'google.',
                     'googleapiclient', 'google_auth_oauthlib')
        assert not any(name.startswith(forbidden) for name in sys.modules)
        print('import_ok')
    """,
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"import_ok\n" and result.stderr == b""


def test_all_four_public_families_reject_credential_values_before_output(tmp_path):
    result = run_code(
        """
        from test_credential_models import envelope as credential
        from test_status_models_boundary import (
            unknown_status, progress, diagnostics, envelope,
        )
        from facet.status.models import Issues
        from facet.status.errors import OutputBoundaryError
        from facet.status.serialization import serialize_public, public_json
        from facet.gmail.client_config import DesktopClientConfig
        from facet.gmail.credential_models import ClientIdText, SecretText
        client = DesktopClientConfig(ClientIdText('synthetic'),
                                     SecretText('SYNTHETIC_PRIVATE_CREDENTIAL'))
        for secret in (credential(), client):
            cases = ((unknown_status(), 'phase'), (progress(), 'epoch'),
                     (Issues(()), 'groups'), (diagnostics(), 'app_version'))
            for data, field in cases:
                safe = envelope(data)
                assert serialize_public(safe) and public_json(safe)
                object.__setattr__(data, field, secret)
                for output in (serialize_public, public_json):
                    try:
                        output(safe)
                    except OutputBoundaryError:
                        pass
                    else:
                        raise AssertionError('credential reached public family')
        print('four_families_rejected')
    """,
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"four_families_rejected\n" and result.stderr == b""


def test_child_guard_really_blocks_network(tmp_path):
    result = run_code(
        """
        import socket
        from fakes.network import NetworkDenied
        try:
            socket.create_connection(('synthetic.invalid', 443))
        except NetworkDenied:
            print('network_denied')
        else:
            raise AssertionError('missing child guard')
    """,
        tmp_path,
    )
    assert result.returncode == 0 and result.stdout == b"network_denied\n"
    assert result.stderr == b""
