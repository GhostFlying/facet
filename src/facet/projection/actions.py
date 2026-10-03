"""Closed readonly action-label producer seam.

This producer only turns typed History label facts into a private activation or
attention value. It deliberately does not publish rules, admit a thread, or
register arbitrary callbacks; the persistence owner will consume its result in
a later transaction slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from facet.contracts import (
    ErrorCode,
    LabelChange,
    ProviderId,
    Timestamp,
)
from facet.contracts.records import SourceEvent, SourceEventKeyLabelChanged
from facet.db.codecs import ActionKind, PrivateAddress, StorageFailure

if TYPE_CHECKING:
    from facet.gmail.credentials import AccountAddress

__all__ = (
    "PrivateActionLabelMap",
    "ActionMessageFact",
    "ActionActivation",
    "ActionAttentionReason",
    "ActionAttention",
    "ActionSourceReader",
    "ActionLabelProducer",
    "registered_action_producer_types",
)


def _fail(code=ErrorCode.INVALID_INPUT):
    raise StorageFailure(code)


@dataclass(frozen=True, slots=True, repr=False)
class PrivateActionLabelMap:
    add_sender_label_id: ProviderId
    add_domain_label_id: ProviderId
    blacklist_label_id: ProviderId

    def __post_init__(self) -> None:
        values = (
            self.add_sender_label_id,
            self.add_domain_label_id,
            self.blacklist_label_id,
        )
        if any(type(value) is not ProviderId for value in values):
            _fail()
        if len({value.value for value in values}) != len(values):
            _fail()

    def kind(self, label_id: ProviderId) -> ActionKind | None:
        if type(label_id) is not ProviderId:
            _fail()
        return {
            self.add_sender_label_id: ActionKind.ADD_SENDER,
            self.add_domain_label_id: ActionKind.ADD_DOMAIN,
            self.blacklist_label_id: ActionKind.BLACKLIST,
        }.get(label_id)


@dataclass(frozen=True, slots=True, repr=False)
class ActionMessageFact:
    source_message_id: ProviderId
    source_thread_id: ProviderId
    sender: PrivateAddress
    observed_at: Timestamp
    is_draft: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.source_message_id) is not ProviderId
            or type(self.source_thread_id) is not ProviderId
            or type(self.sender) is not PrivateAddress
            or type(self.observed_at) is not Timestamp
            or type(self.is_draft) is not bool
        ):
            _fail()

    def __repr__(self) -> str:
        return "<private action message fact>"

    __str__ = __repr__


class ActionAttentionReason(StrEnum):
    REMOVED_LABEL = "removed_label"
    UNKNOWN_LABEL = "unknown_label"
    NO_EXTERNAL_SENDER = "no_external_sender"
    AMBIGUOUS_EXTERNAL_SENDER = "ambiguous_external_sender"
    DUPLICATE_EVENT = "duplicate_event"
    DRAFT = "draft"


@dataclass(frozen=True, slots=True, repr=False)
class ActionActivation:
    event: SourceEventKeyLabelChanged
    kind: ActionKind
    source_thread_id: ProviderId
    sender: PrivateAddress

    def __post_init__(self) -> None:
        if (
            type(self.event) is not SourceEventKeyLabelChanged
            or self.event.change is not LabelChange.ADDED
            or type(self.kind) is not ActionKind
            or type(self.source_thread_id) is not ProviderId
            or type(self.sender) is not PrivateAddress
        ):
            _fail()
        if self.event.source_message_id.value == "":
            _fail()

    def __repr__(self) -> str:
        return "<private action activation>"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class ActionAttention:
    event: SourceEventKeyLabelChanged
    reason: ActionAttentionReason

    def __post_init__(self) -> None:
        if (
            type(self.event) is not SourceEventKeyLabelChanged
            or type(self.reason) is not ActionAttentionReason
        ):
            _fail()

    def __repr__(self) -> str:
        return "<private action attention>"

    __str__ = __repr__


class ActionSourceReader:
    """Provider-boundary protocol for typed facts only."""

    def get_thread_facts(
        self, source_thread_id: ProviderId
    ) -> tuple[ActionMessageFact, ...]:
        raise NotImplementedError


def _own(
    sender: PrivateAddress, own_addresses: tuple[AccountAddress | PrivateAddress, ...]
) -> bool:
    from facet.gmail.credentials import AccountAddress

    if type(sender) is not PrivateAddress or type(own_addresses) is not tuple:
        _fail()
    if any(
        type(address) not in {AccountAddress, PrivateAddress}
        for address in own_addresses
    ):
        _fail()
    sender_value = sender.value.casefold()
    return any(sender_value == address.value.casefold() for address in own_addresses)


class ActionLabelProducer:
    """The sole compiled readonly action-label producer."""

    def consume(
        self,
        event: SourceEvent,
        labels: PrivateActionLabelMap,
        source: ActionSourceReader,
        own_addresses: tuple[AccountAddress | PrivateAddress, ...],
    ) -> ActionActivation | ActionAttention:
        if (
            type(event) is not SourceEvent
            or type(labels) is not PrivateActionLabelMap
            or not hasattr(source, "get_thread_facts")
            or type(own_addresses) is not tuple
            or not own_addresses
        ):
            _fail()
        key = event.key
        if type(key) is not SourceEventKeyLabelChanged:
            _fail()
        if key.change is LabelChange.REMOVED:
            return ActionAttention(key, ActionAttentionReason.REMOVED_LABEL)
        kind = labels.kind(key.label_id)
        if kind is None:
            return ActionAttention(key, ActionAttentionReason.UNKNOWN_LABEL)
        if type(event.source_thread_id) is not ProviderId:
            _fail()
        try:
            facts = source.get_thread_facts(event.source_thread_id)
        except StorageFailure:
            raise
        except Exception:
            _fail()
        if type(facts) is not tuple:
            _fail()
        if any(type(fact) is not ActionMessageFact for fact in facts):
            _fail()
        if any(fact.source_thread_id != event.source_thread_id for fact in facts):
            _fail(ErrorCode.CONSISTENCY_FAILURE)
        fact_keys = {
            (
                fact.source_message_id,
                fact.source_thread_id,
                fact.sender,
                fact.observed_at,
            )
            for fact in facts
        }
        if len(fact_keys) != len(facts):
            return ActionAttention(key, ActionAttentionReason.DUPLICATE_EVENT)
        external = tuple(
            fact
            for fact in facts
            if not fact.is_draft and not _own(fact.sender, own_addresses)
        )
        if not external:
            if facts and all(fact.is_draft for fact in facts):
                return ActionAttention(key, ActionAttentionReason.DRAFT)
            return ActionAttention(key, ActionAttentionReason.NO_EXTERNAL_SENDER)
        ordered = sorted(
            external,
            key=lambda fact: (fact.observed_at.value, fact.source_message_id.value),
            reverse=True,
        )
        latest = ordered[0]
        if len(ordered) > 1 and (
            ordered[1].observed_at == latest.observed_at
            and ordered[1].source_message_id == latest.source_message_id
            and ordered[1].sender != latest.sender
        ):
            return ActionAttention(key, ActionAttentionReason.AMBIGUOUS_EXTERNAL_SENDER)
        return ActionActivation(key, kind, latest.source_thread_id, latest.sender)


def registered_action_producer_types() -> tuple[type, ...]:
    """Return the fixed shipping producer inventory; no plugin registration."""

    return (ActionLabelProducer,)
