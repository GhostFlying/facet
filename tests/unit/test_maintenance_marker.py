import os

import pytest

from facet.runtime.maintenance import acquire_marker, active, release


def test_marker_blocks_until_release(tmp_path):
    acquire_marker(tmp_path, "run-1")
    assert active(tmp_path)
    with pytest.raises(RuntimeError, match="maintenance_active"):
        acquire_marker(tmp_path, "run-2")
    release(tmp_path)
    assert not active(tmp_path)


def test_dead_process_marker_is_reclaimed(tmp_path):
    path = tmp_path / "reconcile.maintenance"
    path.write_text('{"pid":99999999,"run_id":"old"}', encoding="ascii")
    acquire_marker(tmp_path, "run-2")
    assert active(tmp_path)
    release(tmp_path)


def test_marker_is_owner_only(tmp_path):
    path = acquire_marker(tmp_path, "run-1")
    assert path.stat().st_mode & 0o077 == 0
    assert os.getpid() > 0
    release(tmp_path)
