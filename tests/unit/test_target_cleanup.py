"""Synthetic-only fixed-manifest destructive maintenance tests."""

import stat
from uuid import uuid4

import httplib2
import pytest
from fakes.cleanup_http import CleanupHttp as Http
from googleapiclient.discovery import build

from facet.contracts import ErrorCode, Role
from facet.db.codecs import StorageFailure
from facet.gmail.retry import ProviderFailure
from facet.maintenance.target_cleanup import (
    JOURNAL_NAME,
    CleanupJournal,
    call,
    check_profile,
)


def service(http):
    return build("gmail", "v1", http=http, cache_discovery=False, num_retries=0)


@pytest.fixture
def prepared(tmp_path):
    tmp_path.chmod(0o700)
    journal = CleanupJournal(tmp_path)
    http = Http()
    try:
        receipt = journal.preview(
            service(http),
            request_id=uuid4().hex,
            identity="binding-digest",
            mappings=0,
            unknown_inserts=1,
        )
        yield journal, http, receipt["preview_id"]
    finally:
        journal.close()


def start(journal, preview, *, key=None, identity="binding-digest"):
    key = key or uuid4().hex
    journal.start(
        preview_id=preview,
        request_id=key,
        identity=identity,
        confirmation="target@example.com",
    )
    return key


def test_actual_google_client_fixed_manifest_and_new_arrivals(prepared, tmp_path):
    journal, http, preview = prepared
    assert journal.receipt(preview)["messages"] == 2
    assert journal.receipt(preview)["drafts"] == 1
    assert all(method == "GET" for method, _, _ in http.calls)
    http.ids.add("new_after_preview")
    key = start(journal, preview)
    receipt = journal.execute(service(http), preview)
    assert receipt["confirmed_absent"] == 3
    assert receipt["state"] == "completed"
    assert http.ids == {"new_after_preview"}
    assert not any("/drafts/" in path for _, path, _ in http.calls)
    calls = len(http.calls)
    assert not journal.start(
        preview_id=preview,
        request_id=key,
        identity="changed-after-completion",
        confirmation="target@example.com",
    )
    assert len(http.calls) == calls
    assert stat.S_IMODE((tmp_path / JOURNAL_NAME).stat().st_mode) == 0o600
    raw = (tmp_path / JOURNAL_NAME).read_bytes()
    assert b"BODY_CREDENTIAL_SENTINEL" not in raw
    assert b"target@example.com" not in raw


@pytest.mark.parametrize("replacement", ["draft_edit", "sent_replacement"])
def test_draft_edited_or_sent_since_preview_is_not_deleted(prepared, replacement):
    journal, http, preview = prepared
    http.ids.remove("draft_old")
    http.ids.add(replacement)
    start(journal, preview)
    assert journal.execute(service(http), preview)["confirmed_absent"] == 3
    assert http.ids == {replacement}


def test_response_loss_restart_uses_get_then_receipt(prepared, tmp_path, monkeypatch):
    journal, http, preview = prepared
    key = start(journal, preview)
    http.lost = True
    with pytest.raises(ProviderFailure):
        journal.execute(service(http), preview)
    assert journal.receipt(preview)["unknown_deletions"] == 1
    monkeypatch.setattr("facet.maintenance.target_cleanup.time", lambda: 9999999999)
    # Expiry does not invalidate an execution already durably acknowledged.
    journal.close()
    journal.connection = CleanupJournal(tmp_path).connection
    journal.start(
        preview_id=preview,
        request_id=key,
        identity="binding-digest",
        confirmation="target@example.com",
    )
    assert journal.execute(service(http), preview)["state"] == "completed"
    deleted = [path for method, path, _ in http.calls if method == "DELETE"]
    assert len(deleted) == len(set(deleted)) == 3
    assert any(
        method == "GET" and "/messages/" in path for method, path, _ in http.calls
    )
    assert not journal.start(
        preview_id=preview,
        request_id=key,
        identity="binding-digest",
        confirmation="target@example.com",
    )


def test_unknown_present_retries_same_id_only_after_successful_get(prepared):
    journal, http, preview = prepared
    start(journal, preview)
    journal.connection.execute("UPDATE items SET state='dispatched'")
    http.fail_get = True
    before = list(http.calls)
    with pytest.raises(ProviderFailure):
        journal.execute(service(http), preview)
    assert not any(method == "DELETE" for method, _, _ in http.calls[len(before) :])
    http.fail_get = False
    journal.execute(service(http), preview)
    operations = [
        (method, path.rsplit("/", 1)[1])
        for method, path, _ in http.calls
        if "/messages/" in path
    ]
    for identifier in {"mail1", "spam1", "draft_old"}:
        assert operations.index(("GET", identifier)) < operations.index(
            ("DELETE", identifier)
        )


@pytest.mark.parametrize("conflict", ["binding", "expired", "key", "confirmation"])
def test_conflicts_block_before_delete(prepared, monkeypatch, conflict):
    journal, http, preview = prepared
    kwargs = dict(
        preview_id=preview,
        request_id=uuid4().hex,
        identity="binding-digest",
        confirmation="target@example.com",
    )
    if conflict == "binding":
        kwargs["identity"] = "other-binding"
    elif conflict == "expired":
        monkeypatch.setattr("facet.maintenance.target_cleanup.time", lambda: 9999999999)
    else:
        start(journal, preview, key=kwargs["request_id"])
        kwargs["request_id" if conflict == "key" else "confirmation"] = (
            uuid4().hex if conflict == "key" else "source@example.com"
        )
    with pytest.raises(StorageFailure):
        journal.start(**kwargs)
    assert all(method == "GET" for method, _, _ in http.calls)


def test_incomplete_pagination_no_usable_preview(tmp_path):
    tmp_path.chmod(0o700)
    journal = CleanupJournal(tmp_path)
    http = Http()
    http.fail_list = True
    key = uuid4().hex
    try:
        with pytest.raises(ProviderFailure):
            journal.preview(
                service(http),
                request_id=key,
                identity="binding-digest",
                mappings=0,
                unknown_inserts=0,
            )
        preview = journal.connection.execute(
            "SELECT preview_id FROM previews"
        ).fetchone()[0]
        with pytest.raises(StorageFailure):
            journal.receipt(preview)
        assert (
            journal.connection.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
        )
        http.fail_list = False
        assert (
            journal.preview(
                service(http),
                request_id=key,
                identity="binding-digest",
                mappings=0,
                unknown_inserts=0,
            )["total"]
            == 3
        )
    finally:
        journal.close()


def test_profile_mismatch_stops_before_manifest():
    http = Http()
    with pytest.raises(StorageFailure) as caught:
        check_profile(service(http), "source@example.com")
    assert caught.value.code is ErrorCode.BINDING_MISMATCH
    assert len(http.calls) == 1


def test_status_read_only_no_creation_or_writer(prepared, tmp_path):
    journal, _http, preview = prepared
    before = (tmp_path / JOURNAL_NAME).read_bytes()
    reader = CleanupJournal(tmp_path, readonly=True)
    try:
        assert reader.receipt(preview)["state"] == "ready"
        assert reader.connection.execute("PRAGMA query_only").fetchone()[0] == 1
    finally:
        reader.close()
    assert (tmp_path / JOURNAL_NAME).read_bytes() == before


def test_unknown_delete_404_normalized_without_error_body():
    class Request:
        def execute(self, *, num_retries):
            from googleapiclient.errors import HttpError

            assert num_retries == 0
            raise HttpError(
                httplib2.Response({"status": "404"}), b"BODY_CREDENTIAL_SENTINEL"
            )

    with pytest.raises(ProviderFailure) as caught:
        call(Request())
    assert caught.value.status == 404
    assert caught.value.role is Role.TARGET
    assert "BODY_CREDENTIAL_SENTINEL" not in str(caught.value)
    assert "BODY_CREDENTIAL_SENTINEL" not in repr(caught.value)


def test_manifest_cannot_change_between_preview_and_execute(prepared):
    journal, http, preview = prepared
    journal.connection.execute(
        "UPDATE items SET message_id='other_mail' WHERE message_id='mail1'"
    )
    with pytest.raises(StorageFailure) as caught:
        start(journal, preview)
    assert caught.value.code is ErrorCode.CONSISTENCY_FAILURE
    assert not any(method == "DELETE" for method, _, _ in http.calls)


def test_sensitive_sentinel_in_count_cannot_escape_receipt(prepared):
    journal, _http, preview = prepared
    journal.connection.execute(
        "UPDATE previews SET mappings='BODY_CREDENTIAL_SENTINEL'"
    )
    with pytest.raises(StorageFailure) as caught:
        journal.receipt(preview)
    assert caught.value.code is ErrorCode.CONSISTENCY_FAILURE
    assert "BODY_CREDENTIAL_SENTINEL" not in str(caught.value)


def test_request_key_reuse_across_previews_and_commands(prepared):
    journal, http, preview = prepared
    key = journal.get(preview)["preview_key"]
    with pytest.raises(StorageFailure):
        start(journal, preview, key=key)
    other = journal.preview(
        service(http),
        request_id=uuid4().hex,
        identity="binding-digest",
        mappings=0,
        unknown_inserts=0,
    )["preview_id"]
    execution_key = start(journal, preview)
    with pytest.raises(StorageFailure):
        start(journal, other, key=execution_key)
    assert not any(method == "DELETE" for method, _, _ in http.calls)


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_provider_failure_keeps_dispatched_item_and_stops(prepared, status):
    from googleapiclient.errors import HttpError

    journal, http, preview = prepared
    original = http.respond

    def respond(path, query, method):
        if method == "DELETE":
            raise HttpError(
                httplib2.Response({"status": str(status)}), b"BODY_CREDENTIAL_SENTINEL"
            )
        return original(path, query, method)

    http.respond = respond
    start(journal, preview)
    with pytest.raises(ProviderFailure):
        journal.execute(service(http), preview)
    assert journal.receipt(preview)["unknown_deletions"] == 1
    assert journal.receipt(preview)["confirmed_absent"] == 0
    assert sum(method == "DELETE" for method, _, _ in http.calls) == 1
