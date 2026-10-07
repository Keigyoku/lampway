# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""lampway_motion_graphics (specs/motion_graphics/motion_graphics.md): video drawn by code, frame by frame, deterministic.

Section 12 dependencies first (the prompt purpose, the seven templates, the provenance subtype and completeness), then the section 10 tests."""
import re

from lampway_server.library import provenance as P
from lampway_server.library.store import AssetLibrary
from lampway_server.prompts import library as PL
from lampway_server.prompts import render as PR
from lampway_server.prompts import schema as PS

MG_TEMPLATES = ("mg-site-clip", "mg-tutorial", "mg-release", "mg-facelift-ui-demo", "mg-report-card", "mg-titan-animatic", "mg-titan-ui-motion")


def _value_for(spec: dict):
    t = spec.get("type")
    if t == "enum":
        return spec["enum"][0]
    if t in ("integer", "number"):
        return spec.get("min", 1)
    if t == "boolean":
        return True
    return "a test value"


# ------------------------------------------------------------------ section 12: dependencies
def test_the_seven_motion_graphics_templates_are_builtins_that_validate_and_render_with_no_unfilled_slot():
    lib = PL.Library(PL.BUILTIN, None, None)
    refused = [e for e in lib.errors if "/mg-" in e["file"]]
    assert not refused, refused
    found = {i for i, _v in lib._items if i.startswith("mg-")}
    assert found == set(MG_TEMPLATES), f"the builtin motion-graphics templates are {sorted(found)}"
    for tid in MG_TEMPLATES:
        t = lib.get(tid, "1.0.0")
        assert t["purpose"] == "motion-graphics" and t["media"] == "video"
        needed = {k: _value_for(s) for k, s in (t.get("variables") or {}).items() if "default" not in s}
        out = PR.render(lib, tid, needed)
        assert not PS.SLOT.search(out["prompt"]), (tid, PS.SLOT.findall(out["prompt"]))
        assert not [r for r in PS.ROLES if f"[{r}]" in out["prompt"]], tid
        assert "window.__frame(t)" in out["prompt"], f"{tid}: the scene contract rides in the constraints"


def test_motion_graphics_is_a_prompt_purpose():
    assert "motion-graphics" in PS.PURPOSES


def _clip(tmp_path, name="clip.mp4", data=b"motion-graphics bytes"):
    f = tmp_path / name
    f.write_bytes(data)
    return f


def test_record_lands_an_outputs_subtype(tmp_path):
    lib = AssetLibrary(tmp_path / "lib")
    res = P.record(lib, {"generation": {"action": "motion_graphics", "job_id": "mg-1", "params": {"fps": 30}},
                         "outputs": [{"path": str(_clip(tmp_path)), "kind": "video", "subtype": "render"}]})
    assert res["ok"] and lib.get(res["assets"][0]["id"])["subtype"] == "render"


def test_a_motion_graphics_generation_is_judged_on_action_job_id_and_params(tmp_path):
    lib = AssetLibrary(tmp_path / "lib")
    gen = {"action": "motion_graphics", "job_id": "mg-2", "params": {"code_sha256": "4b30a23c", "fps": 30}}
    res = P.record(lib, {"generation": gen, "outputs": [{"path": str(_clip(tmp_path, "a.mp4", b"a")), "kind": "video", "subtype": "render"}]})
    assert res["completeness"] == {"required": 3, "present": 3, "missing": []}, res["completeness"]
    res = P.record(lib, {"generation": {"action": "motion_graphics", "params": {"fps": 30}},
                         "outputs": [{"path": str(_clip(tmp_path, "b.mp4", b"b")), "kind": "video", "subtype": "render"}]})
    assert res["completeness"]["missing"] == ["job_id"], res["completeness"]


# ------------------------------------------------------------------ section 10: the tool
import asyncio  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from lampway_server import motion as M  # noqa: E402
from lampway_server.agent import motion_tools as MT  # noqa: E402
from lampway_server.agent.tools import TOOL_NAMES, TOOLS, UnknownTool, script_for  # noqa: E402
from lampway_server.library.vault import Vault  # noqa: E402
from lampway_server.motion import encode as E  # noqa: E402

from .fake_motion import FakeCapture  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CHROMIUM = os.environ.get("LAMPWAY_CHROMIUM") or ""
TEASER = os.environ.get("LAMPWAY_MOTION_TEASER") or ""
needs_chromium = pytest.mark.skipif(not (CHROMIUM and os.path.isfile(CHROMIUM)), reason="no headless Chromium: set LAMPWAY_CHROMIUM (motion_graphics.md section 13)")
needs_teaser = pytest.mark.skipif(not (TEASER and os.path.isfile(os.path.join(TEASER, "teaser.html"))),
                                  reason="the spike's teaser fixture is outside the repository: set LAMPWAY_MOTION_TEASER to its folder")
TEASER_CODE = "4b30a23cf619b197f67974f1b6ce70de95c6b0b9fb7d83d2abbfaaaec1e3337c"
TEASER_FRAMES = "e6e517e036d987f639ebe59430a7f7eb4d3c0d81f5b8d2dce60d63b5e47b0645"
SMALL = {"fps": 10, "width": 320, "height": 180}

# the three tiny synthetic scenes (section 10), plus the two refusal scenes: a pure ramp; the same with a Math.random() flicker; one that
# fetches from the network; one that runs a CSS animation; one whose font path has a typo
_AUDIT = """window.__audit=function(){var e=document.getElementById('label'),r=e.getBoundingClientRect(),cs=getComputedStyle(e);
 return {text:[{sel:'#label',text:e.textContent,opacity:1,font_px:parseFloat(cs.fontSize),color:cs.color,box:[r.left,r.top,r.right,r.bottom]}],marks:[]};};"""
_HEAD = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;width:320px;height:180px;overflow:hidden;background:#000}
#bg{position:absolute;inset:0} #bar{position:absolute;top:120px;height:20px;width:40px;background:#fff}
#label{position:absolute;left:40px;top:30px;margin:0;font:700 40px/1 monospace;color:#fff}
STYLE</style></head><body><div id="bg"></div><div id="bar"></div><p id="label">RAMP</p><script>
window.__scene={duration_s:1,width:320,height:180};"""
_TAIL = "</script></body></html>"
_FRAME = """window.__frame=function(t){var r=Math.round(80*t);document.getElementById('bg').style.background='rgb('+r+',0,'+(80-r)+')';
 document.getElementById('bar').style.left=(BAR)+'px';};"""
_SETUP = "window.__setup=async function(){SETUP window.__frame(0);return {fonts:FONTS,images:[]};};"


def scene_html(bar="Math.round(40+200*t)", setup="", fonts="[]", style=""):
    return (_HEAD.replace("STYLE", style) + _FRAME.replace("BAR", bar) + _SETUP.replace("SETUP", setup).replace("FONTS", fonts) + _AUDIT + _TAIL)


RAMP = scene_html()
RANDOM = scene_html(bar="Math.round(40+200*Math.random())")
FETCH = scene_html(setup="try{await fetch('https://example.invalid/x.png');}catch(e){}")
CSS_ANIM = scene_html(style="@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}} #bar{animation:spin 1s infinite linear}")
FONT_TYPO = scene_html(style='@font-face{font-family:"Body";src:url(fonts/bodyy.woff2) format("woff2")} #label{font-family:"Body"}',
                       setup="await document.fonts.load('400 40px \"Body\"').catch(function(){});",   # a conforming __setup reports, never throws
                       fonts="[{font:'400 40px \"Body\"',ok:document.fonts.check('400 40px \"Body\"')}]")


def put_scene(project: Path, name: str, html: str) -> str:
    d = project / "motion" / "scenes" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html, encoding="utf-8")
    return f"motion/scenes/{name}"


def tool(project, arguments, vault=None, capture=None):
    text, is_error = asyncio.run(MT.call(vault, project, "lampway_motion_graphics", arguments, capture=capture))
    return json.loads(text), is_error


def a_vault(tmp_path):
    from lampway_server.library.store import AssetLibrary
    return Vault(tmp_path / "state", library=AssetLibrary(tmp_path / "state" / "library"))


def rows(out_dir: Path) -> list:
    return [l.split() for l in (out_dir / "frames.sha256").read_text().splitlines() if l.strip()]


# 12
def test_capture_fake_drives_encode_and_check_without_a_browser(tmp_path, monkeypatch):
    monkeypatch.delenv("LAMPWAY_CHROMIUM", raising=False)
    project = tmp_path / "project"
    scene = put_scene(project, "fake-ramp", "<!doctype html><title>fake</title>")
    cap = FakeCapture(duration_s=1.0)
    res = M.render(project, {"scene": scene, **SMALL}, cap)
    out = project / res["out_dir"]
    assert cap.opened and cap.closed and res["frames"] == 10 and res["out_dir"].startswith("motion/out/fake-ramp-")
    assert {p.name for p in out.iterdir()} >= {"fake-ramp.mp4", "fake-ramp.webm", "receipt.json", "frames.sha256", "contact.png", "samples"}
    r = json.loads((out / "receipt.json").read_text())
    assert r["engine"]["chromium"] == "FakeChrome/1.0" and len(rows(out)) == 10 and r["frames_sha256_digest"] == res["frames_sha256_digest"]
    assert r["frames_sha256_digest"] == hashlib.sha256((out / "frames.sha256").read_bytes()).hexdigest()
    mp4 = r["outputs"]["mp4"]["probe"]["stream"]
    assert (mp4["codec_name"], mp4["profile"], mp4["pix_fmt"], mp4["color_space"], mp4["nb_frames"]) == ("h264", "High", "yuv420p", "bt709", "10")
    assert r["outputs"]["webm"]["probe"]["stream"]["codec_name"] == "vp9"
    assert sorted(p.name for p in (out / "samples").glob("*.png")) == [f"f{i:04d}.png" for i in range(10)]   # 10 frames: every one sampled
    assert {"fail", "warn", "findings"} <= set(res["self_check"]) and res["ok"] is True


# 2
def test_mp4_bytes_depend_on_thread_count_so_receipt_pins_it(tmp_path):
    cap = FakeCapture(duration_s=1.0)
    cap.open(None, 640, 360)
    pngs = [cap.frame(i / 40) for i in range(40)]               # 40 frames: at 10, x264 measured the same bytes for 2 and 4 threads
    got = {}
    for threads in (2, 4):
        paths = {"mp4": tmp_path / f"t{threads}.mp4", "webm": tmp_path / f"t{threads}.webm"}
        enc = E.Encoder(E.argv(paths, 30, threads))
        for p in pngs:
            enc.write(p)
        enc.finish()
        got[threads] = {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in paths.items()}
    assert got[2]["mp4"] != got[4]["mp4"], "x264's output depends on its thread count (measured on the teaser): the pin is load-bearing"
    project = tmp_path / "project"
    res = M.render(project, {"scene": put_scene(project, "pin", "<!doctype html>"), **SMALL}, FakeCapture())
    enc = json.loads((project / res["out_dir"] / "receipt.json").read_text())["engine"]["encoder"]
    assert enc["threads"] == 4 and enc["args"].count("-threads") >= 1 and all(enc["args"][i + 1] == "4" for i, a in enumerate(enc["args"]) if a == "-threads")


# 8
def test_out_of_order_render_is_not_offered(tmp_path):
    spec = next(t for t in TOOLS if t.name == "lampway_motion_graphics")
    assert set(spec.parameters["properties"]) == {"action", "scene", "html", "entry", "name", "duration_s", "fps", "width", "height", "formats", "samples",
                                                  "template", "variables", "vault", "receipt"}
    assert spec.parameters["additionalProperties"] is False
    project = tmp_path / "project"
    out, is_error = tool(project, {"scene": put_scene(project, "x", RAMP), "frame_range": [100, 200]}, capture=FakeCapture())
    assert is_error and "frame_range" in out["error"] and "in order from frame 0" in out["error"]


def test_the_tool_is_registered_and_runs_on_the_server():
    assert "lampway_motion_graphics" in TOOL_NAMES and "lampway_motion_graphics" in MT.NAMES
    with pytest.raises(UnknownTool, match="runs on the server"):
        script_for("lampway_motion_graphics", {})


@pytest.mark.parametrize("args, message", [
    ({"fps": 90}, "fps 90 out of range 1..60: pass fps between 1 and 60"),
    ({"width": 1919}, "size 1919x1080: width and height must be even, 16..3840 x 16..2160"),
    ({"duration_s": 300}, "duration 300 s out of range (0, 120]: split the video or shorten the scene"),
    ({"scene": "../outside"}, "../outside is outside the project root"),
    ({"scene": "motion/scenes/x", "entry": "nope.html"}, "no scene entry nope.html in motion/scenes/x: pass entry"),
])
def test_refusals_name_their_fix(tmp_path, args, message):
    project = tmp_path / "project"
    put_scene(project, "x", RAMP)
    out, is_error = tool(project, {"scene": "motion/scenes/x", **args}, capture=FakeCapture())
    assert is_error and out["ok"] is False and out["error"] == message, out


def test_no_chromium_and_no_ffmpeg_are_refused_with_their_fix(tmp_path, monkeypatch):
    project = tmp_path / "project"
    put_scene(project, "x", RAMP)
    monkeypatch.delenv("LAMPWAY_CHROMIUM", raising=False)
    out, is_error = tool(project, {"scene": "motion/scenes/x"})
    assert is_error and out["error"] == "no headless Chromium: set LAMPWAY_CHROMIUM to a chrome-headless-shell binary"
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    out, is_error = tool(project, {"scene": "motion/scenes/x"}, capture=FakeCapture())
    assert is_error and out["error"] == "ffmpeg not found on PATH: install ffmpeg"


def test_a_scene_without_frame_and_a_page_resize_are_refused(tmp_path):
    project = tmp_path / "project"
    scene = put_scene(project, "x", RAMP)
    out, _e = tool(project, {"scene": scene, **SMALL}, capture=FakeCapture(has_frame=False))
    assert out["error"] == "the scene does not define window.__frame: see the scene contract in motion_graphics.md section 4"
    out, _e = tool(project, {"scene": scene, **SMALL}, capture=FakeCapture(size=(320, 200)))
    assert out["error"] == "frame 0 is 320x200, not 320x180: the scene must not resize the page"


# 9
def test_receipt_has_no_home_paths_and_outputs_have_no_metadata(tmp_path):
    project = tmp_path / "project"
    res = M.render(project, {"scene": put_scene(project, "clean", "<!doctype html>"), **SMALL}, FakeCapture())
    out = project / res["out_dir"]
    text = (out / "receipt.json").read_text()
    assert str(tmp_path) not in text and str(Path.home()) not in text
    gate = subprocess.run([sys.executable, str(REPO / "scripts/lampway/prepublish_gate.py"), "--tree", str(out), "--media", str(out)],
                          capture_output=True, text=True)
    assert gate.returncode == 0 and "[tree] 0 finding(s)" in gate.stdout and "[media] 0 finding(s)" in gate.stdout, gate.stdout


# 10
def test_vault_filing_links_variant_and_receipt(tmp_path):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    out, is_error = tool(project, {"scene": put_scene(project, "filed", "<!doctype html>"), **SMALL, "template": "mg-site-clip@1.0.0"}, vault=vault,
                         capture=FakeCapture())
    assert not is_error and out["ok"] and out["vault"]["spooled"] is False, out
    lib = vault.lib
    by_kind = {}
    for a in out["vault"]["assets"]:
        rec = lib.get(a["id"])
        by_kind.setdefault((rec["kind"], rec["subtype"]), []).append(rec)
    mp4 = next(r for r in by_kind[("video", "render")] if r["name"].endswith("mp4") or r["files"][0]["mime"] == "video/mp4")
    rel = {(x["type"], x["src"], x["dst"]) for x in lib._reader().execute("SELECT type,src,dst FROM relation").fetchall()}
    webm = next(a["id"] for a in out["vault"]["assets"] if a["format"] == "webm")
    receipt = next(r["id"] for (k, s), rs in by_kind.items() for r in rs if k == "receipt" and s == "qa")
    contact = next(r["id"] for (k, s), rs in by_kind.items() for r in rs if k == "image" and s == "strip")
    assert ("variant_of", webm, mp4["id"]) in rel and ("derived_from", receipt, mp4["id"]) in rel and ("derived_from", contact, mp4["id"]) in rel
    g = mp4["generation"][0]
    assert (g["studio"], g["provider"], g["action"], g["cost_basis"], g["template_id"], g["template_version"]) == \
        ("lampway", "local", "motion_graphics", "none", "mg-site-clip", "1.0.0")
    assert json.loads(g["params_json"])["params"]["code_sha256"] == out["code_sha256"] and g["job_id"] == out["run_id"] and g["prompt_text"]
    assert P.audit(lib)["incomplete"] == []


def test_a_failing_self_check_writes_the_files_and_files_nothing(tmp_path):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    tiny = {"text": [{"sel": "#t", "text": "tiny", "opacity": 1, "font_px": 12, "color": "rgb(255,255,255)", "box": [40, 40, 80, 52]}], "marks": []}
    out, is_error = tool(project, {"scene": put_scene(project, "tiny", "<!doctype html>"), **SMALL}, vault=vault, capture=FakeCapture(audit=tiny))
    assert out["ok"] is False and out["self_check"]["fail"] > 0 and (project / out["out_dir"] / "contact.png").is_file()
    assert out["vault"] == {"assets": [], "spooled": False, "filed": False}
    assert lib_count(vault) == 0


def lib_count(vault):
    return vault.lib._reader().execute("SELECT count(*) FROM asset").fetchone()[0]


# 3
@needs_chromium
def test_random_scene_fails_the_determinism_probe(tmp_path):
    project = tmp_path / "project"
    out, _e = tool(project, {"scene": put_scene(project, "flicker", RANDOM), **SMALL})
    assert out["ok"] is False
    probe = [f for f in out["self_check"]["findings"] if f["check"] == "determinism"]
    assert probe and probe[0]["severity"] == "fail" and "the scene is not a pure function of t" in probe[0]["detail"], out["self_check"]


@needs_chromium
def test_a_pure_scene_passes_the_determinism_probe(tmp_path):
    project = tmp_path / "project"
    out, is_error = tool(project, {"scene": put_scene(project, "ramp", RAMP), **SMALL})
    assert not is_error and out["ok"] is True and out["self_check"]["fail"] == 0, out
    assert out["network"] == {"requests": 1, "non_file": []}


# 4
@needs_chromium
def test_network_request_fails_the_render_and_is_listed(tmp_path):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    out, is_error = tool(project, {"scene": put_scene(project, "fetcher", FETCH), **SMALL}, vault=vault)
    assert is_error and out["ok"] is False and out["error"] == "the scene asked for https://example.invalid/x.png: every file must be in the scene folder"
    r = json.loads((project / out["out_dir"] / "receipt.json").read_text())
    assert r["network"]["non_file"] == ["https://example.invalid/x.png"] and lib_count(vault) == 0


# 5
@needs_chromium
def test_css_animation_is_refused_before_capture(tmp_path):
    project = tmp_path / "project"
    out, is_error = tool(project, {"scene": put_scene(project, "spin", CSS_ANIM), **SMALL})
    assert is_error and out["error"] == "the scene runs CSS animations or transitions (document.getAnimations() is not empty): drive them from __frame(t)"
    assert not (project / "motion" / "out").exists()


# 6
@needs_chromium
def test_setup_miss_is_refused_with_the_missing_file(tmp_path):
    project = tmp_path / "project"
    out, is_error = tool(project, {"scene": put_scene(project, "typo", FONT_TYPO), **SMALL})
    assert is_error and out["error"].startswith("scene not ready, these did not load: ") and '400 40px "Body"' in out["error"]
    assert out["error"].endswith(": put them in the scene folder and check the paths")


# 11
@needs_chromium
def test_verify_reproduces_and_detects_an_engine_change(tmp_path):
    project = tmp_path / "project"
    out, is_error = tool(project, {"scene": put_scene(project, "ramp", RAMP), **SMALL})
    assert not is_error, out
    receipt = f"{out['out_dir']}/receipt.json"
    v, is_error = tool(project, {"action": "verify", "receipt": receipt})
    assert not is_error and v == {**v, "reproduced": True, "frames_differing": [], "mp4_equal": True, "webm_equal": True, "engine_matches": True}, v
    path = project / receipt
    r = json.loads(path.read_text())
    real = r["engine"]["chromium"]
    r["engine"]["chromium"] = "HeadlessChrome/1.0.0.0"
    path.write_text(json.dumps(r))
    v, is_error = tool(project, {"action": "verify", "receipt": receipt})
    assert v["reproduced"] is False and v["engine_matches"] is False and v["frames_differing"] == []
    assert v["error"] == f"cannot reproduce: the engine differs (receipt: HeadlessChrome/1.0.0.0, here: {real})"


def _teaser_copy(project: Path, name="teaser") -> str:
    shutil.copytree(TEASER, project / "motion" / "scenes" / name)
    return f"motion/scenes/{name}"


# 1
@needs_chromium
@needs_teaser
@pytest.mark.timeout(1200)                       # two full renders of the 13 s teaser: about 100 s each when the box is quiet
def test_same_scene_twice_gives_identical_frames_and_files(tmp_path):
    project = tmp_path / "project"
    scene = _teaser_copy(project)
    a, _e = tool(project, {"scene": scene, "entry": "teaser.html"})
    assert a["code_sha256"] == TEASER_CODE and a["frames"] == 390
    keep = project / "first"
    shutil.move(str(project / a["out_dir"]), keep)
    b, _e = tool(project, {"scene": scene, "entry": "teaser.html"})
    assert rows(keep) == rows(project / b["out_dir"]) and a["frames_sha256_digest"] == b["frames_sha256_digest"] == TEASER_FRAMES
    assert a["outputs"] == b["outputs"]


# 7
@needs_chromium
@needs_teaser
@pytest.mark.timeout(600)
def test_self_check_finds_the_spike_defects(tmp_path):
    project = tmp_path / "project"
    scene = _teaser_copy(project, "inset-auto")
    html = project / scene / "teaser.html"
    t = html.read_text()
    for good, bad in (("#hero{inset:auto;left:150px;top:250px;", "#hero{left:150px;top:250px;inset:auto;"),
                      ("#fig{inset:auto;left:1250px;top:96px;", "#fig{left:1250px;top:96px;inset:auto;")):
        assert t.count(good) == 1
        t = t.replace(good, bad)
    html.write_text(t)
    out, _e = tool(project, {"scene": scene, "entry": "teaser.html", "duration_s": 6.0, "samples": [4.0, 5.4]})
    checks = {f["check"] for f in out["self_check"]["findings"] if f["severity"] == "fail"}
    assert out["ok"] is False and {"crop", "overlap"} <= checks, out["self_check"]
    scene = _teaser_copy(project, "dark-first")
    js = project / scene / "teaser.js"
    t = js.read_text()
    good = "const a = -0.15 + i * 0.22;"
    assert t.count(good) == 1
    js.write_text(t.replace(good, "const a = 0 + i * 0.22;"))
    out, _e = tool(project, {"scene": scene, "entry": "teaser.html", "duration_s": 0.5, "samples": [0.0]})
    empty = [f for f in out["self_check"]["findings"] if f["check"] == "empty"]
    assert out["ok"] is False and empty and empty[0]["frame"] == 0 and empty[0]["severity"] == "fail", out["self_check"]


def test_an_agent_turn_runs_the_tool_on_the_server():
    from lampway_server.agent.providers.base import ToolCall
    from lampway_server.agent.turns import AgentHub, Session, Turn
    hub = AgentHub(None)
    call = ToolCall(id="c1", name="lampway_motion_graphics", arguments={"scene": "motion/scenes/x", "fps": 90})
    text, is_error = asyncio.run(hub._run_tool(None, Session("s"), Turn("s", "t", "r"), call))
    assert is_error and json.loads(text)["error"] == "fps 90 out of range 1..60: pass fps between 1 and 60", text
