"""Narrow, typed Gmail source adapter used by M2 producers.

Only the Gmail methods required by discovery, History and thread expansion are
exposed.  The service object is injected by the verified credential/profile
consumer; this module never discovers credentials or imports the spike.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import getaddresses
from enum import StrEnum

from facet.contracts import (
    ErrorCode,
    ProviderId,
    ProviderPageToken,
    Role,
    Timestamp,
    Visibility,
)
from facet.db.codecs import ActionKind, PrivateAddress
from facet.projection.actions import ActionMessageFact, PrivateActionLabelMap
from facet.projection.admission import DiscoveryCandidate
from facet.projection.rules import RuleInputError, normalize_sender

from .retry import ProviderFailure, ProviderStage, execute

__all__ = (
    "SourceProfile",
    "DiscoveryQuery",
    "DiscoveryItem",
    "DiscoveryPage",
    "HistoryPage",
    "HistoryMessage",
    "HistoryLabel",
    "HistoryRecord",
    "MessageMetadata",
    "ThreadMetadata",
    "CandidateAttentionReason",
    "CandidateAttention",
    "CandidateResult",
    "CandidatePage",
    "SourceAdapter",
    "GmailSource",
)


def _id(value: object) -> ProviderId:
    if not isinstance(value, str):
        raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.SOURCE)
    try:
        return ProviderId(value)
    except ValueError:
        raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.SOURCE) from None


def _token(value: object | None) -> ProviderPageToken | None:
    if value is None:
        return None
    try:
        return ProviderPageToken(value)
    except (TypeError, ValueError):
        raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.SOURCE) from None


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
class DiscoveryQuery:
    """Bounded provider candidate clauses for one source-window scan."""

    clauses: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.clauses) is not tuple or not self.clauses:
            raise ValueError("invalid_input")
        if any(
            type(clause) is not str
            or not clause
            or any(ord(char) < 0x20 for char in clause)
            for clause in self.clauses
        ):
            raise ValueError("invalid_input")

    def render(self, window: str) -> str:
        query = f"{window} {{{' '.join(self.clauses)}}}"
        if len(query.encode("utf-8")) > 4096:
            raise ValueError("invalid_input")
        return query


@dataclass(frozen=True, slots=True, repr=False)
class DiscoveryPage:
    items: tuple[DiscoveryItem, ...]
    next_page_token: ProviderPageToken | None
    result_size_estimate: int | None


@dataclass(frozen=True, slots=True, repr=False)
class HistoryPage:
    history_id: ProviderId
    records: tuple[HistoryRecord, ...]
    next_page_token: ProviderPageToken | None

    def __repr__(self) -> str:
        return (
            f"HistoryPage(history_id={self.history_id.value!r},"
            f"records={len(self.records)})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class HistoryMessage:
    message_id: ProviderId
    thread_id: ProviderId


@dataclass(frozen=True, slots=True, repr=False)
class HistoryLabel:
    message: HistoryMessage
    label_ids: tuple[ProviderId, ...]


@dataclass(frozen=True, slots=True, repr=False)
class HistoryRecord:
    record_id: ProviderId
    messages_added: tuple[HistoryMessage, ...]
    messages_deleted: tuple[HistoryMessage, ...]
    labels_added: tuple[HistoryLabel, ...]
    labels_removed: tuple[HistoryLabel, ...]


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


class CandidateAttentionReason(StrEnum):
    MISSING_METADATA = "missing_metadata"
    MULTIPLE_FROM = "multiple_from"
    MALFORMED_FROM = "malformed_from"
    UNSUPPORTED_LABELS = "unsupported_labels"
    INVALID_METADATA = "invalid_metadata"
    PROVIDER_FAILURE = "provider_failure"


@dataclass(frozen=True, slots=True, repr=False)
class CandidateAttention:
    reason: CandidateAttentionReason
    message_id: ProviderId
    thread_id: ProviderId

    def __post_init__(self) -> None:
        if (
            type(self.reason) is not CandidateAttentionReason
            or type(self.message_id) is not ProviderId
            or type(self.thread_id) is not ProviderId
        ):
            raise ValueError("invalid_input")

    def __repr__(self) -> str:
        return "<candidate attention>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class CandidateResult:
    candidate: DiscoveryCandidate | None = None
    attention: CandidateAttention | None = None

    def __post_init__(self) -> None:
        if type(self.candidate) not in {DiscoveryCandidate, type(None)} or type(
            self.attention
        ) not in {CandidateAttention, type(None)}:
            raise ValueError("invalid_input")
        if (self.candidate is None) == (self.attention is None):
            raise ValueError("invalid_input")

    def __repr__(self) -> str:
        return "<candidate result>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class CandidatePage:
    items: tuple[CandidateResult, ...]
    next_page_token: ProviderPageToken | None

    def __post_init__(self) -> None:
        if (
            type(self.items) is not tuple
            or any(type(item) is not CandidateResult for item in self.items)
            or type(self.next_page_token) not in {ProviderPageToken, type(None)}
        ):
            raise ValueError("invalid_input")

    def __repr__(self) -> str:
        return f"<candidate page items={len(self.items)}>"

    __str__ = __repr__


class SourceAdapter:
    """Gmail source calls with provider JSON reduced to typed facts."""

    role = Role.SOURCE

    def __init__(
        self,
        service,
        *,
        source_account: PrivateAddress | None = None,
    ) -> None:
        self._service = service
        self._source_account = source_account

    def profile(self) -> SourceProfile:
        value = execute(
            self._service.users().getProfile(userId="me"),
            self.role,
            provider_stage=ProviderStage.PROFILE_PROBE,
        )
        account = value.get("emailAddress")
        if not isinstance(account, str):
            raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role)
        if (
            self._source_account is not None
            and account.casefold() != self._source_account.value.casefold()
        ):
            raise ProviderFailure(ErrorCode.BINDING_MISMATCH, self.role)
        return SourceProfile(
            account,
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
        query: DiscoveryQuery | None = None,
    ) -> DiscoveryPage:
        if (
            window_start.tzinfo is None
            or window_end.tzinfo is None
            or window_start >= window_end
        ):
            raise ValueError("invalid_input")
        start = window_start.astimezone(UTC).strftime("%Y/%m/%d")
        end = window_end.astimezone(UTC).strftime("%Y/%m/%d")
        window = f"after:{start} before:{end}"
        if type(query) not in {DiscoveryQuery, type(None)}:
            raise ValueError("invalid_input")
        rendered_query = window if query is None else query.render(window)
        args = {
            "userId": "me",
            "q": rendered_query,
            "includeSpamTrash": False,
            "maxResults": 100,
        }
        if page_token is not None:
            args["pageToken"] = page_token.value
        value = execute(
            self._service.users().messages().list(**args),
            self.role,
            provider_stage=ProviderStage.MESSAGE_LIST,
        )
        items = []
        seen = set()
        for item in value.get("messages", ()):
            message_id = _id(item["id"])
            if message_id in seen:
                continue
            seen.add(message_id)
            items.append(DiscoveryItem(message_id, _id(item["threadId"])))
        return DiscoveryPage(
            tuple(items),
            _token(value.get("nextPageToken")),
            value.get("resultSizeEstimate"),
        )

    def discover_candidates(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        page_token: ProviderPageToken | None = None,
        source_account: PrivateAddress | None = None,
    ) -> CandidatePage:
        """Discover one closed candidate result for every listed message.

        Enumeration failures are deliberately allowed to cross the page
        boundary as a controlled ``ProviderFailure``.  Metadata failures are
        represented per item so a selected message is never silently dropped.
        """
        if (
            self._source_account is not None
            and source_account is not None
            and source_account != self._source_account
        ):
            raise ProviderFailure(ErrorCode.BINDING_MISMATCH, self.role)
        account = (
            self._source_account if self._source_account is not None else source_account
        )
        if type(account) is not PrivateAddress:
            raise ProviderFailure(ErrorCode.BINDING_PENDING, self.role)

        try:
            listed = self.discover(
                window_start=window_start, window_end=window_end, page_token=page_token
            )
        except ProviderFailure:
            raise
        except (AttributeError, KeyError, TypeError, ValueError):
            raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role) from None
        results: list[CandidateResult] = []
        for item in listed.items:
            results.append(
                self._candidate_result(
                    item,
                    account,
                )
            )
        return CandidatePage(tuple(results), listed.next_page_token)

    def candidate(self, item: DiscoveryItem) -> CandidateResult:
        """Fetch and authenticate one already-enumerated discovery item.

        Enumeration and candidate metadata are deliberately separate calls so
        the foreground producer can perform provider work outside its SQLite
        transaction while retaining the source binding owned by this adapter.
        """
        if type(item) is not DiscoveryItem:
            raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role)
        if type(self._source_account) is not PrivateAddress:
            raise ProviderFailure(ErrorCode.BINDING_PENDING, self.role)
        return self._candidate_result(
            item,
            self._source_account,
        )

    def _candidate_result(
        self,
        item: DiscoveryItem,
        account: PrivateAddress,
    ) -> CandidateResult:
        try:
            value = execute(
                self._service.users()
                .messages()
                .get(userId="me", id=item.message_id.value, format="metadata"),
                self.role,
                provider_stage=ProviderStage.MESSAGE_GET,
            )
        except ProviderFailure:
            return CandidateResult(
                attention=CandidateAttention(
                    CandidateAttentionReason.PROVIDER_FAILURE,
                    item.message_id,
                    item.thread_id,
                )
            )
        try:
            metadata = _strict_message(value)
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
            OSError,
        ):
            return CandidateResult(
                attention=CandidateAttention(
                    CandidateAttentionReason.INVALID_METADATA,
                    item.message_id,
                    item.thread_id,
                )
            )
        if (
            metadata.message_id != item.message_id
            or metadata.thread_id != item.thread_id
        ):
            return CandidateResult(
                attention=CandidateAttention(
                    CandidateAttentionReason.INVALID_METADATA,
                    item.message_id,
                    item.thread_id,
                )
            )
        state = _candidate_state(metadata)
        if isinstance(state, CandidateAttentionReason):
            return CandidateResult(
                attention=CandidateAttention(state, item.message_id, item.thread_id)
            )
        sender, visibility, is_draft = state
        observed_at = Timestamp(datetime.now(UTC))
        return CandidateResult(
            candidate=DiscoveryCandidate(
                source_message_id=item.message_id,
                source_thread_id=item.thread_id,
                sender=sender,
                source_account=account,
                visibility=visibility,
                is_draft=is_draft,
                observed_at=observed_at,
            )
        )

    def history(
        self, cursor: ProviderId, *, page_token: ProviderPageToken | None = None
    ) -> HistoryPage:
        args = {
            "userId": "me",
            "startHistoryId": cursor.value,
            "historyTypes": [
                "messageAdded",
                "messageDeleted",
                "labelAdded",
                "labelRemoved",
            ],
            "maxResults": 100,
        }
        if page_token is not None:
            args["pageToken"] = page_token.value
        value = execute(
            self._service.users().history().list(**args),
            self.role,
            provider_stage=ProviderStage.HISTORY_LIST,
        )
        records = tuple(_history_record(record) for record in value.get("history", ()))
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
            provider_stage=ProviderStage.MESSAGE_GET,
        )
        return _message(value)

    def thread_metadata(self, thread_id: ProviderId) -> ThreadMetadata:
        value = execute(
            self._service.users()
            .threads()
            .get(userId="me", id=thread_id.value, format="metadata"),
            self.role,
            provider_stage=ProviderStage.MESSAGE_GET,
        )
        try:
            return ThreadMetadata(
                _id(value["id"]),
                tuple(_strict_message(item) for item in value.get("messages", ())),
            )
        except (KeyError, TypeError, ValueError):
            raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role) from None

    def raw(
        self,
        message_id: ProviderId,
        *,
        thread_id: ProviderId | None = None,
        max_bytes: int | None = None,
    ) -> bytes:
        if (
            type(message_id) is not ProviderId
            or type(thread_id) not in {ProviderId, type(None)}
            or type(max_bytes) not in {int, type(None)}
            or (max_bytes is not None and max_bytes < 1)
        ):
            raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role)
        value = execute(
            self._service.users()
            .messages()
            .get(userId="me", id=message_id.value, format="raw"),
            self.role,
            provider_stage=ProviderStage.MESSAGE_GET,
        )
        try:
            if not isinstance(value, dict):
                raise ValueError
            if _id(value["id"]) != message_id or (
                thread_id is not None and _id(value["threadId"]) != thread_id
            ):
                raise ValueError
            encoded = value["raw"]
            if not isinstance(encoded, str):
                raise ValueError
            if max_bytes is not None:
                max_encoded = ((max_bytes + 2) // 3) * 4
                if len(encoded) > max_encoded:
                    raise ValueError
            decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            if max_bytes is not None and len(decoded) > max_bytes:
                raise ValueError
            return decoded
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
            raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role) from None

    def action_label_map(self, names=None) -> PrivateActionLabelMap | None:
        """Resolve exact configured action labels without writing Gmail.

        Missing fixed labels are a normal opt-in state: ordinary sync can
        continue, while any matching history work remains explicit attention.
        Duplicate fixed labels and provider failures stay hard typed errors.
        """
        names = names or {
            ActionKind.ADD_SENDER: "AI/AddSender",
            ActionKind.ADD_DOMAIN: "AI/AddDomain",
            ActionKind.BLACKLIST: "AI/BlackList",
        }
        value = execute(
            self._service.users().labels().list(userId="me"),
            self.role,
            provider_stage=ProviderStage.LABEL_LIST,
        )
        found = {}
        for label in value.get("labels", ()):
            if not isinstance(label, dict):
                raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role)
            name, identifier = label.get("name"), label.get("id")
            if type(name) is not str or type(identifier) is not str:
                raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role)
            if name in set(names.values()):
                if name in found:
                    raise ProviderFailure(ErrorCode.CONSISTENCY_FAILURE, self.role)
                found[name] = _id(identifier)
        if set(found) != set(names.values()):
            return None
        return PrivateActionLabelMap(
            found[names[ActionKind.ADD_SENDER]],
            found[names[ActionKind.ADD_DOMAIN]],
            found[names[ActionKind.BLACKLIST]],
        )

    def get_thread_facts(self, source_thread_id: ProviderId):
        """Return redacted sender/timestamp facts for action-label effects."""
        metadata = self.thread_metadata(source_thread_id)
        facts = []
        for message in metadata.messages:
            values = tuple(
                value for name, value in message.headers if name.casefold() == "from"
            )
            if len(values) != 1:
                raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role)
            addresses = tuple(getaddresses([values[0]]))
            if len(addresses) != 1 or not addresses[0][1]:
                raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role)
            try:
                sender = PrivateAddress(addresses[0][1])
            except (TypeError, ValueError):
                raise ProviderFailure(ErrorCode.INVALID_INPUT, self.role) from None
            facts.append(
                ActionMessageFact(
                    message.message_id,
                    metadata.thread_id,
                    sender,
                    Timestamp(message.internal_date),
                    "DRAFT" in message.labels,
                )
            )
        return tuple(facts)


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


def _strict_message(value: object) -> MessageMetadata:
    """Parse candidate metadata without the legacy timestamp fallback."""
    if not isinstance(value, dict):
        raise ValueError("invalid_input")
    payload = value.get("payload")
    labels = value.get("labelIds")
    if not isinstance(payload, dict) or not isinstance(labels, (list, tuple)):
        raise ValueError("invalid_input")
    if any(type(label) is not str for label in labels):
        raise ValueError("invalid_input")
    raw_headers = payload.get("headers")
    if not isinstance(raw_headers, (list, tuple)):
        raise ValueError("invalid_input")
    headers: list[tuple[str, str]] = []
    for header in raw_headers:
        if not isinstance(header, dict):
            raise ValueError("invalid_input")
        name = header.get("name")
        header_value = header.get("value")
        if type(name) is not str or type(header_value) is not str:
            raise ValueError("invalid_input")
        headers.append((name, header_value))
    raw_internal_date = value.get("internalDate")
    if type(raw_internal_date) is not str or not raw_internal_date.isdigit():
        raise ValueError("invalid_input")
    try:
        internal_date = datetime.fromtimestamp(int(raw_internal_date) / 1000, UTC)
    except (OverflowError, OSError, ValueError):
        raise ValueError("invalid_input") from None
    return MessageMetadata(
        _id(value["id"]),
        _id(value["threadId"]),
        tuple(labels),
        internal_date,
        tuple(headers),
    )


_SYSTEM_LABELS = frozenset(
    {
        "INBOX",
        "SENT",
        "TRASH",
        "SPAM",
        "DRAFT",
        "STARRED",
        "UNREAD",
        "IMPORTANT",
        "CATEGORY_PERSONAL",
        "CATEGORY_SOCIAL",
        "CATEGORY_PROMOTIONS",
        "CATEGORY_UPDATES",
        "CATEGORY_FORUMS",
        "CHAT",
    }
)


def _candidate_state(
    metadata: MessageMetadata,
) -> tuple[object, Visibility, bool] | CandidateAttentionReason:
    labels = set(metadata.labels)
    if any(
        label not in _SYSTEM_LABELS and not label.startswith("Label_")
        for label in labels
    ):
        return CandidateAttentionReason.UNSUPPORTED_LABELS
    from_values = tuple(
        value for name, value in metadata.headers if name.casefold() == "from"
    )
    if not from_values:
        return CandidateAttentionReason.MISSING_METADATA
    if len(from_values) != 1:
        return CandidateAttentionReason.MULTIPLE_FROM
    addresses = tuple(getaddresses([from_values[0]]))
    if len(addresses) != 1 or not addresses[0][1]:
        return CandidateAttentionReason.MALFORMED_FROM
    try:
        sender = normalize_sender(addresses[0][1])
    except (RuleInputError, ValueError):
        return CandidateAttentionReason.MALFORMED_FROM
    visibility = Visibility.NORMAL
    if "SPAM" in labels:
        visibility = Visibility.SPAM
    elif "TRASH" in labels:
        visibility = Visibility.TRASH
    return sender, visibility, "DRAFT" in labels


def _history_message(value: dict) -> HistoryMessage:
    try:
        message = value.get("message", value)
        return HistoryMessage(_id(message["id"]), _id(message["threadId"]))
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.SOURCE) from None


def _history_labels(value: dict) -> HistoryLabel:
    try:
        return HistoryLabel(
            _history_message(value),
            tuple(_id(label) for label in value.get("labelIds", ())),
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.SOURCE) from None


def _history_record(value: dict) -> HistoryRecord:
    try:
        return HistoryRecord(
            _id(value["id"]),
            tuple(_history_message(item) for item in value.get("messagesAdded", ())),
            tuple(_history_message(item) for item in value.get("messagesDeleted", ())),
            tuple(_history_labels(item) for item in value.get("labelsAdded", ())),
            tuple(_history_labels(item) for item in value.get("labelsRemoved", ())),
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.SOURCE) from None
