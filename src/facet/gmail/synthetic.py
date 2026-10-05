"""Small deterministic provider transport used only by offline CLI tests."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from facet.contracts import Role

from .credential_models import AccountAddress, ProviderSecret

_SYNTHETIC_RAW = (
    b"From: sender@example.com\r\n"
    b"To: target@example.invalid\r\n"
    b"Message-ID: <synthetic@example.com>\r\n"
    b"Subject: Synthetic\r\n\r\nBody\r\n"
)


class _Request:
    def __init__(self, value):
        self._value = value

    def execute(self, *, num_retries):
        if num_retries != 0:
            raise ValueError("retries_disabled")
        return self._value


class _Messages:
    def __init__(self, service):
        self._service = service

    def list(self, **_kwargs):
        if self._service.role is Role.SOURCE:
            return _Request(
                {"messages": [{"id": "source-message", "threadId": "source-thread"}]}
            )
        return _Request(
            {
                "messages": [
                    {"id": message_id, "threadId": value["threadId"]}
                    for message_id, value in self._service._inserted.items()
                ]
            }
        )

    def get(self, *, id, format, **_kwargs):
        return _Request(self._service._message(id, format))

    def insert(self, *, body, **_kwargs):
        return _Request(self._service._insert(body))


class _History:
    def __init__(self, service):
        self._service = service

    def list(self, **_kwargs):
        return _Request({"historyId": "history-1", "history": []})


class _Threads:
    def __init__(self, service):
        self._service = service

    def get(self, *, id, **_kwargs):
        return _Request(self._service._thread(id))


class _Labels:
    def list(self, **_kwargs):
        return _Request({"labels": []})


class _Users:
    def __init__(self, service):
        self._service = service

    def getProfile(self, **_kwargs):
        return _Request(
            {"emailAddress": self._service.account, "historyId": "history-1"}
        )

    def messages(self):
        return _Messages(self._service)

    def history(self):
        return _History(self._service)

    def threads(self):
        return _Threads(self._service)

    def labels(self):
        return _Labels()


class SyntheticGmailService:
    def __init__(self, role: Role, account: str):
        self.role = role
        self.account = account
        self._inserted = {}
        self._raw = _SYNTHETIC_RAW

    def users(self):
        return _Users(self)

    def _message(self, message_id, format):
        if self.role is Role.TARGET:
            value = self._inserted[message_id]
            return {
                "id": message_id,
                "threadId": value["threadId"],
                "labelIds": [],
                "raw": base64.urlsafe_b64encode(value["raw"]).decode().rstrip("="),
                "payload": {"headers": []},
            }
        metadata = {
            "id": "source-message",
            "threadId": "source-thread",
            "labelIds": [],
            "internalDate": str(int(datetime.now(UTC).timestamp() * 1000)),
            "payload": {
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "target@example.invalid"},
                    {"name": "Message-ID", "value": "<synthetic@example.com>"},
                ]
            },
        }
        if format == "raw":
            metadata["raw"] = base64.urlsafe_b64encode(self._raw).decode().rstrip("=")
        return metadata

    def _thread(self, thread_id):
        return {
            "id": thread_id,
            "messages": [self._message("source-message", "metadata")],
        }

    def _insert(self, body):
        raw = base64.urlsafe_b64decode(body["raw"] + "=" * (-len(body["raw"]) % 4))
        message_id = f"target-message-{len(self._inserted) + 1}"
        thread_id = body.get("threadId", "target-thread")
        self._inserted[message_id] = {"raw": raw, "threadId": thread_id}
        return {"id": message_id, "threadId": thread_id, "historyId": "history-2"}


class SyntheticGmailServiceFactory:
    def __init__(self, source_account: str, target_account: str):
        self._services = {
            Role.SOURCE: SyntheticGmailService(Role.SOURCE, source_account),
            Role.TARGET: SyntheticGmailService(Role.TARGET, target_account),
        }

    def profile_account(self, role: Role, secret: ProviderSecret) -> AccountAddress:
        del secret
        return AccountAddress(self._services[role].account)

    def service(self, role: Role, snapshot):
        if snapshot.role is not role:
            raise ValueError("binding_mismatch")
        return self._services[role]
