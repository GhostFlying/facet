"""Bounded recovery policy tests; full command-path evidence is in CLI tests."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_db_epochs import failed_poll_and_gap
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
    EpochKind,
    ErrorCode,
    PolicyVersion,
    ProviderId,
    ProviderPageToken,
    Revision,
    Role,
    RuleKind,
    RuleOrigin,
    RuleRef,
    Timestamp,
    Visibility,
)
from facet.db.codecs import PrivateAddress, RuleValue, StorageFailure, timestamp_to_sql
from facet.db.models import (
    RevisionGuard,
    RuleRevisionRow,
    RuleRow,
    RulesetMemberRow,
    RulesetRow,
)
from facet.db.repositories import epochs, policy
from facet.gmail.retry import ProviderFailure
from facet.gmail.source import (
    CandidateResult,
    DiscoveryItem,
    DiscoveryPage,
    SourceAdapter,
)
from facet.projection.admission import (
    AdmissionEvaluator,
    AdmissionRule,
    DiscoveryCandidate,
)
from facet.projection.backfill import BackfillProducer
from facet.projection.gap_recovery import GapRecovery
from facet.projection.rules import load_rule_policy, normalize_rule, normalize_sender
from facet.sync import SourceCandidateAdmission


@pytest.mark.parametrize("offset_ms", [0, 1])
def test_integer_end_provider_superset_and_exact_local_membership(
    monkeypatch, offset_ms
):
    end = NOW.value.replace(microsecond=0)
    arrived = end.timestamp() + offset_ms / 1000
    account = PrivateAddress("source@example.invalid")

    class Service:
        def users(self):
            return self

        def messages(self):
            return self

        def list(self, **kwargs):
            # Model strict provider bounds, not a canned reply for any query.
            bounds = dict(term.split(":", 1) for term in kwargs["q"].split())
            found = int(bounds["after"]) < arrived < int(bounds["before"])
            return SimpleNamespace(
                execute=lambda **kw: {
                    "messages": [{"id": "boundary", "threadId": "boundary"}]
                    if found
                    else [],
                }
            )

        def get(self, **kwargs):
            return SimpleNamespace(
                execute=lambda **kw: {
                    "id": "boundary",
                    "threadId": "boundary",
                    "labelIds": [],
                    "internalDate": str(int(end.timestamp() * 1000) + offset_ms),
                    "payload": {
                        "headers": [{"name": "From", "value": "synthetic@example.com"}]
                    },
                }
            )

    source = SourceAdapter(Service(), source_account=account)
    selected = SimpleNamespace(
        kind=EpochKind.HISTORY_GAP,
        window_start=Timestamp(end - timedelta(minutes=10)),
        window_end=Timestamp(end),
    )
    rules = AdmissionEvaluator(
        (
            AdmissionRule(
                RuleRef(lid(10), Revision(1)),
                normalize_rule(RuleKind.ALLOW_SENDER, "synthetic@example.com"),
                Timestamp(end + timedelta(hours=1)),
            ),
        ),
        source_account=account,
    )
    monkeypatch.setattr("facet.sync._now", lambda: Timestamp(end + timedelta(hours=2)))
    page = source.discover(
        window_start=selected.window_start.value,
        window_end=end,
        precise_window=True,
    )
    assert len(page.items) == 1
    result = SourceCandidateAdmission(source, rules).evaluate(page.items[0], selected)
    assert result.admit is (offset_ms == 0)


def recovery(state, *, known=True, rule_policy=None):
    _, _, session, _ = state
    row = RuleRow(
        P,
        lid(10),
        RuleKind.ALLOW_SENDER,
        RuleValue("synthetic@example.com"),
        Revision(1),
    )
    with session.transaction() as uow:
        policy.publish_rules(
            uow,
            P,
            (row,),
            (
                RuleRevisionRow(
                    P,
                    row.rule_id,
                    Revision(1),
                    True,
                    NOW,
                    RuleOrigin.CLI,
                    rule_policy or PolicyVersion("auth-v1"),
                ),
            ),
            RulesetRow(P, Revision(1), NOW, True),
            (RulesetMemberRow(P, Revision(1), row.rule_id, Revision(1)),),
            RevisionGuard(Revision(0)),
        )
    gap = failed_poll_and_gap(session, known=known)
    with session.transaction() as uow:
        epochs.record_gap(uow, P, gap)
    owner = SimpleNamespace(session=session, projection_id=P)
    return GapRecovery(owner, None, None, None, None), row


def test_unknown_coverage_refuses_before_scan_or_insert(state):
    _, connection, _, _ = state
    coordinator, _ = recovery(state, known=False)
    with pytest.raises(StorageFailure, match="maintenance_required"):
        coordinator.prepare()
    assert connection.execute(
        "SELECT COUNT(*) FROM epochs WHERE kind='history_gap'"
    ).fetchone() == (0,)


def test_prepare_preserves_downtime_longer_than_six_months(state):
    _, connection, session, _ = state
    gap = failed_poll_and_gap(session)
    gap = replace(gap, reliable_coverage_at=Timestamp(NOW.value - timedelta(days=240)))
    with session.transaction() as uow:
        uow._execute(
            "UPDATE history_checkpoints SET reliable_coverage_at=? "
            "WHERE projection_id=?",
            (timestamp_to_sql(gap.reliable_coverage_at), P.value),
        )
        epochs.record_gap(uow, P, gap)
    coordinator = GapRecovery(
        SimpleNamespace(session=session, projection_id=P), None, None, None, None
    )
    selected = coordinator.prepare()
    assert selected.window_start.value == (
        gap.reliable_coverage_at.value - timedelta(minutes=5)
    )
    assert selected.window_end == gap.h1_recorded_at
    assert coordinator.prepare() == selected
    assert connection.execute("SELECT cursor FROM history_checkpoints").fetchone() == (
        "expired-id",
    )


@pytest.mark.parametrize("learned_policy", [False, True])
def test_gap_rule_removal_between_failed_pages_prevents_new_admission(
    state, learned_policy
):
    _, connection, session, _ = state
    version = load_rule_policy().version if learned_policy else PolicyVersion("auth-v1")
    coordinator, row = recovery(state, rule_policy=version)
    selected = coordinator.prepare()
    evaluator = AdmissionEvaluator(
        (
            AdmissionRule(
                RuleRef(row.rule_id, Revision(1)),
                normalize_rule(RuleKind.ALLOW_SENDER, row.normalized_value.value),
                NOW,
            ),
        ),
        source_account=PrivateAddress("source@example.invalid"),
        ruleset_revision=Revision(1),
    )

    class Source:
        fail_second = True

        def discover(self, *, page_token=None, **kwargs):
            assert not connection.in_transaction
            if page_token is not None and self.fail_second:
                raise ProviderFailure(ErrorCode.NETWORK_UNAVAILABLE, Role.SOURCE)
            identifier = "first" if page_token is None else "second"
            return DiscoveryPage(
                (DiscoveryItem(ProviderId(identifier), ProviderId(identifier)),),
                ProviderPageToken("page-two") if page_token is None else None,
                None,
            )

        def history_candidate(self, item):
            assert not connection.in_transaction
            return CandidateResult(
                candidate=DiscoveryCandidate(
                    item.message_id,
                    item.thread_id,
                    normalize_sender(row.normalized_value.value),
                    PrivateAddress("source@example.invalid"),
                    Visibility.NORMAL,
                    False,
                    Timestamp(NOW.value - timedelta(minutes=5)),
                )
            )

        candidate = history_candidate

    source = Source()
    producer = BackfillProducer(source, SourceCandidateAdmission(source, evaluator))
    with pytest.raises(ProviderFailure):
        producer.discover(session, P, selected.epoch_id)
    assert connection.execute(
        "SELECT source_thread_id FROM tracked_threads"
    ).fetchall() == [("first",)]
    # Production typed rule publication can remove membership without changing
    # the old revision; checking only its enabled flag is insufficient.
    with session.transaction() as uow:
        policy.publish_rules(
            uow,
            P,
            (),
            (),
            RulesetRow(P, Revision(2), NOW, True),
            (),
            RevisionGuard(Revision(1)),
        )
    source.fail_second = False
    producer.discover(session, P, selected.epoch_id)
    assert connection.execute(
        "SELECT source_thread_id FROM tracked_threads"
    ).fetchall() == [("first",)]
    assert connection.execute("SELECT COUNT(*) FROM insert_attempts").fetchone() == (0,)
