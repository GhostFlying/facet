"""Vertical synthetic evidence for the foreground sync composition."""

import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from test_projection_worker import _raw, _ready_owner

from facet.contracts import ProviderId
from facet.gmail.source import (
    DiscoveryPage,
    HistoryPage,
    MessageMetadata,
    SourceProfile,
    ThreadMetadata,
)
from facet.gmail.target import TargetInsertResult, TargetReadback
from facet.projection.backfill import DiscoveryDecision
from facet.sync import ForegroundSync


class _Admission:
    def evaluate(self, item, epoch):
        return DiscoveryDecision(False)


class _Source:
    def __init__(self, raw):
        self.raw_bytes = raw

    def profile(self):
        return SourceProfile("source@example.invalid", ProviderId("h-1"), 1, 1)

    def discover(self, *, window_start, window_end, page_token=None):
        return DiscoveryPage((), None, 0)

    def history(self, cursor, *, page_token=None):
        return HistoryPage(ProviderId("h-2"), (), None)

    def thread_metadata(self, thread_id):
        return ThreadMetadata(
            thread_id,
            (
                MessageMetadata(
                    ProviderId("m-new"),
                    thread_id,
                    (),
                    datetime(2026, 4, 1, 10, tzinfo=UTC),
                    (("Message-ID", "<m-new@example.invalid>"),),
                ),
            ),
        )

    def raw(self, message_id):
        assert message_id == ProviderId("m-new")
        return self.raw_bytes


class _Target:
    def __init__(self, raw):
        self.raw_bytes = raw
        self.inserted = 0

    def insert(self, raw, *, thread_id=None, date_header=True):
        self.inserted += 1
        return TargetInsertResult(ProviderId("tm-1"), ProviderId("tt-1"), None)

    def readback(self, message_id):
        return TargetReadback(message_id, ProviderId("tt-1"), (), self.raw_bytes)


@pytest.fixture
def trusted_state_parent():
    for candidate in (Path.cwd(), Path(f"/run/user/{os.geteuid()}")):
        try:
            entries = (candidate, *candidate.parents)
            if all(
                stat.S_ISDIR(info.st_mode)
                and info.st_uid in (0, os.geteuid())
                and stat.S_IMODE(info.st_mode) & 0o7022 == 0
                for entry in entries
                for info in (entry.stat(follow_symlinks=False),)
            ):
                return candidate
        except OSError:
            continue
    pytest.skip("no verified trusted test anchor")


def test_foreground_cycle_discovers_catches_up_and_maps_message(
    trusted_state_parent, monkeypatch
):
    raw = _raw("m-new", "VERTICAL_PRIVATE_SENTINEL")
    with TemporaryDirectory(prefix="facet-sync-", dir=trusted_state_parent) as root:
        owner = _ready_owner(Path(root), object(), monkeypatch)
        source = _Source(raw)
        target = _Target(raw)
        try:
            receipt = ForegroundSync(owner, source, target, _Admission()).run_once(
                max_jobs=10
            )
            assert receipt.history_pages == 1
            assert receipt.projected.verified == 1
            assert target.inserted == 1
            assert owner._connection.execute(
                "SELECT COUNT(*) FROM message_mappings"
            ).fetchone() == (1,)
            assert owner._connection.execute(
                "SELECT state FROM epochs WHERE kind='initial_backfill'"
            ).fetchone() == ("draining",)
        finally:
            owner.close()
