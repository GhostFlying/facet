"""Synthetic end-to-end evidence for the serial projection worker."""

import base64
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fakes.gmail import HttpFailure, InsertReply

from facet.config import initial_template
from facet.contracts import (
    BindingState,
    Generation,
    PolicyVersion,
    ProviderId,
    Revision,
    Role,
    RuleKind,
    RuleOrigin,
    RuleRef,
    Sha256Hex,
    Timestamp,
)
from facet.db.codecs import RuleValue, ThreadStopReason
from facet.db.models import (
    BindingRevisionRow,
    RevisionGuard,
    RuleRevisionRow,
    RuleRow,
    RulesetMemberRow,
    RulesetRow,
)
from facet.gmail.credential_models import ScopePolicy, policy_scopes
from facet.gmail.credentials import CredentialManager
from facet.gmail.source import SourceAdapter
from facet.gmail.target import TargetAdapter
from facet.projection.backfill import BackfillProducer, DiscoveryDecision
from facet.projection.fidelity import inspect
from facet.projection.worker import ProjectionWorker
from facet.runtime.state_owner import StateOwner

NOW = Timestamp(datetime(2026, 10, 4, tzinfo=UTC))


class _SourceDiscovery:
    def profile(self):
        from facet.contracts import ProviderId
        from facet.gmail.source import SourceProfile

        return SourceProfile("source@example.invalid", ProviderId("h-1"), 2, 1)

    def discover(self, *, window_start, window_end, page_token=None):
        from facet.contracts import ProviderId
        from facet.gmail.source import DiscoveryItem, DiscoveryPage

        return DiscoveryPage(
            (DiscoveryItem(ProviderId("m-new"), ProviderId("thread-1")),), None, 1
        )


class _Admission:
    def __init__(self, rule_id):
        self.rule_id = rule_id

    def evaluate(self, item, epoch):
        return DiscoveryDecision(True, RuleRef(self.rule_id, Revision(1)))


def _trusted_parent():
    for candidate in (Path.cwd(), Path(f"/run/user/{os.geteuid()}")):
        try:
            entries = (candidate, *candidate.parents)
            if all(
                stat.S_ISDIR(info.st_mode)
                and info.st_uid in (0, os.geteuid())
                and stat.S_IMODE(info.st_mode) & 0o7022 == 0
                for entry in entries
                for info in (entry.stat(follow_symlinks=False),)
            ):
                return candidate
        except OSError:
            continue
    pytest.skip("no verified trusted test anchor")


def _raw(message_id, body):
    return (
        f"Date: Tue, 01 Apr 2026 10:00:00 +0000\r\n"
        f"Message-ID: <{message_id}@example.invalid>\r\n"
        "From: sender@example.invalid\r\n"
        "To: target@example.invalid\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{body}\r\n"
    ).encode()


def _payload(raw):
    headers, _, _ = raw.partition(b"\r\n\r\n")
    return {
        "headers": [
            {
                "name": line.split(b":", 1)[0].decode(),
                "value": line.split(b":", 1)[1].strip().decode(),
            }
            for line in headers.split(b"\r\n")
        ]
    }


def _ready_owner(root, controller, monkeypatch):
    config = initial_template("source@example.invalid", "target@example.invalid")
    owner = StateOwner.create(root / "state", config, b"synthetic-config")
    from test_m2_foundation_consumers import Profiles, write_credentials

    write_credentials(owner)
    manager = CredentialManager(owner.state_dir, config, owner)
    source_scopes = policy_scopes(ScopePolicy.SOURCE_READONLY, Role.SOURCE)
    target_scopes = policy_scopes(ScopePolicy.TARGET_DEFAULT, Role.TARGET)
    manager.verify_and_publish(Profiles(source_scopes, target_scopes))
    projection = config.projection.id
    with owner.session.transaction() as uow:
        from facet.db.repositories.base import _get, _insert

        for role in Role:
            binding = _get(uow, projection, "bindings", (("role", role),))
            _insert(
                uow,
                projection,
                "binding_revisions",
                BindingRevisionRow(
                    projection,
                    role,
                    Revision(2),
                    binding.declared_address,
                    binding.declared_address,
                    BindingState.VERIFIED,
                    NOW,
                ),
            )
            uow._execute(
                "UPDATE bindings SET state='verified',"
                "verified_address=declared_address,"
                "verified_at=?,binding_revision=2,credential_revision=1 "
                "WHERE projection_id=? AND role=?",
                (int(NOW.value.timestamp() * 1_000_000), projection.value, role.value),
            )
        uow._execute(
            "UPDATE projections SET binding_state='verified',daemon_paused=0 "
            "WHERE projection_id=?",
            (projection.value,),
        )
    with owner.session.transaction() as uow:
        uow._execute(
            "UPDATE projections SET daemon_paused=0 WHERE projection_id=?",
            (projection.value,),
        )
    rule = RuleRow(
        projection,
        __import__("test_m2_foundation_consumers").lid(900),
        RuleKind.ALLOW_SENDER,
        RuleValue("synthetic@example.invalid"),
        Revision(1),
    )
    with owner.session.transaction() as uow:
        from facet.db.repositories import policy

        policy.publish_rules(
            uow,
            projection,
            (rule,),
            (
                RuleRevisionRow(
                    projection,
                    rule.rule_id,
                    Revision(1),
                    True,
                    NOW,
                    RuleOrigin.CLI,
                    PolicyVersion("auth-v1"),
                ),
            ),
            RulesetRow(projection, Revision(1), NOW, True),
            (RulesetMemberRow(projection, Revision(1), rule.rule_id, Revision(1)),),
            RevisionGuard(Revision(0)),
        )
    producer = BackfillProducer(_SourceDiscovery(), _Admission(rule.rule_id))
    from test_m2_foundation_consumers import lid

    from facet.db import command_store
    from facet.db.command_records import BackfillPreviewRequest, BackfillStartRequest

    monkeypatch.setattr(command_store, "_owner_now", lambda: NOW)
    monkeypatch.setattr("facet.projection.backfill._now", lambda: NOW)

    preview = producer.preview(
        owner.session,
        projection,
        BackfillPreviewRequest(
            lid(901),
            lid(902),
            Timestamp(datetime(2026, 4, 1, tzinfo=UTC)),
            NOW,
            Timestamp(datetime(2026, 10, 1, tzinfo=UTC)),
            Sha256Hex("a" * 64),
            NOW,
            Revision(0),
            NOW,
        ),
    )
    _, epoch = producer.start(
        owner.session,
        projection,
        BackfillStartRequest(
            lid(903),
            lid(904),
            preview.operation_id,
            lid(905),
            __import__("facet.contracts").contracts.ProviderId("h-0"),
            NOW,
            NOW,
        ),
    )
    producer.discover(owner.session, projection, epoch.epoch_id)
    return owner


def test_fidelity_ignores_transport_headers_and_keeps_raw_only_in_memory():
    raw = _raw("message", "PRIVATE_SENTINEL")
    changed = raw.replace(b"Date:", b"Received: private-hop\r\nDate:")
    first, second = inspect(raw), inspect(changed)
    assert first.semantic_digest == second.semantic_digest
    assert first.raw_digest != second.raw_digest
    assert first.rfc_message_id is not None
    assert repr(first) == "<fidelity facts>"

    multipart = (
        b"Date: invalid-date\r\n"
        b"Message-ID: <multipart@example.invalid>\r\n"
        b"In-Reply-To: <parent@example.invalid>\r\n"
        b"Content-Type: multipart/mixed; boundary=facet-boundary\r\n\r\n"
        b"--facet-boundary\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        b"<p>\xe4\xbd\xa0\xe5\xa5\xbd</p>\r\n"
        b"--facet-boundary\r\n"
        b"Content-Type: text/plain\r\n"
        b"Content-Disposition: attachment; filename=note.txt\r\n\r\n"
        b"attachment\r\n--facet-boundary--\r\n"
    )
    assert inspect(multipart).date_policy.value == "fallback_received_time"


def _worker_adapters(controller, owner):
    source = SourceAdapter(
        controller.service("source", scopes=frozenset({"gmail.readonly"}))
    )
    target = TargetAdapter(
        controller.service(
            "target", scopes=frozenset({"gmail.insert", "gmail.readonly"})
        )
    )
    return ProjectionWorker(owner, source, target), source, target


def test_worker_expands_inserts_reads_back_and_maps(gmail_controller, monkeypatch):
    parent = _trusted_parent()
    raw_old = _raw("old", "OLD_SENTINEL")
    raw_new = _raw("new", "NEW_SENTINEL")
    payload_old, payload_new = _payload(raw_old), _payload(raw_new)
    gmail_controller.seed(
        "source",
        "m-old",
        "thread-1",
        raw_old,
        labels=("SPAM",),
        internal_date="1000",
        payload=payload_old,
    )
    gmail_controller.seed(
        "source",
        "m-new",
        "thread-1",
        raw_new,
        internal_date="2000",
        payload=payload_new,
    )
    with TemporaryDirectory(prefix="facet-worker-", dir=parent) as root:
        owner = _ready_owner(Path(root), gmail_controller, monkeypatch)
        try:
            worker, source, target = _worker_adapters(gmail_controller, owner)
            assert worker.run().expanded == 1
            receipt = worker.run(max_jobs=5)
            assert receipt.processed == 2
            assert receipt.verified == 2
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM message_mappings"
            ).fetchone() == (2,)
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM job_claims"
            ).fetchone() == (0,)
            assert set(gmail_controller.identifiers("target")) == {
                "inserted-1",
                "inserted-2",
            }
            assert worker.run(max_jobs=5).processed == 0
            config = initial_template(
                "source@example.invalid", "target@example.invalid"
            )
            owner.close()
            reopened = StateOwner.open(Path(root) / "state", config)
            try:
                replay = ProjectionWorker(reopened, source, target)
                assert replay.run(max_jobs=5).processed == 0
                assert gmail_controller.identifiers("target") == (
                    "inserted-1",
                    "inserted-2",
                )
            finally:
                reopened.close()
            for path in (owner.database_path, Path(str(owner.database_path) + "-wal")):
                if path.exists():
                    assert b"SENTINEL" not in path.read_bytes()
        finally:
            owner.close()


def test_worker_response_loss_stays_in_recovery_without_blind_retry(
    gmail_controller, monkeypatch
):
    parent = _trusted_parent()
    raw = _raw("uncertain", "UNCERTAIN_SENTINEL")
    gmail_controller.seed(
        "source",
        "m-new",
        "thread-1",
        raw,
        internal_date="1000",
        payload=_payload(raw),
    )
    with TemporaryDirectory(prefix="facet-worker-recovery-", dir=parent) as root:
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
                    "neverMarkSpam": True,
                },
                InsertReply(lose_response=True),
            )
            receipt = worker.run()
            assert receipt.recovery == 1
            assert gmail_controller.identifiers("target") == ("inserted-1",)
            assert owner._connection.execute(
                "SELECT state FROM insert_attempts"
            ).fetchone() == ("pending_recovery",)
            assert owner._connection.execute(
                "SELECT state FROM sync_jobs WHERE kind='recover_insert'"
            ).fetchone() == ("queued",)
            assert worker.run().processed == 0
            assert gmail_controller.identifiers("target") == ("inserted-1",)
        finally:
            owner.close()


def test_worker_excludes_drafts_but_keeps_empty_thread_explainable(
    gmail_controller, monkeypatch
):
    parent = _trusted_parent()
    raw = _raw("draft", "DRAFT_SENTINEL")
    gmail_controller.seed(
        "source",
        "m-new",
        "thread-1",
        raw,
        labels=("DRAFT",),
        payload=_payload(raw),
    )
    with TemporaryDirectory(prefix="facet-worker-draft-", dir=parent) as root:
        owner = _ready_owner(Path(root), gmail_controller, monkeypatch)
        try:
            worker, _, _ = _worker_adapters(gmail_controller, owner)
            assert worker.run().expanded == 1
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM sync_jobs WHERE kind='project_message'"
            ).fetchone() == (0,)
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM job_claims"
            ).fetchone() == (0,)
        finally:
            owner.close()


def test_worker_source_missing_clears_claim_with_typed_state(
    gmail_controller, monkeypatch
):
    parent = _trusted_parent()
    raw = _raw("missing", "MISSING_SENTINEL")
    gmail_controller.seed("source", "m-new", "thread-1", raw, payload=_payload(raw))
    with TemporaryDirectory(prefix="facet-worker-missing-", dir=parent) as root:
        owner = _ready_owner(Path(root), gmail_controller, monkeypatch)
        try:
            worker, _, _ = _worker_adapters(gmail_controller, owner)
            assert worker.run().expanded == 1
            gmail_controller.remove_source_fact("m-new")
            assert worker.run().deferred == 1
            assert owner._connection.execute(
                "SELECT state,last_error_code FROM sync_jobs "
                "WHERE kind='project_message'"
            ).fetchone() == ("source_missing", "source_missing")
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM job_claims"
            ).fetchone() == (0,)
        finally:
            owner.close()


def test_worker_source_raw_cap_clears_claim_without_target_call(
    gmail_controller, monkeypatch
):
    parent = _trusted_parent()
    raw = _raw("oversize", "OVERSIZE_SENTINEL")
    gmail_controller.seed("source", "m-new", "thread-1", raw, payload=_payload(raw))
    with TemporaryDirectory(prefix="facet-worker-cap-", dir=parent) as root:
        owner = _ready_owner(Path(root), gmail_controller, monkeypatch)
        try:
            worker, _, _ = _worker_adapters(gmail_controller, owner)
            assert worker.run().expanded == 1
            bounded = ProjectionWorker(
                owner,
                worker._source,
                worker._target,
                max_raw_bytes=16,
            )
            assert bounded.run().deferred == 1
            assert owner._connection.execute(
                "SELECT state,last_error_code FROM sync_jobs "
                "WHERE kind='project_message'"
            ).fetchone() == ("needs_attention", "invalid_input")
            assert gmail_controller.identifiers("target") == ()
        finally:
            owner.close()


def test_worker_readback_failure_keeps_typed_attention_and_no_claim(
    gmail_controller, monkeypatch
):
    parent = _trusted_parent()
    raw = _raw("readback", "READBACK_SENTINEL")
    gmail_controller.seed("source", "m-new", "thread-1", raw, payload=_payload(raw))
    with TemporaryDirectory(prefix="facet-worker-readback-", dir=parent) as root:
        owner = _ready_owner(Path(root), gmail_controller, monkeypatch)
        try:
            worker, _, _ = _worker_adapters(gmail_controller, owner)
            assert worker.run().expanded == 1
            gmail_controller.script(
                "target",
                "messages.get",
                {"userId": "me", "id": "inserted-1", "format": "raw"},
                HttpFailure(429),
            )
            assert worker.run().deferred == 1
            assert owner._connection.execute(
                "SELECT state,error_code FROM insert_attempts"
            ).fetchone() == ("needs_attention", "target_rate_limited")
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM job_claims"
            ).fetchone() == (0,)
        finally:
            owner.close()


def test_worker_does_not_project_after_thread_stop(gmail_controller, monkeypatch):
    parent = _trusted_parent()
    raw = _raw("stopped", "STOPPED_SENTINEL")
    gmail_controller.seed("source", "m-new", "thread-1", raw, payload=_payload(raw))
    with TemporaryDirectory(prefix="facet-worker-stop-", dir=parent) as root:
        owner = _ready_owner(Path(root), gmail_controller, monkeypatch)
        try:
            worker, _, _ = _worker_adapters(gmail_controller, owner)
            assert worker.run().expanded == 1
            with owner.session.transaction() as uow:
                from facet.db.repositories import policy

                policy.stop_thread(
                    uow,
                    owner.projection_id,
                    ProviderId("thread-1"),
                    Generation(1),
                    NOW,
                    ThreadStopReason.MANUAL_STOP,
                )
            assert worker.run().processed == 0
            assert gmail_controller.identifiers("target") == ()
        finally:
            owner.close()
