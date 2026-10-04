"""Read-only Dashboard boundary tests."""

import json
import signal
import socket
import subprocess
import sys
import time
from http.client import RemoteDisconnected
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from facet.web.server import DashboardServer, UnavailableSnapshotProvider


@pytest.fixture
def dashboard_server():
    server = DashboardServer(("127.0.0.1", 0))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def get_json(base, path):
    with urlopen(base + path, timeout=2) as response:
        return response.status, json.load(response)


def test_default_routes_are_explicitly_unavailable(dashboard_server):
    for path in (
        "/api/v1/status",
        "/api/v1/progress",
        "/api/v1/issues",
        "/api/v1/diagnostics",
    ):
        status, body = get_json(dashboard_server, path)
        assert status == 200
        assert body["freshness"] == "unavailable"
        assert body["age_seconds"] is None
    assert get_json(dashboard_server, "/healthz") == (200, {"status": "ok"})
    with pytest.raises(HTTPError) as error:
        urlopen(dashboard_server + "/readyz", timeout=2)
    assert error.value.code == 503
    assert json.load(error.value) == {"status": "unavailable"}


def test_unknown_paths_and_queries_are_fixed_and_do_not_echo(dashboard_server):
    sentinel = "PRIVATE_SENTINEL_8d0d7f"
    for path in (f"/unknown/{sentinel}", f"/api/v1/status?value={sentinel}"):
        with pytest.raises(HTTPError) as error:
            urlopen(dashboard_server + path, timeout=2)
        assert error.value.code == 404
        body = error.value.read().decode("ascii")
        assert body == '{"error":"not_found"}'
        assert sentinel not in body


def test_mutating_methods_are_rejected_without_provider_access(dashboard_server):
    request = Request(dashboard_server + "/api/v1/status", method="POST")
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)
    assert error.value.code == 405
    assert json.load(error.value) == {"error": "method_not_allowed"}


def test_static_page_is_aggregate_only(dashboard_server):
    with (
        patch.object(Path, "read_bytes", side_effect=AssertionError("request I/O")),
        urlopen(dashboard_server + "/", timeout=2) as response,
    ):
        body = response.read().decode("utf-8").lower()
    assert "facet dashboard" in body
    for forbidden in ("subject", "attachment", "access_token", "refresh_token"):
        assert forbidden not in body


class SpyProvider(UnavailableSnapshotProvider):
    def __init__(self):
        self.ready_calls = 0
        self.snapshot_calls = []

    def ready(self):
        self.ready_calls += 1
        return super().ready()

    def snapshot(self, family):
        self.snapshot_calls.append(family)
        return super().snapshot(family)


def test_health_does_not_read_provider_and_api_reads_only_one_family():
    provider = SpyProvider()
    server = DashboardServer(("127.0.0.1", 0), provider)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert get_json(base, "/healthz") == (200, {"status": "ok"})
        assert provider.ready_calls == 0
        assert provider.snapshot_calls == []
        get_json(base, "/api/v1/issues")
        assert provider.snapshot_calls == ["issues"]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_server_closes_cleanly_without_stderr(capsys):
    server = DashboardServer(("127.0.0.1", 0))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises((HTTPError, RemoteDisconnected)):
            request = Request(f"http://127.0.0.1:{server.server_port}/", method="TRACE")
            urlopen(request, timeout=2)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    assert capsys.readouterr().err == ""


def test_cli_web_subprocess_serves_healthz():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "facet", "web", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(40):
            if process.poll() is not None:
                stderr = process.communicate(timeout=1)[1]
                raise AssertionError(f"CLI web exited early: {stderr!r}")
            try:
                status, body = get_json(f"http://127.0.0.1:{port}", "/healthz")
                if status == 200:
                    assert body == {"status": "ok"}
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("CLI web server did not become ready")
    finally:
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=3)
    assert process.returncode == 0
    assert stdout == ""
    assert stderr == ""
