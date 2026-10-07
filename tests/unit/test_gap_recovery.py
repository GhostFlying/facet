"""Bounded recovery policy tests; full command-path evidence is in CLI tests."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_db_epochs import failed_poll_and_gap
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
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
from facet.gmail.source import CandidateResult, DiscoveryItem, DiscoveryPage
from facet.projection.admission import (
    AdmissionEvaluator,
    AdmissionRule,
    DiscoveryCandidate,
)
from facet.projection.backfill import BackfillProducer
from facet.projection.gap_recovery import GapRecovery
from facet.projection.rules import normalize_rule, normalize_sender
from facet.sync import SourceCandidateAdmission


def recovery(state, *, known=True):
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
                    PolicyVersion("auth-v1"),
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


def test_gap_rule_removal_between_failed_pages_prevents_new_admission(state):
    _, connection, session, _ = state
    coordinator, row = recovery(state)
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
