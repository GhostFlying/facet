"""Vertical synthetic evidence for the foreground sync composition."""

import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from test_projection_worker import _raw, _ready_owner

from facet.contracts import (
    ErrorCode,
    LocalId,
    ProviderId,
    Revision,
    RuleKind,
    RuleRef,
    Timestamp,
    Visibility,
)
from facet.db.codecs import PrivateAddress, StorageFailure
from facet.gmail.source import (
    DiscoveryItem,
    DiscoveryPage,
    DiscoveryQuery,
    HistoryLabel,
    HistoryMessage,
    HistoryPage,
    HistoryRecord,
    MessageMetadata,
    SourceProfile,
    ThreadMetadata,
)
from facet.gmail.target import TargetInsertResult, TargetReadback
from facet.projection.admission import (
    AdmissionEvaluator,
    AdmissionRule,
    DiscoveryCandidate,
)
from facet.projection.backfill import DiscoveryDecision
from facet.projection.rules import normalize_rule, normalize_sender
from facet.sync import ForegroundSync, SourceCandidateAdmission


class _Admission:
    def __init__(self, admit=False):
        self.admit = admit

    def evaluate(self, item, epoch):
        return DiscoveryDecision(
            self.admit,
            RuleRef(LocalId("00000000000040008000000000000384"), Revision(1))
            if self.admit
            else None,
        )

    def discovery_query(self, epoch=None):
        return DiscoveryQuery(('from:"synthetic@example.com"',)) if self.admit else None


class _Source:
    def __init__(self, raw, *, discover=False, deleted=False, action=False):
        self.raw_bytes = raw
        self.discover_item = discover
        self.deleted = deleted
        self.action = action
        self.discover_calls = 0
        self.history_calls = 0

    def profile(self):
        return SourceProfile("source@example.invalid", ProviderId("h-1"), 1, 1)

    def discover(self, *, window_start, window_end, page_token=None, query=None):
        self.discover_calls += 1
        items = (
            (DiscoveryItem(ProviderId("m-new"), ProviderId("thread-1")),)
            if self.discover_item
            else ()
        )
        return DiscoveryPage(items, None, len(items))

    def history(self, cursor, *, page_token=None):
        self.history_calls += 1
        records = ()
        if self.deleted:
            records = (
                HistoryRecord(
                    ProviderId("history-deleted"),
                    (),
                    (HistoryMessage(ProviderId("m-deleted"), ProviderId("thread-1")),),
                    (),
                    (),
                ),
            )
        if self.action:
            records = (
                HistoryRecord(
                    ProviderId("history-action"),
                    (),
                    (),
                    (
                        HistoryLabel(
                            HistoryMessage(
                                ProviderId("m-action"), ProviderId("thread-1")
                            ),
                            (ProviderId("label-action"),),
                        ),
                    ),
                    (),
                ),
            )
        return HistoryPage(ProviderId("h-2"), records, None)

    def thread_metadata(self, thread_id):
        return ThreadMetadata(
            thread_id,
            (
                MessageMetadata(
                    ProviderId("m-new"),
                    thread_id,
                    (),
                    datetime(2026, 4, 1, 10, tzinfo=UTC),
                    (("Message-ID", "<m-new@example.invalid>"),),
                ),
            ),
        )

    def raw(self, message_id):
        assert message_id == ProviderId("m-new")
        return self.raw_bytes


class _Target:
    def __init__(self, raw):
        self.raw_bytes = raw
        self.inserted = 0

    def insert(self, raw, *, thread_id=None, date_header=True):
        self.inserted += 1
        return TargetInsertResult(ProviderId("tm-1"), ProviderId("tt-1"), None)

    def readback(self, message_id):
        return TargetReadback(message_id, ProviderId("tt-1"), (), self.raw_bytes)


class _RetryAction:
    def __init__(self):
        self.calls = 0
        self.owner = None

    def process(self, *args, **kwargs):
        self.calls += 1
        self.owner = args[0]
        raise StorageFailure(ErrorCode.SOURCE_AUTH_REQUIRED)


def test_source_candidate_admission_uses_metadata_and_rules_only():
    candidate = DiscoveryCandidate(
        ProviderId("m-candidate"),
        ProviderId("thread-candidate"),
        normalize_sender("sender@example.com"),
        PrivateAddress("source@example.com"),
        Visibility.NORMAL,
        False,
        Timestamp(datetime(2026, 4, 1, tzinfo=UTC)),
    )

    class CandidateSource:
        def candidate(self, item):
            from facet.gmail.source import CandidateResult

            return CandidateResult(candidate=candidate)

    policy = AdmissionEvaluator(
        (
            AdmissionRule(
                RuleRef(LocalId("00000000000040008000000000000001"), Revision(1)),
                normalize_rule(RuleKind.ALLOW_SENDER, "sender@example.com"),
                Timestamp(datetime(2026, 1, 1, tzinfo=UTC)),
            ),
        ),
        source_account=PrivateAddress("source@example.com"),
    )
    result = SourceCandidateAdmission(CandidateSource(), policy).evaluate(
        DiscoveryItem(ProviderId("m-candidate"), ProviderId("thread-candidate")),
        object(),
    )
    assert result.admit is True


def test_source_candidate_admission_plans_sender_query_and_no_rule_scope():
    source = type("CandidateSource", (), {"candidate": lambda self, item: None})()
    empty = AdmissionEvaluator(
        (),
        source_account=PrivateAddress("source@example.com"),
        ruleset_revision=Revision(1),
    )
    assert SourceCandidateAdmission(source, empty).discovery_query() is None
    policy = AdmissionEvaluator(
        (
            AdmissionRule(
                RuleRef(LocalId("00000000000040008000000000000002"), Revision(1)),
                normalize_rule(RuleKind.ALLOW_SENDER, "sender@example.com"),
                Timestamp(datetime(2026, 1, 1, tzinfo=UTC)),
            ),
        ),
        source_account=PrivateAddress("source@example.com"),
        ruleset_revision=Revision(1),
    )
    query = SourceCandidateAdmission(source, policy).discovery_query()
    assert query is not None
    assert query.clauses == ('from:"sender@example.com"',)


def test_source_candidate_admission_rejects_ruleset_lineage_mismatch():
    source = type("CandidateSource", (), {"candidate": lambda self, item: None})()
    epoch = SimpleNamespace(decision=SimpleNamespace(ruleset_revision=Revision(2)))
    pinned = AdmissionEvaluator(
        (),
        source_account=PrivateAddress("source@example.com"),
        ruleset_revision=Revision(2),
    )
    assert SourceCandidateAdmission(source, pinned).discovery_query(epoch) is None
    policy = AdmissionEvaluator(
        (),
        source_account=PrivateAddress("source@example.com"),
        ruleset_revision=Revision(3),
    )
    with pytest.raises(StorageFailure) as error:
        SourceCandidateAdmission(source, policy).discovery_query(epoch)
    assert error.value.code is ErrorCode.CONSISTENCY_FAILURE


def test_source_candidate_admission_holds_domain_query_until_recall_evidence():
    source = type("CandidateSource", (), {"candidate": lambda self, item: None})()
    policy = AdmissionEvaluator(
        (
            AdmissionRule(
                RuleRef(LocalId("00000000000040008000000000000003"), Revision(1)),
                normalize_rule(RuleKind.ALLOW_DOMAIN, "example.com"),
                Timestamp(datetime(2026, 1, 1, tzinfo=UTC)),
            ),
        ),
        source_account=PrivateAddress("source@example.com"),
    )
    with pytest.raises(StorageFailure) as error:
        SourceCandidateAdmission(source, policy).discovery_query()
    assert error.value.code is ErrorCode.MAINTENANCE_REQUIRED


@pytest.fixture
def trusted_state_parent():
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


def test_foreground_cycle_discovers_catches_up_and_maps_message(
    trusted_state_parent, monkeypatch
):
    raw = _raw("m-new", "VERTICAL_PRIVATE_SENTINEL")
    with TemporaryDirectory(prefix="facet-sync-", dir=trusted_state_parent) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch)
        source = _Source(raw)
        target = _Target(raw)
        try:
            receipt = ForegroundSync(owner, source, target, _Admission()).run_once(
                max_jobs=10
            )
            assert receipt.history_pages == 1
            assert receipt.projected.verified == 1
            assert target.inserted == 1
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM message_mappings"
            ).fetchone() == (1,)
            assert owner._connection.execute(
                "SELECT state FROM epochs WHERE kind='initial_backfill'"
            ).fetchone() == ("draining",)
        finally:
            owner.close()


def test_foreground_cycle_runs_discovery_before_projection(
    trusted_state_parent, monkeypatch
):
    raw = _raw("m-new", "DISCOVERY_PRIVATE_SENTINEL")
    with TemporaryDirectory(prefix="facet-sync-", dir=trusted_state_parent) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch, seed=False)
        source = _Source(raw, discover=True)
        target = _Target(raw)
        try:
            receipt = ForegroundSync(owner, source, target, _Admission(True)).run_once(
                max_jobs=10
            )
            assert receipt.discovered == 1
            assert receipt.projected.verified == 1
            assert target.inserted == 1
        finally:
            owner.close()


def test_foreground_cycle_refuses_paused_owner_before_provider_calls(
    trusted_state_parent, monkeypatch
):
    with TemporaryDirectory(prefix="facet-sync-", dir=trusted_state_parent) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch)
        source = _Source(b"unused")
        try:
            with owner.session.transaction() as uow:
                uow._execute(
                    "UPDATE projections SET daemon_paused=1 WHERE projection_id=?",
                    (owner.projection_id.value,),
                )
            with pytest.raises(StorageFailure) as raised:
                ForegroundSync(
                    owner, source, _Target(b"unused"), _Admission()
                ).run_once()
            assert raised.value.code is ErrorCode.MAINTENANCE_REQUIRED
            assert source.discover_calls == 0
            assert source.history_calls == 0
        finally:
            owner.close()


def test_unsupported_history_event_becomes_durable_attention(
    trusted_state_parent, monkeypatch
):
    with TemporaryDirectory(prefix="facet-sync-", dir=trusted_state_parent) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch)
        source = _Source(b"unused", deleted=True)
        try:
            receipt = ForegroundSync(
                owner, source, _Target(b"unused"), _Admission()
            ).run_once()
            assert receipt.attention == 1
            assert owner._connection.execute(
                "SELECT state FROM sync_jobs WHERE kind='resolve_event'"
            ).fetchone() == ("needs_attention",)
            assert owner._connection.execute(
                "SELECT processing FROM source_events"
            ).fetchone() == ("needs_attention",)
        finally:
            owner.close()


def test_retryable_history_effect_is_not_retried_in_same_cycle(
    trusted_state_parent, monkeypatch
):
    with TemporaryDirectory(prefix="facet-sync-", dir=trusted_state_parent) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch)
        source = _Source(b"unused", action=True)
        action = _RetryAction()
        try:
            receipt = ForegroundSync(
                owner,
                source,
                _Target(b"unused"),
                _Admission(),
                action_consumer=action,
            ).run_once()
            assert receipt.attention == 1
            assert action.calls == 1
            assert action.owner is owner.session
            row = owner._connection.execute(
                "SELECT state,next_attempt_at FROM sync_jobs WHERE kind='resolve_event'"
            ).fetchone()
            assert row[0] == "retry_wait"
            assert row[1] > int(datetime.now(UTC).timestamp() * 1_000_000)
        finally:
            owner.close()
