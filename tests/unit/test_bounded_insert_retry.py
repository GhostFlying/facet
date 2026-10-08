"""Production unknown faults, aged automatic retries and retained uncertainty."""

import base64
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from fakes.gmail import HttpFailure, InsertReply
from test_projection_worker import (
    _payload,
    _raw,
    _ready_owner,
    _trusted_parent,
    _worker_adapters,
)

from facet.contracts import ErrorCode, LocalId, Role, Timestamp
from facet.db.codecs import StorageFailure, ThreadStopReason
from facet.db.repositories import intents, policy, reads
from facet.gmail.retry import ProviderFailure
from facet.projection.recovery import UnknownInsertChecks
from facet.runtime.state_owner import StateOwner


@pytest.fixture
def absent(gmail_controller, monkeypatch):
    raw = _raw("absent-retry", "RETRY_PRIVATE_BODY_SENTINEL")
    dependent = _raw("dependent", "DEPENDENT_PRIVATE_BODY_SENTINEL")
    for mid, content, date in (
        ("m-new", raw, "1000"),
        ("m-dependent", dependent, "2000"),
    ):
        gmail_controller.seed(
            "source",
            mid,
            "thread-1",
            content,
            internal_date=date,
            payload=_payload(content),
        )
    with TemporaryDirectory(prefix="facet-absence-", dir=_trusted_parent()) as root:
        owner = _ready_owner(Path(root), gmail_controller, monkeypatch)
        try:
            worker, source, target = _worker_adapters(gmail_controller, owner)
            assert worker.run().expanded == 1
            gmail_controller.script(
                "target",
                "messages.insert",
                {
                    "userId": "me",
                    "body": {"raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")},
                    "internalDateSource": "dateHeader",
                },
                InsertReply(effect=False, lose_response=True),
            )
            assert worker.run().recovery == 1
            assert worker.run().deferred == 1
            original_rows = owner._connection.execute(
                "SELECT * FROM insert_attempts"
            ).fetchall()
            request = LocalId(uuid4().hex)
            owner.ensure_insert_absence_schema(request, b"synthetic-config")
            assert (
                owner._connection.execute("SELECT * FROM insert_attempts").fetchall()
                == original_rows
            )
            backup = owner.state_dir / "backups" / f"insert-absence-v5-{request.value}"
            with sqlite3.connect(f"file:{backup / 'facet.db'}?mode=ro", uri=True) as db:
                assert db.execute("PRAGMA user_version").fetchone() == (4,)
                assert (
                    db.execute("SELECT * FROM insert_attempts").fetchall()
                    == original_rows
                )
                assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            with owner.session.transaction() as uow:
                aid = owner._connection.execute(
                    "SELECT attempt_id FROM insert_attempts"
                ).fetchone()[0]
                attempt = reads.get_attempt(uow, owner.projection_id, LocalId(aid))
            yield owner, worker, source, target, attempt
        finally:
            owner.close()


def advance(monkeypatch, instant):
    from facet import sync
    from facet.projection import recovery, worker

    class Clock:
        @staticmethod
        def now(_timezone):
            return instant

    for module in (recovery, worker, sync):
        monkeypatch.setattr(module, "datetime", Clock)


def test_deadline_then_ordinary_worker_preserves_uncertainty_and_resumes_dependents(
    absent,
    monkeypatch,
    gmail_controller,
):
    owner, worker, source, target, attempt = absent
    checks = UnknownInsertChecks(owner, source, target)
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(seconds=299))
    assert checks.run() == 1
    assert worker.run().processed == 0
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM insert_absence_retries"
    ).fetchone() == (0,)
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=5))
    assert checks.run() == 1
    assert worker.run().verified == 1
    assert worker.run().verified == 1
    assert worker.run().processed == 0
    with owner.session.transaction() as uow:
        old = reads.get_attempt(uow, owner.projection_id, attempt.attempt_id)
        assert (
            replace(
                old,
                revision=attempt.revision,
                recovery_checks=attempt.recovery_checks,
                next_recovery_at=attempt.next_recovery_at,
            )
            == attempt
        )
        assert (
            reads.counts(uow, owner.projection_id, None).unresolved_attempts.value == 0
        )
    assert len(gmail_controller.identifiers("target")) == 2
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM message_mappings"
    ).fetchone() == (2,)
    from test_db_repositories import view

    with view((None, owner._connection, owner.session, owner.owner_info)) as reader:
        assert reader.get_attempt(owner.projection_id, attempt.attempt_id) == old
        assert reader.counts(owner.projection_id, None).unresolved_attempts.value == 0
    root, config = owner.state_dir, owner.config
    owner.close()
    with StateOwner.open(root, config) as reopened:
        assert reopened._connection.execute(
            "SELECT COUNT(*) FROM insert_absence_retries"
        ).fetchone() == (1,)
        assert reopened._connection.execute("PRAGMA integrity_check").fetchone() == (
            "ok",
        )
    for path in root.rglob("*"):
        if path.is_file():
            assert b"RETRY_PRIVATE_BODY_SENTINEL" not in path.read_bytes()


@pytest.mark.parametrize(
    "fault", ["network", "auth", "rate", "storage", "multiple", "changed", "missing"]
)
def test_aged_errors_or_candidates_never_become_absence(absent, monkeypatch, fault):
    owner, worker, source, target, attempt = absent
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=6))
    if fault in {"network", "auth", "rate", "storage"}:
        code = {
            "network": ErrorCode.NETWORK_UNAVAILABLE,
            "auth": ErrorCode.TARGET_AUTH_REQUIRED,
            "rate": ErrorCode.TARGET_RATE_LIMITED,
            "storage": ErrorCode.TARGET_STORAGE_FULL,
        }[fault]

        def failed(_id):
            raise ProviderFailure(code, Role.TARGET, retry_after_seconds=600)

        monkeypatch.setattr(target, "find_by_rfc_message_id", failed)
    elif fault == "multiple":
        from facet.contracts import ProviderId

        monkeypatch.setattr(
            target,
            "find_by_rfc_message_id",
            lambda _: (ProviderId("x"), ProviderId("y")),
        )
    elif fault == "changed":
        monkeypatch.setattr(
            source, "raw", lambda *args, **kwargs: _raw("changed", "different")
        )
    else:

        def missing(*args, **kwargs):
            raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.SOURCE, status=404)

        monkeypatch.setattr(source, "raw", missing)
    try:
        assert UnknownInsertChecks(owner, source, target).run() == 1
    except ProviderFailure:
        assert fault in {"auth", "storage"}
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM insert_absence_retries"
    ).fetchone() == (0,)
    assert worker.run().processed == 0


def test_stopped_thread_never_requeues(absent, monkeypatch):
    owner, worker, source, target, attempt = absent
    with owner.session.transaction() as uow:
        policy.stop_thread(
            uow,
            owner.projection_id,
            attempt.source_thread_id,
            attempt.generation,
            Timestamp(datetime.now(UTC)),
            ThreadStopReason.BLACKLIST,
        )
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=6))
    assert UnknownInsertChecks(owner, source, target).run() == 0
    assert worker.run().processed == 0


def test_decision_and_requeue_roll_back_together(absent, monkeypatch):
    owner, _, source, target, attempt = absent
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=6))

    def fail(*args, **kwargs):
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)

    monkeypatch.setattr(intents, "_result_disposition", fail)
    with pytest.raises(StorageFailure):
        UnknownInsertChecks(owner, source, target).run()
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM insert_absence_retries"
    ).fetchone() == (0,)
    assert owner._connection.execute(
        "SELECT state,recovery_checks FROM insert_attempts"
    ).fetchone() == ("pending_recovery", 0)


def test_v5_still_rejects_unrelated_unresolved_and_retains_decisions(
    absent, monkeypatch
):
    from facet.db.repositories.serialization import COLUMNS, _encode_row

    owner, worker, source, target, attempt = absent
    columns = COLUMNS["insert_attempts"]
    duplicate = replace(attempt, attempt_id=LocalId(uuid4().hex))
    with pytest.raises(StorageFailure), owner.session.transaction() as uow:
        uow._execute(
            "INSERT INTO insert_attempts("
            + ",".join(columns)
            + ") VALUES("
            + ",".join("?" for _ in columns)
            + ")",
            _encode_row("insert_attempts", duplicate),
        )
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=6))
    assert UnknownInsertChecks(owner, source, target).run() == 1
    assert worker.run().verified == 1
    for sql in (
        "UPDATE insert_absence_retries SET checked_at=checked_at+1",
        "DELETE FROM insert_absence_retries",
    ):
        with pytest.raises(StorageFailure), owner.session.transaction() as uow:
            uow._execute(sql)
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM insert_absence_retries"
    ).fetchone() == (1,)


def test_aged_provider_backoff_is_not_bypassed(absent, monkeypatch):
    owner, _, source, target, attempt = absent
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=6))
    checks = []

    def unavailable(_id):
        checks.append(True)
        raise ProviderFailure(
            ErrorCode.NETWORK_UNAVAILABLE, Role.TARGET, retry_after_seconds=600
        )

    monkeypatch.setattr(target, "find_by_rfc_message_id", unavailable)
    runner = UnknownInsertChecks(owner, source, target)
    assert runner.run() == 1
    assert runner.run() == 0
    assert checks == [True]
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM insert_absence_retries"
    ).fetchone() == (0,)


def test_multiple_threads_are_checked_in_bounded_batches(
    absent, monkeypatch, gmail_controller
):
    from facet.contracts import Count, JobState, ProviderId, Revision
    from facet.contracts.records import ThreadGenerationGuardUntracked
    from facet.db.keys import job_key
    from facet.db.repositories.base import _decode, _get
    from facet.db.repositories.serialization import COLUMNS

    owner, worker, source, target, attempt = absent
    thread_id = ProviderId("second-thread")
    raw = _raw("second", "SECOND_PRIVATE_BODY_SENTINEL")
    gmail_controller.seed(
        "source", "second-message", thread_id.value, raw, payload=_payload(raw)
    )
    with owner.session.transaction() as uow:
        thread = _get(
            uow,
            owner.projection_id,
            "tracked_threads",
            (("source_thread_id", attempt.source_thread_id),),
        )
        admission = _get(
            uow,
            owner.projection_id,
            "thread_admissions",
            (
                ("source_thread_id", thread.source_thread_id),
                ("admission_revision", thread.admission_revision),
            ),
        )
        values = owner._connection.execute(
            "SELECT "
            + ",".join(COLUMNS["sync_jobs"])
            + " FROM sync_jobs WHERE kind='expand_thread'"
        ).fetchone()
        parent = _decode(uow, owner.projection_id, "sync_jobs", values)
        subject = replace(parent.subject, source_thread_id=thread_id)
        parent = replace(
            parent,
            job_id=LocalId(uuid4().hex),
            subject=subject,
            stable_key=job_key(owner.projection_id, subject),
            state=JobState.QUEUED,
            revision=Revision(0),
            attempt_count=Count(0),
        )
        policy.admit_thread(
            uow,
            owner.projection_id,
            replace(thread, source_thread_id=thread_id),
            replace(admission, source_thread_id=thread_id),
            (parent,),
            ThreadGenerationGuardUntracked("untracked"),
        )
    assert worker.run().expanded == 1
    gmail_controller.script(
        "target",
        "messages.insert",
        {
            "userId": "me",
            "body": {"raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")},
            "internalDateSource": "dateHeader",
        },
        InsertReply(effect=False, lose_response=True),
    )
    assert worker.run().recovery == 1
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=6))
    runner = UnknownInsertChecks(owner, source, target)
    assert runner.run(limit=1) == 1
    assert runner.run(limit=1) == 1
    assert runner.run(limit=1) == 0
    assert worker.run(max_jobs=10).verified == 3
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM message_mappings"
    ).fetchone() == (3,)


def test_replacement_unknown_uses_fresh_deadline_again(
    absent, monkeypatch, gmail_controller
):
    owner, worker, source, target, attempt = absent
    checks = UnknownInsertChecks(owner, source, target)
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=6))
    assert checks.run() == 1
    raw = source.raw(attempt.source_message_id)
    gmail_controller.script(
        "target",
        "messages.insert",
        {
            "userId": "me",
            "body": {"raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")},
            "internalDateSource": "dateHeader",
        },
        InsertReply(effect=False, lose_response=True),
    )
    assert worker.run().recovery == 1
    assert checks.run() == 1
    assert worker.run().processed == 0
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=12))
    assert checks.run() == 1
    assert worker.run().verified == 1
    assert worker.run().verified == 1
    assert owner._connection.execute(
        "SELECT COUNT(*) FROM insert_absence_retries"
    ).fetchone() == (2,)


def test_definite_401_retry_not_suppressed_by_old_unknown(
    absent, monkeypatch, gmail_controller
):
    owner, worker, source, target, attempt = absent
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=6))
    assert UnknownInsertChecks(owner, source, target).run() == 1
    raw = source.raw(attempt.source_message_id)
    refreshed = []
    monkeypatch.setattr(
        target, "refresh_credentials", lambda: refreshed.append(True) or True
    )
    gmail_controller.script(
        "target",
        "messages.insert",
        {
            "userId": "me",
            "body": {"raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")},
            "internalDateSource": "dateHeader",
        },
        HttpFailure(401),
    )
    assert worker.run().deferred == 1
    assert refreshed == [True]
    advance(monkeypatch, attempt.dispatch_started_at.value + timedelta(minutes=12))
    assert worker.run().verified == 1


@pytest.mark.parametrize("fail_ddl", [False, True])
def test_v5_upgrade_backs_up_and_rolls_back(monkeypatch, fail_ddl):
    from facet.config import dump_config, initial_template
    from facet.db import schema

    with TemporaryDirectory(prefix="facet-v5-", dir=_trusted_parent()) as root:
        config = initial_template("source@example.com", "target@example.com")
        raw = dump_config(config)
        state = Path(root) / "state"
        with StateOwner.create(state, config, raw) as owner:
            owner.ensure_current_action_schema(LocalId(uuid4().hex), raw)
            before = owner._connection.execute("SELECT * FROM bindings").fetchall()
            request = LocalId(uuid4().hex)
            real = schema._inspect_manifest

            def inspect(connection, manifest):
                if fail_ddl and manifest.version.value == 5:
                    raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE)
                return real(connection, manifest)

            monkeypatch.setattr(schema, "_inspect_manifest", inspect)
            if fail_ddl:
                with pytest.raises(StorageFailure):
                    owner.ensure_insert_absence_schema(request, raw)
            else:
                owner.ensure_insert_absence_schema(request, raw)
            assert owner._connection.execute("PRAGMA user_version").fetchone() == (
                4 if fail_ddl else 5,
            )
            assert (
                owner._connection.execute("SELECT * FROM bindings").fetchall() == before
            )
            bundle = state / "backups" / f"insert-absence-v5-{request.value}"
            with sqlite3.connect(f"file:{bundle / 'facet.db'}?mode=ro", uri=True) as db:
                assert db.execute("PRAGMA user_version").fetchone() == (4,)
            assert bundle.stat().st_mode & 0o077 == 0
        monkeypatch.setattr(schema, "_inspect_manifest", real)
        with StateOwner.open(state, config) as owner:
            assert owner._connection.execute("PRAGMA user_version").fetchone() == (
                4 if fail_ddl else 5,
            )
