# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regressions for the motion-graphics dogfood log (PR #3 follow-ups): a full Chrome's component extension is named as such, the missing
browser says where to get one, the contact sheet keeps the render's aspect, vertical 4K has the landscape ceiling, and a scene whose declared
size differs from the rendered one is warned about. Synthetic fixtures only; no browser unless LAMPWAY_CHROMIUM is set."""
import json
from pathlib import Path

import pytest
from PIL import Image

from lampway_server import motion as M
from lampway_server.agent import motion_tools as MT
from lampway_server.motion import check as C
from lampway_server.motion import frames as F

from .fake_motion import FakeCapture

REPO = Path(__file__).resolve().parents[2]
SMALL = {"fps": 10, "width": 320, "height": 180}


# 1. a browser-owned component extension is not a scene worker
class _RecordingCDP:
    def __init__(self):
        self.sent = []

    def send(self, method, params=None, session=None):
        self.sent.append((method, params, session))
        return {}


def _attach(cap, kind, url):
    cap._event({"method": "Target.attachedToTarget",
                "params": {"sessionId": "s1", "targetInfo": {"targetId": "t1", "type": kind, "url": url}}})


@pytest.mark.parametrize("kind,url", [
    ("service_worker", "chrome-extension://fignfifoniblkonapihmkfakmlgkbkcf/service_worker.js"),
    ("background_page", "chrome-extension://nkeimhogjdpnpccoofpliimaahmaaome/background.html"),
])
def test_a_full_chrome_component_extension_is_refused_as_the_wrong_browser(tmp_path, kind, url):
    cap = F.Chromium("/nonexistent/chrome", tmp_path / "browser")
    cap.cdp = _RecordingCDP()
    with pytest.raises(F.SceneError) as err:
        _attach(cap, kind, url)
    text = str(err.value)
    assert "chrome-headless-shell" in text and "chrome-extension://" in text and "LAMPWAY_CHROMIUM" in text
    assert "use the main-page scene driver" not in text
    assert cap.violation == text
    assert ("Target.closeTarget", {"targetId": "t1"}, None) in cap.cdp.sent        # still closed, never resumed
    assert not any(m == "Runtime.runIfWaitingForDebugger" for m, _p, _s in cap.cdp.sent)


@pytest.mark.parametrize("url", ["file:///scene/worker.js", "blob:file:///abc", ""])
def test_a_scene_worker_keeps_the_worker_refusal(tmp_path, url):
    cap = F.Chromium("/nonexistent/chrome", tmp_path / "browser")
    cap.cdp = _RecordingCDP()
    with pytest.raises(F.SceneError, match="worker may read files outside the scene folder: use the main-page scene driver"):
        _attach(cap, "worker", url)


# 2. the missing browser names where to get one
def test_no_chromium_names_the_browser_to_install():
    with pytest.raises(F.ChromiumMissing) as err:
        F.chromium_binary({})
    text = str(err.value)
    assert "LAMPWAY_CHROMIUM" in text and "chrome-headless-shell" in text and "Chrome for Testing" in text


def test_the_build_guide_documents_the_motion_browser():
    guide = (REPO / "BUILD-LAMPWAY.md").read_text(encoding="utf-8")
    assert "LAMPWAY_CHROMIUM" in guide and "chrome-headless-shell" in guide and "Chrome for Testing" in guide
