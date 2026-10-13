"""Read retries use injected time, never mailbox credentials or real sleeps."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

import pytest

from facet.config import dump_config, initial_template
from facet.contracts import ErrorCode, LocalId, ProviderId, Revision, Role, Timestamp
from facet.gmail.retry import ProviderFailure, ProviderReason, parse_retry_after
from facet.gmail.source import DiscoveryItem, DiscoveryPage
from facet.reconcile import ReconcileScope, SourceReconciler
from facet.reconcile_retry import ReadRetries, retryable
from facet.runtime.state_owner import StateOwner


class Clock:
    def __init__(self):
        self.now = 0.0

    def sleep(self, seconds):
        self.now += seconds

    def retries(self, guard=lambda: None, **kwargs):
        return ReadRetries(
            guard, sleep=self.sleep, clock=lambda: self.now, jitter=lambda: 0, **kwargs
        )


def failure(status=429, after=None, reason=ProviderReason.RATE_LIMIT):
    return ProviderFailure(
        ErrorCode.SOURCE_RATE_LIMITED,
        Role.SOURCE,
        status=status,
        retry_after_seconds=after,
        reason=reason,
    )


@pytest.mark.parametrize(
    "header,expected", [("12", 12), (" 5 ", 5), ("-1", None), ("bad", None)]
)
def test_retry_after_seconds(header, expected):
    assert parse_retry_after(header) == expected


def test_retry_after_http_date():
    now = datetime(2026, 10, 13, tzinfo=UTC)
    assert parse_retry_after("Tue, 13 Oct 2026 00:00:30 GMT", now=now) == 30
    assert parse_retry_after("Mon, 12 Oct 2026 00:00:30 GMT", now=now) is None
    assert parse_retry_after("Tue, 13 Oct 2026 00:00:30", now=now) is None


@pytest.mark.parametrize(
    "error,expected",
    [
        (failure(), True),
        (failure(403), True),
        (failure(403, reason=ProviderReason.USER_RATE_LIMIT), True),
        (failure(403, reason=ProviderReason.DAILY_LIMIT), False),
        (failure(403, reason=ProviderReason.INSUFFICIENT_PERMISSIONS), False),
        (failure(401), False),
        (failure(404), False),
        (failure(500), True),
        (failure(502), True),
        (failure(503), True),
        (failure(504), True),
        (failure(501), False),
        (ProviderFailure(ErrorCode.NETWORK_UNAVAILABLE, Role.SOURCE), True),
        (ProviderFailure(ErrorCode.CONSISTENCY_FAILURE, Role.SOURCE), False),
    ],
)
def test_retry_eligibility(error, expected):
    assert retryable(error) is expected


def test_eight_retries_and_exponential_wait():
    clock = Clock()
    retries = clock.retries()
    calls = []

    def read():
        calls.append(clock.now)
        raise failure()

    with pytest.raises(ProviderFailure):
        retries.call(read)
    assert len(calls) == 9
    assert calls == [0, 1, 3, 7, 15, 31, 63, 123, 183]
    assert retries.waited == 183


def test_provider_deadline_and_global_budget():
    clock = Clock()
    retries = clock.retries()
    assert retries.wait([failure(after=1700)], 1)
    assert clock.now == 1700
    assert not retries.wait([failure(after=101)], 1)
    assert clock.now == 1700


def test_jitter_and_guard():
    clock = Clock()
    guards = []
    retries = clock.retries(lambda: guards.append(clock.now))
    retries.jitter = lambda: 1
    assert retries.wait([failure()], 1)
    assert clock.now == 1.25
    assert guards == [0, 1.25]


def test_partial_batch_retries_only_failed_items():
    clock = Clock()
    items = tuple(DiscoveryItem(ProviderId(x), ProviderId("t")) for x in ("a", "b"))
    calls = []

    def read(pending):
        calls.append(tuple(x.message_id.value for x in pending))
        return (
            {"a": "success", "b": failure(after=3)} if len(calls) == 1 else {"b": "ok"}
        )

    retries = clock.retries()
    assert retries.batch(items, read) == {"a": "success", "b": "ok"}
    assert calls == [("a", "b"), ("b",)]
    assert retries.retried_success == 1
    assert clock.now == 3


def test_outer_batch_failure_and_interrupt():
    clock = Clock()
    item = DiscoveryItem(ProviderId("a"), ProviderId("t"))
    calls = []

    def read(pending):
        calls.append(pending)
        if len(calls) == 1:
            raise failure()
        return {"a": "ok"}

    assert clock.retries().batch((item,), read) == {"a": "ok"}

    def interrupted(_):
        raise KeyboardInterrupt

    retries = ReadRetries(lambda: None, sleep=interrupted, clock=lambda: 0)
    with pytest.raises(KeyboardInterrupt):
        retries.wait([failure()], 1)


def test_batch_outer_failure_preserves_callback_success(monkeypatch):
    from facet.db.codecs import PrivateAddress
    from facet.gmail.source import SourceAdapter

    items = tuple(DiscoveryItem(ProviderId(x), ProviderId("t")) for x in ("a", "b"))
    service = SimpleNamespace(_http=object())
    service.users = lambda: service
    service.messages = lambda: service
    service.get = lambda **kwargs: kwargs

    class Batch:
        def __init__(self, callback, **kwargs):
            self.callback = callback

        def add(self, *args, **kwargs):
            pass

        def execute(self, **kwargs):
            self.callback("a", {}, None)
            raise failure()

    monkeypatch.setattr("googleapiclient.http.BatchHttpRequest", Batch)
    adapter = SourceAdapter(
        service, source_account=PrivateAddress("source@example.invalid")
    )
    monkeypatch.setattr(adapter, "_candidate_from_value", lambda *args, **kw: "success")
    results = adapter.reconcile_candidates_batch(items)
    assert results["a"] == "success"
    assert isinstance(results["b"], ProviderFailure)


def test_retry_log_excludes_private_material(capfd):
    from facet.status.logging import emit_reconcile_retry

    emit_reconcile_retry(failure(after=4), 2, 4, 1790, 3)
    value = capfd.readouterr().err
    assert '"retry_index":2' in value
    assert '"wait_seconds":4' in value
    assert '"failure_count":3' in value
    assert "synthetic-message" not in value


def test_batch_exhaustion_retains_every_result():
    clock = Clock()
    retries = clock.retries()
    items = tuple(DiscoveryItem(ProviderId(x), ProviderId("t")) for x in ("a", "b"))
    calls = []

    def read(pending):
        calls.append(pending)
        return {x.message_id.value: failure(after=1801) for x in pending}

    results = retries.batch(items, read)
    assert set(results) == {"a", "b"}
    assert len(calls) == 1
    assert clock.now == 0


def test_source_reconciler_durable_seen_dedup_and_restart():
    from facet.contracts import ProviderPageToken

    with TemporaryDirectory(dir=f"/run/user/{os.geteuid()}") as root:
        config = initial_template("source@example.invalid", "target@example.invalid")
        raw = dump_config(config)
        with StateOwner.create(Path(root) / "state", config, raw) as owner:
            owner.ensure_reconcile_schema(LocalId(uuid4().hex), raw)
            revision = owner._connection.execute(
                "select ruleset_revision from projections"
            ).fetchone()[0]
            now = Timestamp(datetime.now(UTC))
            scope = ReconcileScope(
                Revision(revision), Timestamp(now.value - timedelta(days=30)), now, now
            )
            item = DiscoveryItem(
                ProviderId("synthetic-message"), ProviderId("synthetic-thread")
            )
            clock = Clock()
            admission = SimpleNamespace(
                discovery_query=lambda _: "query",
                _policy=SimpleNamespace(
                    evaluate=lambda *a, **k: SimpleNamespace(admit=True, rule=None)
                ),
            )
            calls = []
            list_calls = []

            class Source:
                def discover(self, **kwargs):
                    list_calls.append(kwargs["page_token"])
                    if len(list_calls) == 1:
                        raise failure()
                    token = (
                        ProviderPageToken("next")
                        if kwargs["page_token"] is None
                        else None
                    )
                    return DiscoveryPage((item, item), token, 1)

                def candidate(self, value):
                    return self.reconcile_candidate(value)

                def reconcile_candidate(self, value):
                    calls.append(value)
                    stored = owner._connection.execute(
                        "select classification from reconcile_candidates"
                    ).fetchone()
                    assert stored == ("seen",)
                    if len(calls) == 1:
                        raise failure()
                    return SimpleNamespace(
                        attention=None,
                        candidate=SimpleNamespace(is_draft=False, observed_at=now),
                    )

            reconciler = SourceReconciler(
                owner, Source(), admission, scope, read_retries=clock.retries()
            )
            reconciler._assert_scope_revision = lambda: owner.session._check()
            key = uuid4().hex
            queued = []
            result = reconciler.run(
                key, enqueue_candidate=lambda *args: queued.append(args) or True
            )
            assert (result.listed, result.queued, result.remaining_issue) == (1, 1, 0)
            assert len(calls) == 2
            assert len(queued) == 1
            assert len(list_calls) == 3
            replay = reconciler.run(
                key, enqueue_candidate=lambda *args: pytest.fail("re-enqueued")
            )
            assert replay == result
            assert owner._connection.execute(
                "select classification from reconcile_candidates"
            ).fetchone() == ("queued",)
