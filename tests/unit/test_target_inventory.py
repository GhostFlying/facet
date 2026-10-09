"""Target ownership, outbound compatibility and cycle-local insert gates."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from facet.contracts import BindingState, ErrorCode, ProjectionId
from facet.db.codecs import StorageFailure
from facet.gmail.retry import ProviderFailure
from facet.gmail.target import TargetAdapter
from facet.projection.target_inventory import TargetInventory


class Owner:
    projection_id = ProjectionId("projection")

    def __init__(self, *, mapped=(), inserted=(), retained=()):
        self.mapped, self.inserted, self.retained = mapped, inserted, retained
        self.session = self
        self.in_transaction = False

    @contextmanager
    def transaction(self):
        self.in_transaction = True
        try:
            yield self
        finally:
            self.in_transaction = False

    def _execute(self, sql, args):
        rows = self.mapped if "message_mappings" in sql else self.retained
        if "insert_attempts" in sql:
            assert "certainty='inserted'" in sql
            assert "attribution='direct_response'" in sql
            rows = self.inserted
        return SimpleNamespace(fetchall=lambda: [(item,) for item in rows])


class Request:
    def __init__(self, value):
        self.value = value

    def execute(self, *, num_retries):
        assert num_retries == 0
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class Service:
    def __init__(self, owner, pages, metadata=None):
        self.owner, self.pages, self.metadata = owner, iter(pages), metadata or {}
        self.reads, self.lists = [], []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kwargs):
        assert not self.owner.in_transaction
        assert kwargs["includeSpamTrash"] is True and "q" not in kwargs
        self.lists.append(kwargs)
        return Request(next(self.pages))

    def get(self, **kwargs):
        assert not self.owner.in_transaction
        assert kwargs["format"] == "metadata"
        assert kwargs["metadataHeaders"] == ["From"]
        self.reads.append(kwargs["id"])
        return Request(self.metadata[kwargs["id"]])


@pytest.fixture
def binding(monkeypatch):
    from facet.projection import target_inventory

    monkeypatch.setattr(
        target_inventory.reads,
        "get_binding",
        lambda *_: SimpleNamespace(
            state=BindingState.VERIFIED,
            verified_address=SimpleNamespace(value="source@example.com"),
        ),
    )


def metadata(identifier, labels, headers):
    return {
        "id": identifier,
        "labelIds": labels,
        "payload": {"headers": [{"name": "From", "value": value} for value in headers]},
    }


def test_inventory_pagination_ownership_precedes_outbound_and_is_cycle_local(binding):
    owner = Owner(mapped=("mapped",), inserted=("known",), retained=("old",))
    pages = [
        {"messages": [{"id": "mapped"}, {"id": "known"}], "nextPageToken": "next"},
        {"messages": [{"id": "old"}, {"id": "sent"}, {"id": "draft"}]},
    ]
    service = Service(
        owner,
        pages,
        {
            "sent": metadata("sent", ["SENT"], ["Sender <source@EXAMPLE.COM>"]),
            "draft": metadata("draft", ["DRAFT"], ["source@example.com"]),
        },
    )
    progress = []
    inventory = TargetInventory(
        owner, TargetAdapter(service), progress=lambda: progress.append(True)
    )
    inventory.require()
    inventory.require()
    assert inventory.checked and inventory.missing == 0
    assert len(service.lists) == 2 and service.lists[1]["pageToken"] == "next"
    assert service.reads == ["sent", "draft"]
    assert len(progress) >= 2
    next_cycle = TargetInventory(owner, TargetAdapter(Service(owner, [{}])))
    next_cycle.require()
    assert next_cycle.missing == 1


@pytest.mark.parametrize(
    "labels,headers",
    [
        ([], ["source@example.com"]),
        (["SENT"], ["other@example.com"]),
        (["DRAFT"], ["source@example.com", "other@example.com"]),
        (["SENT"], ["source@example.com, other@example.com"]),
        (["SENT"], []),
        (["TRASH"], ["source@example.com"]),
    ],
)
def test_unmanaged_content_blocks_without_adoption(binding, labels, headers, capfd):
    owner = Owner()
    service = Service(
        owner,
        [{"messages": [{"id": "unmanaged"}]}],
        {
            "unmanaged": metadata("unmanaged", labels, headers),
        },
    )
    inventory = TargetInventory(owner, TargetAdapter(service))
    with pytest.raises(StorageFailure) as failure:
        inventory.require()
    assert failure.value.code is ErrorCode.ATTRIBUTION_UNKNOWN
    assert not inventory.checked
    output = capfd.readouterr()
    assert "source@example" not in output.err and "unmanaged" not in output.err


@pytest.mark.parametrize(
    "pages",
    [
        [TimeoutError("PRIVATE_SENTINEL")],
        [{"messages": "PRIVATE_SENTINEL"}],
        [{"messages": [{}]}],
        [{"nextPageToken": "repeat"}, {"nextPageToken": "repeat"}],
    ],
)
def test_incomplete_inventory_never_passes(binding, pages, capfd):
    owner = Owner()
    inventory = TargetInventory(owner, TargetAdapter(Service(owner, pages)))
    with pytest.raises(ProviderFailure):
        inventory.require()
    assert not inventory.checked
    assert "PRIVATE_SENTINEL" not in capfd.readouterr().err


def test_unknown_fingerprint_does_not_prove_target_ownership(binding):
    owner = Owner()
    service = Service(
        owner,
        [{"messages": [{"id": "unowned"}]}],
        {
            "unowned": metadata("unowned", [], ["source@example.com"]),
        },
    )
    with pytest.raises(StorageFailure):
        TargetInventory(owner, TargetAdapter(service)).require()
