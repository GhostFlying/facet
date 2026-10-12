"""A small, read-only HTTP boundary for aggregate Facet status snapshots.

This module deliberately has no Gmail, database, or scheduler dependency. A
runtime owner can publish already-computed public envelopes to a provider;
request handling only reads that in-memory snapshot.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from facet import __version__
from facet.contracts import Freshness, PublicHealth, Role, Timestamp
from facet.db.codecs import timestamp_from_sql
from facet.status.models import (
    Activity,
    CheckState,
    Diagnostics,
    Issues,
    LatencyMetric,
    Pressure,
    Progress,
    PublicEnvelope,
    QueueCounts,
    RateMetric,
    RoleStatus,
    Rules,
    Status,
)
from facet.status.serialization import serialize_public

_ROUTES = {
    "/api/v1/status": "status",
    "/api/v1/progress": "progress",
    "/api/v1/issues": "issues",
    "/api/v1/rules": "rules",
    "/api/v1/activity": "activity",
    "/api/v1/diagnostics": "diagnostics",
    "/api/v1/reconcile": "reconcile",
}
_STATIC_ROOT = Path(__file__).with_name("static")


class SnapshotProvider(Protocol):
    """Memory/cache-only aggregate snapshot source for the HTTP boundary."""

    def snapshot(self, family: str) -> PublicEnvelope:
        """Return a public envelope without external I/O."""

    def ready(self) -> bool:
        """Return whether a readable aggregate snapshot is available."""

    def reconcile_snapshot(self) -> dict:
        """Return aggregate source-reconcile facts without mailbox details."""


def _timestamp() -> Timestamp:
    return Timestamp(datetime.now(UTC))


def serialize_reconcile_public(value: dict) -> dict:
    """Serialize the aggregate reconcile allowlist, never raw SQL rows."""
    fields = {
        "state",
        "ruleset_revision",
        "window_start",
        "window_end",
        "listed",
        "metadata_success",
        "metadata_404",
        "matched",
        "mapped",
        "queued",
        "reset",
        "remaining_issue",
        "created_at",
        "completed_at",
    }
    if type(value) is not dict or not set(value).issubset(fields):
        raise ValueError("invalid_input")
    result = {}
    for key, item in value.items():
        if key.endswith("_at") or key.startswith("window_"):
            result[key] = (
                None
                if item is None
                else timestamp_from_sql(item).value.astimezone().isoformat(
                    timespec="seconds"
                )
            )
        elif key == "state":
            if type(item) is not str or len(item) > 64:
                raise ValueError("invalid_input")
            result[key] = item
        else:
            if type(item) is not int or item < 0:
                raise ValueError("invalid_input")
            result[key] = item
    return {"data": result, "schema_version": 1}


def _unavailable_envelopes() -> dict[str, PublicEnvelope]:
    now = _timestamp()
    status = Status(
        None,
        PublicHealth.UNKNOWN,
        RoleStatus(Role.SOURCE, None, None, None, Freshness.UNAVAILABLE),
        RoleStatus(Role.TARGET, None, None, None, Freshness.UNAVAILABLE),
        None,
        None,
        None,
    )
    progress = Progress(
        None,
        False,
        None,
        None,
        None,
        None,
        None,
        QueueCounts(*([None] * 9)),
        None,
        None,
        None,
        RateMetric(None, "messages_per_second", 60, 0),
        LatencyMetric(None, None, "milliseconds", 60, 0),
    )
    diagnostics = Diagnostics(
        __version__,
        None,
        None,
        CheckState.UNAVAILABLE,
        CheckState.UNKNOWN,
        None,
        CheckState.UNKNOWN,
        CheckState.UNKNOWN,
        Pressure.UNKNOWN,
        Pressure.UNKNOWN,
        None,
        None,
    )
    activity = Activity(())
    return {
        "status": PublicEnvelope(
            status, 1, now, Freshness.UNAVAILABLE, None, "projection"
        ),
        "progress": PublicEnvelope(
            progress, 1, now, Freshness.UNAVAILABLE, None, "projection"
        ),
        "issues": PublicEnvelope(
            Issues(()), 1, now, Freshness.UNAVAILABLE, None, "projection"
        ),
        "rules": PublicEnvelope(
            Rules(()), 1, now, Freshness.UNAVAILABLE, None, "projection"
        ),
        "activity": PublicEnvelope(
            activity, 1, now, Freshness.UNAVAILABLE, None, "projection"
        ),
        "diagnostics": PublicEnvelope(
            diagnostics, 1, now, Freshness.UNAVAILABLE, None, "projection"
        ),
    }


class UnavailableSnapshotProvider:
    """Safe default used until a runtime publishes an aggregate snapshot."""

    def snapshot(self, family: str) -> PublicEnvelope:
        try:
            return _unavailable_envelopes()[family]
        except KeyError:
            raise ValueError("invalid snapshot family") from None

    def ready(self) -> bool:
        return False

    def reconcile_snapshot(self) -> dict:
        return {"state": "unavailable"}


class _Handler(BaseHTTPRequestHandler):
    """Fixed-output handler with no request or exception logging."""

    server_version = "Facet"
    sys_version = ""

    def log_message(self, _format: str, *_args) -> None:
        return

    def log_request(self, *_args) -> None:
        return

    def send_error(self, code: int, _message: str | None = None, _explain=None) -> None:
        error = (
            "method_not_allowed"
            if code == HTTPStatus.METHOD_NOT_ALLOWED
            else "not_found"
        )
        self._write_json(code, {"error": error})

    @property
    def provider(self) -> SnapshotProvider:
        return self.server.provider  # type: ignore[attr-defined]

    @property
    def static_body(self) -> bytes:
        return self.server.static_body  # type: ignore[attr-defined]

    def _write_bytes(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _write_json(self, code: int, value: dict) -> None:
        body = json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        self._write_bytes(code, "application/json; charset=utf-8", body)

    def _route(self) -> str | None:
        try:
            parsed = urlsplit(self.path)
        except ValueError:
            return None
        if (
            parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or parsed.hostname
        ):
            return None
        return parsed.path

    def do_GET(self) -> None:
        path = self._route()
        if path is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if path == "/healthz":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/readyz":
            try:
                ready = self.provider.ready()
            except Exception:
                ready = False
            self._write_json(
                HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "ready" if ready else "unavailable"},
            )
            return
        if path == "/":
            self._write_bytes(
                HTTPStatus.OK, "text/html; charset=utf-8", self.static_body
            )
            return
        family = _ROUTES.get(path)
        if family is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            if family == "reconcile":
                self._write_json(
                    HTTPStatus.OK,
                    serialize_reconcile_public(self.provider.reconcile_snapshot()),
                )
                return
            payload = serialize_public(self.provider.snapshot(family))
        except Exception:
            self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "unavailable"})
            return
        self._write_json(HTTPStatus.OK, payload)

    def do_HEAD(self) -> None:
        self._write_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

    do_POST = do_HEAD
    do_PUT = do_HEAD
    do_PATCH = do_HEAD
    do_DELETE = do_HEAD
    do_OPTIONS = do_HEAD
    do_TRACE = do_HEAD
    do_CONNECT = do_HEAD


class DashboardServer(HTTPServer):
    """Single-owner HTTP server; no worker pool or second sync process."""

    allow_reuse_address = True

    def __init__(self, address, provider: SnapshotProvider | None = None):
        self.provider = provider or UnavailableSnapshotProvider()
        self.static_body = (_STATIC_ROOT / "index.html").read_bytes()
        super().__init__(address, _Handler)

    def handle_error(self, _request, _client_address) -> None:
        """Do not write request data or exception details to stderr."""
        return


def serve_dashboard(host: str = "127.0.0.1", port: int = 8080, provider=None) -> None:
    """Serve the read-only boundary until interrupted."""

    server = DashboardServer((host, port), provider)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        return
    finally:
        server.server_close()
