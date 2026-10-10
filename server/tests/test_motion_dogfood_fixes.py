# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regressions for the motion-graphics dogfood log (PR #3 follow-ups): a full Chrome's component extension is named as such, the missing
browser says where to get one, the contact sheet keeps the render's aspect, vertical 4K has the landscape ceiling, one defaults order
(explicit, template, window.__scene, tool fallback) with each value's source reported, and template defaults and path variables. Synthetic fixtures only; no browser unless LAMPWAY_CHROMIUM is set."""
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

    def keep_request(self, url, request_id, session):
        pass


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


# 6. one defaults order: explicit, then template defaults, then the scene's window.__scene, then the tool fallback
class _Declares(FakeCapture):
    def __init__(self, declared, **kw):
        super().__init__(**kw)
        self.declared = declared

    def scene(self):
        return {"duration_s": self.duration_s, **self.declared}


def _project(tmp_path):
    project = tmp_path / "project"
    (project / "motion" / "scenes" / "vert").mkdir(parents=True)
    (project / "motion" / "scenes" / "vert" / "index.html").write_text("<!doctype html>")
    return project


def _sources(res):
    return {row["name"]: (row["value"], row["source"]) for row in res["inputs"]}


def _render(tmp_path, args, declared, defaults=None, opened=None):
    def new():
        cap = _Declares(declared)
        (opened if opened is not None else []).append(cap)
        return cap
    return M.render(_project(tmp_path), {"scene": "motion/scenes/vert", **args}, new, defaults=defaults)


def test_the_scene_declared_size_is_the_default_and_is_rendered_in_a_fresh_browser(tmp_path):
    opened = []
    res = _render(tmp_path, {"fps": 10}, {"width": 180, "height": 320, "duration_s": 0.5}, opened=opened)
    assert _sources(res) == {"width": (180, "scene"), "height": (320, "scene"), "fps": (10, "explicit"), "duration_s": (0.5, "scene")}
    assert (opened[-1].width, opened[-1].height) == (180, 320) and all(c.closed for c in opened)
    assert len(opened) == 3                                    # the size probe at the fallback, the render at the scene's size, the determinism probe
    assert not [f for f in res["self_check"]["findings"] if f["check"] == "scene_override"]
    receipt = json.loads((tmp_path / "project" / res["out_dir"] / "receipt.json").read_text())
    assert receipt["inputs"]["width"] == 180 and receipt["input_sources"]["width"] == "scene"


def test_the_tool_fallback_is_last_and_named(tmp_path):
    res = _render(tmp_path, {"duration_s": 0.2, "width": 320, "height": 180}, {})
    assert _sources(res) == {"width": (320, "explicit"), "height": (180, "explicit"), "fps": (30, "tool default"), "duration_s": (0.2, "explicit")}


def test_template_defaults_rank_between_explicit_and_scene(tmp_path):
    res = _render(tmp_path, {"fps": 10, "width": 320}, {"width": 180, "height": 320, "duration_s": 2}, defaults={"width": 640, "height": 360, "duration_s": 0.3})
    assert _sources(res) == {"width": (320, "explicit"), "height": (360, "template"), "fps": (10, "explicit"), "duration_s": (0.3, "template")}


def test_an_explicit_or_template_override_of_a_differing_scene_value_is_a_warning_with_help(tmp_path):
    res = _render(tmp_path, SMALL, {"width": 1080, "height": 1920})
    over = [f for f in res["self_check"]["findings"] if f["check"] == "scene_override"]
    assert len(over) == 1 and over[0]["severity"] == "warn" and res["self_check"]["warn"] >= 1
    assert "width 320 (explicit) over the scene's 1080" in over[0]["detail"] and "height 180 (explicit) over the scene's 1920" in over[0]["detail"]
    assert any("omit width and height" in h for h in res["help"])


@pytest.mark.parametrize("declared", [{"width": 320, "height": 180}, {}, {"width": "wide"}])
def test_a_matching_absent_or_malformed_declared_value_is_silent(tmp_path, declared):
    res = _render(tmp_path, SMALL, declared)
    assert not [f for f in res["self_check"]["findings"] if f["check"] == "scene_override"]
    assert not any("omit" in h for h in res["help"])


def test_a_scene_declared_size_out_of_bounds_is_refused_with_the_bounds(tmp_path):
    with pytest.raises(M.Refused, match="long edge 16..3840, short edge 16..2160"):
        _render(tmp_path, {"fps": 10}, {"width": 4096, "height": 2160})


@pytest.mark.parametrize("params,expected", [
    ({"resolution": "1080p", "aspect_ratio": "16:9", "duration": 13}, {"width": 1920, "height": 1080, "duration_s": 13}),
    ({"resolution": "1080p", "aspect_ratio": "9:16"}, {"width": 1080, "height": 1920}),
    ({"resolution": "4k", "aspect_ratio": "16:9"}, {"width": 3840, "height": 2160}),
    ({"resolution": "720p", "aspect_ratio": "1:1"}, {"width": 720, "height": 720}),
    ({"duration": 8, "model": "x"}, {"duration_s": 8}),
    ({}, {}),
])
def test_template_defaults_map_resolution_and_aspect_to_pixels(params, expected):
    assert M.template_defaults(params) == expected


def test_an_unreadable_template_resolution_is_refused():
    with pytest.raises(M.Refused, match="resolution like 1080p"):
        M.template_defaults({"resolution": "huge", "aspect_ratio": "16:9"})


# 7. a template's defaults flow into the tool; its path-like variables are checked against the project
def _tool(project, arguments):
    import asyncio
    text, is_error = asyncio.run(MT.call(None, project, MT.NAME, arguments, capture=FakeCapture))
    return json.loads(text), is_error


def test_template_defaults_flow_into_the_tool_below_explicit_arguments(tmp_path):
    project = _project(tmp_path)
    out, is_error = _tool(project, {"scene": "motion/scenes/vert", "width": 180, "fps": 10, "duration_s": 0.2, "template": "mg-site-clip@1.0.0", "vault": False})
    assert not is_error, out
    assert _sources(out) == {"width": (180, "explicit"), "height": (1080, "template"), "fps": (10, "explicit"), "duration_s": (0.2, "explicit")}


def test_missing_template_paths_are_warned_about_with_a_help_line(tmp_path):
    project = _project(tmp_path)
    (project / "public" / "assets").mkdir(parents=True)
    out, _ = _tool(project, {"scene": "motion/scenes/vert", **SMALL, "duration_s": 0.2, "template": "mg-site-clip@1.0.0", "vault": False,
                             "variables": {"media_dir": "../elsewhere"}})
    assert out["warnings"] == ["mg-site-clip@1.0.0: copy_source=public/index.html does not exist under the project",
                               "mg-site-clip@1.0.0: media_dir=../elsewhere is outside the project"]
    assert 'pass variables {"copy_source": "<project-relative path>"} naming the real copy the scene was built from' in out["help"]


def test_prose_path_variables_and_untemplated_renders_carry_no_path_warning(tmp_path):
    project = _project(tmp_path)
    out, _ = _tool(project, {"scene": "motion/scenes/vert", **SMALL, "duration_s": 0.2, "template": "mg-tutorial@1.0.0", "vault": False,
                             "variables": {"task": "open a project"}})
    assert "warnings" not in out                                                   # steps_source is prose ("the tutorial page's numbered list")
    out, _ = _tool(project, {"scene": "motion/scenes/vert", **SMALL, "duration_s": 0.2, "vault": False})
    assert "warnings" not in out and all(row["source"] != "template" for row in out["inputs"])


def test_the_social_clip_template_is_vertical_by_default(tmp_path):
    from lampway_server.prompts import library as PL
    t = PL.Library(PL.BUILTIN, None, None).get("mg-social-clip", "1.0.0")
    assert M.template_defaults(t["defaults"]) == {"width": 1080, "height": 1920, "duration_s": 12}
    out, is_error = _tool(_project(tmp_path), {"scene": "motion/scenes/vert", "fps": 2, "duration_s": 0.5, "template": "mg-social-clip@1.0.0", "vault": False,
                                               "variables": {"copy_source": "motion/scenes/vert/index.html", "focus": "a launch"}})
    assert not is_error, out
    assert _sources(out)["width"] == (1080, "template") and _sources(out)["height"] == (1920, "template")
    assert out["warnings"] == ["mg-social-clip@1.0.0: logo_dir=assets does not exist under the project", "mg-social-clip@1.0.0: media_dir=media does not exist under the project"]


# containment: an out-of-scene file request is refused at once, not deferred to the next check
def test_an_outside_file_request_is_failed_and_refused_at_once(tmp_path):
    scene = tmp_path / "scene"
    scene.mkdir()
    (tmp_path / "private.svg").write_text("<svg/>")
    cap = F.Chromium("/nonexistent/chrome", tmp_path / "browser")
    cap.cdp, cap.scene_root = _RecordingCDP(), scene.resolve()
    with pytest.raises(F.SceneError, match="file outside the scene folder"):
        cap._event({"method": "Fetch.requestPaused", "sessionId": "s1",
                    "params": {"requestId": "r1", "request": {"url": (tmp_path / "private.svg").as_uri()}}})
    assert cap.cdp.sent == [("Fetch.failRequest", {"requestId": "r1", "errorReason": "AccessDenied"}, "s1")]


def test_a_scene_file_request_is_still_fulfilled(tmp_path):
    scene = tmp_path / "scene"
    scene.mkdir()
    (scene / "ok.svg").write_text("<svg/>")
    cap = F.Chromium("/nonexistent/chrome", tmp_path / "browser")
    cap.cdp, cap.scene_root = _RecordingCDP(), scene.resolve()
    cap._event({"method": "Fetch.requestPaused", "sessionId": "s1",
                "params": {"requestId": "r1", "request": {"url": (scene / "ok.svg").as_uri()}}})
    assert [m for m, _p, _s in cap.cdp.sent] == ["Fetch.fulfillRequest"] and cap.violation is None


@pytest.fixture
def live_browser(tmp_path, monkeypatch):
    import os
    binary = os.environ.get("LAMPWAY_CHROMIUM")
    if not binary or not os.path.isfile(binary):
        pytest.skip("set LAMPWAY_CHROMIUM to a headless Chromium; navigation containment UNVERIFIED")
    monkeypatch.setattr(F, "CHROME_FLAGS", [*F.CHROME_FLAGS, "--no-sandbox"])    # container only, as in the containment suite
    cap = F.Chromium(binary, tmp_path / "browser")
    yield cap
    cap.close()


@pytest.mark.parametrize("when", ["setup", "frame"])
def test_navigating_the_scene_to_an_outside_file_is_a_prompt_containment_refusal(live_browser, tmp_path, when):
    import time
    outside = tmp_path / "private.html"
    outside.write_text("<body style='background:red'>")
    scene = tmp_path / "scene"
    scene.mkdir()
    go = f"location.href='{outside.as_uri()}'"
    setup = f"window.__setup=async()=>{{{go};await new Promise(r=>setTimeout(r,400));return {{fonts:[],images:[]}}}};" if when == "setup" else \
        "window.__setup=async()=>({fonts:[],images:[]});"
    frame = f"window.__frame=(t)=>{{if(!window.gone){{window.gone=1;{go}}}}};" if when == "frame" else "window.__frame=()=>{};"
    (scene / "index.html").write_text("<!doctype html><body><script>window.__audit=()=>({text:[],marks:[]});" + setup + frame + "</script>")
    live_browser.scene_root = scene
    t0 = time.monotonic()
    with pytest.raises(F.SceneError, match="file outside the scene folder"):
        live_browser.open(scene / "index.html", 64, 64)
        live_browser.setup()
        for i in range(5):
            live_browser.frame(i / 10)
            time.sleep(0.2)
    assert time.monotonic() - t0 < 30
