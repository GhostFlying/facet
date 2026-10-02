"""Bounded, consumed test scripts; labels contain no scenario/private values."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Lock

HOOKS = frozenset(
    [
        "provider.before_execute",
        "provider.before_effect",
        "provider.after_effect",
        "provider.before_response",
        "event.before_commit",
        "event.after_commit",
        "cursor.before_final_commit",
        "cursor.after_final_commit",
        "fence.before_commit",
        "fence.after_commit",
        "scan.before_start",
        "scan.after_page",
        "intent.before_commit",
        "intent.after_commit",
        "dispatch.before_guard",
        "dispatch.entry",
        "result.before_commit",
        "result.after_commit",
        "mapping.before_commit",
        "mapping.after_commit",
        "stop.before_effect",
        "stop.after_effect",
        "claim.before_reentry",
        "owner.before_restart",
        "owner.after_restart",
        "request.before_journal",
        "request.before_submit",
        "request.before_accept_commit",
        "request.after_accept_commit",
        "request.before_effect_commit",
        "request.after_effect_commit",
        "request.before_first_response",
        "request.before_lookup",
        "credential.before_refresh",
        "credential.before_replace",
        "credential.after_replace",
        "maintenance.before_lock",
        "maintenance.after_lock",
        "backup.before_snapshot",
        "backup.after_snapshot",
        "bundle.before_replace",
        "bundle.after_replace",
    ]
)


class InjectedFailure(RuntimeError):
    def __init__(self) -> None:
        super().__init__("injected test interruption")


class Barrier:
    def __init__(self, timeout: float = 2.0) -> None:
        if not 0 < timeout <= 10:
            raise ValueError("invalid barrier timeout")
        self.timeout = timeout
        self.reached = Event()
        self._release = Event()

    def wait(self) -> None:
        self.reached.set()
        if not self._release.wait(self.timeout):
            raise AssertionError("test barrier timed out")

    def await_reached(self) -> None:
        if not self.reached.wait(self.timeout):
            raise AssertionError("test barrier was not reached")

    def release(self) -> None:
        self._release.set()


@dataclass(frozen=True)
class HookVisit:
    hook: str
    occurrence: int


class Faults:
    def __init__(self, limit: int = 1000) -> None:
        if not 1 <= limit <= 10000:
            raise ValueError("invalid script limit")
        self._limit = limit
        self._counts: Counter[str] = Counter()
        self._actions: dict[tuple[str, int], Barrier | Callable[[], None] | None] = {}
        self._visits: list[HookVisit] = []
        self._barriers: list[Barrier] = []
        self._lock = Lock()

    def at(
        self,
        hook: str,
        *,
        occurrence: int = 1,
        repeat: int = 1,
        barrier: Barrier | None = None,
        callback: Callable[[], None] | None = None,
    ) -> None:
        if (barrier is not None and callback is not None) or (
            callback is not None and not callable(callback)
        ):
            raise ValueError("invalid test action")
        if hook not in HOOKS or not 1 <= occurrence <= self._limit:
            raise ValueError("invalid test hook")
        if not 1 <= repeat <= self._limit or occurrence + repeat - 1 > self._limit:
            raise ValueError("invalid test repetition")
        with self._lock:
            keys = [(hook, n) for n in range(occurrence, occurrence + repeat)]
            if len(self._actions) + repeat > self._limit or any(
                key in self._actions or key[1] <= self._counts[hook] for key in keys
            ):
                raise ValueError("invalid or duplicate script registration")
            for key in keys:
                self._actions[key] = callback if callback is not None else barrier
            if barrier is not None:
                self._barriers.append(barrier)

    def hit(self, hook: str) -> None:
        if hook not in HOOKS:
            raise ValueError("invalid test hook")
        with self._lock:
            if len(self._visits) >= self._limit:
                raise AssertionError("test trace limit exceeded")
            self._counts[hook] += 1
            key = (hook, self._counts[hook])
            self._visits.append(HookVisit(*key))
            if key not in self._actions:
                return
            action = self._actions.pop(key)
        if action is None:
            raise InjectedFailure()
        if isinstance(action, Barrier):
            action.wait()
        else:
            action()

    def visits(self) -> tuple[HookVisit, ...]:
        with self._lock:
            return tuple(self._visits)

    def assert_consumed(self) -> None:
        with self._lock:
            if self._actions:
                raise AssertionError("unconsumed test fault script")

    def close(self) -> None:
        for barrier in self._barriers:
            barrier.release()
