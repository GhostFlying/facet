"""Scriptable Google-shaped facts, not a Facet adapter or business model.

All raw/provider error data remains in memory. Controller-only setup knowledge
is never emitted as a provenance, scope, binding or authenticity oracle.
"""

import base64
import copy
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import RLock

from .clock import Clock
from .faults import Faults
from .transport import Transport, TransportFactory


class ResponseLost(ConnectionError):
    def __init__(self) -> None:
        super().__init__("synthetic response unavailable")


@dataclass(frozen=True)
class HttpFailure:
    status: int
    body: bytes = b'{"error":{"message":"synthetic failure"}}'
    headers: tuple[tuple[str, str], ...] = ()

    def raise_error(self) -> None:
        from googleapiclient.errors import HttpError
        from httplib2 import Response

        response = Response({"status": str(self.status), **dict(self.headers)})
        raise HttpError(response, self.body, uri="https://synthetic.invalid/")


@dataclass(frozen=True)
class InsertReply:
    effect: bool = True
    lose_response: bool = False
    thread_id: str | None = None
    rfc_id: str | None = None
    search_visible: bool = False
    internal_date: str = "1767225600000"


@dataclass
class _Message:
    identifier: str
    thread: str
    raw: bytes
    labels: list[str]
    internal_date: str
    rfc_id: str | None
    searchable: bool
    payload: dict


@dataclass
class _Mailbox:
    profile: dict
    labels: list[dict] = field(default_factory=list)
    messages: dict[str, _Message] = field(default_factory=dict)
    counter: int = 0


@dataclass(frozen=True)
class _Step:
    arguments: dict
    result: dict | HttpFailure | InsertReply


class Controller:
    """Test owner retains this object; application receives only service views."""

    def __init__(
        self, clock: Clock, faults: Faults, *, raw_budget: int = 64_000_000
    ) -> None:
        if type(raw_budget) is not int or not 1 <= raw_budget <= 64_000_000:
            raise ValueError("invalid fixture raw budget")
        self.clock = clock
        self.faults = faults
        self.transports = TransportFactory(clock)
        self._lock = RLock()
        self._raw_budget = raw_budget
        self._raw_size = 0
        self._boxes = {
            role: _Mailbox(
                {
                    "emailAddress": role + "@example.invalid",
                    "messagesTotal": 0,
                    "threadsTotal": 0,
                    "historyId": "701",
                }
            )
            for role in ("source", "target")
        }
        self._scripts: dict[tuple[str, str], deque[_Step]] = defaultdict(deque)

    def profile(self, role: str, facts: dict) -> None:
        if set(facts) != {"emailAddress", "messagesTotal", "threadsTotal", "historyId"}:
            raise ValueError("invalid profile fields")
        if (
            not isinstance(facts["emailAddress"], str)
            or not isinstance(facts["historyId"], str)
            or not facts["historyId"]
            or any(
                type(facts[k]) is not int or facts[k] < 0
                for k in ("messagesTotal", "threadsTotal")
            )
        ):
            raise ValueError("invalid profile values")
        with self._lock:
            self._box(role).profile = copy.deepcopy(facts)

    def labels(self, role: str, facts: list[dict]) -> None:
        _validate_response("labels.list", {"labels": facts})
        with self._lock:
            self._box(role).labels = copy.deepcopy(facts)

    def seed(
        self,
        role: str,
        identifier: str,
        thread: str,
        raw: bytes,
        *,
        labels: tuple[str, ...] = (),
        internal_date: str = "1767225600000",
        rfc_id: str | None = None,
        searchable: bool = True,
        payload: dict | None = None,
    ) -> None:
        if not isinstance(raw, bytes) or len(raw) > 35_000_000:
            raise ValueError("invalid synthetic raw")
        _validate_message(
            {
                "id": identifier,
                "threadId": thread,
                "labelIds": list(labels),
                "internalDate": internal_date,
                "payload": payload or {"headers": []},
            }
        )
        with self._lock:
            box = self._box(role)
            if identifier in box.messages or len(box.messages) >= 1000:
                raise ValueError("duplicate or excessive fixture message")
            if self._raw_size + len(raw) > self._raw_budget:
                raise ValueError("fixture raw budget exceeded")
            self._raw_size += len(raw)
            box.messages[identifier] = _Message(
                identifier,
                thread,
                raw,
                list(labels),
                internal_date,
                rfc_id,
                searchable,
                copy.deepcopy(payload or {"headers": []}),
            )

    def visibility(self, role: str, identifier: str, visible: bool) -> None:
        with self._lock:
            self._box(role).messages[identifier].searchable = visible

    def remove_source_fact(self, identifier: str) -> None:
        """Simulate source loss; this is not an exposed delete API."""
        with self._lock:
            removed = self._box("source").messages.pop(identifier)
            self._raw_size -= len(removed.raw)

    def identifiers(self, role: str) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._box(role).messages)

    def script(
        self,
        role: str,
        method: str,
        arguments: dict,
        result: dict | HttpFailure | InsertReply,
    ) -> None:
        from .transport import METHODS

        if method not in METHODS or not isinstance(
            result, dict | HttpFailure | InsertReply
        ):
            raise ValueError("invalid provider script")
        if isinstance(result, InsertReply) and method != "messages.insert":
            raise ValueError("insert outcome on non-insert script")
        if method == "profile.get" and isinstance(result, dict):
            raise ValueError("profile facts use the validated profile controller")
        if isinstance(result, dict):
            _validate_response(method, result)
        with self._lock:
            self._box(role)
            queue = self._scripts[role, method]
            if len(queue) >= 1000:
                raise ValueError("provider script budget exceeded")
            queue.append(_Step(copy.deepcopy(arguments), copy.deepcopy(result)))

    def service(
        self,
        role: str,
        *,
        scopes: frozenset[str] = frozenset(),
        transport: Transport | None = None,
    ) -> "Service":
        self._box(role)
        return Service(self, role, scopes, transport or self.transports.new())

    def assert_consumed(self) -> None:
        with self._lock:
            if any(self._scripts.values()):
                raise AssertionError("unconsumed provider script")

    def _box(self, role: str) -> _Mailbox:
        if role not in self._boxes:
            raise ValueError("invalid synthetic mailbox role")
        return self._boxes[role]

    def _run(self, role: str, method: str, args: dict, scopes: frozenset[str]) -> dict:
        self.faults.hit("provider.before_execute")
        with self._lock:
            queue = self._scripts[role, method]
            if queue:
                if queue[0].arguments != args:
                    raise AssertionError("unexpected provider call arguments")
                result = queue.popleft().result
            else:
                result = None
        if isinstance(result, HttpFailure):
            result.raise_error()
        if method == "messages.insert":
            if role != "target" or "gmail.insert" not in scopes:
                HttpFailure(403).raise_error()
            if result is not None and not isinstance(result, InsertReply):
                raise ValueError("insert script requires an effect outcome")
            return self._insert(role, args, result or InsertReply())
        if method == "messages.modify":
            if "gmail.modify" not in scopes:
                HttpFailure(403).raise_error()
            if not isinstance(result, dict):
                raise AssertionError("label mutation requires an explicit script")
            self.faults.hit("provider.before_effect")
            with self._lock:
                mail = self._get(role, args["id"])
                labels = set(mail.labels)
                labels.difference_update(args["body"].get("removeLabelIds", []))
                labels.update(args["body"].get("addLabelIds", []))
                mail.labels = sorted(labels)
            self.faults.hit("provider.after_effect")
        if isinstance(result, dict):
            response = copy.deepcopy(result)
        else:
            with self._lock:
                response = self._read(role, method, args)
        _validate_response(method, response)
        if method == "messages.get":
            response = _get_format(
                response, args["format"], args.get("metadataHeaders")
            )
        elif method == "threads.get":
            response["messages"] = [
                _get_format(mail, args["format"], args.get("metadataHeaders"))
                for mail in response.get("messages", [])
            ]
            if args["format"] != "full":
                response.pop("snippet", None)
        self.faults.hit("provider.before_response")
        return response

    def _get(self, role: str, identifier: str) -> _Message:
        mail = self._box(role).messages.get(identifier)
        if mail is None:
            HttpFailure(404).raise_error()
        return mail

    def _wire(self, mail: _Message, format: str) -> dict:
        result = {
            "id": mail.identifier,
            "threadId": mail.thread,
            "labelIds": list(mail.labels),
            "internalDate": mail.internal_date,
            "sizeEstimate": len(mail.raw),
        }
        if format == "raw":
            result["raw"] = base64.urlsafe_b64encode(mail.raw).decode().rstrip("=")
        elif format == "full":
            result["payload"] = copy.deepcopy(mail.payload)
        elif format == "metadata":
            result["payload"] = {
                "headers": copy.deepcopy(mail.payload.get("headers", []))
            }
        return result

    def _read(self, role: str, method: str, args: dict) -> dict:
        box = self._box(role)
        if method == "profile.get":
            return copy.deepcopy(box.profile)
        if method == "labels.list":
            return {"labels": copy.deepcopy(box.labels)}
        if method == "messages.get":
            return self._wire(self._get(role, args["id"]), args["format"])
        if method == "threads.get":
            mails = [m for m in box.messages.values() if m.thread == args["id"]]
            if not mails:
                HttpFailure(404).raise_error()
            return {
                "id": args["id"],
                "historyId": box.profile["historyId"],
                "messages": [self._wire(m, args["format"]) for m in mails],
            }
        if method == "messages.list":
            query = args.get("q", "")
            if args.get("pageToken") is not None:
                raise AssertionError("unexpected provider page token")
            if query and not re.fullmatch(r"rfc822msgid:<[^\s<>]+>", query):
                raise AssertionError("unsupported unscripted provider query")
            mails = [m for m in box.messages.values() if m.searchable]
            if query:
                mails = [m for m in mails if m.rfc_id == query[len("rfc822msgid:") :]]
            if not args.get("includeSpamTrash", False):
                mails = [
                    m for m in mails if not {"SPAM", "TRASH"}.intersection(m.labels)
                ]
            if args.get("labelIds"):
                mails = [m for m in mails if set(args["labelIds"]).issubset(m.labels)]
            limit = args.get("maxResults", 100)
            if len(mails) > limit:
                raise AssertionError(
                    "multi-page listing requires explicit page scripts"
                )
            result = {"resultSizeEstimate": len(mails)}
            if mails:
                result["messages"] = [
                    {"id": m.identifier, "threadId": m.thread} for m in mails
                ]
            return result
        raise AssertionError("provider operation requires an explicit script")

    def _insert(self, role: str, args: dict, outcome: InsertReply) -> dict:
        if not outcome.effect and not outcome.lose_response:
            raise ValueError("non-effect requires a failure outcome")
        raw = _decode(args["body"]["raw"])
        self.faults.hit("provider.before_effect")
        response = {}
        if outcome.effect:
            with self._lock:
                box = self._box(role)
                box.counter += 1
                identifier = "inserted-" + str(box.counter)
                while identifier in box.messages:
                    box.counter += 1
                    identifier = "inserted-" + str(box.counter)
                thread = outcome.thread_id or args["body"].get("threadId") or identifier
                self.seed(
                    role,
                    identifier,
                    thread,
                    raw,
                    labels=tuple(args["body"].get("labelIds", [])),
                    internal_date=outcome.internal_date,
                    rfc_id=outcome.rfc_id,
                    searchable=outcome.search_visible,
                )
                response = {
                    "id": identifier,
                    "threadId": thread,
                    "labelIds": list(args["body"].get("labelIds", [])),
                }
        self.faults.hit("provider.after_effect")
        self.faults.hit("provider.before_response")
        if outcome.lose_response:
            raise ResponseLost()
        return response


def _get_format(value: dict, format: str, requested_headers: list[str] | None) -> dict:
    """Apply get-format projection to seeded and explicitly scripted responses."""
    result = copy.deepcopy(value)
    if format != "raw":
        result.pop("raw", None)
    if format in {"minimal", "raw"}:
        result.pop("payload", None)
    if format in {"minimal", "metadata"}:
        result.pop("snippet", None)
    if format == "metadata":
        headers = result.get("payload", {}).get("headers", [])
        # An empty repeated argument sends no header filters, as when omitted.
        if requested_headers:
            selected = {name.lower() for name in requested_headers}
            headers = [
                header for header in headers if header["name"].lower() in selected
            ]
        result["payload"] = {"headers": headers}
    return result


def _object(value: object, allowed: set[str], required: set[str] = frozenset()) -> None:
    if (
        not isinstance(value, dict)
        or set(value) - allowed
        or not required <= set(value)
    ):
        raise ValueError("invalid provider wire fields")


def _list(value: object) -> list:
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError("invalid provider wire collection")
    return value


def _strings(value: object) -> None:
    if any(not isinstance(item, str) or not item for item in _list(value)):
        raise ValueError("invalid provider string collection")


def _payload(value: dict, depth: int = 0) -> None:
    if depth > 16:
        raise ValueError("provider payload depth exceeded")
    _object(value, {"partId", "mimeType", "filename", "headers", "body", "parts"})
    for header in _list(value.get("headers", [])):
        _object(header, {"name", "value"}, {"name", "value"})
        if any(not isinstance(header[key], str) for key in ("name", "value")):
            raise ValueError("invalid provider header")
    if "body" in value:
        _object(value["body"], {"size", "data", "attachmentId"})
    for part in _list(value.get("parts", [])):
        _payload(part, depth + 1)


def _validate_message(value: dict, *, minimal: bool = False) -> None:
    allowed = {"id", "threadId"}
    if not minimal:
        allowed |= {
            "labelIds",
            "snippet",
            "historyId",
            "internalDate",
            "payload",
            "sizeEstimate",
            "raw",
        }
    _object(value, allowed, {"id"})
    for key in ("id", "threadId", "historyId", "internalDate"):
        if key in value and (not isinstance(value[key], str) or not value[key]):
            raise ValueError("invalid provider string value")
    if "labelIds" in value:
        _strings(value["labelIds"])
    if "payload" in value:
        _payload(value["payload"])


def _validate_response(method: str, value: dict) -> None:
    if method == "profile.get":
        _object(value, {"emailAddress", "messagesTotal", "threadsTotal", "historyId"})
    elif method == "labels.list":
        _object(value, {"labels"})
        for label in _list(value.get("labels", [])):
            _object(label, {"id", "name", "type"}, {"id", "name", "type"})
            if any(not isinstance(item, str) for item in label.values()):
                raise ValueError("invalid provider label value")
    elif method in {"messages.get", "messages.modify"}:
        _validate_message(value)
    elif method == "messages.list":
        _object(value, {"messages", "nextPageToken", "resultSizeEstimate"})
        for mail in _list(value.get("messages", [])):
            _validate_message(mail, minimal=True)
    elif method == "threads.get":
        _object(value, {"id", "historyId", "messages", "snippet"}, {"id"})
        for mail in _list(value.get("messages", [])):
            _validate_message(mail)
    elif method == "history.list":
        _object(value, {"history", "nextPageToken", "historyId"})
        for record in _list(value.get("history", [])):
            _object(
                record,
                {
                    "id",
                    "messages",
                    "messagesAdded",
                    "messagesDeleted",
                    "labelsAdded",
                    "labelsRemoved",
                },
                {"id"},
            )
            if not isinstance(record["id"], str):
                raise ValueError("invalid provider history string")
            for mail in _list(record.get("messages", [])):
                _validate_message(mail)
            for kind in (
                "messagesAdded",
                "messagesDeleted",
                "labelsAdded",
                "labelsRemoved",
            ):
                for event in _list(record.get(kind, [])):
                    labels = kind.startswith("labels")
                    fields = {"message", "labelIds"} if labels else {"message"}
                    _object(event, fields, fields)
                    _validate_message(event["message"])
                    if labels:
                        _strings(event["labelIds"])
    else:
        raise ValueError("unsupported scripted provider response")
    if "nextPageToken" in value and not isinstance(value["nextPageToken"], str):
        raise ValueError("invalid provider page token")
    if "historyId" in value and not isinstance(value["historyId"], str):
        raise ValueError("invalid provider history string")


def _decode(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]*={0,2}", value):
        raise ValueError("invalid synthetic raw encoding")
    if len(value) > 47_000_000:
        raise ValueError("synthetic raw budget exceeded")
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except ValueError:
        raise ValueError("invalid synthetic raw encoding") from None
    if len(raw) > 35_000_000:
        raise ValueError("synthetic raw budget exceeded")
    return raw


class Request:
    def __init__(self, service: "Service", method: str, arguments: dict) -> None:
        self._service = service
        self._method = method
        self._arguments = copy.deepcopy(arguments)

    def execute(self, http=None, num_retries: int = 0) -> dict:
        if http is not None or num_retries != 0:
            raise ValueError("fake requires its own transport and no implicit retries")
        raw_bytes = 0
        if self._method == "messages.insert":
            raw_bytes = len(_decode(self._arguments["body"]["raw"]))
        with self._service.transport.call(self._method, raw_bytes):
            return self._service._controller._run(
                self._service._role,
                self._method,
                self._arguments,
                self._service._scopes,
            )


class Service:
    def __init__(
        self,
        controller: Controller,
        role: str,
        scopes: frozenset[str],
        transport: Transport,
    ) -> None:
        self._controller = controller
        self._role = role
        self._scopes = scopes
        self.transport = transport

    def users(self) -> "Service":
        return self

    def getProfile(self, *, userId: str) -> Request:
        return self._request("profile.get", {"userId": userId})

    def messages(self) -> "Resource":
        return Resource(self, "messages")

    def threads(self) -> "Resource":
        return Resource(self, "threads")

    def history(self) -> "Resource":
        return Resource(self, "history")

    def labels(self) -> "Resource":
        return Resource(self, "labels")

    def _request(self, method: str, arguments: dict) -> Request:
        if arguments.get("userId") != "me":
            raise ValueError("synthetic service requires explicit me selector")
        return Request(self, method, arguments)


class Resource:
    def __init__(self, service: Service, resource: str) -> None:
        self._service = service
        self._resource = resource

    def list(self, **kwargs) -> Request:
        allowed = {
            "messages": {
                "userId",
                "q",
                "pageToken",
                "includeSpamTrash",
                "maxResults",
                "labelIds",
            },
            "history": {
                "userId",
                "startHistoryId",
                "pageToken",
                "historyTypes",
                "labelId",
                "maxResults",
            },
            "labels": {"userId"},
        }
        self._validate(kwargs, allowed.get(self._resource, set()))
        if self._resource == "history" and not isinstance(
            kwargs.get("startHistoryId"), str
        ):
            raise ValueError("history cursor must be a string")
        if self._resource == "history" and not kwargs["startHistoryId"]:
            raise ValueError("history cursor must be a string")
        if "maxResults" in kwargs and (
            type(kwargs["maxResults"]) is not int
            or not 1 <= kwargs["maxResults"] <= 500
        ):
            raise ValueError("invalid provider page size")
        return self._service._request(self._resource + ".list", kwargs)

    def get(self, **kwargs) -> Request:
        if self._resource not in {"messages", "threads"}:
            raise ValueError("unsupported provider method")
        self._validate(kwargs, {"userId", "id", "format", "metadataHeaders"})
        if not isinstance(kwargs.get("id"), str) or not kwargs["id"]:
            raise ValueError("missing provider identifier")
        kwargs.setdefault("format", "full")
        formats = {"full", "metadata", "minimal"}
        if self._resource == "messages":
            formats.add("raw")
        if kwargs["format"] not in formats:
            raise ValueError("unsupported provider format")
        return self._service._request(self._resource + ".get", kwargs)

    def insert(self, **kwargs) -> Request:
        if self._resource != "messages":
            raise ValueError("unsupported provider method")
        self._validate(
            kwargs, {"userId", "body", "internalDateSource", "neverMarkSpam"}
        )
        body = kwargs.get("body")
        if (
            not isinstance(body, dict)
            or "raw" not in body
            or set(body) - {"raw", "threadId", "labelIds"}
        ):
            raise ValueError("invalid insert body")
        _decode(body["raw"])
        if "threadId" in body and (
            not isinstance(body["threadId"], str) or not body["threadId"]
        ):
            raise ValueError("invalid insert thread")
        if "labelIds" in body:
            _strings(body["labelIds"])
        if kwargs.get("internalDateSource", "receivedTime") not in {
            "receivedTime",
            "dateHeader",
        }:
            raise ValueError("invalid date source")
        return self._service._request("messages.insert", kwargs)

    def modify(self, **kwargs) -> Request:
        if self._resource != "messages":
            raise ValueError("unsupported provider method")
        self._validate(kwargs, {"userId", "id", "body"})
        body = kwargs.get("body")
        if not isinstance(body, dict) or set(body) - {"addLabelIds", "removeLabelIds"}:
            raise ValueError("invalid label mutation body")
        if not isinstance(kwargs.get("id"), str) or not kwargs["id"]:
            raise ValueError("missing provider identifier")
        for values in body.values():
            _strings(values)
        return self._service._request("messages.modify", kwargs)

    @staticmethod
    def _validate(arguments: dict, allowed: set[str]) -> None:
        if not allowed or "userId" not in arguments or set(arguments) - allowed:
            raise ValueError("unsupported provider method or arguments")
        for key in ("id", "q", "pageToken", "labelId", "format"):
            if key in arguments and not isinstance(arguments[key], str):
                raise ValueError("invalid provider argument type")
        for key in ("includeSpamTrash", "neverMarkSpam"):
            if key in arguments and type(arguments[key]) is not bool:
                raise ValueError("invalid provider argument type")
        for key in ("labelIds", "historyTypes", "metadataHeaders"):
            if key in arguments:
                _strings(arguments[key])
