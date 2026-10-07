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
        assert parsed.hostname in {"gmail.googleapis.com", "www.googleapis.com"}
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

    def arrive(self):
        self.revision += 1
        self.arrived_at = int(time.time() * 1000) + 1

    def message(self, identifier, raw=False):
        sender = (
            "sender@example.com" if identifier == "future-new" else "other@example.com"
        )
        value = {
            "id": identifier,
            "threadId": "future-thread",
            "labelIds": ["DRAFT"] if identifier == "future-draft" else [],
            "internalDate": str(
                self.arrived_at if identifier == "future-new" else 1767225600000
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
                    self.reply(
                        {
                            "emailAddress": f"{role}@example.com",
                            "historyId": f"history-{mailbox.revision}",
                            "messagesTotal": len(mailbox.target) if not source else 3,
                            "threadsTotal": 1,
                        }
                    )
                elif path.endswith("/labels"):
                    self.reply({"labels": []})
                elif path.endswith("/messages"):
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
                    self.reply(
                        {"historyId": f"history-{mailbox.revision}", "history": rows}
                    )
                elif "/threads/" in path:
                    self.reply(
                        {
                            "id": "future-thread",
                            "messages": [
                                mailbox.message(mid)
                                for mid in ("future-old", "future-new", "future-draft")
                            ],
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
                        value = mailbox.target.get(identifier)
                        self.reply(value or {}, 200 if value else 404)
                else:
                    self.reply({}, 404)

            def do_POST(self):
                data = self.rfile.read(int(self.headers["Content-Length"]))
                mailbox.calls.append(("POST", urlsplit(self.path).path))
                if self.headers.get("x-http-method-override") == "GET":
                    self.reply({"messages": []})
                    return
                body = json.loads(data)
                raw = base64.urlsafe_b64decode(
                    body["raw"] + "=" * (-len(body["raw"]) % 4)
                )
                mailbox.inserted_raw.append(raw)
                fault = mailbox.fault
                if fault in {401, 429, 503, 307, 308}:
                    self.reply(
                        {"error": {"message": "WIRE_ERROR_SENTINEL"}},
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
