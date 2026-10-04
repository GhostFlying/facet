"""Synthetic end-to-end proof for the production foreground composition seam."""

import os
import stat
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))

from test_credential_manager import FUTURE, _manager
from test_m2_foundation_consumers import write_credentials
from test_projection_worker import _raw, _ready_owner

import facet.runtime.foreground_runtime as foreground_runtime
from facet.contracts import ErrorCode, LocalId, Revision, Role, Timestamp
from facet.db.codecs import StorageFailure
from facet.gmail.credential_codec import encode_envelope
from facet.gmail.credential_models import AccountAddress
from facet.projection.actions import PrivateActionLabelMap
from facet.projection.backfill import DiscoveryDecision
from facet.runtime.foreground_runtime import run_foreground_once


class _Factory:
    def __init__(self, controller):
        self.controller = controller
        self.profiles = []
        self.services = []

    def profile_account(self, role, secret):
        self.profiles.append((role, secret))
        return AccountAddress(
            "source@example.invalid"
            if role is Role.SOURCE
            else "target@example.invalid"
        )

    def service(self, role, snapshot):
        self.services.append((role, snapshot))
        return self.controller.service(
            "source" if role is Role.SOURCE else "target",
            scopes=frozenset(
                {"gmail.readonly"}
                if role is Role.SOURCE
                else {"gmail.readonly", "gmail.insert"}
            ),
        )


class _Admission:
    def evaluate(self, _item, _epoch):
        return DiscoveryDecision(
            True,
            __import__("facet.contracts").contracts.RuleRef(
                LocalId("00000000000040008000000000000384"), Revision(1)
            ),
        )


@pytest.mark.parametrize("mode", ["missing", "swapped", "expired", "mismatched"])
def test_runtime_rejects_credential_lineage_before_provider_services(
    trusted_state_parent, monkeypatch, mode
):
    owner, _, _, source, _ = _manager(trusted_state_parent, monkeypatch)
    try:
        before = owner.bindings()
        root = Path(owner.state_dir) / "credentials"
        source_path = root / "source.json"
        target_path = root / "target.json"
        if mode == "missing":
            source_path.unlink()
        elif mode == "swapped":
            source_bytes = source_path.read_bytes()
            target_bytes = target_path.read_bytes()
            source_path.write_bytes(target_bytes)
            target_path.write_bytes(source_bytes)
        elif mode == "expired":
            source_path.write_bytes(
                encode_envelope(
                    replace(
                        source,
                        secret=replace(
                            source.secret,
                            expires_at=Timestamp(FUTURE.value - timedelta(seconds=1)),
                        ),
                    )
                )
            )
        factory = _Factory(None)
        if mode == "mismatched":
            original_profile = factory.profile_account

            def mismatched_profile(role, secret):
                account = original_profile(role, secret)
                return (
                    AccountAddress("wrong@example.invalid")
                    if role is Role.TARGET
                    else account
                )

            monkeypatch.setattr(factory, "profile_account", mismatched_profile)
        with pytest.raises(StorageFailure) as caught:
            run_foreground_once(owner, owner.config, factory, _Admission())
        assert caught.value.code in {
            ErrorCode.SOURCE_AUTH_REQUIRED,
            ErrorCode.BINDING_MISMATCH,
        }
        assert [role for role, _ in factory.profiles] == (
            [Role.SOURCE, Role.TARGET] if mode == "mismatched" else []
        )
        assert factory.services == []
        assert owner.bindings() == before
    finally:
        owner.close()


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
                with TemporaryDirectory(
                    prefix="facet-runtime-", dir=candidate
                ) as value:
                    yield Path(value)
                return
        except OSError:
            continue
    pytest.skip("no_verified_trusted_test_anchor")


def test_runtime_composes_profiles_services_and_projection(
    trusted_state_parent, gmail_controller, monkeypatch
):
    owner = _ready_owner(Path(trusted_state_parent), object(), monkeypatch, seed=False)
    try:
        gmail_controller.labels(
            "source",
            [
                {"id": "add-sender", "name": "AI/AddSender", "type": "user"},
                {"id": "add-domain", "name": "AI/AddDomain", "type": "user"},
                {"id": "blacklist", "name": "AI/BlackList", "type": "user"},
            ],
        )
        captured = {}

        class SpyActionConsumer:
            def __init__(self, labels, source, own_addresses, source_primary):
                captured.update(
                    labels=labels,
                    source=source,
                    own_addresses=own_addresses,
                    source_primary=source_primary,
                )

        monkeypatch.setattr(
            foreground_runtime, "ActionEffectConsumer", SpyActionConsumer
        )
        source, target = write_credentials(owner)
        # _ready_owner advances the synthetic binding revision to exercise the
        # production worker. Keep the credential files on that same lineage.
        root = Path(owner.state_dir) / "credentials"
        for role, value in ((Role.SOURCE, source), (Role.TARGET, target)):
            value = replace(
                value,
                binding_revision=Revision(2),
            )
            credential_path = root / (
                "source.json" if role is Role.SOURCE else "target.json"
            )
            credential_path.write_bytes(encode_envelope(value))
        raw = _raw("runtime", "RUNTIME_PRIVATE_SENTINEL")
        gmail_controller.seed(
            "source",
            "source-message",
            "source-thread",
            raw,
            rfc_id="<runtime@example.invalid>",
            payload={
                "headers": [
                    {"name": "Message-ID", "value": "<runtime@example.invalid>"},
                    {"name": "From", "value": "sender@example.invalid"},
                    {"name": "To", "value": "target@example.invalid"},
                ]
            },
        )
        original_run = gmail_controller._run

        def run(role, method, args, scopes):
            if method == "history.list":
                return {"historyId": "h-1", "history": []}
            if method == "messages.list" and args.get("q", "").startswith("after:"):
                return {
                    "messages": [{"id": "source-message", "threadId": "source-thread"}],
                    "resultSizeEstimate": 1,
                }
            return original_run(role, method, args, scopes)

        monkeypatch.setattr(gmail_controller, "_run", run)
        factory = _Factory(gmail_controller)
        receipt = run_foreground_once(
            owner,
            owner.config,
            factory,
            _Admission(),
            max_jobs=10,
        )
        assert receipt.projected.verified == 1
        assert [role for role, _ in factory.profiles] == [Role.SOURCE, Role.TARGET]
        assert [role for role, _ in factory.services] == [Role.SOURCE, Role.TARGET]
        assert isinstance(captured["labels"], PrivateActionLabelMap)
        assert captured["own_addresses"][0].value == "source@example.invalid"
        assert captured["source_primary"] == "source@example.invalid"
        assert owner.session._connection.execute(
            "SELECT COUNT(*) FROM message_mappings"
        ).fetchone() == (1,)
        assert b"RUNTIME_PRIVATE_SENTINEL" not in owner.database_path.read_bytes()
    finally:
        owner.close()
