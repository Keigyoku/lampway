# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Motion templates must stop before provider planning, uploads, jobs, or generation."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from lampway_server import choices as CH, imagegen as IG
from lampway_server.agent import image_tools as IT, video_tools as VT
from lampway_server.agent import providers
from lampway_server.config import DEFAULT_VIDEO_PURPOSES
from lampway_server.prompts.library import Library
from lampway_server.prompts.runlog import RunLog
from lampway_server.prompts.render import RenderError
from lampway_server.prompts.service import PromptService
from .test_motion_graphics import MG_TEMPLATES, _value_for


@pytest.fixture
def routes(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    svc = PromptService(Library(builtin_dir=Library().dirs["builtin"], user_dir=tmp_path / "user"), RunLog(tmp_path / "runs.jsonl"))
    seen = []
    actual_render = svc.render
    def render(*args, **kwargs):
        seen.append("render")
        return actual_render(*args, **kwargs)
    monkeypatch.setattr(svc, "render", render)
    def resolve(*args, **kwargs):
        seen.append("choice")
        return SimpleNamespace(model="openai/gpt-image-2.5-flare")
    monkeypatch.setattr(CH, "resolve", resolve)
    monkeypatch.setattr(providers, "spend_ledger", lambda _: seen.append("ledger") or SimpleNamespace(spent=0))
    monkeypatch.setattr(IG, "openrouter_images", lambda *a, **kw: seen.append("image_send") or [(b"synthetic image", "image/png")])
    def upload(*a, **kw):
        seen.append("upload")
        return {"s3_key": "synthetic-key"}
    def plan(service, model, payload):
        seen.append("plan")
        return {"plan": {"ok": True, "model": model, "params": payload["params"]}}
    def submit(*a, **kw):
        seen.append("job")
        return SimpleNamespace(awaiting=True, status="WAITING", job_id="synthetic-job")
    def run(*a, **kw):
        seen.append("video_send")
        return SimpleNamespace(extra={})
    system = SimpleNamespace(prompts=svc, root=tmp_path,
                             settings=SimpleNamespace(video_purposes=DEFAULT_VIDEO_PURPOSES),
                             uploads=SimpleNamespace(put=upload), plan=plan, run=run,
                             jobs=SimpleNamespace(submit=submit, approvals=SimpleNamespace(all=lambda: [])),
                             save_to_project=lambda *a: ["synthetic.mp4"])
    return svc, system, seen


@pytest.mark.parametrize("template", MG_TEMPLATES)
@pytest.mark.parametrize("surface,model", [("image", None), ("image", "openai/gpt-image-2.5-flare"),
                                            ("video", "heygen/heygen-video-1"), ("video", "higgsfield/synthetic")])
@pytest.mark.parametrize("dry_run", [True, False])
def test_motion_template_refuses_before_any_provider_path(routes, template, surface, model, dry_run):
    svc, system, seen = routes
    tpl = svc.library.get(template)
    variables = {k: _value_for(v) for k, v in tpl["variables"].items() if "default" not in v}
    args = {"template": template, "variables": variables, "dry_run": dry_run}
    if model:
        args["model"] = model
    call = IT.call(svc, "lampway_image_gen", args) if surface == "image" else VT.call(system, "lampway_video_gen", args)
    text, error = asyncio.run(call)
    assert error and "motion-graphics" in text and "lampway_motion_graphics" in text, text
    assert seen == [], "motion refusal must precede even template rendering and provider choice"
    assert not svc.runlog.runs()


@pytest.mark.parametrize("dry_run", [True, False])
def test_ordinary_image_template_still_renders_and_generates_at_the_fake_seam(routes, dry_run):
    svc, _, seen = routes
    text, error = asyncio.run(IT.call(svc, "lampway_image_gen", {"template": "seamless-tile", "dry_run": dry_run}))
    assert not error, text
    out = json.loads(text)
    assert out["template"].startswith("seamless-tile@")
    assert "render" in seen and "choice" in seen
    assert ("image_send" in seen) is (not dry_run)


@pytest.mark.parametrize("model", ["heygen/heygen-video-1", "higgsfield/synthetic"])
@pytest.mark.parametrize("dry_run", [True, False])
def test_ordinary_video_template_still_reaches_only_the_fake_provider_seam(routes, model, dry_run):
    _, system, seen = routes
    text, error = asyncio.run(VT.call(system, "lampway_video_gen", {"template": "anim-walk-side-track", "model": model, "dry_run": dry_run}))
    assert not error, text
    assert "render" in seen
    if model.startswith("higgsfield/"):
        assert json.loads(text)["state"] == "needs_approval" and "job" in seen
    else:
        assert "plan" in seen
        assert ("video_send" in seen) is (not dry_run)


@pytest.mark.parametrize("service", ["image_gen", "video_gen"])
def test_motion_payload_refuses_before_render_or_payload_mutation(routes, service):
    svc, _, seen = routes
    payload = {"template": {"id": "mg-site-clip"}, "prompt": "keep", "params": {"duration": 8}}
    before = copy.deepcopy(payload)
    with pytest.raises(RenderError, match="motion-graphics.*lampway_motion_graphics"):
        svc.apply_to_payload(service, "synthetic", payload)
    assert payload == before and seen == []


def test_motion_image_prompt_file_refuses_before_writing(routes, tmp_path, monkeypatch):
    svc, _, _ = routes
    monkeypatch.setattr(Library, "from_env", classmethod(lambda cls: svc.library))
    with pytest.raises(RenderError, match="motion-graphics.*lampway_motion_graphics"):
        IG.render_prompt_file("mg-site-clip", {}, "prompt-output")
    assert not (tmp_path / "prompt-output").exists()


@pytest.mark.parametrize("service,template", [("image_gen", "seamless-tile"), ("video_gen", "anim-walk-side-track")])
def test_ordinary_payload_template_still_fills_prompt_and_params(routes, service, template):
    svc, _, seen = routes
    payload = {"template": {"id": template}, "params": {}}
    rendered = svc.apply_to_payload(service, "synthetic", payload)
    assert payload["prompt"] == rendered["prompt"] and seen == ["render"]
    assert payload["params"]


def test_ordinary_image_prompt_file_is_still_written(routes, tmp_path, monkeypatch):
    svc, _, _ = routes
    monkeypatch.setattr(Library, "from_env", classmethod(lambda cls: svc.library))
    path, rendered = IG.render_prompt_file("seamless-tile", {}, "prompt-output")
    assert (tmp_path / path).read_text() == rendered["prompt"]


def test_actual_video_system_job_prompt_binding_refuses_motion_template(routes, tmp_path):
    from lampway_server.videojobs import VideoSystem
    svc, fake, seen = routes
    system = VideoSystem(fake.settings, None, None, None, root=tmp_path)
    system.jobs = SimpleNamespace(prompts=svc)
    text, error = asyncio.run(VT.call(system, "lampway_video_gen", {"template": "mg-site-clip"}))
    assert error and "motion-graphics" in text and "lampway_motion_graphics" in text, text
    assert seen == []


def test_queued_motion_template_refuses_before_video_catalogue_lookup(routes, tmp_path):
    from lampway_server.jobqueue import BadJob, JobQueue
    from lampway_server.videojobs import VideoSystem
    svc, fake, seen = routes
    def models():
        seen.append("catalogue")
        return [{"id": "synthetic"}]
    video = VideoSystem(fake.settings, SimpleNamespace(models=models), None, None, root=tmp_path)
    queue = JobQueue({}, SimpleNamespace(sockets={}), "http://127.0.0.1:1", video=video, prompts=svc)
    payload = {"template": {"id": "mg-site-clip"}}
    with pytest.raises(BadJob, match="motion-graphics.*lampway_motion_graphics"):
        queue.submit("video_gen", "synthetic", payload)
    assert seen == [] and not queue.jobs
    assert payload == {"template": {"id": "mg-site-clip"}}
