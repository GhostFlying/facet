"""Incremental product behavior through the existing durable foreground runner."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from test_projection_worker import _raw, _ready_owner, _trusted_parent
from test_sync import _Source, _Target

from facet.contracts import (
    ErrorCode,
    Generation,
    LocalId,
    PolicyVersion,
    ProviderId,
    Revision,
    Role,
    RuleKind,
    RuleOrigin,
    Timestamp,
    Visibility,
)
from facet.db.codecs import PrivateAddress, RuleValue, StorageFailure, ThreadStopReason
from facet.db.models import (
    RevisionGuard,
    RuleRevisionRow,
    RuleRow,
    RulesetMemberRow,
    RulesetRow,
)
from facet.db.repositories import events, policy
from facet.db.repositories.base import _get
from facet.gmail.retry import ProviderFailure
from facet.gmail.source import (
    CandidateResult,
    HistoryMessage,
    HistoryPage,
    HistoryRecord,
)
from facet.projection.admission import DiscoveryCandidate
from facet.projection.rules import normalize_sender
from facet.runtime.foreground_runtime import load_persisted_admission
from facet.sync import ForegroundSync

DATE = Timestamp(datetime(2026, 10, 6, tzinfo=UTC))


class HistorySource(_Source):
    def __init__(
        self,
        owner,
        *,
        sender="synthetic@example.com",
        draft=False,
        visibility=Visibility.NORMAL,
        date=DATE,
    ):
        super().__init__(_raw("m-new", "HISTORY_PRIVATE_BODY"))
        self.owner = owner
        self.sender = sender
        self.draft = draft
        self.visibility = visibility
        self.date = date
        self.metadata_calls = 0
        self.on_metadata = lambda: None
        self.arrivals = True

    def history(self, cursor, *, page_token=None):
        return HistoryPage(
            ProviderId("h-2"),
            (
                HistoryRecord(
                    ProviderId("record-new"),
                    (HistoryMessage(ProviderId("m-new"), ProviderId("thread-1")),),
                    (),
                    (),
                    (),
                ),
            )
            if self.arrivals
            else (),
            None,
        )

    def history_candidate(self, item):
        assert not self.owner._connection.in_transaction
        self.metadata_calls += 1
        self.on_metadata()
        return CandidateResult(
            candidate=DiscoveryCandidate(
                item.message_id,
                item.thread_id,
                normalize_sender(self.sender),
                PrivateAddress(self.owner.config.projection.source_email),
                self.visibility,
                self.draft,
                self.date,
            )
        )

    candidate = history_candidate

    def message_metadata(self, message_id):
        assert not self.owner._connection.in_transaction
        self.metadata_calls += 1
        self.on_metadata()
        value = self.thread_metadata(ProviderId("thread-1")).messages[0]
        labels = (
            ("DRAFT",)
            if self.draft
            else {Visibility.SPAM: ("SPAM",), Visibility.TRASH: ("TRASH",)}.get(
                self.visibility, ()
            )
        )
        return replace(value, labels=labels)


def _runner(owner, source, target):
    return ForegroundSync(
        owner,
        source,
        target,
        load_persisted_admission(owner, owner.config),
        admission_for_history=lambda: load_persisted_admission(owner, owner.config),
    )


@pytest.mark.parametrize(
    "case", ["sender", "no_match", "empty", "draft", "spam", "trash", "old"]
)
def test_history_new_thread_admission_or_normal_no_effect(monkeypatch, case):
    with TemporaryDirectory(prefix="facet-history-", dir=_trusted_parent()) as root:
        owner = _ready_owner(
            Path(root), object(), monkeypatch, seed=False, with_rule=case != "empty"
        )
        source = HistorySource(
            owner,
            sender="other@example.com"
            if case == "no_match"
            else "synthetic@example.com",
            draft=case == "draft",
            visibility={"spam": Visibility.SPAM, "trash": Visibility.TRASH}.get(
                case, Visibility.NORMAL
            ),
            date=Timestamp(datetime(2026, 1, 1, tzinfo=UTC)) if case == "old" else DATE,
        )
        target = _Target(source.raw_bytes)
        try:
            result = _runner(owner, source, target).run_once()
            assert result.attention == 0
            assert target.inserted == (1 if case == "sender" else 0)
            assert owner._connection.execute(
                "SELECT processing FROM source_events"
            ).fetchone() == ("consumed",)
            assert owner._connection.execute(
                "SELECT state FROM sync_jobs WHERE kind='resolve_event'"
            ).fetchone() == ("completed",)
            if case == "sender":
                assert owner._connection.execute(
                    "SELECT tag FROM thread_admissions"
                ).fetchone() == ("future_rule",)
                assert owner._connection.execute(
                    "SELECT COUNT(*) FROM message_mappings"
                ).fetchone() == (1,)
                _runner(owner, source, target).run_once()
                assert target.inserted == 1
            if case == "empty":
                assert source.metadata_calls == 0
            assert (
                b"HISTORY_PRIVATE_BODY"
                not in (Path(owner.state_dir) / "facet.db").read_bytes()
            )
        finally:
            owner.close()


@pytest.mark.parametrize(
    "stopped,draft", [(True, False), (False, True), (False, False)]
)
def test_tracked_history_never_readmits_and_filters_draft(monkeypatch, stopped, draft):
    with TemporaryDirectory(prefix="facet-history-", dir=_trusted_parent()) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch)
        source = HistorySource(
            owner,
            sender="not-allowed@example.com",
            draft=draft,
            visibility=Visibility.SPAM,
        )
        target = _Target(source.raw_bytes)
        try:
            # Cancel the unstarted fixture expansion; exercise only History.
            with owner.session.transaction() as uow:
                uow._execute(
                    "UPDATE sync_jobs SET state='cancelled' WHERE kind='expand_thread'",
                    (),
                )
                if stopped:
                    policy.stop_thread(
                        uow,
                        owner.projection_id,
                        ProviderId("thread-1"),
                        Generation(1),
                        DATE,
                        ThreadStopReason.MANUAL_STOP,
                    )
                # Removing allow rules does not revoke existing thread consent.
                policy.publish_rules(
                    uow,
                    owner.projection_id,
                    (),
                    (),
                    RulesetRow(owner.projection_id, Revision(2), DATE, True),
                    (),
                    RevisionGuard(Revision(1)),
                )
            result = _runner(owner, source, target).run_once()
            assert result.attention == 0
            assert target.inserted == (0 if stopped or draft else 1)
            assert owner._connection.execute(
                "SELECT active,generation,admission_revision FROM tracked_threads"
            ).fetchone() == (0 if stopped else 1, 2 if stopped else 1, 1)
            assert source.metadata_calls == (0 if stopped else 1)
            assert owner._connection.execute(
                "SELECT processing FROM source_events"
            ).fetchone() == ("consumed",)
        finally:
            owner.close()


@pytest.mark.parametrize("matching", [True, False])
def test_rules_changed_during_metadata_read_retain_event_for_retry(
    monkeypatch, matching
):
    with TemporaryDirectory(prefix="facet-history-", dir=_trusted_parent()) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch, seed=False)
        source = HistorySource(
            owner, sender="synthetic@example.com" if matching else "other@example.com"
        )
        target = _Target(source.raw_bytes)

        def change_rule():
            source.on_metadata = lambda: None
            with owner.session.transaction() as uow:
                current = _get(uow, owner.projection_id, "projections", ())
                policy.publish_rules(
                    uow,
                    owner.projection_id,
                    (),
                    (),
                    RulesetRow(owner.projection_id, Revision(2), DATE, True),
                    (),
                    RevisionGuard(current.ruleset_revision),
                )

        source.on_metadata = change_rule
        try:
            result = _runner(owner, source, target).run_once()
            assert result.attention == 1
            assert target.inserted == 0
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM tracked_threads"
            ).fetchone() == (0,)
            assert owner._connection.execute(
                "SELECT processing FROM source_events"
            ).fetchone() == ("pending",)
            assert owner._connection.execute(
                "SELECT state,last_error_code FROM sync_jobs WHERE kind='resolve_event'"
            ).fetchone() == ("retry_wait", "owner_busy")
        finally:
            owner.close()


def test_metadata_network_failure_is_durable_retry_then_continues(monkeypatch):
    with TemporaryDirectory(prefix="facet-history-", dir=_trusted_parent()) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch, seed=False)
        source = HistorySource(owner)
        target = _Target(source.raw_bytes)

        def fail():
            raise ProviderFailure(
                ErrorCode.NETWORK_UNAVAILABLE,
                Role.SOURCE,
            )

        source.on_metadata = fail
        try:
            assert _runner(owner, source, target).run_once().attention == 1
            assert target.inserted == 0
            assert owner._connection.execute(
                "SELECT state FROM sync_jobs WHERE kind='resolve_event'"
            ).fetchone() == ("retry_wait",)
            source.on_metadata = lambda: None
            import facet.sync as sync

            real_now = sync._now
            monkeypatch.setattr(
                sync, "_now", lambda: Timestamp(real_now().value + timedelta(seconds=2))
            )
            assert _runner(owner, source, target).run_once().projected.verified == 1
            assert target.inserted == 1
        finally:
            owner.close()


def _add_rule(owner, kind, value, effective_at, *, retain_sender=False):
    p = owner.projection_id
    with owner.session.transaction() as uow:
        projection = _get(uow, p, "projections", ())
        rev = Revision(projection.ruleset_revision.value + 1)
        rule_id = LocalId(uuid4().hex)
        members = [RulesetMemberRow(p, rev, rule_id, Revision(1))]
        if retain_sender:
            members.append(
                RulesetMemberRow(
                    p, rev, LocalId("00000000000040008000000000000384"), Revision(1)
                )
            )
        policy.publish_rules(
            uow,
            p,
            (RuleRow(p, rule_id, kind, RuleValue(value), Revision(1)),),
            (
                RuleRevisionRow(
                    p,
                    rule_id,
                    Revision(1),
                    True,
                    effective_at,
                    RuleOrigin.CLI,
                    PolicyVersion("auth-v1"),
                ),
            ),
            RulesetRow(p, rev, effective_at, True),
            tuple(members),
            RevisionGuard(projection.ruleset_revision),
        )


@pytest.mark.parametrize(
    "sender,admitted",
    [
        ("sender@example.com", True),
        ("sender@sub.example.com", True),
        ("sender@notexample.com", False),
    ],
)
def test_current_domain_rule_after_initial_epoch(monkeypatch, sender, admitted):
    with TemporaryDirectory(prefix="facet-history-", dir=_trusted_parent()) as root:
        owner = _ready_owner(
            Path(root), object(), monkeypatch, seed=False, with_rule=False
        )
        source = HistorySource(owner, sender=sender)
        source.arrivals = False
        target = _Target(source.raw_bytes)
        try:
            _runner(owner, source, target).run_once()
            _add_rule(
                owner,
                RuleKind.ALLOW_DOMAIN,
                "example.com",
                Timestamp(DATE.value - timedelta(days=1)),
            )
            source.arrivals = True
            result = _runner(owner, source, target).run_once()
            assert result.attention == 0
            assert target.inserted == int(admitted)
        finally:
            owner.close()


def test_current_blacklist_denies_old_eligible_message(monkeypatch):
    with TemporaryDirectory(prefix="facet-history-", dir=_trusted_parent()) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch, seed=False)
        source = HistorySource(owner, date=Timestamp(DATE.value - timedelta(days=1)))
        source.arrivals = False
        target = _Target(source.raw_bytes)
        try:
            _runner(owner, source, target).run_once()
            _add_rule(
                owner,
                RuleKind.BLACKLIST_SENDER,
                "synthetic@example.com",
                DATE,
                retain_sender=True,
            )
            source.arrivals = True
            assert _runner(owner, source, target).run_once().attention == 0
            assert target.inserted == 0
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM tracked_threads"
            ).fetchone() == (0,)
        finally:
            owner.close()


def test_admission_and_event_fault_roll_back_then_resume(monkeypatch):
    with TemporaryDirectory(prefix="facet-history-", dir=_trusted_parent()) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch, seed=False)
        source = HistorySource(owner)
        target = _Target(source.raw_bytes)
        original = events.classify_event

        def fail_after_enqueue(*args, **kwargs):
            original(*args, **kwargs)
            raise StorageFailure(ErrorCode.OWNER_BUSY)

        monkeypatch.setattr(events, "classify_event", fail_after_enqueue)
        try:
            assert _runner(owner, source, target).run_once().attention == 1
            assert target.inserted == 0
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM tracked_threads"
            ).fetchone() == (0,)
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM sync_jobs WHERE kind='expand_thread'"
            ).fetchone() == (0,)
            assert owner._connection.execute(
                "SELECT processing FROM source_events"
            ).fetchone() == ("pending",)
            monkeypatch.setattr(events, "classify_event", original)
            import facet.sync as sync

            real_now = sync._now
            monkeypatch.setattr(
                sync, "_now", lambda: Timestamp(real_now().value + timedelta(seconds=2))
            )
            assert _runner(owner, source, target).run_once().projected.verified == 1
            assert target.inserted == 1
        finally:
            owner.close()
