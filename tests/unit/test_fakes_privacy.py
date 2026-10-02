import base64
import json
import logging
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fakes import network
from fakes.gmail import HttpFailure
from fakes.network import NetworkDenied, deny_network
from fakes.privacy import (
    MarkerKind,
    Profile,
    assert_private_boundary,
    inspect_files,
    inspect_sqlite,
    markers,
)


def marker(kind):
    return next(item for item in markers() if item.kind == kind)


@pytest.mark.parametrize("profile", list(Profile))
def test_content_is_forbidden_even_in_credential_file(profile):
    content = marker(MarkerKind.CONTENT)
    with pytest.raises(
        AssertionError, match="privacy sentinel detected: content"
    ) as caught:
        assert_private_boundary(content.value, markers(), profile)
    assert content.value not in str(caught.value)


@pytest.mark.parametrize(
    "profile", [Profile.METADATA, Profile.PRIVATE_CLI, Profile.CREDENTIAL_FILE]
)
def test_legitimate_metadata_is_not_falsely_rejected(profile):
    assert_private_boundary(marker(MarkerKind.METADATA).value, markers(), profile)


@pytest.mark.parametrize("profile", [Profile.PUBLIC, Profile.LOG])
def test_same_metadata_rejected_from_public_and_logs(profile):
    with pytest.raises(AssertionError, match="metadata"):
        assert_private_boundary(marker(MarkerKind.METADATA).value, markers(), profile)


def test_credentials_only_allowed_in_explicit_credential_sink():
    value = marker(MarkerKind.CREDENTIAL).value
    assert_private_boundary(value, markers(), Profile.CREDENTIAL_FILE)
    for profile in (Profile.METADATA, Profile.PUBLIC, Profile.PRIVATE_CLI, Profile.LOG):
        with pytest.raises(AssertionError, match="credential"):
            assert_private_boundary(value, markers(), profile)


@pytest.mark.parametrize(
    "encode",
    [
        lambda s: s.encode(),
        lambda s: json.dumps(s).encode(),
        lambda s: base64.b64encode(s.encode()),
        lambda s: base64.urlsafe_b64encode(s.encode()).rstrip(b"="),
    ],
)
def test_common_encoded_leaks_detected_without_echoing_values(encode):
    with pytest.raises(AssertionError, match="content"):
        assert_private_boundary(
            encode(marker(MarkerKind.CONTENT).value), markers(), Profile.PUBLIC
        )


@pytest.mark.parametrize(
    "kind", [MarkerKind.CONTENT, MarkerKind.CREDENTIAL, MarkerKind.OUTPUT_ONLY]
)
def test_log_and_console_capture_are_explicit_test_owned_sinks(caplog, capsys, kind):
    value = marker(kind).value
    logging.warning(value)
    print(value)
    print(value, file=sys.stderr)
    captured = capsys.readouterr()
    for output in (caplog.text, captured.out, captured.err):
        with pytest.raises(AssertionError, match=kind.value):
            assert_private_boundary(output, markers(), Profile.PRIVATE_CLI)


def test_sqlite_logical_and_active_wal_leaks_before_checkpoint(tmp_path):
    path = tmp_path / "metadata.sqlite"
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("CREATE TABLE metadata(value TEXT)")
        connection.execute(
            "INSERT INTO metadata VALUES(?)", (marker(MarkerKind.METADATA).value,)
        )
        connection.commit()
        inspect_sqlite(connection, markers())
        inspect_files(tmp_path, [path, Path(str(path) + "-wal")], markers())
        connection.execute(
            "INSERT INTO metadata VALUES(?)", (marker(MarkerKind.CONTENT).value,)
        )
        connection.commit()
        with pytest.raises(AssertionError, match="content"):
            inspect_sqlite(connection, markers())
        with pytest.raises(AssertionError, match="content"):
            inspect_files(tmp_path, [Path(str(path) + "-wal")], markers())
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with pytest.raises(AssertionError, match="content"):
            inspect_files(tmp_path, [path], markers())
    finally:
        connection.close()


def test_active_rollback_journal_marker_is_detected(tmp_path):
    path = tmp_path / "journal.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("CREATE TABLE metadata(value TEXT)")
        connection.execute(
            "INSERT INTO metadata VALUES(?)", (marker(MarkerKind.CONTENT).value,)
        )
        connection.commit()
        connection.execute("UPDATE metadata SET value='controlled'")
        with pytest.raises(AssertionError, match="content"):
            inspect_files(tmp_path, [Path(str(path) + "-journal")], markers())
        connection.rollback()
    finally:
        connection.close()


def test_explicit_files_and_credential_exceptions_are_not_directory_exclusions(
    tmp_path,
):
    credential = tmp_path / "private-credential.fixture"
    credential.write_text(marker(MarkerKind.CREDENTIAL).value)
    credential.chmod(0o600)
    with pytest.raises(AssertionError, match="credential"):
        inspect_files(tmp_path, [credential], markers())
    inspect_files(tmp_path, [credential], markers(), credential_files=(credential,))
    credential.write_text(marker(MarkerKind.CONTENT).value)
    with pytest.raises(AssertionError, match="content"):
        inspect_files(tmp_path, [credential], markers(), credential_files=(credential,))
    link = tmp_path / "unsafe-link"
    link.symlink_to(credential)
    with pytest.raises(ValueError, match="symlink"):
        inspect_files(tmp_path, [link], markers())
    with pytest.raises(ValueError, match="outside"):
        inspect_files(tmp_path, [tmp_path.parent / "not-inspected"], markers())


def test_provider_error_bytes_stay_out_of_call_evidence(gmail_controller):
    from googleapiclient.errors import HttpError

    value = marker(MarkerKind.OUTPUT_ONLY).value
    body = json.dumps({"error": {"message": value}}).encode()
    gmail_controller.script(
        "source", "profile.get", {"userId": "me"}, HttpFailure(401, body)
    )
    service = gmail_controller.service("source")
    with pytest.raises(HttpError):
        service.getProfile(userId="me").execute()
    assert_private_boundary(repr(service.transport.calls()), markers(), Profile.LOG)


def test_raw_and_headers_stay_out_of_call_and_fault_evidence(
    gmail_controller, fake_faults
):
    raw = (
        "Subject: "
        + marker(MarkerKind.CONTENT).value
        + "\r\n\r\n"
        + marker(MarkerKind.OUTPUT_ONLY).value
    ).encode()
    target = gmail_controller.service("target", scopes=frozenset({"gmail.insert"}))
    target.messages().insert(
        userId="me", body={"raw": base64.urlsafe_b64encode(raw).decode()}
    ).execute()
    assert_private_boundary(repr(target.transport.calls()), markers(), Profile.LOG)
    assert_private_boundary(repr(fake_faults.visits()), markers(), Profile.LOG)


def test_inspection_limits_and_credential_mode_are_enforced(tmp_path):
    with pytest.raises(AssertionError, match="budget"):
        assert_private_boundary(
            b"x" * (8 * 1024 * 1024 + 1), markers(), Profile.METADATA
        )
    credential = tmp_path / "private.fixture"
    credential.write_text(marker(MarkerKind.CREDENTIAL).value)
    credential.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        inspect_files(tmp_path, [credential], markers(), credential_files=(credential,))


def test_network_guard_blocks_before_any_real_connection(monkeypatch):
    called = []

    def lower_layer(*args, **kwargs):
        called.append(True)
        raise AssertionError("unexpected real network path")

    monkeypatch.setattr(socket.socket, "connect", lower_layer)
    with deny_network():
        with socket.socket() as sock:
            for call in (
                lambda: sock.connect(("192.0.2.1", 443)),
                lambda: sock.connect_ex(("192.0.2.1", 443)),
                lambda: sock.sendto(b"synthetic", ("192.0.2.1", 9)),
            ):
                with pytest.raises(NetworkDenied):
                    call()
        with pytest.raises(NetworkDenied):
            socket.getaddrinfo("synthetic.invalid", 443)
        with pytest.raises(NetworkDenied):
            socket.create_connection(("synthetic.invalid", 443))
    assert called == []
    assert socket.socket.connect is lower_layer


def test_client_network_paths_are_guarded():
    import httplib2
    import requests

    with deny_network():
        with pytest.raises(NetworkDenied):
            requests.get("https://synthetic.invalid/", timeout=0.1)
        with pytest.raises(NetworkDenied):
            httplib2.Http(timeout=0.1).request("https://synthetic.invalid/")


def test_unix_ipc_requires_explicit_allowance(tmp_path):
    endpoint = str(tmp_path / "local.sock")
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(endpoint)
        server.listen(1)
        with (
            deny_network(),
            socket.socket(socket.AF_UNIX) as client,
            pytest.raises(NetworkDenied),
        ):
            client.connect(endpoint)
        with deny_network(allow_unix=True), socket.socket(socket.AF_UNIX) as client:
            client.connect(endpoint)
            accepted, _ = server.accept()
            accepted.close()


def test_subprocess_installs_its_own_guard_without_network():
    # Parent monkeypatches are not inherited. Child explicitly loads the helper,
    # installs its own guard, and makes a negative-control connection attempt.
    program = """
import runpy, socket, sys
guard = runpy.run_path(sys.argv[1])
with guard['deny_network']():
    try:
        socket.create_connection(('192.0.2.1', 443), timeout=0.1)
    except guard['NetworkDenied']:
        print('child guard verified')
    else:
        raise AssertionError('child guard failed')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", program, str(Path(network.__file__).absolute())],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "child guard verified\n"
    assert result.stderr == ""
