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


_STATE = {"PENDING": "pending", "POLLING": "running", "DONE": "succeeded", "FAILED": "failed", "CANCELLED": "cancelled"}
_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class JobQueue:
    def __init__(self, backends: dict, hub, base_url: str, model_labels: Optional[dict] = None):
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
        return {"capabilities": capabilities, "styles": {}, "credit_costs": {}}

    def chat_options(self) -> list:
        return [{"service_key": "image_gen", "label": "Image", "display_label": "Generate an image", "default_model": "default",
                 "models": [{"slug": "default", "label": self.model_labels.get("image_gen", "default")}]}] \
            if "image_gen" in self.backends else []

    # ------------------------------------------------------------------ submit
    def submit(self, service: str, model: str, payload: dict, idempotency_key: Optional[str] = None, origin: str = "user") -> Job:
        if service not in self.backends:
            raise UnknownService(f"no backend for service {service!r}; the services are {sorted(self.backends) or 'none'}")
        payload = payload if isinstance(payload, dict) else {}
        if service == "image_gen" and not str(payload.get("prompt") or "").strip():
            raise BadJob("image_gen needs payload.prompt")
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

    async def run(self, job: Job) -> None:
        job.status = "POLLING"
        await self.push(job)
        try:
            out = await asyncio.to_thread(self.backends[job.service], job.model, job.payload)
            if job.status == "CANCELLED":
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
