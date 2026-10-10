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


# 4. the agent tool's refusals carry help[] next steps
def test_no_browser_refusal_points_at_the_build_guide(tmp_path, monkeypatch):
    def missing():
        raise F.ChromiumMissing(F.NO_CHROMIUM)
    monkeypatch.setattr(MT.F, "chromium_binary", missing)
    import asyncio
    text, is_error = asyncio.run(MT.call(None, _project(tmp_path), MT.NAME, {"scene": "motion/scenes/vert"}))
    out = json.loads(text)
    assert is_error and out["ok"] is False and out["help"] == [MT.BROWSER_HELP] and "BUILD-LAMPWAY.md section 8" in out["help"][0]


def test_an_out_of_bounds_size_refusal_gives_the_bounds(tmp_path):
    out, is_error = _tool(_project(tmp_path), {"scene": "motion/scenes/vert", "width": 4096, "height": 2160})
    assert is_error and out["error"].startswith("size 4096x2160")
    assert out["help"] == ["width and height: even integers, long edge 16..3840, short edge 16..2160 (e.g. 1920x1080, 1080x1920, 3840x2160, 2160x3840)"]


def test_every_refusal_has_a_help_line(tmp_path):
    project = _project(tmp_path)
    for args in ({"scene": "motion/scenes/vert", "fps": 0}, {"scene": "motion/scenes/vert", "duration_s": 500}, {"scene": "nowhere"}):
        out, is_error = _tool(project, args)
        assert is_error and out["help"] and all(isinstance(h, str) and h for h in out["help"]), out


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


# 13. a scene's script error is reported, and the refusal points at the scene contract's real home
def test_an_uncaught_exception_and_a_console_error_are_kept_scene_relative(tmp_path):
    cap = F.Chromium("/nonexistent/chrome", tmp_path / "browser")
    cap.cdp, cap.scene_root = _RecordingCDP(), (tmp_path / "scene").resolve()
    url = (tmp_path / "scene" / "scene.js").resolve().as_uri()
    cap._event({"method": "Runtime.exceptionThrown", "params": {"exceptionDetails": {
        "text": "Uncaught", "url": url, "lineNumber": 2, "columnNumber": 11, "exception": {"description": "SyntaxError: Unexpected token ','"}}}})
    cap._event({"method": "Runtime.consoleAPICalled", "params": {"type": "error", "args": [{"type": "string", "value": "no data"}],
                                                                  "stackTrace": {"callFrames": [{"url": url, "lineNumber": 0, "columnNumber": 0}]}}})
    cap._event({"method": "Runtime.consoleAPICalled", "params": {"type": "log", "args": [{"value": "fine"}]}})
    assert cap.errors() == ["scene.js:3:12: SyntaxError: Unexpected token ','", "scene.js:1:1: console.error: no data"]
    assert str(tmp_path) not in " ".join(cap.errors())


class _Broken(FakeCapture):
    def has_frame(self):
        return False

    def errors(self):
        return ["scene.js:1:11: SyntaxError: Unexpected token ','"]


def test_no_frame_after_a_script_error_names_the_error_and_scene_md(tmp_path):
    with pytest.raises(M.Refused) as exc:
        M._ready(_Broken(), tmp_path / "index.html", 64, 64)
    assert str(exc.value) == ("the scene does not define window.__frame (the page reported 1 script error; the first: scene.js:1:11: SyntaxError: "
                              "Unexpected token ','): see the scene contract in specs/motion_graphics/scene.md")
    with pytest.raises(M.Refused, match=r"window.__frame: see the scene contract in specs/motion_graphics/scene.md$"):
        M._ready(type("NoFrame", (FakeCapture,), {"has_frame": lambda self: False})(), tmp_path / "index.html", 64, 64)


def test_a_script_error_that_does_not_stop_the_render_is_a_warning(tmp_path):
    class Noisy(FakeCapture):
        def errors(self):
            return ["scene.js:9:1: console.error: missing glyph"]
    res = M.render(_project(tmp_path), {"scene": "motion/scenes/vert", **SMALL, "duration_s": 0.2}, Noisy)
    page = [f for f in res["self_check"]["findings"] if f["check"] == "page_error"]
    assert page == [{"frame": 0, "check": "page_error", "severity": "warn", "detail": "the page reported 1 script error(s); the first: scene.js:9:1: console.error: missing glyph"}]


def test_the_doc_pointers_name_files_and_sections_that_exist():
    import re
    spec = (REPO / "specs" / "motion_graphics" / "motion_graphics.md").read_text(encoding="utf-8")
    assert "## 2. Timeline, rendering and export" in spec and "## 4. Containment and security" in spec
    assert "## Self-check contract" in (REPO / "specs" / "motion_graphics" / "scene.md").read_text(encoding="utf-8")
    for p in (REPO / "server" / "lampway_server" / "motion").glob("*.py"):
        assert not re.search(r"\(motion_graphics\.md section", p.read_text(encoding="utf-8")), p.name


def test_a_syntax_error_in_scene_js_is_reported_with_file_line_and_message(live_browser, tmp_path):
    scene = tmp_path / "scene"
    scene.mkdir()
    (scene / "index.html").write_text("<!doctype html><body><script src='scene.js'></script>")
    (scene / "scene.js").write_text("window.__setup = async () => ({fonts: [], images: []});\nvar a = 1,;\nwindow.__frame = t => {};\n")
    live_browser.scene_root = scene
    with pytest.raises(M.Refused) as exc:
        M._ready(live_browser, scene / "index.html", 64, 64, scene_root=scene)
    assert "the first: scene.js:2:" in str(exc.value) and "SyntaxError" in str(exc.value) and "specs/motion_graphics/scene.md" in str(exc.value)


# 11. a draw-on opening the scene declares is not a weak poster frame
def _sparse_png(w=320, h=180):
    import io as _io
    im = Image.new("RGB", (w, h), (10, 10, 12))
    for x in range(40, 44):                                       # a few pixels of stroke: detail share between 0.01% and 0.1%
        im.putpixel((x, 90), (240, 240, 240))
    buf = _io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


class _DrawOn(FakeCapture):
    def __init__(self, opening=None, **kw):
        super().__init__(duration_s=2.0, **kw)
        self.opening = opening

    def scene(self):
        return {"duration_s": 2.0, **({"opening_s": self.opening} if self.opening is not None else {})}

    def frame(self, t):
        self.frames_asked.append(t)
        return _sparse_png(self.width, self.height) if t < 0.5 else super().frame(t)


def _sparse_rows(res):
    return [(f["frame"], f["severity"]) for f in res["self_check"]["findings"] if f["check"] == "sparse"]


def test_the_sparse_opening_still_warns_without_a_declaration(tmp_path):
    res = M.render(_project(tmp_path), {"scene": "motion/scenes/vert", **SMALL}, lambda: _DrawOn())
    assert (0, "warn") in _sparse_rows(res) and "opening_s" not in res


def test_a_declared_opening_turns_sparse_into_info_and_is_recorded(tmp_path):
    res = M.render(_project(tmp_path), {"scene": "motion/scenes/vert", **SMALL}, lambda: _DrawOn(opening=0.6))
    assert _sparse_rows(res) and all(sev == "info" for _f, sev in _sparse_rows(res))
    assert res["opening_s"] == 0.6 and res["self_check"]["warn"] == 0
    detail = [f["detail"] for f in res["self_check"]["findings"] if f["check"] == "sparse"][0]
    assert "inside the scene's declared opening (window.__scene.opening_s 0.6 s)" in detail


def test_the_opening_ends_where_declared_and_empty_still_fails(tmp_path):
    from lampway_server.motion import check as C
    f = [{"check": "sparse", "severity": "warn", "detail": "d"}, {"check": "empty", "severity": "fail", "detail": "e"}]
    assert C.opening_grace(f, 0.6, 0.6) == f                              # t == opening_s is after the opening
    inside = C.opening_grace(f, 0.0, 0.6)
    assert inside[0]["severity"] == "info" and inside[1] == f[1]


@pytest.mark.parametrize("bad", [-0.1, 1.5, 4.0, "1", True])
def test_an_opening_beyond_bounds_is_refused(tmp_path, bad):
    with pytest.raises(M.Refused, match="opening_s"):
        M.render(_project(tmp_path), {"scene": "motion/scenes/vert", **SMALL}, lambda: _DrawOn(opening=bad))


# 15. an audit-only stride records authored geometry for the whole timeline, without a PNG per row
class _Counting(FakeCapture):
    audits = 0

    def audit(self):
        type(self).audits += 1
        return {"text": [{"sel": "#t", "text": "hi", "box": [40, 40, 120, 70], "font_px": 28, "opacity": 1}], "marks": []}


def test_audit_every_s_writes_a_stream_without_extra_pngs(tmp_path):
    project = _project(tmp_path)
    res = M.render(project, {"scene": "motion/scenes/vert", **SMALL, "duration_s": 2, "samples": [0], "audit_every_s": 0.5}, _Counting)
    out = project / res["out_dir"]
    rows = [json.loads(line) for line in (out / "audit.jsonl").read_text().splitlines()]
    assert [r["frame"] for r in rows] == [0, 5, 10, 15, 19] and rows[1]["t"] == 0.5 and rows[1]["audit"]["text"][0]["text"] == "hi"
    assert len(list((out / "samples").glob("*.png"))) == 1                       # one sample, five audit rows
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["audit_stream"] == {"every_frames": 5, "audits": 5} and receipt["inputs"]["audit_every_s"] == 0.5
    assert receipt["artifact_hashes"]["audit"] and res["files"]["audit"].endswith("/audit.jsonl")


def test_without_a_stride_nothing_changes(tmp_path):
    project = _project(tmp_path)
    res = M.render(project, {"scene": "motion/scenes/vert", **SMALL, "duration_s": 0.2}, FakeCapture)
    out = project / res["out_dir"]
    assert not (out / "audit.jsonl").exists() and "audit" not in res["files"]
    assert json.loads((out / "receipt.json").read_text())["audit_stream"] is None


def test_the_probe_audits_the_stream_frames_as_the_first_pass_did(tmp_path):
    _Counting.audits = 0
    M.render(_project(tmp_path), {"scene": "motion/scenes/vert", **SMALL, "duration_s": 2, "samples": [0], "audit_every_s": 0.5}, _Counting)
    first_pass = 5                                                                # frames 0, 5, 10, 15, 19 (frame 0 is also the sample)
    assert _Counting.audits == 2 * first_pass                                    # the probe renders 0..19 too and audits the same frames


@pytest.mark.parametrize("bad", [0, -1, 121, "1", True, float("nan")])
def test_a_bad_stride_is_refused(bad):
    with pytest.raises(M.Refused, match="audit_every_s"):
        M.inputs({"scene": "x", "audit_every_s": bad})


def test_a_stream_render_verifies_and_an_old_receipt_still_reads(tmp_path):
    project = _project(tmp_path)
    res = M.render(project, {"scene": "motion/scenes/vert", **SMALL, "duration_s": 0.5, "audit_every_s": 0.2}, FakeCapture)
    v = M.verify(project, {"receipt": f"{res['out_dir']}/receipt.json"}, FakeCapture)
    assert v["reproduced"] is True
    receipt = json.loads((project / res["out_dir"] / "receipt.json").read_text())
    del receipt["inputs"]["audit_every_s"]
    assert M._receipt_inputs(receipt)["audit_every_s"] is None


# 14. timeline checks the sampled frames cannot see: reading time, near-blank beats, a caller's safe zone
def _row(frame, t, *texts):
    return {"frame": frame, "t": t, "audit": {"text": [{"sel": sel, "text": text, "box": box, "font_px": 40, "opacity": op}
                                                      for sel, text, box, op in texts], "marks": []}}


HEAD = ("#h", "Seven words is a lot to read", [100, 300, 900, 360], 1.0)


def test_a_line_held_shorter_than_its_words_need_warns_reading():
    from lampway_server.motion import check as C
    stream = [_row(i * 5, i * 0.5, HEAD) for i in range(3)] + [_row(15, 1.5)]     # fully visible 0.0-1.0 s (+ the stride): 1.5 s
    found = C.stream_findings(stream, 0.5, 2.0, 1080, 1920)
    reading = [f for f in found if f["check"] == "reading"]
    assert len(reading) == 1 and reading[0]["frame"] == 0 and reading[0]["severity"] == "warn"
    assert "fully visible about 1.50 s from 0.00 s; 7 words need 2.33 s" in reading[0]["detail"]
    long = [_row(i * 5, i * 0.5, HEAD) for i in range(6)]                             # 3.0 s: enough
    assert not [f for f in C.stream_findings(long, 0.5, 3.0, 1080, 1920) if f["check"] == "reading"]


def test_a_second_without_readable_text_warns_low_content_but_the_opening_does_not():
    from lampway_server.motion import check as C
    faint = ("#h", "fading", [100, 300, 900, 360], 0.2)
    stream = [_row(0, 0.0, HEAD), _row(5, 0.5, HEAD), _row(10, 1.0, faint), _row(15, 1.5), _row(20, 2.0), _row(25, 2.5, HEAD)]
    low = [f for f in C.stream_findings(stream, 0.5, 3.0, 1080, 1920) if f["check"] == "low_content"]
    assert len(low) == 1 and low[0]["frame"] == 10 and "from 1.00 s to 2.50 s (1.50 s" in low[0]["detail"]
    short = [_row(0, 0.0, HEAD), _row(5, 0.5), _row(10, 1.0, HEAD)]                   # a 0.5 s transition: fine
    assert not [f for f in C.stream_findings(short, 0.5, 1.5, 1080, 1920) if f["check"] == "low_content"]
    opening = [_row(0, 0.0), _row(5, 0.5), _row(10, 1.0), _row(15, 1.5, HEAD)]
    assert [f["check"] for f in C.stream_findings(opening, 0.5, 2.0, 1080, 1920, opening_s=1.5)] == ["reading"]


def test_text_outside_the_safe_zone_fails_once_per_text_over_the_stream():
    from lampway_server.motion import check as C
    low_line = ("#cta", "Tap to learn more", [100, 1700, 900, 1760], 1.0)              # y 1700 > 0.8 * 1920
    stream = [_row(i * 5, i * 0.5, HEAD, low_line) for i in range(6)]
    zone = [0.05, 0.12, 0.95, 0.8]
    found = [f for f in C.stream_findings(stream, 0.5, 3.0, 1080, 1920, zone, skip={0}) if f["check"] == "safe_zone"]
    assert len(found) == 1 and found[0]["severity"] == "fail" and found[0]["frame"] == 5
    assert "'Tap to learn more'" in found[0]["detail"] and "(5 audited frames from frame 5)" in found[0]["detail"]
    assert not [f for f in C.stream_findings(stream, 0.5, 3.0, 1080, 1920, None) if f["check"] == "safe_zone"]


class _Feed(FakeCapture):
    def audit(self):
        return {"text": [{"sel": "#cta", "text": "Tap", "box": [40, 150, 120, 170], "font_px": 28, "opacity": 1}], "marks": []}


def test_safe_zone_fails_a_render_at_samples_and_in_the_stream(tmp_path):
    project = _project(tmp_path)
    args = {"scene": "motion/scenes/vert", **SMALL, "duration_s": 1, "samples": [0], "audit_every_s": 0.5, "safe_zone": [0.05, 0.1, 0.95, 0.8]}
    res = M.render(project, args, _Feed)
    zone = [f for f in res["self_check"]["findings"] if f["check"] == "safe_zone"]
    assert res["ok"] is False and [f["frame"] for f in zone] == [0, 5]                 # the sample, then the stream (frames 5 and 9)
    receipt = json.loads((project / res["out_dir"] / "receipt.json").read_text())
    assert receipt["inputs"]["safe_zone"] == [0.05, 0.1, 0.95, 0.8]
    assert M.verify(project, {"receipt": f"{res['out_dir']}/receipt.json"}, _Feed)["reproduced"] is True


@pytest.mark.parametrize("bad", [[0, 0, 1], [0.5, 0, 0.4, 1], [0, 0, 1, 1.2], "0,0,1,1", [0, 0, True, 1]])
def test_a_bad_safe_zone_is_refused(bad):
    with pytest.raises(M.Refused, match="safe_zone"):
        M.inputs({"scene": "x", "safe_zone": bad})


# 10. progress: a long render must not look like a hung one
def test_progress_is_throttled_and_reports_each_phase_first_and_last_frame():
    from lampway_server.motion.progress import Progress
    now = [0.0]
    rows = []
    p = Progress(rows.append, every=5.0, clock=lambda: now[0])
    for i in range(1, 101):
        now[0] = i * 0.5                                                     # 0.5 s a frame: 50 s for 100 frames
        p.report("render", i, 100)
    assert [r["frame"] for r in rows] == [1, 11, 21, 31, 41, 51, 61, 71, 81, 91, 100]
    assert rows[1] == {"phase": "render", "frame": 11, "frames": 100, "elapsed_s": 5.0, "eta_s": 40.5}
    now[0] = 60.0
    p.report("probe", 1, 8)
    assert rows[-1]["phase"] == "probe" and rows[-1]["elapsed_s"] == 0.0
    assert p.phases == [{"phase": "render", "frames": 100, "seconds": 49.5}, {"phase": "probe", "frames": 1, "seconds": 0.0}]


def test_render_and_verify_answer_with_their_phases_and_feed_a_callable(tmp_path):
    project = _project(tmp_path)
    rows = []
    res = M.render(project, {"scene": "motion/scenes/vert", **SMALL, "duration_s": 0.5}, FakeCapture, progress=rows.append)
    assert [p["phase"] for p in res["progress"]] == ["render", "probe"] and res["progress"][0]["frames"] == res["frames"]
    assert rows[0]["frame"] == 1 and rows[0]["phase"] == "render" and {r["phase"] for r in rows} == {"render", "probe"}
    v = M.verify(project, {"receipt": f"{res['out_dir']}/receipt.json"}, FakeCapture)
    assert [p["phase"] for p in v["progress"]] == ["render"] and v["progress"][0]["frames"] == res["frames"]


def test_the_agent_tool_logs_progress_and_hands_rows_to_its_caller(tmp_path, caplog):
    import asyncio
    import logging
    project = _project(tmp_path)
    rows = []
    with caplog.at_level(logging.INFO, logger="lampway.motion"):
        text, is_error = asyncio.run(MT.call(None, project, MT.NAME, {"scene": "motion/scenes/vert", **SMALL, "duration_s": 0.5, "vault": False},
                                             capture=FakeCapture, progress=rows.append))
    out = json.loads(text)
    assert not is_error and [p["phase"] for p in out["progress"]] == ["render", "probe"]
    assert rows and any(r.getMessage().startswith("lampway_motion_graphics render 1/") for r in caplog.records)
    assert MT.progress_line({"phase": "render", "frame": 120, "frames": 450, "elapsed_s": 48.1, "eta_s": 132.3}) == "render 120/450 frames, 48.1 s, eta 132.3 s"


# 7, the mg-site-clip note: a new wording is a new version
def test_mg_site_clip_1_0_1_says_its_paths_are_the_site_repos_and_1_0_0_is_kept():
    from lampway_server.prompts import library as PL
    lib = PL.Library(PL.BUILTIN, None, None)
    new, old = lib.get("mg-site-clip"), lib.get("mg-site-clip", "1.0.0")
    assert new["version"] == "1.0.1" and "separate lampway-site repository" in new["description"]
    assert "lampway-site" not in old["description"]
    strip = lambda t: {k: v for k, v in t.items() if k not in ("version", "description", "provenance", "variables", "file", "scope")}
    assert strip(new) == strip(old)                                               # wording only: body, defaults, gates and beats unchanged
    assert {k: v.get("default") for k, v in new["variables"].items()} == {k: v.get("default") for k, v in old["variables"].items()}


# 2, the probe left open: the test environment says when the real-browser motion tests will skip
@pytest.mark.parametrize("binary,expect", [(None, "will SKIP"), ("/bin/sh", "headless Chromium at")])
def test_test_env_says_whether_the_motion_browser_tests_can_run(tmp_path, binary, expect):
    import subprocess
    text = (REPO / "scripts" / "lampway" / "test_env.sh").read_text(encoding="utf-8")
    start = text.index('if [ -n "${LAMPWAY_CHROMIUM:-}" ]')
    snippet = text[start:text.index("\nfi\n", start) + 4]
    env = {"PATH": "/usr/bin:/bin", **({"LAMPWAY_CHROMIUM": binary} if binary else {})}
    r = subprocess.run(["bash", "-c", snippet], env=env, capture_output=True, text=True, timeout=10)
    assert r.returncode == 0 and expect in r.stdout + r.stderr and "BUILD-LAMPWAY.md section 8" in text[start - 300:start]
