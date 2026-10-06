"""Typed Gmail target adapter.  It exposes insert and readback only."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from facet.contracts import ErrorCode, ProviderId, Role
from facet.db.codecs import RfcMessageId

from .retry import ProviderFailure, ProviderStage, execute

__all__ = (
    "TargetProfile",
    "TargetInsertResult",
    "TargetReadback",
    "TargetAdapter",
    "GmailTarget",
)


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


@dataclass(frozen=True, slots=True, repr=False)
class TargetReadback:
    message_id: ProviderId
    thread_id: ProviderId
    labels: tuple[str, ...]
    raw: bytes

    def __repr__(self) -> str:
        return (
            f"TargetReadback(message_id={self.message_id.value!r},"
            f"thread_id={self.thread_id.value!r},labels={len(self.labels)})"
        )


def _id(value: object) -> ProviderId:
    try:
        return ProviderId(value)
    except (TypeError, ValueError):
        raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.TARGET) from None


class TargetAdapter:
    role = Role.TARGET

    def __init__(self, service) -> None:
        self._service = service

    def profile(self):
        value = execute(
            self._service.users().getProfile(userId="me"),
            self.role,
            provider_stage=ProviderStage.PROFILE_PROBE,
        )
        return TargetProfile(
            value["emailAddress"],
            _id(value["historyId"]),
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
            provider_stage=ProviderStage.TARGET_INSERT,
        )
        try:
            return TargetInsertResult(
                _id(value["id"]),
                _id(value["threadId"]),
                None if value.get("historyId") is None else _id(value["historyId"]),
            )
        except (KeyError, TypeError, ValueError):
            raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.TARGET) from None

    def find_by_rfc_message_id(self, value: str):
        if type(value) is not RfcMessageId:
            raise ValueError("invalid_input")
        response = execute(
            self._service.users()
            .messages()
            .list(
                userId="me",
                q=(
                    f"rfc822msgid:{value.value}"
                    if value.value.startswith("<")
                    else f"rfc822msgid:<{value.value}>"
                ),
                includeSpamTrash=True,
                maxResults=100,
            ),
            self.role,
            provider_stage=ProviderStage.MESSAGE_GET,
        )
        try:
            return tuple(
                ProviderId(item["id"]) for item in response.get("messages", ())
            )
        except (KeyError, TypeError, ValueError):
            raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.TARGET) from None

    def readback(self, message_id: ProviderId) -> TargetReadback:
        if type(message_id) is not ProviderId:
            raise ValueError("invalid_input")
        value = execute(
            self._service.users()
            .messages()
            .get(userId="me", id=message_id.value, format="raw"),
            self.role,
            provider_stage=ProviderStage.MESSAGE_GET,
        )
        try:
            encoded = value["raw"]
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            labels = tuple(value.get("labelIds", ()))
            if any(type(label) is not str or not label for label in labels):
                raise ValueError
            return TargetReadback(_id(value["id"]), _id(value["threadId"]), labels, raw)
        except (KeyError, TypeError, ValueError):
            raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.TARGET) from None


GmailTarget = TargetAdapter
