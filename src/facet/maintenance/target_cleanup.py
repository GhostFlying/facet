"""Fixed-manifest target cleanup with private, crash-resumable receipts.

This deliberately does not use or change projection jobs or insert recovery.
The caller owns the normal writer lock and verifies both account bindings.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from time import time
from uuid import uuid4

from facet.contracts import ErrorCode, LocalId, Role
from facet.db.codecs import StorageFailure
from facet.gmail.retry import ProviderFailure, provider_failure
from facet.private_paths import _owner_only

TTL_SECONDS = 1800
JOURNAL_NAME = "target-cleanup.sqlite3"


def fail(code=ErrorCode.REQUEST_CONFLICT):
    raise StorageFailure(code)


def _provider_id(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value):
        fail(ErrorCode.INVALID_INPUT)
    return value


def call(request):
    try:
        return request.execute(num_retries=0)
    except Exception as error:
        raise provider_failure(error, Role.TARGET) from None


def check_profile(service, expected_target):
    value = call(service.users().getProfile(userId="me", fields="emailAddress"))
    address = value.get("emailAddress") if type(value) is dict else None
    if type(address) is not str or address.casefold() != expected_target.casefold():
        fail(ErrorCode.BINDING_MISMATCH)


def _list_pages(resource, key, **kwargs):
    result = {}
    seen = set()
    token = None
    while True:
        arguments = {"userId": "me", "maxResults": 500, **kwargs}
        if token is not None:
            arguments["pageToken"] = token
        page = call(resource.list(**arguments))
        if type(page) is not dict or type(page.get(key, [])) is not list:
            fail(ErrorCode.INVALID_INPUT)
        for item in page.get(key, []):
            if type(item) is not dict:
                fail(ErrorCode.INVALID_INPUT)
            identifier = _provider_id(item.get("id"))
            if key == "drafts":
                message = item.get("message")
                if type(message) is not dict:
                    fail(ErrorCode.INVALID_INPUT)
                contained = _provider_id(message.get("id"))
                if identifier in result and result[identifier] != contained:
                    # A changing draft during pagination cannot give a stable preview.
                    fail(ErrorCode.REQUEST_CONFLICT)
                result[identifier] = contained
            else:
                result[identifier] = identifier
        token = page.get("nextPageToken")
        if token is None:
            return result
        if type(token) is not str or not token or len(token) > 2048 or token in seen:
            fail(ErrorCode.INVALID_INPUT)
        seen.add(token)


def collect_manifest(service):
    messages = _list_pages(
        service.users().messages(),
        "messages",
        includeSpamTrash=True,
        fields="messages(id),nextPageToken",
    )
    drafts = _list_pages(
        service.users().drafts(),
        "drafts",
        fields="drafts(id,message(id)),nextPageToken",
    )
    draft_messages = set(drafts.values())
    # Draft IDs are mutable containers. Only the contained message IDs are targets.
    return [
        (identifier, int(identifier in draft_messages))
        for identifier in sorted(set(messages) | draft_messages)
    ]


class CleanupJournal:
    """A finite private maintenance DB, separate from the projection DB."""

    def __init__(self, root: Path, *, readonly=False):
        path = root / JOURNAL_NAME
        _owner_only(root.lstat(), directory=True)
        if not readonly and not path.exists():
            descriptor = os.open(
                path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
            )
            os.close(descriptor)
        try:
            _owner_only(path.lstat())
        except FileNotFoundError:
            fail(ErrorCode.OWNER_UNAVAILABLE)
        self.connection = sqlite3.connect(
            f"{path.as_uri()}?mode={'ro' if readonly else 'rw'}",
            uri=True,
            isolation_level=None,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA trusted_schema=OFF")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA query_only=" + ("ON" if readonly else "OFF"))
        if not readonly:
            self.connection.execute("PRAGMA synchronous=FULL")
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS previews (
                    preview_id TEXT PRIMARY KEY, preview_key TEXT UNIQUE NOT NULL,
                    identity TEXT NOT NULL, created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK(state IN
                        ('building','ready','running','completed')),
                    execution_key TEXT UNIQUE, confirmation TEXT,
                    manifest_digest TEXT, mappings INTEGER NOT NULL,
                    unknown_inserts INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS items (
                    preview_id TEXT NOT NULL REFERENCES previews(preview_id),
                    message_id TEXT NOT NULL,
                    is_draft INTEGER NOT NULL CHECK(is_draft IN (0,1)),
                    state TEXT NOT NULL CHECK(state IN
                        ('pending','dispatched','confirmed')),
                    PRIMARY KEY(preview_id,message_id)
                );
            """)

    def close(self):
        self.connection.close()

    def get(self, preview_id):
        LocalId(preview_id)
        row = self.connection.execute(
            "SELECT * FROM previews WHERE preview_id=?", (preview_id,)
        ).fetchone()
        if row is None:
            fail(ErrorCode.OWNER_UNAVAILABLE)
        if row["state"] not in {"building", "ready", "running", "completed"} or any(
            type(row[field]) is not int or row[field] < 0
            for field in ("created_at", "expires_at", "mappings", "unknown_inserts")
        ):
            fail(ErrorCode.CONSISTENCY_FAILURE)
        return row

    def receipt(self, preview_id):
        row = self.get(preview_id)
        if row["state"] == "building":
            fail(ErrorCode.MAINTENANCE_INCOMPLETE)
        items = self.connection.execute(
            "SELECT is_draft,state,COUNT(*) AS n FROM items WHERE preview_id=? "
            "GROUP BY is_draft,state",
            (preview_id,),
        ).fetchall()
        total = sum(item["n"] for item in items)
        drafts = sum(item["n"] for item in items if item["is_draft"])
        confirmed = sum(item["n"] for item in items if item["state"] == "confirmed")
        return {
            "preview_id": preview_id,
            "state": row["state"],
            "messages": total - drafts,
            "drafts": drafts,
            "total": total,
            "confirmed_absent": confirmed,
            "remaining": total - confirmed,
            "unknown_deletions": sum(
                item["n"] for item in items if item["state"] == "dispatched"
            ),
            "existing_mappings": row["mappings"],
            "unknown_inserts": row["unknown_inserts"],
            "expires_at_unix_seconds": row["expires_at"],
            "irreversible": True,
            "includes_spam_trash": True,
            "new_arrivals_included": False,
            "sync_state_reset": False,
        }

    def preview(self, service, *, request_id, identity, mappings, unknown_inserts):
        LocalId(request_id)
        existing = self.connection.execute(
            "SELECT * FROM previews WHERE preview_key=? OR execution_key=?",
            (request_id, request_id),
        ).fetchone()
        if existing is not None:
            if (
                existing["preview_key"] != request_id
                or existing["identity"] != identity
            ):
                fail()
            preview_id = existing["preview_id"]
            if existing["state"] != "building":
                return self.receipt(preview_id)
        else:
            preview_id = uuid4().hex
            now = int(time())
            self.connection.execute(
                "INSERT INTO previews VALUES (?,?,?,?,?,'building',NULL,NULL,NULL,?,?)",
                (
                    preview_id,
                    request_id,
                    identity,
                    now,
                    now + TTL_SECONDS,
                    mappings,
                    unknown_inserts,
                ),
            )
        manifest = collect_manifest(service)
        digest = hashlib.sha256(
            json.dumps(manifest, separators=(",", ":")).encode()
        ).hexdigest()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.executemany(
                "INSERT INTO items VALUES (?,?,?,'pending')",
                [(preview_id, identifier, draft) for identifier, draft in manifest],
            )
            self.connection.execute(
                "UPDATE previews SET state='ready',expires_at=?,manifest_digest=? "
                "WHERE preview_id=?",
                (int(time()) + TTL_SECONDS, digest, preview_id),
            )
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        return self.receipt(preview_id)

    def start(self, *, preview_id, request_id, identity, confirmation):
        LocalId(request_id)
        row = self.get(preview_id)
        confirmation_digest = hashlib.sha256(
            confirmation.casefold().encode()
        ).hexdigest()
        if row["execution_key"] is not None:
            if (
                row["execution_key"] != request_id
                or row["confirmation"] != confirmation_digest
            ):
                fail()
            if row["state"] == "completed":
                return False
        if row["identity"] != identity:
            fail(ErrorCode.BINDING_MISMATCH)
        manifest = [
            list(item)
            for item in self.connection.execute(
                "SELECT message_id,is_draft FROM items WHERE preview_id=? "
                "ORDER BY message_id",
                (preview_id,),
            ).fetchall()
        ]
        digest = hashlib.sha256(
            json.dumps(manifest, separators=(",", ":")).encode()
        ).hexdigest()
        if row["manifest_digest"] != digest:
            fail(ErrorCode.CONSISTENCY_FAILURE)
        if row["execution_key"] is not None:
            return True
        if row["state"] != "ready" or int(time()) >= row["expires_at"]:
            fail(ErrorCode.REQUEST_CONFLICT)
        if (
            self.connection.execute(
                "SELECT 1 FROM previews WHERE preview_key=? OR execution_key=?",
                (request_id, request_id),
            ).fetchone()
            is not None
        ):
            fail()
        self.connection.execute(
            "UPDATE previews SET state='running',execution_key=?,confirmation=? "
            "WHERE preview_id=?",
            (request_id, confirmation_digest, preview_id),
        )
        return True

    def execute(self, service, preview_id):
        if self.get(preview_id)["state"] != "running":
            fail()
        for item in self.connection.execute(
            "SELECT * FROM items WHERE preview_id=? AND state!='confirmed' "
            "ORDER BY message_id",
            (preview_id,),
        ).fetchall():
            identifier = item["message_id"]
            _provider_id(identifier)
            absent = False
            if item["state"] == "dispatched":
                try:
                    result = call(
                        service.users()
                        .messages()
                        .get(userId="me", id=identifier, format="minimal", fields="id")
                    )
                    if type(result) is not dict or result.get("id") != identifier:
                        fail(ErrorCode.CONSISTENCY_FAILURE)
                except ProviderFailure as error:
                    if error.status != 404:
                        raise
                    absent = True
            if not absent:
                self.connection.execute(
                    "UPDATE items SET state='dispatched' "
                    "WHERE preview_id=? AND message_id=?",
                    (preview_id, identifier),
                )
                try:
                    call(service.users().messages().delete(userId="me", id=identifier))
                except ProviderFailure as error:
                    if error.status != 404:
                        raise
            self.connection.execute(
                "UPDATE items SET state='confirmed' "
                "WHERE preview_id=? AND message_id=?",
                (preview_id, identifier),
            )
        self.connection.execute(
            "UPDATE previews SET state='completed' WHERE preview_id=?", (preview_id,)
        )
        return self.receipt(preview_id)
