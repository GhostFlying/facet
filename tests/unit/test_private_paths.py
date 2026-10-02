import os
from pathlib import Path

import pytest

from facet.config import ConfigError
from facet.contracts import ErrorCode
from facet.private_paths import (
    filesystem_warning,
    inspect_state_root,
    read_standalone_config,
    select_paths,
)


def standalone(tmp_path):
    config = tmp_path / "standalone.yaml"
    config.write_bytes(b"structural-only-content")
    config.chmod(0o600)
    return select_paths(str(tmp_path / "state"), str(config))


def test_selectors_do_not_create_or_change_permissions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = list(tmp_path.iterdir())
    paths = select_paths()
    assert paths.root == tmp_path / ".facet"
    assert paths.config == paths.root / "config.yaml"
    assert paths.db == paths.root / "facet.db"
    assert paths.credentials == paths.root / "credentials"
    assert inspect_state_root(paths.root) is False
    assert list(tmp_path.iterdir()) == before


def test_spike_paths_cannot_be_imported_as_production_config(tmp_path):
    with pytest.raises(ConfigError):
        select_paths(str(tmp_path / ".facet-spike"))
    with pytest.raises(ConfigError):
        select_paths(config=str(tmp_path / ".facet-spike" / "tokens.json"))


def test_managed_read_never_falls_back_even_without_locks(tmp_path):
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    config = root / "config.yaml"
    config.write_bytes(b"managed bundle must not be read")
    config.chmod(0o600)
    for explicit in [False, True]:
        with pytest.raises(ConfigError) as error:
            read_standalone_config(
                select_paths(str(root), str(config)), explicit=explicit
            )
        assert error.value.code is ErrorCode.OWNER_UNAVAILABLE
    assert set(p.name for p in root.iterdir()) == {"config.yaml"}


def test_standalone_read_safe_and_bounded(tmp_path):
    paths = standalone(tmp_path)
    assert read_standalone_config(paths, explicit=True) == b"structural-only-content"
    paths.config.chmod(0o644)
    with pytest.raises(ConfigError):
        read_standalone_config(paths, explicit=True)
    assert paths.config.stat().st_mode & 0o777 == 0o644


def test_symlink_components_hardlinks_fifo_and_wrong_owner_refused(
    tmp_path, monkeypatch
):
    paths = standalone(tmp_path)
    link = tmp_path / "alias.yaml"
    link.symlink_to(paths.config)
    with pytest.raises(ConfigError):
        read_standalone_config(select_paths(str(paths.root), str(link)), explicit=True)
    directory_alias = tmp_path / "dir-alias"
    directory_alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ConfigError):
        read_standalone_config(
            select_paths(str(paths.root), str(directory_alias / paths.config.name)),
            explicit=True,
        )
    hardlink = tmp_path / "hardlink.yaml"
    os.link(paths.config, hardlink)
    with pytest.raises(ConfigError):
        read_standalone_config(paths, explicit=True)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(ConfigError):
        read_standalone_config(select_paths(str(paths.root), str(fifo)), explicit=True)
    monkeypatch.setattr(os, "geteuid", lambda: paths.config.stat().st_uid + 1)
    with pytest.raises(ConfigError):
        read_standalone_config(select_paths(str(paths.root), str(fifo)), explicit=True)


def test_unsafe_and_symlink_state_root_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o755)
    with pytest.raises(ConfigError):
        inspect_state_root(root)
    root.chmod(0o700)
    assert inspect_state_root(root) is True
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ConfigError):
        inspect_state_root(alias)


def test_observable_file_swap_during_read_is_refused(tmp_path, monkeypatch):
    paths = standalone(tmp_path)
    read = os.read
    switched = False

    def replace_during_read(descriptor, amount):
        nonlocal switched
        chunk = read(descriptor, amount)
        if not switched:
            switched = True
            replacement = tmp_path / "replacement"
            replacement.write_bytes(b"new private config")
            replacement.chmod(0o600)
            replacement.replace(paths.config)
        return chunk

    monkeypatch.setattr(os, "read", replace_during_read)
    with pytest.raises(ConfigError) as error:
        read_standalone_config(paths, explicit=True)
    assert error.value.code is ErrorCode.OWNER_BUSY


def test_known_remote_fs_refused_unknown_pending(monkeypatch):
    monkeypatch.setattr(
        Path, "read_text", lambda *a, **kw: "1 2 0:1 / / rw - nfs server rw"
    )
    with pytest.raises(ConfigError):
        filesystem_warning(Path("/state"))
    monkeypatch.setattr(
        Path, "read_text", lambda *a, **kw: "1 2 0:1 / / rw - ext4 device rw"
    )
    assert filesystem_warning(Path("/state")) == "filesystem_verification_pending"


def test_independent_parse_does_not_claim_bundle_during_bootstrap(
    tmp_path, monkeypatch
):
    paths = standalone(tmp_path)
    read = os.read

    def bootstrap_during_read(descriptor, amount):
        if not paths.root.exists():
            paths.root.mkdir(mode=0o700)
            (paths.root / "bootstrap.json").write_text("synthetic-bootstrap")
        return read(descriptor, amount)

    monkeypatch.setattr(os, "read", bootstrap_during_read)
    assert read_standalone_config(paths, explicit=True) == b"structural-only-content"
    managed = select_paths(str(paths.root), str(paths.root / "config.yaml"))
    with pytest.raises(ConfigError) as error:
        read_standalone_config(managed, explicit=True)
    assert error.value.code is ErrorCode.OWNER_UNAVAILABLE


def test_parent_inode_swap_during_read_is_refused(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    paths = standalone(parent)
    read = os.read
    switched = False

    def replace_parent(descriptor, amount):
        nonlocal switched
        chunk = read(descriptor, amount)
        if not switched:
            switched = True
            parent.rename(tmp_path / "old-parent")
            parent.mkdir(mode=0o700)
            replacement = parent / paths.config.name
            replacement.write_bytes(b"other config")
            replacement.chmod(0o600)
        return chunk

    monkeypatch.setattr(os, "read", replace_parent)
    with pytest.raises(ConfigError) as error:
        read_standalone_config(paths, explicit=True)
    assert error.value.code is ErrorCode.OWNER_BUSY
