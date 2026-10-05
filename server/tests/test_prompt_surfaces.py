"""Every image and video surface takes ``template`` + ``variables`` and stores the rendered prompt: the agent tools (lampway_prompt_*, lampway_image_gen,
lampway_video_gen), the imagegen CLI/module, studio_image_generate and tripo.image, and the Higgsfield image provider through the job queue. A scan proves no
image path keeps a hard-coded prompt string."""

import ast
import asyncio
import base64
import json
import re
from pathlib import Path

import httpx
import pytest

from lampway_server import imagegen as IG
from lampway_server.agent import image_tools as IT
from lampway_server.agent import prompt_tools as PT
from lampway_server.prompts.library import Library
from lampway_server.prompts.runlog import RunLog
from lampway_server.prompts.service import PromptService

PNG = b"\x89PNG\r\n\x1a\n" + b"x"


@pytest.fixture
def svc(tmp_path):
    return PromptService(Library(builtin_dir=Library().dirs["builtin"], user_dir=tmp_path / "u"), RunLog(tmp_path / "runs.jsonl"))


@pytest.fixture
def root(tmp_path, monkeypatch):
    r = tmp_path / "root"
    r.mkdir()
    for n in ("clay.png", "painted.png", "plate.png"):
        (r / n).write_bytes(PNG)
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(r))
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))
    return r


def run(coro):
    return asyncio.run(coro)


def call(system_tools, name, args):
    out, err = run(system_tools(name, args))
    return (json.loads(out) if not err else out), err


# --------------------------------------------------------------------------------- the prompt tools
def test_the_prompt_tools_list_get_render_save_and_rate(svc):
    listing, err = call(lambda n, a: PT.call(svc, n, a), "lampway_prompt_list", {"media": "video"})
    assert not err and "anim-walk-side-track" in [t["id"] for t in listing["templates"]] and all(t["media"] == "video" for t in listing["templates"])
    got, _ = call(lambda n, a: PT.call(svc, n, a), "lampway_prompt_get", {"id": "anim-walk-side-track"})
    assert got["variables"]["cadence_spm"]["max"] == 160
    out, _ = call(lambda n, a: PT.call(svc, n, a), "lampway_prompt_render", {"id": "anim-walk-side-track", "variables": {"cadence_spm": 100}, "model": "bytedance/seedance-2.0-mini"})
    assert "100 steps per minute" in out["prompt"] and "the start image" in out["prompt"]
    bad, err = call(lambda n, a: PT.call(svc, n, a), "lampway_prompt_render", {"id": "anim-walk-side-track", "variables": {"cadence_spm": 5}})
    assert err and "cadence_spm" in bad
    mine = dict(got, version="1.0.1", title="Mine")
    mine.pop("scope", None), mine.pop("versions", None)
    saved, err = call(lambda n, a: PT.call(svc, n, a), "lampway_prompt_save", {"template": mine})
    assert not err and saved["scope"] == "user" and svc.library.get("anim-walk-side-track")["title"] == "Mine"
    svc.runlog.record("j1", prompt="p", template="anim-walk-side-track@1.0.1")
    rated, err = call(lambda n, a: PT.call(svc, n, a), "lampway_prompt_rate", {"job_id": "j1", "rating": 5, "note": "great"})
    assert not err and svc.runlog.runs()[0]["rating"] == 5


def test_no_agent_tool_writes_outside_the_user_scope_or_confirms_anything():
    names = {s.name for s in PT.specs()}
    assert names == {"lampway_prompt_list", "lampway_prompt_get", "lampway_prompt_render", "lampway_prompt_save", "lampway_prompt_rate", "lampway_prompt_stats"}
    save = next(s for s in PT.specs() if s.name == "lampway_prompt_save")
    assert "user" in save.description.lower() and "scope" not in save.parameters["properties"]


# ------------------------------------------------------------------------------- lampway_image_gen
@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "ab12" * 16)
    monkeypatch.setenv("LAMPWAY_OPENROUTER_BUDGET_USD", "5")
    monkeypatch.setattr(IG, "_SUPPORTED", {})
    posts = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(404, json={})
        posts.append(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode(), "media_type": "image/png"}], "usage": {"cost": 0.04}})
    monkeypatch.setattr(IG, "openrouter_transport", httpx.MockTransport(handler))
    return posts


def image_call(svc, args):
    return call(lambda n, a: IT.call(svc, n, a), "lampway_image_gen", args)


def test_image_gen_dry_run_renders_orders_the_references_and_validates_the_size(svc, root, wire):
    out, err = image_call(svc, {"template": "mesh-paint-albedo-front", "references": {"design_plate": "plate.png", "clay_render": "clay.png", "painted_view": "painted.png"}})
    assert not err and out["dry_run"] is True and out["prompt"].startswith("The FIRST image is a grey clay render")
    assert [r["role"] for r in out["references"]] == ["clay_render", "painted_view", "design_plate"] and [r["file"] for r in out["references"]] == ["clay.png", "painted.png", "plate.png"]
    assert out["params"]["size"] == "2880x2880" and wire == []
    miss, err = image_call(svc, {"template": "mesh-paint-albedo-front", "references": {"clay_render": "clay.png"}})
    assert err and "painted_view" in miss
    big, err = image_call(svc, {"template": "seamless-tile", "size": "3840x3840"})
    assert err and "size" in big
    flux, err = image_call(svc, {"template": "seamless-tile", "model": "black-forest-labs/flux-3-image", "size": "2048x2048"})
    assert err and "resolution" in flux


def test_image_gen_live_sends_the_ordered_references_saves_the_file_and_logs_the_rendered_prompt(svc, root, wire):
    out, err = image_call(svc, {"template": "mesh-paint-albedo-front", "references": ["clay.png", "painted.png", "plate.png"], "dry_run": False, "count": 1})
    assert not err and out["files"][0].endswith(".png") and Path(out["files"][0]).exists()
    body = wire[0]
    assert body["prompt"] == out["prompt"] and len(body["input_references"]) == 3 and body["size"] == "2880x2880"
    row = svc.runlog.runs()[-1]
    assert row["prompt"] == out["prompt"] and row["template"] == "mesh-paint-albedo-front@1.0.0" and row["output"] == out["files"][0] and out["job_id"] == row["job_id"]


def test_a_raw_prompt_is_still_logged(svc, root, wire):
    out, err = image_call(svc, {"prompt": "a brass lamp on a plain background", "dry_run": False, "count": 1, "model": "openai/gpt-image-2.5-flare"})
    assert not err and svc.runlog.runs()[-1]["prompt"] == "a brass lamp on a plain background" and svc.runlog.runs()[-1]["template"] is None


# ------------------------------------------------------------------------------- imagegen CLI and studio tools
def test_the_imagegen_module_renders_a_template_and_stores_the_rendered_prompt(root, wire, capsys):
    rc = IG.main(["--backend", "openrouter", "--template", "seamless-tile", "--var", "material=blue linen", "--var", "motif=white dots", "--out", "runs/tile", "--count", "1"])
    out = capsys.readouterr().out
    assert rc == 0
    stored = (root / "runs" / "tile" / "prompt.txt").read_text()
    assert "blue linen with white dots" in stored and stored.startswith("A seamless tileable texture")
    assert "template: seamless-tile@1.0.0" in out
    rc2 = IG.main(["--backend", "openrouter", "--template", "seamless-tile", "--var", "nonsense=1", "--out", "runs/t2"])
    assert rc2 == 1 and "nonsense" in capsys.readouterr().out


def test_studio_image_generate_and_tripo_image_take_a_template(root, wire, monkeypatch, tmp_path):
    from lampway_server.agent import server_tools as ST
    seen = {}
    monkeypatch.setattr(IG, "generate", lambda backend, prompt_file, refs, out_dir, count=4, live=False, size="", aspect_ratio="", purpose="plates": seen.update(
        prompt=Path(ST.jail(prompt_file)).read_text(), refs=list(refs)) or {"backend": backend, "files": [], "dry_run": True, "output": "ok"})
    text, is_err = ST._run_imagegen({"template": "plate-4k-crisper", "variables": {"view": "back"}, "out_dir": "runs/plate", "refs": ["clay.png"]})
    assert not is_err and "the same back orthographic view" in seen["prompt"]
    props = ST.BY_NAME["studio_image_generate"].spec().parameters["properties"]
    assert "template" in props and "variables" in props
    from lampway_server.studios.actions import ACTIONS
    from lampway_server.studios.service import StudioService
    svcs = StudioService(root, lambda argv, env, timeout: (0, "dry_run: verified\n"), shelf=None)
    clean = ACTIONS["tripo.image"].validate({"template": "plate-4k-crisper", "variables": {"view": "front"}, "refs": ["clay.png"], "out_dir": "x"}, svcs.jail)
    assert Path(clean["prompt_file"]).read_text().startswith("Recreate this exact image") and clean["template"] == "plate-4k-crisper@1.0.0"


# ------------------------------------------------------------------------------- video tool
def test_lampway_video_gen_takes_a_template_and_the_plan_shows_the_rendered_prompt(svc, root, monkeypatch):
    from lampway_server.agent import video_tools as VT
    from lampway_server import videogen as VG
    from lampway_server.agent.providers.openrouter import SpendLedger

    models = json.loads((Path(__file__).parent / "fixtures" / "video_models.json").read_text())
    client = VG.VideoClient(ledger=SpendLedger(5.0, root / "s.jsonl"), transport=httpx.MockTransport(lambda r: httpx.Response(200, json=models)), key="k" * 20)

    rootpath = Path(root)

    class System:
        settings = type("S", (), {"video_purposes": __import__("lampway_server.config", fromlist=["x"]).DEFAULT_VIDEO_PURPOSES, "video_max_job_usd": 2.0})()
        uploads = type("U", (), {"put": staticmethod(lambda kind, data, name="": {"s3_key": "k-" + name})})()
        jobs = None
        prompts = svc
        root = rootpath

        def plan(self, service, model, payload):
            return {"plan": client.plan(model, payload["prompt"], payload["params"]), "provider": "openrouter"}
    out, err = run(VT.call(System(), "lampway_video_gen", {"template": "anim-walk-side-track", "variables": {"cadence_spm": 100}, "images": ["clay.png"]}))
    data = json.loads(out)
    assert not err and data["ok"] and "100 steps per minute" in data["prompt"] and data["template"] == "anim-walk-side-track@1.0.0" and data["params"]["resolution"] == "768p"


# ------------------------------------------------------------------- no image path keeps a hard-coded prompt
PATHS = ["lampway_server/imagegen.py", "lampway_server/agent/server_tools.py", "lampway_server/agent/image_tools.py", "lampway_server/studios/actions.py",
         "lampway_server/videojobs.py", "lampway_server/higgsfield.py", "lampway_server/jobqueue.py"]
SOURCE_PHRASES = ["Recreate this exact image", "flat ALBEDO", "seamless tileable", "The FIRST image is", "MetaHuman seen from the front", "Photoreal game-character"]


def test_no_image_path_keeps_a_hard_coded_prompt_string():
    root = Path(__file__).resolve().parents[1]
    for rel in PATHS:
        tree = ast.parse((root / rel).read_text())
        doc_ids = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                   and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc_ids:
                assert not any(p.lower() in n.value.lower() for p in SOURCE_PHRASES), f"{rel}:{n.lineno} keeps prompt wording: {n.value[:60]!r}"
    for py in (root / "lampway_server").rglob("*.py"):
        text = py.read_text()
        for p in SOURCE_PHRASES:
            assert p not in text or py.name in ("prompt_tools.py",), f"{py.name} contains the prompt wording {p!r}: it belongs in a template"
    client = root.parent / "src/scripts/mixar/modules/lampway_tools"
    assert "prompt_meshpaint_v2" not in (client / "meshpaint.py").read_text(), "mesh-paint still reads the prompt .txt files"
    assert not (client / "scripts/texlib/prompts").exists() or not list((client / "scripts/texlib/prompts").glob("prompt_meshpaint*.txt")), "the prompt files were not removed"
