"""Offline evidence for the narrow M2 Gmail adapter and History normalizer."""

import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from fakes.gmail import HttpFailure, InsertReply
from test_db_history import checkpoint_fixture
from test_db_schema import NOW, P, create_state, lid

from facet.config import initial_template
from facet.contracts import (
    Count,
    ErrorCode,
    PolicyVersion,
    ProjectionId,
    ProviderId,
    ProviderPageToken,
    Revision,
    Role,
    RuleKind,
    RuleOrigin,
    RuleRef,
    Sha256Hex,
    Timestamp,
)
from facet.db.codecs import (
    PollOrigin,
    PollState,
    RuleValue,
    StorageFailure,
)
from facet.db.models import (
    HistoryPollRow,
    RevisionGuard,
    RuleRevisionRow,
    RuleRow,
    RulesetMemberRow,
    RulesetRow,
)
from facet.db.repositories import policy
from facet.gmail.credential_models import ScopePolicy, policy_scopes
from facet.gmail.credentials import CredentialManager
from facet.gmail.retry import ProviderFailure, ProviderStage, classify_http_status
from facet.gmail.source import (
    HistoryLabel,
    HistoryMessage,
    HistoryRecord,
    SourceAdapter,
)
from facet.gmail.target import TargetAdapter
from facet.projection.backfill import (
    AdmissionEvaluator,
    BackfillProducer,
    DiscoveryDecision,
)
from facet.projection.history import HistoryProducer, _typed_events
from facet.projection.worker import ProjectionWorker
from facet.runtime.state_owner import StateOwner


@pytest.fixture
def trusted_state_parent():
    candidates = (Path.cwd(), Path(f"/run/user/{os.geteuid()}"))
    for candidate in candidates:
        trusted = True
        for entry in (candidate, *candidate.parents):
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                trusted = False
                break
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in (0, os.geteuid())
                or stat.S_IMODE(info.st_mode) & 0o7022
            ):
                trusted = False
                break
        if trusted:
            return candidate
    pytest.skip("no_verified_trusted_test_anchor")


def test_source_discovery_uses_fixed_window_and_typed_page(gmail_controller):
    source = gmail_controller.service("source")
    args = {
        "userId": "me",
        "q": "after:2026/01/01 before:2026/07/01",
        "includeSpamTrash": False,
        "maxResults": 100,
        "pageToken": "next",
    }
    gmail_controller.script(
        "source",
        "messages.list",
        args,
        {
            "messages": [{"id": "m-1", "threadId": "t-1"}],
            "nextPageToken": "later",
            "resultSizeEstimate": 999,
        },
    )
    page = SourceAdapter(source).discover(
        window_start=datetime(2026, 1, 1, tzinfo=UTC),
        window_end=datetime(2026, 7, 1, tzinfo=UTC),
        page_token=ProviderPageToken("next"),
    )
    assert page.items[0].message_id == ProviderId("m-1")
    assert page.next_page_token == ProviderPageToken("later")
    assert page.result_size_estimate == 999


def test_source_history_requests_deleted_events(gmail_controller):
    gmail_controller.script(
        "source",
        "history.list",
        {
            "userId": "me",
            "startHistoryId": "h0",
            "historyTypes": [
                "messageAdded",
                "messageDeleted",
                "labelAdded",
                "labelRemoved",
            ],
            "maxResults": 100,
        },
        {"historyId": "h1", "history": []},
    )
    page = SourceAdapter(gmail_controller.service("source")).history(ProviderId("h0"))
    assert page.history_id == ProviderId("h1")


@dataclass
class _DiscoverySource:
    def profile(self):
        from facet.gmail.source import SourceProfile

        return SourceProfile("source@example.invalid", ProviderId("h0"), 1, 1)

    def discover(self, *, window_start, window_end, page_token=None, query=None):
        from facet.gmail.source import DiscoveryItem, DiscoveryPage

        return DiscoveryPage(
            (DiscoveryItem(ProviderId("m-1"), ProviderId("t-1")),), None, 1
        )


class _MismatchedProfileSource(_DiscoverySource):
    def profile(self):
        raise ProviderFailure(ErrorCode.BINDING_MISMATCH, Role.SOURCE)


@dataclass
class _TrustedAdmission(AdmissionEvaluator):
    rule_id: object

    def evaluate(self, item, epoch):
        return DiscoveryDecision(True, RuleRef(self.rule_id, Revision(1)))

    def discovery_query(self, epoch=None):
        from facet.gmail.source import DiscoveryQuery

        return DiscoveryQuery(('from:"synthetic@example.com"',))


def test_backfill_producer_uses_verified_owner_and_durable_expansion_job(
    monkeypatch, trusted_state_parent
):
    """Exercise PR32/33 preview, start and producer discovery on one owner."""

    with TemporaryDirectory(prefix="facet-m2-", dir=trusted_state_parent) as root:
        config = initial_template("source@example.invalid", "target@example.invalid")
        projection = config.projection.id
        owner = StateOwner.create(Path(root) / "state", config, b"synthetic-config")
        try:
            from test_m2_foundation_consumers import Profiles, write_credentials

            write_credentials(owner)
            manager = CredentialManager(owner.state_dir, config, owner)
            scopes = policy_scopes(ScopePolicy.SOURCE_READONLY, Role.SOURCE)
            target_scopes = policy_scopes(ScopePolicy.TARGET_DEFAULT, Role.TARGET)
            verified = manager.verify_and_publish(Profiles(scopes, target_scopes))
            assert {profile.role for profile in verified.profiles} == {
                Role.SOURCE,
                Role.TARGET,
            }
            rule = RuleRow(
                projection,
                lid(760),
                RuleKind.ALLOW_SENDER,
                RuleValue("synthetic@example.invalid"),
                Revision(1),
            )
            policy_revision = PolicyVersion("auth-v1")
            rule_revision = RuleRevisionRow(
                projection,
                rule.rule_id,
                Revision(1),
                True,
                NOW,
                RuleOrigin.CLI,
                policy_revision,
            )
            snapshot = RulesetRow(projection, Revision(1), NOW, True)
            member = RulesetMemberRow(
                projection, Revision(1), rule.rule_id, Revision(1)
            )
            with owner.session.transaction() as uow:
                policy.publish_rules(
                    uow,
                    projection,
                    (rule,),
                    (rule_revision,),
                    snapshot,
                    (member,),
                    RevisionGuard(Revision(0)),
                )
            from facet.db import command_store
            from facet.db.command_records import (
                BackfillPreviewRequest,
                BackfillStartRequest,
            )

            monkeypatch.setattr(command_store, "_owner_now", lambda: NOW)
            monkeypatch.setattr("facet.projection.backfill._now", lambda: NOW)
            window_start = Timestamp(datetime(2026, 4, 1, tzinfo=UTC))
            preview_request = BackfillPreviewRequest(
                lid(761),
                lid(762),
                window_start,
                NOW,
                Timestamp(datetime(2026, 9, 1, tzinfo=UTC)),
                Sha256Hex("a" * 64),
                NOW,
                Revision(0),
                NOW,
            )
            producer = BackfillProducer(
                _DiscoverySource(),
                _TrustedAdmission(rule.rule_id),
            )
            preview = producer.preview(owner.session, projection, preview_request)
            start_request = BackfillStartRequest(
                lid(763),
                lid(764),
                preview.operation_id,
                lid(765),
                ProviderId("ignored-h0"),
                NOW,
                NOW,
            )
            with pytest.raises(ProviderFailure) as mismatch:
                BackfillProducer(
                    _MismatchedProfileSource(), _TrustedAdmission(rule.rule_id)
                ).start(owner.session, projection, start_request)
            assert mismatch.value.code is ErrorCode.BINDING_MISMATCH
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM epochs"
            ).fetchone() == (0,)
            _, epoch = producer.start(owner.session, projection, start_request)
            assert epoch.fence_history_id == ProviderId("h0")
            assert producer.discover(owner.session, projection, epoch.epoch_id) == 1
            assert owner._connection.execute(
                "SELECT kind FROM sync_jobs"
            ).fetchone() == ("expand_thread",)
            assert owner._connection.execute(
                "SELECT state FROM epoch_partitions"
            ).fetchone() == ("complete",)
        finally:
            owner.close()


def test_history_normalization_keeps_typed_events_and_deduplicates():
    projection = ProjectionId("p1")
    observed = Timestamp(datetime(2026, 7, 1, tzinfo=UTC))
    rows, jobs = _typed_events(
        projection,
        ProviderId("h-1"),
        (
            HistoryRecord(
                ProviderId("h-1"),
                (HistoryMessage(ProviderId("m-1"), ProviderId("t-1")),),
                (),
                (
                    HistoryLabel(
                        HistoryMessage(ProviderId("m-1"), ProviderId("t-1")),
                        (ProviderId("AI/AddSender"),),
                    ),
                ),
                (),
            ),
            HistoryRecord(
                ProviderId("h-1"),
                (HistoryMessage(ProviderId("m-1"), ProviderId("t-1")),),
                (),
                (),
                (),
            ),
        ),
        observed,
    )
    assert len(rows) == 2
    assert len(jobs) == 2
    assert {row.event.key.tag for row in rows} == {"message_added", "label_changed"}


def test_target_adapter_has_insert_and_readback_only(gmail_controller):
    target = gmail_controller.service("target", scopes=frozenset({"gmail.insert"}))
    gmail_controller.script(
        "target",
        "messages.insert",
        {
            "userId": "me",
            "body": {"raw": "aGVsbG8"},
            "internalDateSource": "dateHeader",
        },
        InsertReply(thread_id="target-thread"),
    )
    result = TargetAdapter(target).insert(b"hello")
    assert result.message_id == ProviderId("inserted-1")
    assert result.thread_id == ProviderId("target-thread")
    assert not hasattr(TargetAdapter, "send")
    assert not hasattr(TargetAdapter, "delete")
    assert not hasattr(TargetAdapter, "message_metadata")
    assert not hasattr(TargetAdapter, "thread_metadata")


def test_provider_failures_are_closed_and_do_not_expose_wire_text(gmail_controller):
    gmail_controller.script(
        "source",
        "messages.list",
        {
            "userId": "me",
            "q": "after:2026/01/01 before:2026/07/01",
            "includeSpamTrash": False,
            "maxResults": 100,
        },
        HttpFailure(429, b"PRIVATE_PROVIDER_BODY"),
    )
    try:
        SourceAdapter(gmail_controller.service("source")).discover(
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 7, 1, tzinfo=UTC),
        )
    except ProviderFailure as error:
        assert error.code.value == "source_rate_limited"
        assert error.provider_stage is ProviderStage.MESSAGE_LIST
        assert "PRIVATE_PROVIDER_BODY" not in repr(error)
    else:
        raise AssertionError("expected a closed provider failure")


def test_provider_error_classes_are_typed_without_response_payloads():
    assert classify_http_status(403, Role.SOURCE).value == "scope_required"
    assert (
        classify_http_status(
            403, Role.TARGET, body=b'{"reason":"rateLimitExceeded"}'
        ).value
        == "target_rate_limited"
    )
    assert (
        classify_http_status(
            403,
            Role.TARGET,
            body=b'{"reason":"storageQuotaExceeded"}',
        ).value
        == "target_storage_full"
    )


def test_provider_failure_keeps_retry_after_and_maps_invalid_grant_to_auth(
    gmail_controller,
):
    gmail_controller.script(
        "source",
        "messages.list",
        {
            "userId": "me",
            "q": "after:2026/01/01 before:2026/07/01",
            "includeSpamTrash": False,
            "maxResults": 100,
        },
        HttpFailure(429, b'{"error":"invalid_grant"}', (("Retry-After", "17"),)),
    )
    with pytest.raises(ProviderFailure) as caught:
        SourceAdapter(gmail_controller.service("source")).discover(
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 7, 1, tzinfo=UTC),
        )
    assert caught.value.code is ErrorCode.SOURCE_AUTH_REQUIRED
    assert caught.value.retry_after_seconds == 17
    assert caught.value.provider_stage is ProviderStage.MESSAGE_LIST
    assert "invalid_grant" not in repr(caught.value)


def test_provider_failure_rewrap_preserves_stage_and_retry_metadata():
    original = ProviderFailure(
        ErrorCode.INVALID_INPUT,
        Role.SOURCE,
        404,
        17,
        ProviderStage.MESSAGE_GET,
        30,
        1,
        NOW,
    )
    converted = original.with_code(ErrorCode.SOURCE_MISSING, role=Role.SOURCE)
    assert converted.code is ErrorCode.SOURCE_MISSING
    assert converted.role is Role.SOURCE
    assert converted.status == 404
    assert converted.retry_after_seconds == 17
    assert converted.provider_stage is ProviderStage.MESSAGE_GET
    assert converted.timeout_seconds == 30
    assert converted.attempt == 1
    assert converted.observed_at is NOW


def test_worker_source_missing_rewrap_preserves_provider_stage_metadata():
    original = ProviderFailure(
        ErrorCode.INVALID_INPUT,
        Role.SOURCE,
        404,
        11,
        ProviderStage.MESSAGE_GET,
        30,
        1,
        NOW,
    )

    class Source:
        def thread_metadata(self, _thread_id):
            raise original

        def raw(self, _message_id):
            raise original

    worker = object.__new__(ProjectionWorker)
    worker._source = Source()
    expanded_job = SimpleNamespace(
        subject=SimpleNamespace(source_thread_id=ProviderId("thread"))
    )
    projected_job = SimpleNamespace(
        subject=SimpleNamespace(source_message_id=ProviderId("message"))
    )
    with pytest.raises(ProviderFailure) as expanded:
        worker._expand(expanded_job)
    with pytest.raises(ProviderFailure) as projected:
        worker._project(projected_job)
    for caught in (expanded.value, projected.value):
        assert caught.code is ErrorCode.SOURCE_MISSING
        assert caught.role is Role.SOURCE
        assert caught.status == 404
        assert caught.retry_after_seconds == 11
        assert caught.provider_stage is ProviderStage.MESSAGE_GET
        assert caught.timeout_seconds == 30
        assert caught.attempt == 1
        assert caught.observed_at is NOW


@dataclass
class _ExpiredSource:
    def history(self, cursor, *, page_token=None):
        raise ProviderFailure(ErrorCode.INVALID_INPUT, Role.SOURCE, 404)

    def profile(self):
        from facet.gmail.source import SourceProfile

        return SourceProfile("source@example.invalid", ProviderId("h1"), 0, 0)


def test_history_404_abandons_poll_and_records_bounded_gap(tmp_path):
    connection, session, _ = create_state(tmp_path / "history-gap.db")
    try:
        checkpoint_fixture(session)
        poll = HistoryPollRow(
            P,
            lid(700),
            PollOrigin.CHECKPOINT,
            None,
            ProviderId("old-checkpoint"),
            Revision(0),
            NOW,
            PollState.READING,
            Count(0),
            None,
            None,
            None,
            Revision(0),
        )
        with pytest.raises(ProviderFailure) as caught:
            HistoryProducer(_ExpiredSource()).consume(session, P, poll)
        assert caught.value.status == 404
        assert connection.execute("SELECT state FROM history_polls").fetchone() == (
            "abandoned",
        )
        assert connection.execute("SELECT COUNT(*) FROM history_gaps").fetchone() == (
            1,
        )
        assert connection.execute(
            "SELECT cursor FROM history_checkpoints"
        ).fetchone() == ("old-checkpoint",)
    finally:
        session.close()
        connection.close()


@dataclass
class _PagedSource:
    pages: tuple
    calls: int = 0

    def history(self, cursor, *, page_token=None):
        page = self.pages[self.calls]
        self.calls += 1
        return page


def test_history_producer_paginates_and_replays_final_cursor(tmp_path, monkeypatch):
    from facet.gmail.source import HistoryPage

    connection, session, _ = create_state(tmp_path / "history-pages.db")
    try:
        checkpoint_fixture(session)
        pages = _PagedSource(
            (
                HistoryPage(
                    ProviderId("h1"),
                    (
                        HistoryRecord(
                            ProviderId("record-1"),
                            (HistoryMessage(ProviderId("m-1"), ProviderId("t-1")),),
                            (),
                            (),
                            (),
                        ),
                    ),
                    ProviderPageToken("next"),
                ),
                HistoryPage(
                    ProviderId("h2"),
                    (
                        HistoryRecord(
                            ProviderId("record-2"),
                            (),
                            (),
                            (
                                HistoryLabel(
                                    HistoryMessage(
                                        ProviderId("m-2"), ProviderId("t-1")
                                    ),
                                    (ProviderId("AI/AddSender"),),
                                ),
                            ),
                            (),
                        ),
                    ),
                    None,
                ),
            )
        )
        poll = HistoryPollRow(
            P,
            lid(701),
            PollOrigin.CHECKPOINT,
            None,
            ProviderId("old-checkpoint"),
            Revision(0),
            NOW,
            PollState.READING,
            Count(0),
            None,
            None,
            None,
            Revision(0),
        )
        from facet.db.repositories import history

        real_finish = history.finish_history_poll

        def fault_before_cursor(*args, **kwargs):
            raise RuntimeError("synthetic final-page boundary")

        monkeypatch.setattr(history, "finish_history_poll", fault_before_cursor)
        with pytest.raises(StorageFailure):
            HistoryProducer(pages).consume(session, P, poll)
        assert connection.execute(
            "SELECT cursor FROM history_checkpoints"
        ).fetchone() == ("old-checkpoint",)
        assert connection.execute(
            "SELECT completed_pages FROM history_polls"
        ).fetchone() == (2,)
        monkeypatch.setattr(history, "finish_history_poll", real_finish)
        assert HistoryProducer(pages).consume(session, P, poll) == ProviderId("h2")
        assert connection.execute("SELECT COUNT(*) FROM source_events").fetchone() == (
            2,
        )
        assert connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone() == (2,)
        assert connection.execute(
            "SELECT cursor FROM history_checkpoints"
        ).fetchone() == ("h2",)
        assert HistoryProducer(pages).consume(session, P, poll) == ProviderId("h2")
        assert pages.calls == 2
    finally:
        session.close()
        connection.close()
