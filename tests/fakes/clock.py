"""Independent UTC wall and monotonic clocks for deterministic tests."""

from datetime import UTC, datetime, timedelta
from threading import Lock


class Clock:
    def __init__(self) -> None:
        self._wall = datetime(2026, 1, 1, tzinfo=UTC)
        self._mono = 0.0
        self._lock = Lock()

    def now(self) -> datetime:
        with self._lock:
            return self._wall

    def monotonic(self) -> float:
        with self._lock:
            return self._mono

    def advance(self, seconds: float) -> None:
        if not 0 <= seconds <= 86400:
            raise ValueError("invalid clock advancement")
        with self._lock:
            self._mono += seconds
            self._wall += timedelta(seconds=seconds)

    def shift_wall(self, seconds: float) -> None:
        if not -86400 <= seconds <= 86400:
            raise ValueError("invalid wall shift")
        with self._lock:
            self._wall += timedelta(seconds=seconds)
