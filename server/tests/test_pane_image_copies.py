# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retention applies only to recorded pane image copies."""
import json
import os
from pathlib import Path
import pytest
from lampway_server.herdr.host import Cockpit

PNG = b"\x89PNG\r\n\x1a\n" + b"fake image bytes"
DAY = 86400

@pytest.fixture
def pane(tmp_path, monkeypatch):
    from lampway_server.herdr import host
    clock = [1_800_000_000.0]
    monkeypatch.setattr(host.time, "time", lambda: clock[0])
    project = tmp_path / "project"
    project.mkdir()
    cockpit = Cockpit(tmp_path / "herdr", project_root=project)
    cockpit._save({"version": 1, "sessions": [{"id": sid, "project_root": str(project), "state": "ended"}
                                              for sid in ("pane-one", "pane-two")]})
    return cockpit, project, clock


def test_expiry_removes_only_30_day_owned_copies_and_survives_restart(pane):
    cockpit, project, clock = pane
    original = project / "original.png"
    original.write_bytes(PNG)
    first = Path(cockpit.write_pane_images("pane-one", [original.read_bytes()])[0])
    legacy = first.parent / "legacy-image.png"
    legacy.write_bytes(PNG)
    clock[0] += 29 * DAY
    second = Path(cockpit.write_pane_images("pane-two", [PNG])[0])
    cockpit = Cockpit(cockpit.root, project_root=project)
    assert cockpit.expire_pane_images() == [] and first.exists()
    clock[0] += DAY
    assert cockpit.expire_pane_images() == [str(first)]
    assert not first.exists() and second.exists()
    assert original.read_bytes() == PNG and legacy.read_bytes() == PNG
    assert cockpit.expire_pane_images() == []


def test_sending_new_images_expires_the_sessions_older_owned_copies(pane):
    cockpit, project, clock = pane
    old = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    clock[0] += 30 * DAY
    new = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    assert not old.exists() and new.read_bytes() == PNG


@pytest.mark.parametrize("replacement", ["symlink", "hardlink", "different_bytes", "same_bytes_new_inode"])
def test_replaced_or_shared_files_are_never_deleted_as_owned_copies(pane, replacement):
    cockpit, project, clock = pane
    image = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    original = project / "original.png"
    original.write_bytes(PNG)
    if replacement == "different_bytes":
        image.write_bytes(b"user-owned replacement")
    elif replacement == "hardlink":
        os.link(image, project / "shared.png")
    else:
        image.rename(image.with_suffix(".saved"))  # keep inode allocated
        if replacement == "symlink":
            image.symlink_to(original)
        else:
            image.write_bytes(PNG)
    clock[0] += 31 * DAY
    assert cockpit.expire_pane_images() == []
    assert image.exists() and original.read_bytes() == PNG


def test_manifest_is_private_session_scoped_metadata_outside_image_folder(pane):
    cockpit, project, clock = pane
    image = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    manifest = cockpit.root / "panes" / "pane-one" / "image-copies.json"
    assert manifest.is_file(), "copies need durable ownership metadata"
    saved = json.loads(manifest.read_text())
    assert saved["session_id"] == "pane-one" and saved["files"][0]["name"] == image.name
    assert saved["files"][0]["created_at"] == clock[0]
    assert manifest.stat().st_mode & 0o777 == 0o600 and list(image.parent.iterdir()) == [image]


def test_expiry_never_follows_a_replaced_image_directory(pane):
    cockpit, project, clock = pane
    image = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    moved = project / "moved-images"
    image.parent.rename(moved)
    image.parent.symlink_to(moved, target_is_directory=True)
    clock[0] += 31 * DAY
    assert cockpit.expire_pane_images() == [] and image.read_bytes() == PNG


def test_missing_or_corrupt_ownership_metadata_cannot_delete_files(pane):
    cockpit, project, clock = pane
    image = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    manifest = cockpit.root / "panes" / "pane-one" / "image-copies.json"
    manifest.write_text("corrupt metadata")
    clock[0] += 31 * DAY
    assert cockpit.expire_pane_images() == [] and image.read_bytes() == PNG
    manifest.unlink()
    assert cockpit.expire_pane_images() == [] and image.read_bytes() == PNG


def test_startup_reconcile_expires_owned_images_even_when_herdr_is_stopped(pane, monkeypatch):
    from lampway_server.herdr import launcher
    cockpit, project, clock = pane
    image = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    clock[0] += 30 * DAY
    monkeypatch.setattr(launcher, "server_status", lambda root: {"running": False})
    assert cockpit.reconcile()["server"] == "not_running"
    assert not image.exists()


@pytest.mark.parametrize("bad_metadata", ["[]", '{"version":1,"session_id":"another-pane","files":[]}'])
def test_invalid_ownership_metadata_is_never_deletion_authority(pane, bad_metadata):
    cockpit, project, clock = pane
    image = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    manifest = cockpit.root / "panes" / "pane-one" / "image-copies.json"
    manifest.write_text(bad_metadata)
    clock[0] += 31 * DAY
    assert cockpit.expire_pane_images() == [] and image.read_bytes() == PNG


def test_metadata_cannot_name_a_file_outside_the_owned_image_directory(pane):
    cockpit, project, clock = pane
    image = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    original = project / "original.png"
    original.write_bytes(PNG)
    manifest = cockpit.root / "panes" / "pane-one" / "image-copies.json"
    saved = json.loads(manifest.read_text())
    saved["files"][0]["name"] = "../../../../original.png"
    manifest.write_text(json.dumps(saved))
    clock[0] += 31 * DAY
    assert cockpit.expire_pane_images() == [] and original.read_bytes() == PNG and image.exists()


def test_copy_expiry_survives_registry_record_removal_without_claiming_legacy_files(pane):
    cockpit, project, clock = pane
    original = project / "original.png"
    original.write_bytes(PNG)
    image = Path(cockpit.write_pane_images("pane-one", [original.read_bytes()])[0])
    legacy = image.parent / "legacy.png"
    legacy.write_bytes(PNG)
    cockpit._save({"version": 1, "sessions": []})
    clock[0] += 30 * DAY
    assert cockpit.expire_pane_images() == [str(image)]
    assert not image.exists() and original.read_bytes() == PNG and legacy.read_bytes() == PNG
    assert cockpit.expire_pane_images() == []


@pytest.mark.parametrize("link", ["panes", "session", "manifest"])
def test_orphan_manifest_discovery_never_follows_symlinks(pane, link):
    cockpit, project, clock = pane
    image = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    manifest = cockpit.root / "panes" / "pane-one" / "image-copies.json"
    source = {"panes": cockpit.root / "panes", "session": manifest.parent, "manifest": manifest}[link]
    moved = cockpit.root / "moved-metadata"
    source.rename(moved)
    source.symlink_to(moved, target_is_directory=link != "manifest")
    cockpit._save({"version": 1, "sessions": []})
    clock[0] += 31 * DAY
    assert cockpit.expire_pane_images() == [] and image.read_bytes() == PNG


def test_orphan_expiry_never_follows_a_replaced_project_ancestor(pane):
    cockpit, project, clock = pane
    container = project / "container"
    nested = container / "nested"
    nested.mkdir(parents=True)
    cockpit._save({"version": 1, "sessions": [{"id": "pane-one", "project_root": str(nested)}]})
    image = Path(cockpit.write_pane_images("pane-one", [PNG])[0])
    container.rename(project / "moved-container")
    container.symlink_to(project / "moved-container", target_is_directory=True)
    cockpit._save({"version": 1, "sessions": []})
    clock[0] += 31 * DAY
    assert cockpit.expire_pane_images() == [] and image.read_bytes() == PNG


def test_oversized_metadata_timestamp_retains_copy_and_receipt_without_breaking_reconcile(pane, monkeypatch):
    from lampway_server.herdr import launcher
    cockpit, project, clock = pane
    original = project / "original.png"
    original.write_bytes(PNG)
    image = Path(cockpit.write_pane_images("pane-one", [original.read_bytes()])[0])
    manifest = cockpit.root / "panes" / "pane-one" / "image-copies.json"
    saved = json.loads(manifest.read_text())
    saved["files"][0]["created_at"] = 10**400
    manifest.write_text(json.dumps(saved))
    clock[0] += 31 * DAY
    assert cockpit.expire_pane_images() == []
    assert image.read_bytes() == original.read_bytes() == PNG
    assert json.loads(manifest.read_text()) == saved, "invalid timestamps must retain the ownership receipt too"
    monkeypatch.setattr(launcher, "server_status", lambda root: {"running": False})
    assert cockpit.reconcile()["server"] == "not_running"
