"""Video (and Higgsfield) generation on the job queue: what the client's Video Gen / Video Upscale surfaces run on.

The client (Mixar's, so it is the spec): ``video_gen`` / ``video_upscale`` services with a catalogue row per model (``parameters``,
``input_spec``), media staged first with ``POST /uploads/<image|video>`` -> ``data{s3_key, duration_seconds}``, the job payload carrying
``reference_image_s3_keys`` / ``reference_video_s3_keys`` / ``video_s3_key``, and the result as ``result_files[{type: VIDEO, url}]``.

Two providers, routed by the model slug: OpenRouter's videos API (``videogen``; on the spend ledger with a per-job cap) and Higgsfield
(``higgsfield/<model>``; the owner's own subscription through Lampway's own MCP client). A Higgsfield job is a CREDIT spend: its
price is read back first (get_cost), then the job WAITS for the captain's confirm in the Client (the same gate as the Studios); the
agent and swarm workers can only plan. A server-asked ``unlim_choice`` is a question for the captain, never auto-answered; a transport
timeout is never resubmitted.
"""

import json
import logging
import os
import secrets
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import videogen as VG
from .higgsfield import Higgsfield, HiggsfieldError, _pick_role
from .higgsfield_auth import HiggsfieldAuth

log = logging.getLogger("lampway.video")

PREFIX = "higgsfield/"
VIDEO_SERVICES = ("video_gen", "video_upscale")
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_BYTES = 250 * 1024 * 1024
VIDEO_EXTENSIONS = ["mp4", "mov", "webm", "m4v"]
_KINDS = {"image", "video"}


@dataclass
class VideoOutput:
    files: list                         # [(bytes, media_type)]
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------------- uploads
def probe_video(path: str) -> dict:
    """duration, width, height of a video file (ffprobe)."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                              "-of", "json", path], capture_output=True, text=True, timeout=30)
        data = json.loads(out.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        return {"duration": float((data.get("format") or {}).get("duration") or 0), "width": int(stream.get("width") or 0),
                "height": int(stream.get("height") or 0)}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"duration": 0.0, "width": 0, "height": 0}


class UploadStore:
    """The files the client stages for a job. A key is an unguessable token; nothing here is path-addressable from outside."""

    def __init__(self, root: Path, probe: Callable = probe_video):
        self.root = Path(root)
        self.probe = probe

    def put(self, kind: str, data: bytes, filename: str = "") -> dict:
        if kind not in _KINDS:
            raise ValueError(f"unsupported media kind {kind!r}: image or video")
        if not data:
            raise ValueError("the upload is empty")
        if len(data) > (MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES):
            raise ValueError(f"the {kind} is larger than the {(MAX_IMAGE_BYTES if kind == 'image' else MAX_VIDEO_BYTES) // 1_000_000} MB limit")
        key = f"{kind}-{secrets.token_urlsafe(18)}"
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / key
        path.write_bytes(data)
        out = {"s3_key": key, "size_bytes": len(data)}
        if kind == "video":
            info = self.probe(str(path))
            out.update(duration_seconds=info.get("duration") or 0.0, width=info.get("width"), height=info.get("height"))
        return out

    def path(self, key: str) -> Path:
        if not key or "/" in key or "\\" in key or key.startswith("."):
            raise ValueError("bad media key")
        p = self.root / key
        if not p.is_file():
            raise ValueError(f"unknown media key {key!r}: upload the file again")
        return p

    def get(self, key: str) -> bytes:
        return self.path(key).read_bytes()


# ------------------------------------------------------------------------------------------------ the system
class VideoSystem:
    def __init__(self, settings, client: Optional[VG.VideoClient], higgsfield: Optional[Higgsfield], auth: Optional[HiggsfieldAuth], *,
                 root, probe: Callable = probe_video):
        self.settings = settings
        self.client = client
        self.higgs = higgsfield
        self.auth = auth
        self.root = Path(root)
        self.uploads = UploadStore(self.root / "uploads", probe)
        self.jobs = None                          # set by create_app: the JobQueue this system serves
        self._or_models = None
        self._or_failed_until = 0.0
        self._hf_cache: dict = {}

    # -------------------------------------------------------------------------------------- availability
    def openrouter_ready(self) -> bool:
        if self.client is None:
            return False
        try:
            return bool(self._openrouter_models())
        except Exception:  # noqa: BLE001
            return False

    def higgs_ready(self) -> bool:
        return bool(self.higgs is not None and self.auth is not None and self.auth.status().get("signed_in"))

    def _openrouter_models(self) -> list:
        if self._or_models is None and time.time() >= self._or_failed_until:
            try:
                self._or_models = self.client.models()
            except Exception as exc:  # noqa: BLE001 - no key, no network: the capability stays hidden, retried in a minute
                log.info("the OpenRouter video catalogue is unavailable: %s", type(exc).__name__)
                self._or_failed_until = time.time() + 60
        return self._or_models or []

    def handles(self, service: str, model: str) -> bool:
        if service in VIDEO_SERVICES:
            return True
        return service == "image_gen" and str(model).startswith(PREFIX)

    def available(self, service: str) -> bool:
        if service in VIDEO_SERVICES:
            return self.openrouter_ready() or self.higgs_ready()
        return False

    # -------------------------------------------------------------------------------------------- catalogue
    @staticmethod
    def _enum(values, default, label, order):
        return {"type": "string" if values and isinstance(values[0], str) else "integer", "label": label, "enum": list(values),
                "default": default if default in values else (values[0] if values else default), "visible": True, "order": order}

    def _params_openrouter(self, row: dict, purpose: dict) -> dict:
        p = {}
        if row.get("supported_durations"):
            p["duration"] = self._enum(row["supported_durations"], purpose.get("duration"), "Duration (s)", 1)
        if row.get("supported_resolutions"):
            p["resolution"] = self._enum(row["supported_resolutions"], purpose.get("resolution"), "Resolution", 2)
        if row.get("supported_aspect_ratios"):
            p["aspect_ratio"] = self._enum(row["supported_aspect_ratios"], purpose.get("aspect_ratio"), "Aspect ratio", 3)
        if row.get("generate_audio"):
            p["generate_audio"] = {"type": "boolean", "label": "Generate audio", "default": False, "visible": True, "order": 4}
        modes = ["first_frame", "first_last_frame", "reference"] if row.get("supported_frame_images") else ["reference"]
        p["image_mode"] = self._enum(modes, purpose.get("image_mode"), "Images are", 5)
        if row.get("seed"):
            p["seed"] = {"type": "integer", "label": "Seed", "default": 0, "min": 0, "max": 2147483647, "visible": False, "order": 6}
        return p

    def _params_higgs(self, row: dict) -> dict:
        p = {}
        if row["durations"]:
            p["duration"] = self._enum(row["durations"], None, "Duration (s)", 1)
        if row["resolutions"]:
            p["resolution"] = self._enum(row["resolutions"], None, "Resolution", 2)
        if row["aspect_ratios"]:
            p["aspect_ratio"] = self._enum(row["aspect_ratios"], None, "Aspect ratio", 3)
        modes = [m for m, needs in (("first_frame", "start_image"), ("first_last_frame", "end_image")) if needs in row["roles"]] + ["reference"]
        p["image_mode"] = self._enum(modes, None, "Images are", 5)
        return p

    def _higgs_models(self, kind: str) -> list:
        cached = self._hf_cache.get(kind)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        try:
            rows = self.higgs.models(kind)
        except Exception as exc:  # noqa: BLE001
            log.info("the Higgsfield %s catalogue is unavailable: %s", kind, type(exc).__name__)
            rows = []
        self._hf_cache[kind] = (time.time(), rows)
        return rows

    @staticmethod
    def _input_spec() -> dict:
        return {"inputs": [{"kind": "image", "multiple": True, "max_count": 9, "max_size_mb": 30},
                           {"kind": "video", "multiple": True, "max_count": 1, "max_total_duration_seconds": 30, "max_size_mb": 250,
                            "extensions": VIDEO_EXTENSIONS}], "max_materials": 9}

    def video_models(self) -> list:
        purposes = self.settings.video_purposes
        default = purposes["bulk"]["model"]
        out = []
        for row in self._openrouter_models():
            if VG.is_upscaler(row):
                continue
            purpose = next((p for p in purposes.values() if p.get("model") == row["id"]), purposes["bulk"])
            out.append({"slug": row["id"], "label": row.get("name") or row["id"], "is_default": row["id"] == default, "max_reference_images": 9,
                        "parameters": self._params_openrouter(row, purpose)})
        if self.higgs_ready():
            for row in self._higgs_models("video"):
                out.append({"slug": PREFIX + row["id"], "label": f"{row['name']} (Higgsfield)", "is_default": False, "max_reference_images": 9,
                            "parameters": self._params_higgs(row)})
        if out and not any(m["is_default"] for m in out):
            out[0]["is_default"] = True
        return out

    def upscale_models(self) -> list:
        out = []
        for row in self._openrouter_models():
            if VG.is_upscaler(row):
                span = row["upscale_factor"]
                out.append({"slug": row["id"], "label": row.get("name") or row["id"], "is_default": not out, "max_reference_images": 0, "parameters": {
                    "upscale_factor": {"type": "number", "label": "Upscale factor", "default": 2, "min": span["min"], "max": span["max"], "visible": True, "order": 1},
                    "creativity": {"type": "integer", "label": "Creativity (0 precise, 1 creative)", "enum": [0, 1], "default": 0, "visible": True, "order": 2}}})
        return out

    def image_models(self) -> list:
        out = []
        if self.higgs_ready():
            for row in self._higgs_models("image"):
                p = {"number_of_images": {"type": "integer", "label": "Images", "default": 1, "min": 1, "max": 4, "visible": True, "order": 1}}
                if row["aspect_ratios"]:
                    p["aspect_ratio"] = self._enum(row["aspect_ratios"], None, "Aspect ratio", 2)
                out.append({"slug": PREFIX + row["id"], "label": f"{row['name']} (Higgsfield)", "is_default": False, "max_reference_images": 4, "parameters": p})
        return out

    def capabilities(self) -> list:
        caps = []
        models = self.video_models()
        if models:
            caps.append({"key": "video_gen", "label": "Video generation", "sort_order": 2, "services": [
                {"key": "video_gen", "surface": "moodboard", "sort_order": 1, "models": models, "input_spec": self._input_spec()}]})
        up = self.upscale_models()
        if up:
            caps.append({"key": "video_upscale", "label": "Video upscale", "sort_order": 3, "services": [
                {"key": "video_upscale", "surface": "moodboard", "sort_order": 1, "models": up, "input_spec": {
                    "inputs": [{"kind": "video", "multiple": False, "max_count": 1, "max_total_duration_seconds": 30, "max_size_mb": 250,
                                "extensions": VIDEO_EXTENSIONS}], "max_materials": 0}}]})
        return caps

    # -------------------------------------------------------------------------------------------------- plan
    def _payload_media(self, payload: dict):
        images = [self.uploads.get(k) for k in payload.get("reference_image_s3_keys") or []]
        videos = [self.uploads.get(k) for k in ([payload["video_s3_key"]] if payload.get("video_s3_key") else payload.get("reference_video_s3_keys") or [])]
        return images, videos

    def plan(self, service: str, model: str, payload: dict) -> dict:
        """What the job would do and cost; for Higgsfield also the uploads and the get_cost price (``gated``: the captain confirms)."""
        payload = payload if isinstance(payload, dict) else {}
        params = dict(payload.get("params") or {})
        if str(model).startswith(PREFIX):
            return self._plan_higgsfield(service, model[len(PREFIX):], payload, params)
        if service == "image_gen":
            raise ValueError("image_gen runs through the image backend, not the video system")
        return self._plan_openrouter(service, model, payload, params)

    def _frames(self, params: dict, images: list):
        mode = params.get("image_mode") or "reference"
        if images and mode in ("first_frame", "first_last_frame"):
            frames = [("first_frame", images[0])]
            if mode == "first_last_frame":
                frames.append(("last_frame", images[1] if len(images) > 1 else images[0]))
            return frames, []
        return [], images

    def _plan_openrouter(self, service, model, payload, params) -> dict:
        if self.client is None:
            raise ValueError("no OpenRouter key: video generation needs one (or sign in to Higgsfield)")
        self.client.max_job_usd = float(self.settings.video_max_job_usd)
        images, videos = self._payload_media(payload)
        frames, refs = self._frames(params, images)
        source = None
        if service == "video_upscale":
            info = self.uploads.probe(str(self.uploads.path(payload["video_s3_key"])))
            source = {"duration": info["duration"], "source_width": info["width"], "source_height": info["height"],
                      "upscale_factor": params.get("upscale_factor"), "creativity": params.get("creativity", 0)}
        clean = {k: v for k, v in params.items() if k != "image_mode"}
        plan = self.client.plan(model, payload.get("prompt") or "", clean, frame_images=frames, reference_images=refs, reference_videos=videos, source=source)
        return {"provider": "openrouter", "gated": False, "service": service, "model": model, "ok": plan.get("ok", False), "plan": plan,
                "frames": frames, "refs": refs, "videos": videos, "clean": clean, "source": source}

    def _plan_higgsfield(self, service, model_id, payload, params) -> dict:
        if not self.higgs_ready():
            raise ValueError("not signed in to Higgsfield: open /app/higgsfield on this server")
        prompt = payload.get("prompt") or ""
        images, videos = self._payload_media(payload)
        h = self.higgs

        def upload(data, kind, i):
            ctype = "image/png" if kind == "image" else "video/mp4"
            from .imagegen import _sniff_mime
            if kind == "image":
                ctype = _sniff_mime(data)
            return h.upload(data, kind, f"ref{i}.{'png' if kind == 'image' else 'mp4'}", ctype)
        image_ids = [upload(d, "image", i) for i, d in enumerate(images)]
        video_ids = [upload(d, "video", i) for i, d in enumerate(videos)]
        if service == "image_gen":
            tool, args = "generate_image", {"model": model_id, "prompt": prompt, "count": int(params.get("number_of_images") or 1)}
            roles = h.model(model_id, "image")["roles"]
            for k in ("aspect_ratio", "resolution"):
                if params.get(k):
                    args[k] = params[k]
            if image_ids:
                args["medias"] = [{"value": i, "role": _pick_role(roles, "image") or "image_references"} for i in image_ids]
        else:
            tool, args = "generate_video", h.video_args(model_id, prompt, params, images=image_ids, videos=video_ids)
        credits = h.cost(tool, args, literal=bool(params.get("literal") or payload.get("template")))
        return {"provider": "higgsfield", "gated": True, "service": service, "model": model_id, "tool": tool, "args": args, "credits": credits,
                "label": f"Higgsfield {model_id}: {credits:g} credits"}

    # --------------------------------------------------------------------------------------------------- run
    def run(self, service: str, model: str, payload: dict, plan: dict, ask: Optional[Callable] = None):
        if plan["provider"] == "higgsfield":
            return self._run_higgsfield(service, plan, ask)
        return self._run_openrouter(service, model, payload, plan)

    def _run_openrouter(self, service, model, payload, plan) -> VideoOutput:
        if not plan.get("ok"):
            raise VG.VideoError((plan.get("plan") or {}).get("error") or "the request is not valid")
        self.client.max_job_usd = float(self.settings.video_max_job_usd)
        out = self.client.generate(model, payload.get("prompt") or "", plan["clean"], frame_images=plan["frames"] or None, reference_images=plan["refs"] or None,
                                   reference_videos=plan["videos"] or None, source=plan["source"], label="video")
        return VideoOutput([(out["video"], out["media_type"])], {"provider": "openrouter", "job_id": out["job_id"], "generation_id": out["generation_id"],
                                                              "inputs": out["inputs"], "estimate_usd": out["estimate_usd"], "actual_usd": out["actual_usd"],
                                                              "delta_usd": out["delta_usd"], "tokens": out["tokens"], "basis": out["basis"]})

    def _run_higgsfield(self, service, plan, ask):
        h = self.higgs
        args = dict(plan["args"])
        sub = h.submit(plan["tool"], args)
        if sub["question"] is not None:                       # unlim_choice: the CAPTAIN's answer, never ours
            if ask is None:
                raise HiggsfieldError("Higgsfield asks whether to use the unlimited allowance and nobody can answer here")
            args["use_unlim"] = bool(ask(sub["question"]))
            sub = h.submit(plan["tool"], args)
        if not sub["job_ids"]:
            raise HiggsfieldError(f"Higgsfield accepted the request but returned no job id: {str(sub['raw'])[:200]}")
        done = h.wait(sub["job_ids"])
        bad = [d for d in done if d["status"] != "completed" or not d["url"]]
        if bad:
            raise HiggsfieldError(f"Higgsfield job {bad[0]['job_id']} {bad[0]['status']}: {bad[0].get('error') or 'no result'}")
        files = [h.download(d["url"]) for d in done]
        extra = {"provider": "higgsfield", "credits": plan["credits"], "job_ids": sub["job_ids"], "model": plan["model"]}
        if service == "image_gen":
            return VideoOutput([(data, mime or "image/png") for data, mime in files], extra)
        return VideoOutput([(data, mime or "video/mp4") for data, mime in files[:1]], extra)

    def save_to_project(self, job_id: str, out: VideoOutput) -> list:
        """The finished clip(s) as files in the project: <root>/video/<job>.mp4."""
        d = self.root / "video"
        d.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, (data, mime) in enumerate(out.files):
            ext = {"video/webm": "webm", "video/quicktime": "mov", "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "mp4")
            p = d / f"{job_id}{'' if i == 0 else f'-{i + 1}'}.{ext}"
            p.write_bytes(data)
            paths.append(str(p))
        return paths


def build_default(settings, auth: HiggsfieldAuth, root) -> "VideoSystem":
    """The production wiring: OpenRouter's videos API on the shared spend ledger, and Higgsfield through Lampway's own MCP client."""
    from .agent.providers import spend_ledger
    from .higgsfield_mcp import HiggsfieldMCP
    client = VG.VideoClient(ledger=spend_ledger(settings), max_job_usd=float(settings.video_max_job_usd))
    return VideoSystem(settings, client, Higgsfield(HiggsfieldMCP(auth)), auth, root=root)
