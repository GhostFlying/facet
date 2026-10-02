from __future__ import annotations

import stat

from facet_spike.files import load_json, write_private_json


def test_private_json_is_owner_only_and_atomic(tmp_path) -> None:
    path = tmp_path / "private" / "state.json"

    write_private_json(path, {"status": "pending"})

    assert load_json(path, {}) == {"status": "pending"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
