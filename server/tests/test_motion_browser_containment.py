# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Public synthetic fixtures: file resources must be refused before capture."""
import os
from io import BytesIO

from PIL import Image

import pytest

from lampway_server.motion import frames as F


@pytest.fixture
def browser(tmp_path, monkeypatch):
    binary = os.environ.get("LAMPWAY_CHROMIUM")
    if not binary or not os.path.isfile(binary):
        pytest.skip("set LAMPWAY_CHROMIUM to a headless Chromium; browser containment UNVERIFIED")
    # Container browser tests lack the setuid sandbox; this flag is test-only, never a production default.
    monkeypatch.setattr(F, "CHROME_FLAGS", [*F.CHROME_FLAGS, "--no-sandbox"])
    cap = F.Chromium(binary, tmp_path / "browser")
    yield cap
    cap.close()


def scene(tmp_path, script):
    root = tmp_path / "scene"
    root.mkdir()
    entry = root / "index.html"
    entry.write_text("<!doctype html><body><script>window.__frame=()=>{};"
                     "window.__audit=()=>({text:[],marks:[]});" + script + "</script>")
    return root, entry


@pytest.mark.parametrize("kind", ["absolute", "encoded", "symlink", "iframe", "worker"])
def test_outside_file_never_reaches_capture(browser, tmp_path, kind):
    outside = tmp_path / "private.svg"
    outside.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="red"/></svg>')
    root, entry = scene(tmp_path, "")
    uri = outside.as_uri()
    if kind == "encoded":
        uri = uri.replace("private", "%70rivate")
    if kind == "symlink":
        (root / "linked.svg").symlink_to(outside)
        uri = (root / "linked.svg").as_uri()
    if kind == "iframe":
        script = f"window.__setup=()=>new Promise(r=>{{let x=document.createElement('iframe');x.onload=r;x.onerror=r;x.src='{uri}';document.body.append(x)}});"
    elif kind == "worker":
        (root / "worker.js").write_text(f"fetch('{uri}').finally(()=>postMessage('done'));")
        script = "window.__setup=()=>new Promise(r=>{let w=new Worker('worker.js');w.onmessage=r;w.onerror=r});"
    else:
        script = f"window.__setup=()=>new Promise(r=>{{let x=new Image();x.onload=r;x.onerror=r;x.src='{uri}';document.body.append(x)}});"
    entry.write_text("<!doctype html><body><script>window.__frame=()=>{};window.__audit=()=>({text:[],marks:[]});" + script + "</script>")
    with pytest.raises(F.SceneError, match="outside.*scene|scene.*outside"):
        browser.open(entry, 32, 32)
        browser.setup()
        browser.frame(0)


def test_allowed_file_resources_still_render(browser, tmp_path):
    root, entry = scene(tmp_path, "window.__setup=()=>new Promise(r=>{let x=new Image();x.onload=()=>r({});x.src='safe.svg';document.body.append(x)});")
    (root / "safe.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="green"/></svg>')
    browser.open(entry, 32, 32)
    browser.setup()
    png = browser.frame(0)
    assert Image.open(BytesIO(png)).convert("RGB").getpixel((16, 16)) == (0, 128, 0)
    assert browser.audit() == {"text": [], "marks": []}


def test_missing_audit_is_refused(browser, tmp_path):
    root, entry = scene(tmp_path, "delete window.__audit;")
    browser.open(entry, 32, 32)
    with pytest.raises(F.SceneError, match="__audit"):
        browser.audit()


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_scene_hash_rejects_escaping_symlinks(tmp_path, kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("synthetic secret")
    root = tmp_path / "scene"
    root.mkdir()
    (root / "link").symlink_to(outside if kind == "directory" else outside / "secret.txt")
    with pytest.raises(F.SceneError, match="outside.*scene"):
        F.scene_hash(root)


@pytest.mark.parametrize("suffix", ["../outside.svg", "%2e%2e/outside.svg"])
def test_file_uri_containment_decodes_traversal(tmp_path, suffix):
    root = tmp_path / "scene"
    root.mkdir()
    assert not F.allowed_file_url(root.as_uri() + "/" + suffix, root)
    assert not F.allowed_file_url("file://remote" + str(root / "x.svg"), root)
    assert F.allowed_file_url((root / "x.svg").as_uri(), root)


def test_opened_inode_checked_against_symlink_swap(tmp_path, monkeypatch):
    root = tmp_path / "scene"
    root.mkdir()
    path = root / "asset.svg"
    path.write_text("allowed")
    outside = tmp_path / "private.svg"
    outside.write_text("synthetic secret")
    original_open = F.os.open
    def swap_then_open(candidate, flags):
        path.unlink()
        path.symlink_to(outside)
        return original_open(candidate, flags)
    monkeypatch.setattr(F.os, "open", swap_then_open)
    with pytest.raises(F.SceneError, match="outside.*scene"):
        F._open_scene_file(path, root)


def test_popup_cannot_load_outside_file(browser, tmp_path):
    outside = tmp_path / "private.html"
    outside.write_text("<body>SYNTHETIC SECRET</body>")
    root, entry = scene(tmp_path, "window.__setup=async()=>{let w=window.open('" + outside.as_uri() + "');"
                        "await new Promise(r=>setTimeout(r,100));return {}};")
    with pytest.raises(F.SceneError, match="outside.*scene|scene.*outside"):
        browser.open(entry, 32, 32)
        browser.setup()
        browser.frame(0)


def test_browser_owned_ui_target_does_not_enable_scene_access(tmp_path):
    from types import SimpleNamespace
    calls = []
    cap = F.Chromium("not-launched", tmp_path)
    cap.cdp = SimpleNamespace(send=lambda method, params=None, session=None: calls.append((method, params, session)))
    cap._event({"method": "Target.attachedToTarget", "params": {
        "sessionId": "browser-ui", "targetInfo": {"targetId": "ui", "type": "browser_ui"}}})
    assert cap.violation is None
    assert calls == [("Runtime.runIfWaitingForDebugger", None, "browser-ui")]
