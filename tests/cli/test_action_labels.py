"""CLI privacy and offline action-label listing guards."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_status_doctor import _init, _run
from test_status_doctor import trusted_root as _trusted_root_fixture

trusted_root = _trusted_root_fixture


def test_action_label_list_requires_private_metadata_and_digest_checks(trusted_root):
    state = trusted_root / "state"
    _init(trusted_root, state)
    public = _run(
        trusted_root, "rules", "action-label", "list", "--state-dir", str(state)
    )
    assert public.returncode == 3
    assert json.loads(public.stdout)["code"] == "scope_required"
    explicit_public = _run(
        trusted_root,
        "rules",
        "action-label",
        "list",
        "--state-dir",
        str(state),
        "--public",
    )
    assert explicit_public.returncode == 3
    assert json.loads(explicit_public.stdout)["code"] == "scope_required"
    private = _run(
        trusted_root,
        "rules",
        "action-label",
        "list",
        "--state-dir",
        str(state),
        "--private-metadata",
    )
    assert private.returncode == 0
    assert json.loads(private.stdout)["data"]["labels"] == {
        "add_domain": "AI/AddDomain",
        "add_sender": "AI/AddSender",
        "blacklist": "AI/BlackList",
    }
    assert "source@synthetic.example" not in private.stdout


def test_action_label_set_remove_is_single_writer_and_remove_restores_default(
    trusted_root,
):
    state = trusted_root / "state"
    _init(trusted_root, state)
    request = "323e4567e89b42d3a456426614174001"
    changed = _run(
        trusted_root,
        "rules",
        "action-label",
        "set",
        "--state-dir",
        str(state),
        "--kind",
        "add_sender",
        "--name",
        "Facet/AddSender",
        "--request-id",
        request,
        "--yes",
    )
    assert changed.returncode == 0, changed.stderr + changed.stdout
    assert "name" not in json.loads(changed.stdout)["data"]
    private = _run(
        trusted_root,
        "rules",
        "action-label",
        "list",
        "--state-dir",
        str(state),
        "--private-metadata",
    )
    assert json.loads(private.stdout)["data"]["labels"]["add_sender"] == (
        "Facet/AddSender"
    )
    removed = _run(
        trusted_root,
        "rules",
        "action-label",
        "remove",
        "--state-dir",
        str(state),
        "--kind",
        "add_sender",
        "--request-id",
        "423e4567e89b42d3a456426614174001",
        "--yes",
        "--private-metadata",
    )
    assert removed.returncode == 0, removed.stderr + removed.stdout
    assert json.loads(removed.stdout)["data"]["name"] == "AI/AddSender"
