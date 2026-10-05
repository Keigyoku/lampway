"""The job queue and the generation catalog: what Mixar's generation surfaces run on.

The client (audit/protocol.json, job_queue.* and generation_catalog) hides every generation tab until the catalog lists a
capability, submits work as ``POST /api/v1/job-queue/jobs {service, model, payload, idempotency_key}``, learns of state
changes by a compact ``job.update`` push over the agent socket, fetches the finished snapshot with ``job.get`` (or
``job.sync`` after a reconnect), and downloads ``result.images[].url`` with plain urllib. So:

  * a service is advertised only when a BACKEND exists for it (``job_backends`` at create_app); none -> an empty
    catalog, which is the client's own kill switch;
  * a backend is a plain callable ``(model, payload) -> ImageOutput`` run off the event loop; today there is one,
    ``imagegen.openrouter_image_backend`` (OpenRouter's images API, on the session spend ledger);
  * result files are kept in memory per job and served at an unguessable per-job URL (``/api/v1/jobs/files/<token>/
    <name>``) without a bearer, because the client's downloader sends none.
"""

import asyncio
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

CAPABILITY_LABELS = {"image_gen": "Image generation"}
IMAGE_PARAMETERS = {
    "number_of_images": {"type": "integer", "label": "Images", "description": "How many images to generate (one request each)",
                         "default": 1, "min": 1, "max": 4, "visible": True, "order": 1},
}
MAX_REFERENCE_IMAGES = 4
_KEEP_TERMINAL = 64


class UnknownService(ValueError):
    pass


class BadJob(ValueError):
    pass


@dataclass
class ImageOutput:
    images: list                      # [(bytes, media_type)]
    image_name: str = ""


log = logging.getLogger("lampway.jobs")


@dataclass
class Job:
    job_id: str
    service: str
    model: str
    payload: dict
    idempotency_key: str
    origin: str = "user"
    status: str = "PENDING"           # PENDING | POLLING | DONE | FAILED | CANCELLED
    result: Optional[dict] = None
    error: str = ""
    created: float = field(default_factory=time.time)
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    files: dict = field(default_factory=dict)
    task: Optional[asyncio.Task] = None
    note: str = ""                    # what the job is waiting for (shown to the user while PENDING)
    awaiting: str = ""                # the approval id the job waits on
    decision: Optional[asyncio.Future] = None


_STATE = {"PENDING": "pending", "POLLING": "running", "DONE": "succeeded", "FAILED": "failed", "CANCELLED": "cancelled"}
_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class JobQueue:
    def __init__(self, backends: dict, hub, base_url: str, model_labels: Optional[dict] = None, video=None, approvals=None):
        self.video = video                # videojobs.VideoSystem: video_gen / video_upscale and Higgsfield models
        self.approvals = approvals        # studios.approvals.Approvals: the captain's confirm gate (shared with the Studios)
        self.backends: dict[str, Callable] = dict(backends or {})
        self.hub = hub
        self.base_url = base_url.rstrip("/")
        self.model_labels = model_labels or {}
        self.jobs: dict[str, Job] = {}
        self._by_key: dict[str, str] = {}

    # ----------------------------------------------------------------- catalog
    def catalog(self) -> dict:
        capabilities = []
        if "image_gen" in self.backends:
            label = self.model_labels.get("image_gen", "default")
            capabilities.append({
                "key": "image_gen", "label": CAPABILITY_LABELS["image_gen"], "sort_order": 1,
                "services": [{"key": "image_gen", "surface": "moodboard", "sort_order": 1, "models": [{
                    "slug": "default", "label": label, "is_default": True,
                    "max_reference_images": MAX_REFERENCE_IMAGES, "parameters": dict(IMAGE_PARAMETERS)}]}]})
        if self.video is not None:
            extra_images = self.video.image_models()
            if extra_images:
                if not capabilities:
                    capabilities.append({"key": "image_gen", "label": CAPABILITY_LABELS["image_gen"], "sort_order": 1,
                                         "services": [{"key": "image_gen", "surface": "moodboard", "sort_order": 1, "models": []}]})
                capabilities[0]["services"][0]["models"].extend(extra_images)
            capabilities.extend(self.video.capabilities())
        return {"capabilities": capabilities, "styles": {}, "credit_costs": {}}

    def chat_options(self) -> list:
        return [{"service_key": "image_gen", "label": "Image", "display_label": "Generate an image", "default_model": "default",
                 "models": [{"slug": "default", "label": self.model_labels.get("image_gen", "default")}]}] \
            if "image_gen" in self.backends else []

    # ------------------------------------------------------------------ submit
    def submit(self, service: str, model: str, payload: dict, idempotency_key: Optional[str] = None, origin: str = "user") -> Job:
        video_job = self.video is not None and self.video.handles(service, model)
        if service not in self.backends and not (video_job and (service in ("video_gen", "video_upscale") and self.video.available(service) or service == "image_gen")):
            raise UnknownService(f"no backend for service {service!r}; the services are {sorted(self.backends) or 'none'}")
        payload = payload if isinstance(payload, dict) else {}
        if service in ("image_gen", "video_gen") and not str(payload.get("prompt") or "").strip():
            raise BadJob(f"{service} needs payload.prompt")
        if service == "video_upscale" and not payload.get("video_s3_key"):
            raise BadJob("video_upscale needs payload.video_s3_key (stage the source clip first)")
        key = idempotency_key or str(uuid.uuid4())
        if key in self._by_key:
            return self.jobs[self._by_key[key]]
        job = Job(str(uuid.uuid4()), service, model or "default", payload, key, origin)
        self.jobs[job.job_id] = job
        self._by_key[key] = job.job_id
        self._prune()
        job.task = asyncio.get_running_loop().create_task(self.run(job))
        return job

    def _prune(self) -> None:
        terminal = [j for j in self.jobs.values() if j.status in ("DONE", "FAILED", "CANCELLED")]
        for old in sorted(terminal, key=lambda j: j.created)[:-_KEEP_TERMINAL] if len(terminal) > _KEEP_TERMINAL else []:
            self.jobs.pop(old.job_id, None)
            self._by_key.pop(old.idempotency_key, None)

    # ------------------------------------------------------------------ the confirm gate
    async def _await_approval(self, job: Job, approval) -> object:
        """The job waits (PENDING, with a note) for the captain's click on ``approval``; returns his answer (True/False or the
        answer to a question), or raises on expiry."""
        loop = asyncio.get_running_loop()
        job.awaiting, job.decision = approval.id, loop.create_future()
        job.status = "PENDING"
        await self.push(job)
        try:
            return await asyncio.wait_for(job.decision, timeout=max(1.0, approval.expires - approval.created))
        except asyncio.TimeoutError:
            raise RuntimeError("the confirmation expired: submit the job again so the price is read back fresh") from None
        finally:
            job.awaiting, job.decision = "", None

    def resolve_approval(self, approval_id: str, confirmed: bool, answer=None) -> bool:
        """Called by the Studio service when the captain confirms or rejects an approval a job waits on."""
        for job in self.jobs.values():
            if job.awaiting == approval_id and job.decision is not None and not job.decision.done():
                job.decision.get_loop().call_soon_threadsafe(job.decision.set_result, (answer if answer is not None else confirmed) if confirmed else False)
                return True
        return False

    async def _run_video(self, job: Job):
        plan = await asyncio.to_thread(self.video.plan, job.service, job.model, job.payload)
        if plan["provider"] == "higgsfield":
            job.note = f"Waiting for your confirmation: {plan['credits']:g} credits on Higgsfield. Confirm it in the Studios panel."
            a = self.approvals.propose(action="higgsfield.job", studio="higgsfield", label=plan["label"], args={"job_id": job.job_id},
                                       price=plan["credits"], requested_by=job.origin,
                                       settings={"unit": "credits", "model": plan["model"], "tool": plan["tool"], "service": job.service})
            if not await self._await_approval(job, a):
                job.status = "CANCELLED"
                job.note = "Rejected."
                await self.push(job)
                return None
            job.note = ""
        job.status = "POLLING"
        await self.push(job)
        loop = asyncio.get_running_loop()

        def ask(question: dict):
            q = self.approvals.propose(action="higgsfield.question", studio="higgsfield", label="Higgsfield asks: " + str(question.get("question", ""))[:120],
                                       args={"job_id": job.job_id}, price=0, requested_by=job.origin,
                                       settings={"unit": "answer", "question": question.get("question"), "options": question.get("options")})
            job.note = "Higgsfield asks you a question: answer it in the Studios panel."
            return asyncio.run_coroutine_threadsafe(self._await_approval(job, q), loop).result()
        return await asyncio.to_thread(self.video.run, job.service, job.model, job.payload, plan, ask)

    async def run(self, job: Job) -> None:
        job.status = "POLLING"
        await self.push(job)
        try:
            if self.video is not None and self.video.handles(job.service, job.model):
                out = await self._run_video(job)
                if out is None:
                    return
            else:
                out = await asyncio.to_thread(self.backends[job.service], job.model, job.payload)
            if job.status == "CANCELLED":
                return
            if hasattr(out, "files"):                              # a video (or a Higgsfield image): result_files, saved into the project
                job.note = ""
                paths = await asyncio.to_thread(self.video.save_to_project, job.job_id, out)
                kind = "VIDEO" if job.service != "image_gen" else "IMAGE"
                files = []
                for i, (data, media_type) in enumerate(out.files, 1):
                    name = f"{i}.{'mp4' if kind == 'VIDEO' else 'png'}"
                    job.files[name] = (data, media_type)
                    files.append({"type": kind, "url": f"{self.base_url}/api/v1/jobs/files/{job.token}/{name}"})
                job.result = {"result_files": files, "saved": paths, **out.extra}
                if job.service == "image_gen":
                    job.result["images"] = [{"url": f["url"]} for f in files]
                job.status = "DONE"
                await self.push(job)
                return
            images = []
            for i, (data, media_type) in enumerate(out.images, 1):
                name = f"{i}.{_EXT.get(media_type, 'png')}"
                job.files[name] = (data, media_type)
                images.append({"url": f"{self.base_url}/api/v1/jobs/files/{job.token}/{name}"})
            job.result = {"images": images}
            if out.image_name:
                job.result["image_name"] = out.image_name
            job.status = "DONE"
        except asyncio.CancelledError:
            job.status = "CANCELLED"
            raise
        except Exception as exc:  # noqa: BLE001 - the job carries the reason to the client
            job.status = "FAILED"
            job.error = f"{type(exc).__name__}: {exc}"[:600]
        finally:
            job.payload = {}
        await self.push(job)

    # ------------------------------------------------------------------- read
    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def cancel(self, job_id: str) -> Optional[Job]:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        if job.status in ("PENDING", "POLLING"):
            job.status = "CANCELLED"
            if job.task is not None:
                job.task.cancel()
        return job

    def file(self, token: str, name: str):
        for job in self.jobs.values():
            if job.token == token and name in job.files:
                return job.files[name]
        return None

    def snapshot(self, job: Job) -> dict:
        snap = {"job_id": job.job_id, "id": job.job_id, "status": job.status, "state": _STATE[job.status],
                "service": job.service, "model": job.model, "queue_position": 0, "attempts": 1, "created": job.created}
        if job.result is not None:
            snap["result"] = job.result
        if job.note:
            snap["user_message"] = job.note
        if job.error:
            snap["error"] = job.error
            snap["user_message"] = job.error
        return snap

    def snapshots(self) -> list:
        return [self.snapshot(j) for j in sorted(self.jobs.values(), key=lambda j: j.created)]

    async def push(self, job: Job) -> None:
        params = {"job_id": job.job_id, "state": _STATE[job.status], "service": job.service, "model": job.model}
        if job.error:
            params["error"] = job.error
        for socket in list(self.hub.sockets.values()):
            try:
                await socket.notify("job.update", params)
            except Exception:  # noqa: BLE001 - a gone socket learns the state from job.sync on reconnect
                pass
