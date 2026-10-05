"""The agent's video tools: PLAN or generate, never confirm a credit spend. ``lampway_video_gen`` on an OpenRouter model is a dry run that prices the
job (set ``dry_run`` false to run it; it is held to the per-job cap and the session ledger); on a Higgsfield model it submits the job, which then WAITS
for the user's confirmation in the Client - the agent only ever sees ``needs_approval`` with the price read back."""

import asyncio
import json
import time
from pathlib import Path

from ..videojobs import PREFIX
from .providers.base import ToolSpec

NAMES = {"lampway_video_gen", "lampway_video_models", "lampway_video_gate"}


def specs() -> list:
    return [
        ToolSpec("lampway_video_models", "List the video models (OpenRouter's, and Higgsfield's when signed in) with their durations, resolutions and the per-purpose "
                 "defaults (bulk, loop, motion). Prices are in lampway_video_gen's dry run.", {"type": "object", "properties": {}, "additionalProperties": False}),
        ToolSpec("lampway_video_gate", "Deterministic gates on a video file in the project (no model, no spend, ffmpeg only). kind loop: closure_diff and wrap_jump (closed when <= 6 and <= 2.0); fix=pingpong writes a SECOND "
                 "file <name>_loop.mp4 (forward then reversed: closed by construction) and never touches the source. kind clip: the character-clip gates (24 fps all distinct, 720x1280, 5.0 s, figure >= 1000 px not touching "
                 "the border, locked camera, >= 4 strides: unverified without foot_contacts). kind duplicates: held frames and the true motion rate. kind upscale: video vs `source` at `factor` (size, duration, fps, SSIM, a "
                 "'no gain over Lanczos' flag). kind edit: video vs `source` with a region `mask` PNG (outside-mask PSNR >= 35 dB, length within a frame). Thresholds are proposed.",
                 {"type": "object", "properties": {"kind": {"type": "string", "description": "loop | clip | duplicates | upscale | edit"}, "video": {"type": "string", "description": "project-relative path"},
                  "source": {"type": "string"}, "mask": {"type": "string"}, "factor": {"type": "number"}, "fix": {"type": "string", "description": "pingpong"},
                  "foot_contacts": {"type": "array", "items": {"type": "number"}, "description": "frame indices of the foot contacts, from the tracker"}}, "required": ["kind", "video"], "additionalProperties": False}),
        ToolSpec("lampway_video_gen", "Generate a video. Default is a DRY RUN: the validated parameters and the price. `purpose` picks the default model: bulk (HeyGen), "
                 "loop (Seedance 1.5 Pro, first = last frame from one image) motion (Seedance 2.0 Mini with a driving video), edit (FLUX Video Edit: a source video in `videos` and the instruction as the prompt) or upscale (FLUX Video Upscale: one source video, `upscale_factor` 1.5 to 3). OpenRouter models: dry_run=false runs "
                 "within the per-job cap and the session budget and saves an .mp4 in the project. Higgsfield models (model `higgsfield/<id>`; incl. hf_mult_motion_control "
                 "and kling_motion_control): the job is submitted and WAITS for the user's confirmation of the credits in the Client; you cannot confirm it. "
                 "`images` and `videos` are project-relative paths.",
                 {"type": "object", "properties": {
                     "prompt": {"type": "string"}, "model": {"type": "string"}, "purpose": {"type": "string", "description": "bulk | loop | motion | edit | upscale"},
                     "upscale_factor": {"type": "number", "description": "upscale purpose: 1.5 to 3"}, "creativity": {"type": "integer", "description": "upscale purpose: 0 precise, 1 creative"},
                     "duration": {"type": "integer"}, "resolution": {"type": "string"}, "aspect_ratio": {"type": "string"}, "generate_audio": {"type": "boolean"},
                     "image_mode": {"type": "string", "description": "first_frame | first_last_frame (one image = a loop) | reference"},
                     "template": {"type": "string", "description": "a prompt-library template id (e.g. anim-walk-side-track): replaces `prompt`; its defaults fill duration/resolution/aspect"},
                     "variables": {"type": "object", "description": "the template's variables"},
                     "images": {"type": "array", "items": {"type": "string"}}, "videos": {"type": "array", "items": {"type": "string"}},
                     "dry_run": {"type": "boolean", "description": "default true"}}, "additionalProperties": False}),
    ]


def _jail(root: Path, rel: str) -> Path:
    import os
    full = Path(rel) if Path(rel).is_absolute() else root / rel
    real_root, real = Path(os.path.realpath(root)), Path(os.path.realpath(full))
    if real != real_root and real_root not in real.parents:
        raise ValueError(f"{rel} is outside the project root")
    if not real.is_file():
        raise ValueError(f"{rel} is not a file")
    return real


async def call(system, name: str, arguments: dict) -> tuple:
    arguments = arguments if isinstance(arguments, dict) else {}
    try:
        if system is None:
            return "video generation is not available on this server", True
        if name == "lampway_video_gate":
            from .. import videogate as VGT
            root = system.root
            paths = {k: str(_jail(root, arguments[k])) for k in ("video", "source", "mask") if arguments.get(k)}
            result = await asyncio.to_thread(VGT.run_gate, arguments.get("kind"), paths["video"], paths.get("source"), paths.get("mask"), arguments.get("factor"), arguments.get("fix"),
                                              arguments.get("foot_contacts"))
            return json.dumps(result, default=lambda o: o.item() if hasattr(o, "item") else str(o)), False
        if name == "lampway_video_models":
            rows = await asyncio.to_thread(system.video_models)
            return json.dumps({"purposes": system.settings.video_purposes, "per_job_cap_usd": system.settings.video_max_job_usd,
                               "models": [{"slug": m["slug"], "label": m["label"], "parameters": {k: v.get("enum") or v.get("type") for k, v in m["parameters"].items()}}
                                          for m in rows]}), False
        purpose = system.settings.video_purposes.get(arguments.get("purpose") or "bulk")
        if purpose is None:
            return f"unknown purpose {arguments.get('purpose')!r}; the purposes are {sorted(system.settings.video_purposes)}", True
        rendered = None
        if arguments.get("template"):
            rendered = system.prompts.render(arguments["template"], arguments.get("variables"), arguments.get("model"))
            purpose = {**purpose, **{k: v for k, v in rendered["params"].items() if k in ("model", "duration", "resolution", "aspect_ratio", "image_mode")}}
            arguments = dict(arguments, prompt=rendered["prompt"])
        elif not str(arguments.get("prompt") or "").strip():
            return "give a prompt or a template", True
        model = arguments.get("model") or purpose["model"]
        params = {k: arguments.get(k) if arguments.get(k) is not None else purpose.get(k) for k in ("duration", "resolution", "aspect_ratio", "image_mode")}
        for key in ("upscale_factor", "creativity"):
            if arguments.get(key) is not None:
                params[key] = arguments[key]
        if arguments.get("generate_audio") is not None:
            params["generate_audio"] = bool(arguments["generate_audio"])
        params = {k: v for k, v in params.items() if v is not None}
        payload = {"prompt": arguments.get("prompt") or "", "params": params}
        root = system.root
        imgs = [system.uploads.put("image", _jail(root, p).read_bytes(), Path(p).name)["s3_key"] for p in arguments.get("images") or []]
        vids = [system.uploads.put("video", _jail(root, p).read_bytes(), Path(p).name)["s3_key"] for p in arguments.get("videos") or []]
        if imgs:
            payload["reference_image_s3_keys"] = imgs
        if vids:
            payload["reference_video_s3_keys"] = vids
        if model.startswith(PREFIX):
            job = system.jobs.submit("video_gen", model, payload, None, "agent")
            for _ in range(600):                                   # the plan (uploads + get_cost) takes a moment; then the job waits for the user
                if job.awaiting or job.status in ("FAILED", "CANCELLED", "DONE"):
                    break
                await asyncio.sleep(0.05)
            if job.status == "FAILED":
                return f"the plan failed: {job.error}", True
            ap = next((a for a in system.jobs.approvals.all() if a.args.get("job_id") == job.job_id and a.state == "pending"), None)
            return json.dumps({"state": "needs_approval", "job_id": job.job_id, "credits": ap.price if ap else None, "model": model,
                               "message": "The job is waiting for the user's confirmation of the credits in the Client (Studios panel). It cannot be confirmed from here."}), False
        plan = await asyncio.to_thread(system.plan, "video_gen", model, payload)
        info = plan["plan"]
        if rendered:
            info = dict(info, prompt=rendered["prompt"], template=rendered["template"], variables=rendered["variables"], warnings=rendered["warnings"])
        if arguments.get("dry_run", True) is not False:
            return json.dumps(info), not info.get("ok", False)
        if not info.get("ok"):
            return json.dumps(info), True
        out = await asyncio.to_thread(system.run, "video_gen", model, payload, plan)
        paths = await asyncio.to_thread(system.save_to_project, f"agent-{int(time.time())}", out)
        keep = ("provider", "job_id", "generation_id", "estimate_usd", "actual_usd", "delta_usd", "inputs", "tokens")
        return json.dumps({"video_file": paths[0], **{k: v for k, v in out.extra.items() if k in keep}}), False
    except Exception as exc:  # noqa: BLE001 - reported to the model, never with a token
        return f"{type(exc).__name__}: {exc}", True
