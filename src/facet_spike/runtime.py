"""Runtime paths for private OAuth and experiment state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from facet_spike.constants import DEFAULT_RUNTIME_DIR
from facet_spike.files import ensure_private_dir


@dataclass(frozen=True)
class RuntimePaths:
    root: Path

    @classmethod
    def from_value(cls, value: str | None) -> RuntimePaths:
        root = Path(value or DEFAULT_RUNTIME_DIR).expanduser().resolve()
        ensure_private_dir(root)
        return cls(root=root)

    @property
    def client_secret(self) -> Path:
        return self.root / "client_secret.json"

    def token(self, role: str) -> Path:
        return self.root / f"{role}-token.json"

    @property
    def accounts(self) -> Path:
        return self.root / "accounts.json"

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def experiments(self) -> Path:
        return self.root / "experiments.json"

    @property
    def evidence(self) -> Path:
        return self.root / "evidence.jsonl"

    @property
    def report(self) -> Path:
        return self.root / "report.md"
