"""Narrow, typed Gmail source adapter used by M2 producers.

Only the Gmail methods required by discovery, History and thread expansion are
exposed.  The service object is injected by the verified credential/profile
consumer; this module never discovers credentials or imports the spike.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime

from facet.contracts import ErrorCode, ProviderId, ProviderPageToken, Role

from .retry import ProviderFailure, execute

__all__ = (
    "SourceProfile",
    "DiscoveryItem",
    "DiscoveryPage",
    "HistoryPage",
    "MessageMetadata",
    "ThreadMetadata",
    "SourceAdapter",
    "GmailSource",
)


def _id(value: object) -> ProviderId:
    if not isinstance(value, str):
        raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.SOURCE)
    return ProviderId(value)


def _token(value: object | None) -> ProviderPageToken | None:
    return None if value is None else ProviderPageToken(value)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.isdigit():
        return datetime.now(UTC)
    return datetime.fromtimestamp(int(value) / 1000, UTC)


@dataclass(frozen=True, slots=True, repr=False)
class SourceProfile:
    account: str
    history_id: ProviderId
    messages_total: int
    threads_total: int

    def __repr__(self) -> str:
        return "<source profile>"


@dataclass(frozen=True, slots=True, repr=False)
class DiscoveryItem:
    message_id: ProviderId
    thread_id: ProviderId


@dataclass(frozen=True, slots=True, repr=False)
class DiscoveryPage:
    items: tuple[DiscoveryItem, ...]
    next_page_token: ProviderPageToken | None
    result_size_estimate: int | None


@dataclass(frozen=True, slots=True, repr=False)
class HistoryPage:
    history_id: ProviderId
    records: tuple[dict, ...]
    next_page_token: ProviderPageToken | None

    def __repr__(self) -> str:
        return (
            f"HistoryPage(history_id={self.history_id.value!r},"
            f"records={len(self.records)})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class MessageMetadata:
    message_id: ProviderId
    thread_id: ProviderId
    labels: tuple[str, ...]
    internal_date: datetime
    headers: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True, repr=False)
class ThreadMetadata:
    thread_id: ProviderId
    messages: tuple[MessageMetadata, ...]


class SourceAdapter:
    """Gmail source calls with provider JSON reduced to typed facts."""

    role = Role.SOURCE

    def __init__(self, service) -> None:
        self._service = service

    def profile(self) -> SourceProfile:
        value = execute(self._service.users().getProfile(userId="me"), self.role)
        return SourceProfile(
            value["emailAddress"],
            _id(value["historyId"]),
            int(value.get("messagesTotal", 0)),
            int(value.get("threadsTotal", 0)),
        )

    def discover(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        page_token: ProviderPageToken | None = None,
    ) -> DiscoveryPage:
        if (
            window_start.tzinfo is None
            or window_end.tzinfo is None
            or window_start >= window_end
        ):
            raise ValueError("invalid_input")
        start = window_start.astimezone(UTC).strftime("%Y/%m/%d")
        end = window_end.astimezone(UTC).strftime("%Y/%m/%d")
        query = f"after:{start} before:{end}"
        args = {
            "userId": "me",
            "q": query,
            "includeSpamTrash": False,
            "maxResults": 100,
        }
        if page_token is not None:
            args["pageToken"] = page_token.value
        value = execute(self._service.users().messages().list(**args), self.role)
        return DiscoveryPage(
            tuple(
                DiscoveryItem(_id(item["id"]), _id(item["threadId"]))
                for item in value.get("messages", ())
            ),
            _token(value.get("nextPageToken")),
            value.get("resultSizeEstimate"),
        )

    def history(
        self, cursor: ProviderId, *, page_token: ProviderPageToken | None = None
    ) -> HistoryPage:
        args = {
            "userId": "me",
            "startHistoryId": cursor.value,
            "historyTypes": ["messageAdded", "labelAdded", "labelRemoved"],
            "maxResults": 100,
        }
        if page_token is not None:
            args["pageToken"] = page_token.value
        value = execute(self._service.users().history().list(**args), self.role)
        records = tuple(value.get("history", ()))
        return HistoryPage(
            _id(value.get("historyId", cursor.value)),
            records,
            _token(value.get("nextPageToken")),
        )

    def message_metadata(self, message_id: ProviderId) -> MessageMetadata:
        value = execute(
            self._service.users()
            .messages()
            .get(userId="me", id=message_id.value, format="metadata"),
            self.role,
        )
        return _message(value)

    def thread_metadata(self, thread_id: ProviderId) -> ThreadMetadata:
        value = execute(
            self._service.users()
            .threads()
            .get(userId="me", id=thread_id.value, format="metadata"),
            self.role,
        )
        return ThreadMetadata(
            _id(value["id"]),
            tuple(_message(item) for item in value.get("messages", ())),
        )

    def raw(self, message_id: ProviderId) -> bytes:
        value = execute(
            self._service.users()
            .messages()
            .get(userId="me", id=message_id.value, format="raw"),
            self.role,
        )
        encoded = value.get("raw", "")
        try:
            return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except (ValueError, TypeError):
            raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role) from None


GmailSource = SourceAdapter


def _message(value: dict) -> MessageMetadata:
    payload = value.get("payload", {})
    headers = tuple(
        (str(item.get("name", "")), str(item.get("value", "")))
        for item in payload.get("headers", ())
    )
    return MessageMetadata(
        _id(value["id"]),
        _id(value["threadId"]),
        tuple(value.get("labelIds", ())),
        _timestamp(value.get("internalDate")),
        headers,
    )
