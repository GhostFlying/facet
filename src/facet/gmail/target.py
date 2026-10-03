"""Typed Gmail target adapter.  It exposes insert and readback only."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from facet.contracts import ProviderId, Role

from .retry import execute

__all__ = ("TargetProfile", "TargetInsertResult", "TargetAdapter", "GmailTarget")


@dataclass(frozen=True, slots=True, repr=False)
class TargetProfile:
    account: str
    history_id: ProviderId
    messages_total: int
    threads_total: int

    def __repr__(self) -> str:
        return "<target profile>"


@dataclass(frozen=True, slots=True, repr=False)
class TargetInsertResult:
    message_id: ProviderId
    thread_id: ProviderId
    history_id: ProviderId | None

    def __repr__(self) -> str:
        return (
            f"TargetInsertResult(message_id={self.message_id.value!r},"
            f"thread_id={self.thread_id.value!r})"
        )


class TargetAdapter:
    role = Role.TARGET

    def __init__(self, service) -> None:
        self._service = service

    def profile(self):
        value = execute(self._service.users().getProfile(userId="me"), self.role)
        return TargetProfile(
            value["emailAddress"],
            ProviderId(value["historyId"]),
            int(value.get("messagesTotal", 0)),
            int(value.get("threadsTotal", 0)),
        )

    def insert(
        self,
        raw: bytes,
        *,
        thread_id: ProviderId | None = None,
        date_header: bool = True,
    ) -> TargetInsertResult:
        if type(raw) is not bytes or not raw:
            raise ValueError("invalid_input")
        body = {"raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")}
        if thread_id is not None:
            body["threadId"] = thread_id.value
        value = execute(
            self._service.users()
            .messages()
            .insert(
                userId="me",
                body=body,
                internalDateSource="dateHeader" if date_header else "receivedTime",
                neverMarkSpam=True,
            ),
            self.role,
        )
        return TargetInsertResult(
            ProviderId(value["id"]),
            ProviderId(value["threadId"]),
            None if value.get("historyId") is None else ProviderId(value["historyId"]),
        )

    def message_metadata(self, message_id: ProviderId):
        return execute(
            self._service.users()
            .messages()
            .get(userId="me", id=message_id.value, format="metadata"),
            self.role,
        )

    def thread_metadata(self, thread_id: ProviderId):
        return execute(
            self._service.users()
            .threads()
            .get(userId="me", id=thread_id.value, format="metadata"),
            self.role,
        )

    def find_by_rfc_message_id(self, value: str):
        if type(value) is not str or not value:
            raise ValueError("invalid_input")
        response = execute(
            self._service.users()
            .messages()
            .list(
                userId="me",
                q=f"rfc822msgid:<{value}>",
                includeSpamTrash=True,
                maxResults=100,
            ),
            self.role,
        )
        return tuple(ProviderId(item["id"]) for item in response.get("messages", ()))


GmailTarget = TargetAdapter
