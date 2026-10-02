"""Live Gmail operations used by the Phase 0 experiments."""

from __future__ import annotations

from collections.abc import Iterable
from email.utils import parseaddr
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from facet_spike import evidence
from facet_spike.errors import SpikeError
from facet_spike.files import load_json, write_private_json
from facet_spike.message import (
    MessageAnalysis,
    compare_messages,
    parse_raw,
    rfc822_query,
)
from facet_spike.oauth import load_credentials
from facet_spike.privacy import fingerprint
from facet_spike.runtime import RuntimePaths


class GmailSpike:
    """Thin live client with account and evidence guardrails."""

    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self._services: dict[str, Any] = {}

    def service(self, role: str) -> Any:
        if role not in self._services:
            credentials = load_credentials(self.paths, role)
            self._services[role] = build(
                "gmail",
                "v1",
                credentials=credentials,
                cache_discovery=False,
            )
        return self._services[role]

    def profile(self, role: str, *, bind: bool = True) -> dict[str, Any]:
        profile = self.service(role).users().getProfile(userId="me").execute()
        email = profile["emailAddress"].strip().lower()
        if bind:
            bindings = load_json(self.paths.accounts, {})
            previous = bindings.get(role)
            if previous is not None and previous != email:
                raise SpikeError(
                    f"{role} token now resolves to a different account; "
                    "remove the private binding only after reviewing the change"
                )
            other_role = "target" if role == "source" else "source"
            if bindings.get(other_role) == email:
                raise SpikeError("source and target Gmail accounts must be distinct")
            bindings[role] = email
            write_private_json(self.paths.accounts, bindings)
        return profile

    def verify_distinct_accounts(self) -> tuple[dict[str, Any], dict[str, Any]]:
        source = self.profile("source")
        target = self.profile("target")
        if (
            source["emailAddress"].strip().lower()
            == target["emailAddress"].strip().lower()
        ):
            raise SpikeError("source and target Gmail accounts must be distinct")
        return source, target

    def search(
        self,
        role: str,
        query: str,
        *,
        max_results: int,
        show_headers: bool,
    ) -> list[dict[str, Any]]:
        response = (
            self.service(role)
            .users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=max_results,
                includeSpamTrash=True,
            )
            .execute()
        )
        results = []
        for item in response.get("messages", []):
            metadata = (
                self.service(role)
                .users()
                .messages()
                .get(
                    userId="me",
                    id=item["id"],
                    format="metadata",
                    metadataHeaders=["Date", "From", "Subject", "Message-ID"],
                )
                .execute()
            )
            headers = _headers(metadata)
            result = {
                "message_id": item["id"],
                "thread_id": item["threadId"],
                "internal_date": metadata.get("internalDate"),
                "rfc_message_id": fingerprint(
                    headers.get("message-id"),
                    prefix="rfc-message-id",
                ),
                "subject": (
                    headers.get("subject")
                    if show_headers
                    else fingerprint(headers.get("subject"), prefix="subject")
                ),
                "from": (
                    headers.get("from")
                    if show_headers
                    else fingerprint(headers.get("from"), prefix="from")
                ),
                "date": headers.get("date"),
            }
            results.append(result)
        return results

    def fetch_raw(
        self, role: str, message_id: str
    ) -> tuple[dict[str, Any], MessageAnalysis]:
        resource = (
            self.service(role)
            .users()
            .messages()
            .get(userId="me", id=message_id, format="raw")
            .execute()
        )
        raw = resource.get("raw")
        if not raw:
            raise SpikeError(f"Gmail returned no raw content for {role} message")
        return resource, parse_raw(raw)

    def copy_message(self, source_message_id: str) -> dict[str, Any]:
        self.verify_distinct_accounts()
        source_resource, source_analysis = self.fetch_raw("source", source_message_id)
        target_resource = self._insert(source_resource["raw"])
        target_full, target_analysis = self.fetch_raw("target", target_resource["id"])
        comparison = compare_messages(source_analysis, target_analysis)
        comparison["internal_date_equal"] = source_resource.get(
            "internalDate"
        ) == target_full.get("internalDate")
        details = {
            "source_message_id": fingerprint(source_message_id),
            "target_message_id": fingerprint(target_resource["id"]),
            "source_thread_id": fingerprint(
                source_resource.get("threadId"), prefix="thread"
            ),
            "target_thread_id": fingerprint(
                target_resource.get("threadId"), prefix="thread"
            ),
            "comparison": comparison,
            "source": source_analysis.redacted_summary(),
            "target": target_analysis.redacted_summary(),
        }
        evidence.record(self.paths.evidence, "message_copied", details)
        return {
            "target_message_id": target_resource["id"],
            "target_thread_id": target_resource.get("threadId"),
            "comparison": comparison,
        }

    def copy_thread(self, source_thread_id: str) -> dict[str, Any]:
        self.verify_distinct_accounts()
        thread = (
            self.service("source")
            .users()
            .threads()
            .get(userId="me", id=source_thread_id, format="metadata")
            .execute()
        )
        source_messages = sorted(
            thread.get("messages", []),
            key=lambda item: int(item.get("internalDate", "0")),
        )
        if not source_messages:
            raise SpikeError("source thread contains no messages")

        requested_target_thread_id: str | None = None
        target_thread_ids: set[str] = set()
        copied = []
        fallback_count = 0
        for item in source_messages:
            source_resource, source_analysis = self.fetch_raw("source", item["id"])
            try:
                target_resource = self._insert(
                    source_resource["raw"],
                    thread_id=requested_target_thread_id,
                )
            except HttpError as error:
                if requested_target_thread_id is None or error.resp.status != 400:
                    raise
                fallback_count += 1
                target_resource = self._insert(source_resource["raw"])

            actual_target_thread_id = target_resource.get("threadId")
            if actual_target_thread_id:
                requested_target_thread_id = actual_target_thread_id
                target_thread_ids.add(actual_target_thread_id)
            target_full, target_analysis = self.fetch_raw(
                "target", target_resource["id"]
            )
            comparison = compare_messages(source_analysis, target_analysis)
            comparison["internal_date_equal"] = source_resource.get(
                "internalDate"
            ) == target_full.get("internalDate")
            message_details = {
                "source_message_id": fingerprint(item["id"]),
                "target_message_id": fingerprint(target_resource["id"]),
                "source_thread_id": fingerprint(source_thread_id, prefix="thread"),
                "target_thread_id": fingerprint(
                    actual_target_thread_id, prefix="thread"
                ),
                "comparison": comparison,
                "source": source_analysis.redacted_summary(),
                "target": target_analysis.redacted_summary(),
            }
            evidence.record(self.paths.evidence, "message_copied", message_details)
            copied.append(
                {
                    "source_message_id": item["id"],
                    "target_message_id": target_resource["id"],
                    "target_thread_id": actual_target_thread_id,
                    "comparison": comparison,
                }
            )

        summary = {
            "source_thread_id": fingerprint(source_thread_id, prefix="thread"),
            "message_count": len(copied),
            "target_thread_count": len(target_thread_ids),
            "thread_insert_fallback_count": fallback_count,
            "all_mime_payloads_equal": all(
                item["comparison"]["mime_payloads_equal"] for item in copied
            ),
        }
        evidence.record(self.paths.evidence, "thread_copied", summary)
        return {**summary, "messages": copied}

    def insert_for_crash_experiment(self, source_message_id: str) -> dict[str, Any]:
        self.verify_distinct_accounts()
        source_resource, _ = self.fetch_raw("source", source_message_id)
        return self._insert(source_resource["raw"])

    def find_target_by_rfc_message_id(self, message_id: str) -> list[dict[str, Any]]:
        response = (
            self.service("target")
            .users()
            .messages()
            .list(
                userId="me",
                q=rfc822_query(message_id),
                includeSpamTrash=True,
                maxResults=500,
            )
            .execute()
        )
        return response.get("messages", [])

    def history_since(self, start_history_id: str) -> dict[str, Any]:
        service = self.service("source")
        history: list[dict[str, Any]] = []
        page_token: str | None = None
        newest_history_id = start_history_id
        while True:
            request = (
                service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=start_history_id,
                    maxResults=500,
                    pageToken=page_token,
                )
            )
            response = request.execute()
            history.extend(response.get("history", []))
            newest_history_id = response.get("historyId", newest_history_id)
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return {
            "start_history_id": start_history_id,
            "history_id": newest_history_id,
            "history": history,
        }

    def evaluate_history(
        self,
        history: Iterable[dict[str, Any]],
        *,
        expected_subject: str,
        action_label: str | None,
    ) -> dict[str, Any]:
        history = list(history)
        label_names = {
            label["id"]: label["name"]
            for label in (
                self.service("source")
                .users()
                .labels()
                .list(userId="me")
                .execute()
                .get("labels", [])
            )
        }
        own_address = self.profile("source")["emailAddress"].strip().lower()
        added_message_ids = []
        label_events = []
        for record in history:
            for event in record.get("messagesAdded", []):
                added_message_ids.append(event["message"]["id"])
            for event in record.get("labelsAdded", []):
                event_names = {
                    label_names.get(label_id, label_id)
                    for label_id in event.get("labelIds", [])
                }
                if action_label is None or action_label in event_names:
                    label_events.append(
                        {
                            "history_id": record.get("id"),
                            "message_id": event["message"]["id"],
                            "thread_id": event["message"].get("threadId"),
                        }
                    )

        metadata = {}
        candidate_ids = set(added_message_ids)
        candidate_ids.update(event["message_id"] for event in label_events)
        for message_id in candidate_ids:
            resource = (
                self.service("source")
                .users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["Subject", "From"],
                )
                .execute()
            )
            headers = _headers(resource)
            from_address = parseaddr(headers.get("from", ""))[1].strip().lower()
            metadata[message_id] = {
                "thread_id": resource.get("threadId"),
                "subject_matches": expected_subject in headers.get("subject", ""),
                "own_sender": from_address == own_address,
            }

        matching_added = [
            metadata[message_id]
            for message_id in added_message_ids
            if metadata[message_id]["subject_matches"]
        ]
        matching_labels = [
            event
            for event in label_events
            if metadata[event["message_id"]]["subject_matches"]
        ]
        return {
            "matching_messages_added": len(matching_added),
            "incoming_count": sum(not item["own_sender"] for item in matching_added),
            "own_sent_count": sum(item["own_sender"] for item in matching_added),
            "distinct_test_threads": len(
                {item["thread_id"] for item in matching_added}
            ),
            "matching_action_label_events": len(matching_labels),
            "label_event_history_record_count": len(
                {event["history_id"] for event in matching_labels}
            ),
            "label_event_distinct_threads": len(
                {event["thread_id"] for event in matching_labels}
            ),
            "action_label_found": action_label is None
            or action_label in set(label_names.values()),
        }

    def _insert(self, raw: str, *, thread_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"raw": raw}
        if thread_id is not None:
            body["threadId"] = thread_id
        return (
            self.service("target")
            .users()
            .messages()
            .insert(
                userId="me",
                body=body,
                internalDateSource="dateHeader",
            )
            .execute()
        )


def sanitize_history(history: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized = []
    for record in history:
        item: dict[str, Any] = {
            "history_id": record.get("id"),
        }
        for event_name in (
            "messagesAdded",
            "messagesDeleted",
            "labelsAdded",
            "labelsRemoved",
        ):
            events = []
            for event in record.get(event_name, []):
                message = event.get("message", {})
                sanitized_event = {
                    "message_id": fingerprint(message.get("id")),
                    "thread_id": fingerprint(message.get("threadId"), prefix="thread"),
                }
                if "labelIds" in event:
                    sanitized_event["label_ids"] = sorted(event["labelIds"])
                events.append(sanitized_event)
            if events:
                item[event_name] = events
        if len(item) > 1:
            sanitized.append(item)
    return sanitized


def _headers(resource: dict[str, Any]) -> dict[str, str]:
    headers = {}
    for header in resource.get("payload", {}).get("headers", []):
        headers[header["name"].lower()] = header["value"]
    return headers
