"""Unknown checks use the production worker fault path, never invented success."""

import base64
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fakes.gmail import InsertReply
from test_projection_worker import (
    _payload,
    _raw,
    _ready_owner,
    _trusted_parent,
    _worker_adapters,
)

from facet.contracts import ErrorCode, ProviderId
from facet.db.repositories import reads
from facet.gmail.retry import ProviderFailure, Role
from facet.projection.recovery import UnknownInsertChecks, check_unknown


@pytest.fixture
def unknown(gmail_controller, monkeypatch):
    raw = _raw("uncertain", "RECOVERY_BODY_SENTINEL")
    gmail_controller.seed(
        "source", "m-new", "thread-1", raw, internal_date="1000", payload=_payload(raw)
    )
    with TemporaryDirectory(prefix="facet-recovery-", dir=_trusted_parent()) as root:
        owner = _ready_owner(Path(root), gmail_controller, monkeypatch)
        try:
            worker, source, target = _worker_adapters(gmail_controller, owner)
            assert worker.run().expanded == 1
            encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
            gmail_controller.script(
                "target",
                "messages.insert",
                {
                    "userId": "me",
                    "body": {"raw": encoded},
                    "internalDateSource": "dateHeader",
                },
                InsertReply(
                    lose_response=True,
                    search_visible=True,
                    rfc_id="<uncertain@example.invalid>",
                ),
            )
            assert worker.run().recovery == 1
            with owner.session.transaction() as uow:
                identifier = owner._connection.execute(
                    "SELECT attempt_id FROM insert_attempts"
                ).fetchone()[0]
                from facet.contracts import LocalId

                attempt = reads.get_attempt(
                    uow, owner.projection_id, LocalId(identifier)
                )
            yield owner, worker, source, target, attempt
        finally:
            owner.close()


def test_unique_content_is_checked_but_not_claimed_or_resent(unknown, gmail_controller):
    owner, worker, source, target, attempt = unknown
    evidence = check_unknown(source, target, attempt)
    assert evidence.result == "unique_match"
    assert evidence.code is ErrorCode.ATTRIBUTION_UNKNOWN
    assert UnknownInsertChecks(owner, source, target).run() == 1
    assert owner._connection.execute(
        "SELECT state,recovery_checks,error_code FROM insert_attempts"
    ).fetchone() == ("needs_attention", 1, "attribution_unknown")
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM message_mappings"
    ).fetchone() == (0,)
    assert worker.run().processed == 0
    assert UnknownInsertChecks(owner, source, target).run() == 0
    assert gmail_controller.identifiers("target") == ("inserted-1",)


def test_missing_index_is_scheduled_durably_without_resend(unknown, monkeypatch):
    owner, worker, source, target, attempt = unknown
    monkeypatch.setattr(target, "find_by_rfc_message_id", lambda _id: ())
    checks = UnknownInsertChecks(owner, source, target)
    assert checks.run() == 1
    row = owner._connection.execute(
        "SELECT state,recovery_checks,next_recovery_at FROM insert_attempts"
    ).fetchone()
    assert row[:2] == ("pending_recovery", 1)
    assert row[2] is not None
    assert owner._connection.execute(
        "SELECT state,next_attempt_at,last_error_code FROM sync_jobs "
        "WHERE kind='recover_insert'"
    ).fetchone() == ("retry_wait", row[2], "insert_result_unknown")
    assert checks.run() == 0
    assert worker.run().processed == 0
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM insert_attempts"
    ).fetchone() == (1,)


def test_network_failure_checks_wait_and_preserve_thread_blocker(unknown, monkeypatch):
    owner, worker, source, target, _ = unknown

    def unavailable(_id):
        raise ProviderFailure(ErrorCode.NETWORK_UNAVAILABLE, Role.TARGET)

    monkeypatch.setattr(target, "find_by_rfc_message_id", unavailable)
    assert UnknownInsertChecks(owner, source, target).run() == 1
    assert owner._connection.execute(
        "SELECT state,last_error_code FROM sync_jobs WHERE kind='recover_insert'"
    ).fetchone() == ("retry_wait", "network_unavailable")
    assert worker.run().processed == 0


def test_source_404_retains_missing_cause_without_resend_or_ownership(
    unknown, monkeypatch
):
    owner, worker, source, target, attempt = unknown

    def gone(*args, **kwargs):
        raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.SOURCE, status=404)

    monkeypatch.setattr(source, "raw", gone)
    evidence = check_unknown(source, target, attempt)
    assert evidence.code is ErrorCode.SOURCE_MISSING
    assert UnknownInsertChecks(owner, source, target).run() == 1
    assert owner._connection.execute(
        "SELECT state,certainty,attribution,error_code,recovery_checks "
        "FROM insert_attempts"
    ).fetchone() == ("needs_attention", "unknown", "none", "source_missing", 1)
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM sync_jobs WHERE last_error_code='source_missing'"
    ).fetchone() == (2,)
    assert worker.run().processed == 0
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM message_mappings"
    ).fetchone() == (0,)


def test_due_check_increments_without_another_insert(unknown, monkeypatch):
    from facet.projection import recovery

    owner, worker, source, target, _ = unknown
    monkeypatch.setattr(target, "find_by_rfc_message_id", lambda _id: ())
    checks = UnknownInsertChecks(owner, source, target)
    assert checks.run() == 1
    from facet.db.codecs import timestamp_from_sql

    due = timestamp_from_sql(
        owner._connection.execute(
            "SELECT next_recovery_at FROM insert_attempts"
        ).fetchone()[0]
    )
    real_datetime = recovery.datetime

    class Later:
        @staticmethod
        def now(_timezone):
            return due.value + timedelta(seconds=1)

    monkeypatch.setattr(recovery, "datetime", Later)
    assert checks.run() == 1
    assert owner._connection.execute(
        "SELECT recovery_checks FROM insert_attempts"
    ).fetchone() == (2,)
    monkeypatch.setattr(recovery, "datetime", real_datetime)
    assert worker.run().processed == 0


@pytest.mark.parametrize(
    "fault",
    [
        "sent",
        "draft",
        "spam",
        "trash",
        "changed",
        "wrong_id",
        "wrong_thread",
        "multiple",
        "missing_rfc",
        "oversize",
    ],
)
def test_real_ambiguity_is_precise_attention_not_an_insert(unknown, monkeypatch, fault):
    owner, worker, source, target, attempt = unknown
    if fault == "multiple":
        monkeypatch.setattr(
            target,
            "find_by_rfc_message_id",
            lambda _id: (ProviderId("x"), ProviderId("y")),
        )
    elif fault == "missing_rfc":
        attempt = replace(attempt, rfc_message_id=None)
    else:
        readback = target.readback(ProviderId("inserted-1"))
        if fault in {"sent", "draft", "spam", "trash"}:
            readback = replace(readback, labels=(fault.upper(),))
        elif fault == "changed":
            readback = replace(readback, raw=readback.raw + b"CHANGED_SENTINEL")
        elif fault == "wrong_id":
            readback = replace(readback, message_id=ProviderId("another"))
        elif fault == "wrong_thread":
            attempt = replace(attempt, requested_target_thread_id=ProviderId("another"))
        monkeypatch.setattr(target, "readback", lambda _id: readback)
    if fault == "oversize":
        with pytest.raises(ProviderFailure) as error:
            check_unknown(source, target, attempt, max_raw_bytes=1)
        assert error.value.code is ErrorCode.INVALID_INPUT
        assert worker.run().processed == 0
        return
    evidence = check_unknown(
        source, target, attempt, max_raw_bytes=1 if fault == "oversize" else 35_000_000
    )
    assert evidence.result != "unique_match"
    assert evidence.code in {
        ErrorCode.DUPLICATE_CANDIDATES,
        ErrorCode.ATTRIBUTION_UNKNOWN,
        ErrorCode.FIDELITY_MISMATCH,
        ErrorCode.INVALID_INPUT,
    }
    if fault not in {"missing_rfc", "wrong_thread", "oversize"}:
        assert UnknownInsertChecks(owner, source, target).run() == 1
        assert owner._connection.execute(
            "SELECT state FROM insert_attempts"
        ).fetchone() == ("needs_attention",)
        assert owner._connection.execute(
            "SELECT COUNT(*) FROM message_mappings"
        ).fetchone() == (0,)
    assert worker.run().processed == 0


def test_recovery_schedule_failure_rolls_back_attempt_and_claim_result(
    unknown, monkeypatch
):
    from facet.db.codecs import StorageFailure
    from facet.db.repositories import intents

    owner, _, source, target, _ = unknown
    monkeypatch.setattr(target, "find_by_rfc_message_id", lambda _id: ())

    def failure(*args, **kwargs):
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)

    monkeypatch.setattr(intents, "_audit", failure)
    with pytest.raises(StorageFailure):
        UnknownInsertChecks(owner, source, target).run()
    assert owner._connection.execute(
        "SELECT state,recovery_checks,next_recovery_at FROM insert_attempts"
    ).fetchone() == ("pending_recovery", 0, None)
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM message_mappings"
    ).fetchone() == (0,)


def test_target_search_does_not_assert_unique_first_page(unknown, gmail_controller):
    _, _, _, target, attempt = unknown
    arguments = {
        "userId": "me",
        "q": "rfc822msgid:<uncertain@example.invalid>",
        "includeSpamTrash": True,
        "maxResults": 100,
    }
    gmail_controller.script(
        "target",
        "messages.list",
        arguments,
        {"messages": [{"id": "one"}], "nextPageToken": "next"},
    )
    gmail_controller.script(
        "target",
        "messages.list",
        {**arguments, "pageToken": "next"},
        {"messages": [{"id": "two"}]},
    )
    assert target.find_by_rfc_message_id(attempt.rfc_message_id) == (
        ProviderId("one"),
        ProviderId("two"),
    )
