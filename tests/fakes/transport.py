"""Separate transport instances with an overlapping-use negative control."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock

from .clock import Clock

METHODS = frozenset(
    {
        "profile.get",
        "labels.list",
        "messages.list",
        "messages.get",
        "messages.insert",
        "threads.get",
        "history.list",
        "messages.modify",
    }
)


def assert_no_transaction(connection) -> None:
    """Probe a caller-owned real connection at a transport callback."""
    if connection.in_transaction:
        raise AssertionError("network callback observed an open transaction")


@dataclass(frozen=True)
class Call:
    method: str
    ordinal: int
    transport_id: int
    started: float
    status: str
    raw_bytes: int


class Transport:
    def __init__(self, identifier: int, clock: Clock) -> None:
        self.identifier = identifier
        self._clock = clock
        self._busy = Lock()
        self._calls: list[Call] = []

    @contextmanager
    def call(self, method: str, raw_bytes: int = 0) -> Iterator[None]:
        if method not in METHODS or not 0 <= raw_bytes <= 35_000_000:
            raise ValueError("invalid call metadata")
        if not self._busy.acquire(blocking=False):
            raise AssertionError("overlapping use of one test transport")
        started = self._clock.monotonic()
        status = "failed"
        try:
            if len(self._calls) >= 1000:
                raise AssertionError("test call trace limit exceeded")
            yield
            status = "returned"
        finally:
            if len(self._calls) < 1000:
                self._calls.append(
                    Call(
                        method,
                        len(self._calls) + 1,
                        self.identifier,
                        started,
                        status,
                        raw_bytes,
                    )
                )
            self._busy.release()

    def calls(self) -> tuple[Call, ...]:
        return tuple(self._calls)


class TransportFactory:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._next = 0
        self._lock = Lock()

    def new(self) -> Transport:
        with self._lock:
            self._next += 1
            return Transport(self._next, self._clock)
