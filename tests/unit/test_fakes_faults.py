import base64
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC

import pytest
from fakes.faults import HOOKS, Barrier, Faults, InjectedFailure
from fakes.mime import message
from fakes.transport import TransportFactory, assert_no_transaction

pytestmark = pytest.mark.usefixtures("deny_external_network")


def test_clock_has_independent_wall_and_monotonic_time(fake_clock):
    initial = fake_clock.now()
    assert initial.tzinfo == UTC
    fake_clock.advance(5)
    fake_clock.shift_wall(-20)
    assert (fake_clock.now() - initial).total_seconds() == -15
    assert fake_clock.monotonic() == 5
    with pytest.raises(ValueError):
        fake_clock.advance(-1)


def test_faults_require_reached_consumed_hooks_and_bound_repeats():
    faults = Faults()
    faults.at("event.before_commit", occurrence=2, repeat=2)
    faults.hit("event.before_commit")
    with pytest.raises(AssertionError, match="unconsumed"):
        faults.assert_consumed()
    for _ in range(2):
        with pytest.raises(InjectedFailure):
            faults.hit("event.before_commit")
    faults.assert_consumed()
    assert [visit.occurrence for visit in faults.visits()] == [1, 2, 3]
    with pytest.raises(ValueError, match="invalid test hook"):
        faults.hit("provider.secret-account")
    with pytest.raises(ValueError, match="registration"):
        faults.at("event.before_commit", occurrence=1)
    with pytest.raises(ValueError, match="repetition"):
        faults.at("event.after_commit", repeat=1001)


@pytest.mark.parametrize("hook", sorted(HOOKS))
def test_every_declared_hook_can_interrupt_independently(hook):
    faults = Faults()
    faults.at(hook)
    with pytest.raises(InjectedFailure):
        faults.hit(hook)
    faults.assert_consumed()


def test_trace_budget_and_barrier_timeout_fail_closed():
    faults = Faults(limit=1)
    faults.hit("event.after_commit")
    with pytest.raises(AssertionError, match="trace limit"):
        faults.hit("event.after_commit")
    barrier = Barrier(timeout=0.01)
    with pytest.raises(AssertionError, match="barrier timed out"):
        barrier.wait()
    with pytest.raises(ValueError, match="timeout"):
        Barrier(timeout=0)


def test_transport_overlap_fails_but_independent_worker_proceeds(
    gmail_controller,
    fake_faults,
    fake_clock,
):
    barrier = Barrier()
    fake_faults.at("provider.before_response", barrier=barrier)
    first = gmail_controller.service("source")
    same = gmail_controller.service("source", transport=first.transport)
    other = gmail_controller.service("source")
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(lambda: first.getProfile(userId="me").execute())
        try:
            barrier.await_reached()
            with pytest.raises(AssertionError, match="overlapping"):
                same.getProfile(userId="me").execute()
            assert other.getProfile(userId="me").execute()["historyId"] == "701"
        finally:
            barrier.release()
        assert future.result(timeout=2)["historyId"] == "701"
    assert first.transport.identifier != other.transport.identifier
    factory = TransportFactory(fake_clock)
    assert factory.new() is not factory.new()


def test_close_releases_barriers_even_on_failure():
    faults, barrier = Faults(), Barrier()
    faults.at("request.before_first_response", barrier=barrier)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(faults.hit, "request.before_first_response")
        try:
            barrier.await_reached()
        finally:
            faults.close()
        future.result(timeout=2)
    faults.assert_consumed()


@pytest.mark.parametrize(
    "boundary,expected_effect",
    [
        ("provider.before_effect", False),
        ("provider.after_effect", True),
        ("provider.before_response", True),
    ],
)
def test_insert_effect_boundaries_are_distinct(
    gmail_controller,
    fake_faults,
    boundary,
    expected_effect,
):
    fake_faults.at(boundary)
    service = gmail_controller.service("target", scopes=frozenset({"gmail.insert"}))
    args = {
        "userId": "me",
        "body": {"raw": base64.urlsafe_b64encode(message()).decode()},
    }
    with pytest.raises(InjectedFailure):
        service.messages().insert(**args).execute()
    assert len(gmail_controller.identifiers("target")) == int(expected_effect)
    assert len(service.transport.calls()) == 1


def test_transaction_probe_at_fake_network_boundary(gmail_controller, fake_faults):
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE metadata(value INTEGER)")
        connection.execute("INSERT INTO metadata VALUES(1)")
        fake_faults.at(
            "provider.before_execute",
            repeat=2,
            callback=lambda: assert_no_transaction(connection),
        )
        service = gmail_controller.service("source")
        with pytest.raises(AssertionError, match="open transaction"):
            service.getProfile(userId="me").execute()
        connection.rollback()
        assert service.getProfile(userId="me").execute()["historyId"] == "701"
    finally:
        connection.close()


def test_early_interruption_does_not_consume_later_provider_script(
    gmail_controller,
    fake_faults,
):
    args = {"userId": "me", "startHistoryId": "701"}
    gmail_controller.script("source", "history.list", args, {"historyId": "1307"})
    fake_faults.at("provider.before_execute")
    service = gmail_controller.service("source")
    with pytest.raises(InjectedFailure):
        service.history().list(**args).execute()
    with pytest.raises(AssertionError, match="unconsumed"):
        gmail_controller.assert_consumed()
    assert service.history().list(**args).execute() == {"historyId": "1307"}
