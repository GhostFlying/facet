"""External-only synthetic mailbox persisted across real CLI subprocesses."""

import base64
import json
import os
from pathlib import Path

from facet.contracts import Role
from facet.gmail import synthetic


def install():
    mailbox = Path(os.environ["FACET_TEST_HISTORY_MAILBOX"])
    original_init = synthetic.SyntheticGmailService.__init__

    def read():
        return json.loads(mailbox.read_text())

    def initialize(self, role, account):
        original_init(self, role, account)
        if role is Role.TARGET:
            for key, value in read()["target"].items():
                self._inserted[key] = {
                    "threadId": value["threadId"],
                    "raw": base64.b64decode(value["raw"]),
                }

    original_list = synthetic._Messages.list

    def listed(self, **kwargs):
        if self._service.role is Role.SOURCE:
            if kwargs.get("labelIds"):
                tags = read().get("tags", [])
                return synthetic._Request(
                    {
                        "messages": [{"id": "future-new", "threadId": "future-thread"}]
                        if kwargs["labelIds"][0] in tags
                        else []
                    }
                )
            # Initial discovery/preview is genuinely empty; future arrivals are
            # exposed through History, never by changing production DB state.
            return synthetic._Request({"messages": []})
        return original_list(self, **kwargs)

    def history(self, *, startHistoryId, **kwargs):
        state = read()
        revision = state["revision"]
        rows = []
        if revision > 1 and startHistoryId != f"history-{revision}":
            if state.get("action_mode"):
                messages = [
                    {"id": mid, "threadId": "future-thread"}
                    for mid in (
                        "future-old",
                        "future-new",
                        "future-third",
                        "future-fourth",
                    )
                ]
                rows = [
                    {
                        "id": f"record-{revision}",
                        "labelsRemoved"
                        if state.get("removed_event")
                        else "labelsAdded": [
                            {"message": message, "labelIds": ["deleted-action-id"]}
                            for message in messages
                        ],
                    }
                ]
                return synthetic._Request(
                    {"historyId": f"history-{revision}", "history": rows}
                )
            rows = [
                {
                    "id": f"record-{revision}",
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
        return synthetic._Request({"historyId": f"history-{revision}", "history": rows})

    original_message = synthetic.SyntheticGmailService._message

    def message(self, message_id, format):
        if self.role is Role.TARGET:
            return original_message(self, message_id, format)
        state = read()
        state["source_metadata_reads"] = state.get("source_metadata_reads", 0) + (
            format == "metadata"
        )
        mailbox.write_text(json.dumps(state))
        sender = (
            state.get(
                "sender",
                "sender@vendor.com"
                if state.get("action_mode")
                else "sender@example.com",
            )
            if message_id == "future-new"
            else "other@example.com"
        )
        headers = [
            {"name": "From", "value": sender},
            {"name": "Message-ID", "value": f"<{message_id}@example.com>"},
        ]
        value = {
            "id": message_id,
            "threadId": "future-thread",
            "labelIds": ["DRAFT"]
            if message_id == "future-draft"
            else state.get("tags", []),
            "internalDate": str(
                read()["arrived_at"] if message_id == "future-new" else 1767225600000
            ),
            "payload": {"headers": headers},
        }
        if format == "raw":
            raw = (
                f"From: {sender}\r\n"
                f"Message-ID: <{message_id}@example.com>\r\n"
                "Date: Thu, 01 Jan 2026 00:00:00 +0000\r\n"
                "Subject: HISTORY_HEADER_SENTINEL\r\n\r\nHISTORY_BODY_SENTINEL\r\n"
            ).encode()
            value["raw"] = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        return value

    def thread(self, thread_id):
        state = read()
        state["thread_reads"] = state.get("thread_reads", 0) + 1
        mailbox.write_text(json.dumps(state))
        if state.get("source_failure"):
            from facet.contracts import ErrorCode
            from facet.gmail.retry import ProviderFailure

            raise ProviderFailure(ErrorCode.NETWORK_UNAVAILABLE, Role.SOURCE)
        return {
            "id": thread_id,
            "messages": [
                self._message(mid, "metadata")
                for mid in (
                    (
                        "future-old",
                        "future-new",
                        "future-third",
                        "future-fourth",
                        "future-draft",
                    )
                    if state.get("action_mode")
                    else ("future-old", "future-new", "future-draft")
                )
            ],
        }

    def labels(self, **kwargs):
        state = read()
        return synthetic._Request(
            {
                "labels": [
                    {"id": f"current-{kind}", "name": name}
                    for kind, name in (
                        ("sender", "Facet/AddSender"),
                        ("domain", "Facet/AddDomain"),
                        ("blacklist", "AI/BlackList"),
                    )
                ]
                if state.get("action_mode")
                else []
            }
        )

    original_insert = synthetic.SyntheticGmailService._insert

    def insert(self, body):
        result = original_insert(self, body)
        state = read()
        state["target"] = {
            key: {
                "threadId": value["threadId"],
                "raw": base64.b64encode(value["raw"]).decode(),
            }
            for key, value in self._inserted.items()
        }
        state["insert_calls"] += 1
        mailbox.write_text(json.dumps(state))
        return result

    synthetic.SyntheticGmailService.__init__ = initialize
    synthetic._Messages.list = listed
    synthetic._History.list = history
    synthetic._Labels.list = labels
    synthetic.SyntheticGmailService._message = message
    synthetic.SyntheticGmailService._thread = thread
    synthetic.SyntheticGmailService._insert = insert
