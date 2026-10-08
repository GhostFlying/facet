"""External Gmail HTTP fixture; production SDK, transport and state stay real."""

import base64
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


def install_route():
    """Redirect only the final Requests socket destination to the test server."""
    import requests

    original = requests.Session.request
    origin = os.environ["FACET_TEST_WIRE_ORIGIN"]

    def request(self, method, url, **kwargs):
        parsed = urlsplit(url)
        assert parsed.scheme == "https"
        assert parsed.hostname in {
            "gmail.googleapis.com",
            "www.googleapis.com",
            "oauth2.googleapis.com",
        }
        self.trust_env = False
        local = origin + parsed.path
        if parsed.query:
            local += "?" + parsed.query
        return original(self, method, local, **kwargs)

    requests.Session.request = request


class Mailbox:
    def __init__(self):
        self.revision = 1
        self.arrived_at = 0
        self.target = {}
        self.calls = []
        self.inserted_raw = []
        self.fault = None
        self.source_missing = False
        self.source_metadata_reads = 0
        self.historical = False
        self.discovery_queries = []
        self.discovery_failure = False
        self.gap = False
        self.expired_cursors = set()
        self.gap_page_failure = False
        self.catchup_page_failure = False
        self.gap_arrived_at = 0
        self.learn_sender = False
        self.readback_status = None
        self.read_reason = "authError"
        self.reject_insert_once = False
        self.refresh_error = None
        self.refresh_calls = []
        self.refresh_account = None
        self.refresh_scopes = None
        self.insert_reason = "authError"
        self.expired_profile_roles = set()

    def arrive(self):
        self.revision += 1
        self.arrived_at = int(time.time() * 1000) + 1

    def message(self, identifier, raw=False):
        sender = (
            "sender@example.com"
            if identifier
            in {
                "future-new",
                "historical-new",
                "blocked-new",
                "gap-new",
                "removed-new",
                "catchup-new",
            }
            else "other@example.com"
        )
        value = {
            "id": identifier,
            "threadId": "future-thread"
            if identifier == "future-gap"
            else identifier.split("-", 1)[0] + "-thread",
            "labelIds": ["DRAFT"] if identifier.endswith("-draft") else [],
            "internalDate": str(
                self.gap_arrived_at
                if identifier in {"gap-new", "removed-new", "catchup-new", "future-gap"}
                else self.arrived_at
                if identifier == "future-new"
                else int((time.time() - 10 * 86400) * 1000)
                if identifier.endswith("-new")
                else 1767225600000
            ),
            "payload": {
                "headers": [
                    {"name": "From", "value": sender},
                    {"name": "Message-ID", "value": f"<{identifier}@example.com>"},
                ]
            },
        }
        if raw:
            data = (
                f"From: {sender}\r\nMessage-ID: <{identifier}@example.com>\r\n"
                "Date: Thu, 01 Jan 2026 00:00:00 +0000\r\n"
                "Subject: WIRE_HEADER_SENTINEL\r\n\r\nWIRE_BODY_SENTINEL\r\n"
            ).encode()
            value["raw"] = base64.urlsafe_b64encode(data).decode().rstrip("=")
        return value

    def __enter__(self):
        mailbox = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, value, status=200, **headers):
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                parsed = urlsplit(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)
                mailbox.calls.append(("GET", path))
                source = "source" in self.headers["Authorization"]
                if path.endswith("/profile"):
                    role = "source" if source else "target"
                    if (
                        role in mailbox.expired_profile_roles
                        and "refreshed" not in self.headers["Authorization"]
                    ):
                        self.reply(
                            {"error": {"errors": [{"reason": "authError"}]}}, 401
                        )
                        return
                    self.reply(
                        {
                            "emailAddress": mailbox.refresh_account
                            if mailbox.refresh_account
                            and "refreshed" in self.headers["Authorization"]
                            else f"{role}@example.com",
                            "historyId": f"history-{mailbox.revision}",
                            "messagesTotal": len(mailbox.target) if not source else 3,
                            "threadsTotal": 1,
                        }
                    )
                elif path.endswith("/labels"):
                    self.reply(
                        {
                            "labels": [
                                {"id": "label-add-sender", "name": "Facet/AddSender"}
                            ]
                            if mailbox.learn_sender
                            else []
                        }
                    )
                elif path.endswith("/messages"):
                    if source:
                        mailbox.discovery_queries.append(query)
                        if mailbox.gap:
                            if query.get("pageToken") == ["gap-second"]:
                                if mailbox.gap_page_failure:
                                    self.reply(
                                        {"error": {"message": "WIRE_ERROR_SENTINEL"}},
                                        503,
                                    )
                                else:
                                    self.reply(
                                        {
                                            "messages": [
                                                {
                                                    "id": "removed-new",
                                                    "threadId": "removed-thread",
                                                }
                                            ]
                                        }
                                    )
                            else:
                                self.reply(
                                    {
                                        "messages": [
                                            {"id": "gap-new", "threadId": "gap-thread"},
                                            {
                                                "id": "historical-new",
                                                "threadId": "historical-thread",
                                            },
                                        ],
                                        "nextPageToken": "gap-second",
                                    }
                                )
                            return
                        if mailbox.historical:
                            if query.get("pageToken") == ["second"]:
                                if mailbox.discovery_failure:
                                    self.reply(
                                        {"error": {"message": "WIRE_ERROR_SENTINEL"}},
                                        503,
                                    )
                                else:
                                    self.reply(
                                        {
                                            "messages": [
                                                {
                                                    "id": "blocked-new",
                                                    "threadId": "blocked-thread",
                                                }
                                            ]
                                        }
                                    )
                            else:
                                self.reply(
                                    {
                                        "messages": [
                                            {
                                                "id": "historical-new",
                                                "threadId": "historical-thread",
                                            }
                                        ],
                                        "nextPageToken": "second",
                                    }
                                )
                            return
                    self.reply(
                        {
                            "messages": []
                            if source
                            else [
                                {"id": key, "threadId": value["threadId"]}
                                for key, value in mailbox.target.items()
                            ]
                        }
                    )
                elif path.endswith("/history"):
                    if query["startHistoryId"][0] in mailbox.expired_cursors:
                        self.reply({"error": {"message": "WIRE_ERROR_SENTINEL"}}, 404)
                        return
                    if mailbox.gap:
                        if query.get("pageToken") == ["catchup-second"]:
                            if mailbox.catchup_page_failure:
                                self.reply(
                                    {"error": {"message": "WIRE_ERROR_SENTINEL"}}, 503
                                )
                            else:
                                self.reply({"historyId": f"history-{mailbox.revision}"})
                        else:
                            self.reply(
                                {
                                    "historyId": f"history-{mailbox.revision}",
                                    "history": [
                                        {
                                            "id": f"catchup-record-{mailbox.revision}",
                                            "messagesAdded": [
                                                {
                                                    "message": {
                                                        "id": "catchup-new",
                                                        "threadId": "catchup-thread",
                                                    }
                                                }
                                            ],
                                        }
                                    ],
                                    "nextPageToken": "catchup-second",
                                }
                            )
                        return
                    rows = []
                    if mailbox.revision > 1 and query["startHistoryId"] != [
                        f"history-{mailbox.revision}"
                    ]:
                        rows = [
                            {
                                "id": f"record-{mailbox.revision}",
                                "messagesAdded": [
                                    {
                                        "message": {
                                            "id": "future-new",
                                            "threadId": "future-thread",
                                        }
                                    }
                                ],
                            }
                        ]
                        if mailbox.learn_sender:
                            rows[0]["labelsAdded"] = [
                                {
                                    "message": {
                                        "id": "future-new",
                                        "threadId": "future-thread",
                                    },
                                    "labelIds": ["label-add-sender"],
                                }
                            ]
                    self.reply(
                        {"historyId": f"history-{mailbox.revision}", "history": rows}
                    )
                elif "/threads/" in path:
                    prefix = path.rsplit("/", 1)[1].removesuffix("-thread")
                    self.reply(
                        {
                            "id": prefix + "-thread",
                            "messages": [
                                mailbox.message(mid)
                                for mid in (
                                    prefix + "-old",
                                    prefix + "-new",
                                    prefix + "-draft",
                                )
                            ]
                            + (
                                [mailbox.message("future-gap")]
                                if mailbox.gap and prefix == "future"
                                else []
                            ),
                        }
                    )
                elif "/messages/" in path:
                    identifier = path.rsplit("/", 1)[1]
                    if source:
                        raw = query.get("format") == ["raw"]
                        mailbox.source_metadata_reads += not raw
                        if mailbox.source_missing:
                            self.reply(
                                {"error": {"message": "WIRE_ERROR_SENTINEL"}}, 404
                            )
                        else:
                            self.reply(mailbox.message(identifier, raw=raw))
                    else:
                        if mailbox.readback_status:
                            self.reply(
                                {
                                    "error": {
                                        "errors": [{"reason": mailbox.read_reason}],
                                        "message": "WIRE_ERROR_SENTINEL",
                                    }
                                },
                                mailbox.readback_status,
                            )
                            return
                        value = mailbox.target.get(identifier)
                        self.reply(value or {}, 200 if value else 404)
                else:
                    self.reply({}, 404)

            def do_POST(self):
                data = self.rfile.read(int(self.headers["Content-Length"]))
                mailbox.calls.append(("POST", urlsplit(self.path).path))
                if urlsplit(self.path).path == "/token":
                    form = parse_qs(data.decode())
                    role = (
                        "source" if "source" in form["refresh_token"][0] else "target"
                    )
                    mailbox.refresh_calls.append(role)
                    if mailbox.refresh_error:
                        self.reply(
                            {
                                "error": mailbox.refresh_error,
                                "error_description": "WIRE_ERROR_SENTINEL",
                            },
                            400,
                        )
                    else:
                        scopes = "https://www.googleapis.com/auth/gmail.readonly"
                        if role == "target":
                            scopes += " https://www.googleapis.com/auth/gmail.insert"
                        self.reply(
                            {
                                "access_token": (
                                    f"facet-synthetic-{role}-refreshed-access"
                                ),
                                "expires_in": 3600,
                                "token_type": "Bearer",
                                "scope": mailbox.refresh_scopes or scopes,
                            }
                        )
                    return
                if self.headers.get("x-http-method-override") == "GET":
                    self.reply({"messages": []})
                    return
                body = json.loads(data)
                raw = base64.urlsafe_b64decode(
                    body["raw"] + "=" * (-len(body["raw"]) % 4)
                )
                mailbox.inserted_raw.append(raw)
                fault = mailbox.fault
                if mailbox.reject_insert_once:
                    mailbox.reject_insert_once = False
                    fault = 401
                if fault in {401, 403, 429, 503, 307, 308}:
                    self.reply(
                        {
                            "error": {
                                "message": "WIRE_ERROR_SENTINEL",
                                "errors": [{"reason": mailbox.insert_reason}],
                            }
                        },
                        fault,
                        Location="/gmail/v1/users/me/messages/redirected",
                        **{"Retry-After": "123"},
                    )
                    return
                identifier = f"target-{len(mailbox.target) + 1}"
                value = {
                    "id": identifier,
                    "threadId": body.get("threadId", "target-thread"),
                    "labelIds": [],
                    "raw": body["raw"],
                }
                mailbox.target[identifier] = value
                if fault == "lost_response":
                    mailbox.fault = None
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                else:
                    self.reply(value)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
