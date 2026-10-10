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


# 3. the contact sheet keeps the render's aspect
def _samples(tmp_path, w, h, n=3):
    d = tmp_path / "samples"
    d.mkdir()
    for i in range(n):
        Image.new("RGB", (w, h), (200, 30, 30)).save(d / f"f{i:04d}.png")
        (d / f"f{i:04d}.json").write_text(json.dumps({"t": i / 10, "findings": []}), encoding="utf-8")
    return d


@pytest.mark.parametrize("w,h", [(1080, 1920), (320, 180), (1920, 1080), (1080, 1080), (3840, 16)])
def test_contact_sheet_tiles_keep_the_frame_aspect(tmp_path, w, h):
    d = _samples(tmp_path, w, h)
    out = tmp_path / "contact.png"
    assert C.contact_sheet(d, out) == 3
    sheet = Image.open(out)
    tw = sheet.width // 3
    th = sheet.height - 28
    assert max(tw, th) == 640
    assert abs(th - tw * h / w) <= 0.5 and abs(tw - th * w / h) <= 0.5 * w / h + 0.5    # the aspect, to the rounded pixel
    # the tile itself is red edge to edge: no squash, no letterbox bars inside the tile
    assert sheet.getpixel((tw // 2, 28 + th // 2)) == (200, 30, 30)


def test_a_16_9_contact_sheet_is_unchanged(tmp_path):
    d = _samples(tmp_path, 1920, 1080)
    C.contact_sheet(d, tmp_path / "contact.png")
    assert Image.open(tmp_path / "contact.png").size == (1920, 388)


# 5. vertical 4K has the landscape ceiling
@pytest.mark.parametrize("w,h", [(2160, 3840), (3840, 2160), (1080, 1920), (16, 3840), (3840, 16)])
def test_long_edge_3840_and_short_edge_2160_either_way(w, h):
    a = M.inputs({"scene": "x", "width": w, "height": h})
    assert (a["width"], a["height"]) == (w, h)


@pytest.mark.parametrize("w,h", [(3840, 3840), (2162, 3840), (3842, 2160), (14, 1080), (1919, 1080)])
def test_out_of_range_sizes_are_still_refused(w, h):
    with pytest.raises(M.Refused, match="long edge 16..3840, short edge 16..2160"):
        M.inputs({"scene": "x", "width": w, "height": h})


def test_the_tool_schema_allows_vertical_4k():
    props = MT.SPEC.parameters["properties"]
    assert props["width"]["maximum"] == 3840 and props["height"]["maximum"] == 3840
