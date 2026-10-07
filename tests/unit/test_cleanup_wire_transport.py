"""Real requests/urllib3 wire faults against a synthetic loopback Gmail server."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from facet.contracts import ErrorCode
from facet.gmail.cleanup_transport import build_cleanup_service
from facet.gmail.retry import ProviderFailure
from facet.maintenance.target_cleanup import CleanupJournal, check_profile


@pytest.fixture
def wire(monkeypatch):
    state = {
        "ids": {"mail1", "spam1", "draft_old", "new_arrival"},
        "calls": [],
        "fault": "lost_response",
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value, status=200, location=None):
            body = json.dumps(value).encode()
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            state["calls"].append(("GET", path))
            if path.endswith("/profile"):
                self.reply({"emailAddress": "target@example.com"})
            elif path.endswith("/messages"):
                self.reply(
                    {
                        "messages": [
                            {"id": value} for value in ("mail1", "spam1", "draft_old")
                        ]
                    }
                )
            elif path.endswith("/drafts"):
                self.reply(
                    {
                        "drafts": [
                            {"id": "draft_container", "message": {"id": "draft_old"}}
                        ]
                    }
                )
            else:
                identifier = path.rsplit("/", 1)[1]
                self.reply(
                    {"id": identifier} if identifier in state["ids"] else {},
                    200 if identifier in state["ids"] else 404,
                )

        def do_DELETE(self):
            path = urlsplit(self.path).path
            state["calls"].append(("DELETE", path))
            identifier = path.rsplit("/", 1)[1]
            assert self.headers["Authorization"] == "Bearer synthetic-access"
            if state["fault"] == "redirect":
                self.reply({}, 307, self.path.replace(identifier, "new_arrival"))
            elif state["fault"] == "unauthorized":
                self.reply({"error": {"message": "BODY_CREDENTIAL_SENTINEL"}}, 401)
            else:
                state["ids"].discard(identifier)
                if state["fault"] == "lost_response":
                    state["fault"] = None
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                else:
                    self.reply({})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    service = build_cleanup_service("synthetic-access")
    session = service._http.session
    session.trust_env = False
    original = session.request

    def route(method, url, **kwargs):
        parsed = urlsplit(url)
        local = f"http://127.0.0.1:{server.server_port}{parsed.path}"
        if parsed.query:
            local += "?" + parsed.query
        return original(method, local, **kwargs)

    monkeypatch.setattr(session, "request", route)
    try:
        yield service, state
    finally:
        service.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def prepare(tmp_path, service):
    tmp_path.chmod(0o700)
    journal = CleanupJournal(tmp_path)
    check_profile(service, "target@example.com")
    identifier = journal.preview(
        service,
        request_id=uuid4().hex,
        identity="binding-digest",
        mappings=0,
        unknown_inserts=0,
    )["preview_id"]
    key = uuid4().hex
    journal.start(
        preview_id=identifier,
        request_id=key,
        identity="binding-digest",
        confirmation="target@example.com",
    )
    return journal, identifier, key


def test_real_wire_response_loss_dispatches_once_then_get_before_recovery(
    wire, tmp_path
):
    service, state = wire
    journal, identifier, key = prepare(tmp_path, service)
    try:
        with pytest.raises(ProviderFailure) as caught:
            journal.execute(service, identifier)
        assert caught.value.code is ErrorCode.NETWORK_UNAVAILABLE
        deletes = [path for method, path in state["calls"] if method == "DELETE"]
        assert len(deletes) == 1
        assert journal.receipt(identifier)["unknown_deletions"] == 1
        assert journal.receipt(identifier)["confirmed_absent"] == 0
        first_deleted = deletes[0]
        journal.close()
        journal = CleanupJournal(tmp_path)
        journal.start(
            preview_id=identifier,
            request_id=key,
            identity="binding-digest",
            confirmation="target@example.com",
        )
        boundary = len(state["calls"])
        assert journal.execute(service, identifier)["state"] == "completed"
        assert state["calls"][boundary] == ("GET", first_deleted)
        deletes = [path for method, path in state["calls"] if method == "DELETE"]
        assert len(deletes) == len(set(deletes)) == 3
        assert state["ids"] == {"new_arrival"}
    finally:
        journal.close()


@pytest.mark.parametrize("fault", ["redirect", "unauthorized"])
def test_real_wire_no_redirect_or_authentication_resend(wire, tmp_path, fault):
    service, state = wire
    journal, identifier, _ = prepare(tmp_path, service)
    try:
        state["fault"] = fault
        boundary = len(state["calls"])
        with pytest.raises(ProviderFailure):
            journal.execute(service, identifier)
        assert len(state["calls"][boundary:]) == 1
        assert journal.receipt(identifier)["unknown_deletions"] == 1
        assert len(state["ids"]) == 4
        assert (
            b"BODY_CREDENTIAL_SENTINEL"
            not in (tmp_path / "target-cleanup.sqlite3").read_bytes()
        )
    finally:
        journal.close()
