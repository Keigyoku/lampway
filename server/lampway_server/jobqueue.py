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

from . import jobreceipts as JR
from .services import WIRE_KEYS, ServiceRegistry
from .spendpolicy import DEFAULT_SPEND_POLICY, SpendPolicy

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
class FilesOutput:
    """A files-based result (a mesh, a clip, ...): the Client reads ``result.result_files[{type, url}]`` (type GLB | OBJ | FBX | VIDEO | IMAGE)."""
    files: list                       # [(bytes, media_type, name)]
    kind: str = "GLB"
    extra: dict = field(default_factory=dict)


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
    rendered: Optional[dict] = None   # the render of the payload's template (None for a raw prompt)
    rendered_prompt: str = ""         # the prompt text this job was run with: stored with EVERY image or video job
    variant_of: str = ""
    receipt: Optional[dict] = None    # the write-ahead receipt (jobreceipts.py): on disk before the provider is called
    recovered: bool = False           # built from a receipt after a restart, not run in this process


IMAGE_USD_ESTIMATE = 0.07          # about $0.067 per image through OpenRouter (specs/cloud/WORKFLOWS.md C7, measured by the spike); only the click decision uses it, never a charge


_STATE = {"PENDING": "pending", "POLLING": "running", "DONE": "succeeded", "FAILED": "failed", "CANCELLED": "cancelled"}
_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class JobQueue:
    def __init__(self, backends: dict, hub, base_url: str, model_labels: Optional[dict] = None, video=None, approvals=None, prompts=None, registry=None, policy=None,
                 receipts=None, provenance=None):
        self.provenance = provenance      # library.hooks.job_hook: called with (job, ok, provider) as a job ends, before its payload is cleared; it can never fail a job
        self.policy = policy if policy is not None else SpendPolicy(lambda: DEFAULT_SPEND_POLICY)      # per-provider caps and clicks (the Providers dialog)
        self.registry = registry if registry is not None else ServiceRegistry()           # services.py: the Client's other job types
        self.prompts = prompts            # prompts.service.PromptService: templates, rendering, the run log
        self.video = video                # videojobs.VideoSystem: video_gen / video_upscale and Higgsfield models
        self.approvals = approvals        # studios.approvals.Approvals: the user's confirm gate (shared with the Studios)
        self.backends: dict[str, Callable] = dict(backends or {})
        self.hub = hub
        self.base_url = base_url.rstrip("/")
        self.model_labels = model_labels or {}
        self.jobs: dict[str, Job] = {}
        self._by_key: dict[str, str] = {}
        self.receipts = receipts          # jobreceipts.JobReceipts or None: with it, no paid call is sent without a receipt on disk first

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
        capabilities.extend(c for c in self.registry.capabilities() if c["key"] not in {x["key"] for x in capabilities})
        return {"capabilities": capabilities, "styles": {}, "credit_costs": {}}

    def chat_options(self) -> list:
        return [{"service_key": "image_gen", "label": "Image", "display_label": "Generate an image", "default_model": "default",
                 "models": [{"slug": "default", "label": self.model_labels.get("image_gen", "default")}]}] \
            if "image_gen" in self.backends else []

    # ------------------------------------------------------------------ submit
    def submit(self, service: str, model: str, payload: dict, idempotency_key: Optional[str] = None, origin: str = "user") -> Job:
        video_job = self.video is not None and self.video.handles(service, model)
        if service not in self.backends and self.registry.get(service) is None and not (video_job and (service in ("video_gen", "video_upscale") and self.video.available(service) or service == "image_gen")):
            raise UnknownService(f"no backend for service {service!r}; the services are {sorted(set(self.backends) | set(self.registry.keys())) or 'none'}: "
                                 "register a backend (see lampway_job_services) or pick a service from the catalog")
        payload = payload if isinstance(payload, dict) else {}
        rendered = None
        if self.prompts is not None and service in ("image_gen", "video_gen") and payload.get("template"):
            try:
                rendered = self.prompts.apply_to_payload(service, model, payload)
            except ValueError as exc:                                   # RenderError and LibraryError are ValueErrors
                raise BadJob(str(exc)) from None
        if service in ("image_gen", "video_gen") and not str(payload.get("prompt") or "").strip():
            raise BadJob(f"{service} needs payload.prompt or payload.template")
        if service == "video_upscale" and not payload.get("video_s3_key"):
            raise BadJob("video_upscale needs payload.video_s3_key (stage the source clip first)")
        key = idempotency_key or str(uuid.uuid4())
        if key in self._by_key:
            return self.jobs[self._by_key[key]]
        job_id, receipt = str(uuid.uuid4()), None
        if self.receipts is not None:
            try:
                JR.check_rendered({"prompt": payload.get("prompt"), "params": payload.get("params")})
                receipt, created = self.receipts.create(self._provider_of(service, model), model or "default", payload, key, origin, job_id=job_id)
            except JR.ReceiptError as exc:
                raise BadJob(str(exc)) from None
            if not created:                                               # a restart (or a second submitter) met the same key: never a second job
                job = self._adopt(receipt)
                self._by_key[key] = job.job_id
                return job
        job = Job(job_id, service, model or "default", payload, key, origin)
        job.receipt = receipt
        job.rendered, job.rendered_prompt = rendered, str(payload.get("prompt") or "")
        job.variant_of = str((payload.get("template") or {}).get("variant_of") or "") if isinstance(payload.get("template"), dict) else ""
        self.jobs[job.job_id] = job
        self._by_key[key] = job.job_id
        self._prune()
        job.task = asyncio.get_running_loop().create_task(self.run(job))
        return job

    # ------------------------------------------------------------------ receipts
    def _provider_of(self, service: str, model: str) -> str:
        from .videojobs import PREFIX
        if str(model or "").startswith(PREFIX):
            return "higgsfield"
        if self.video is not None and self.video.handles(service, model) and service != "image_gen":
            return "openrouter"
        if service in self.backends:
            return "openrouter"
        return service

    _RECEIPT_STATUS = {"planned": "PENDING", "submission_pending": "POLLING", "submitted": "POLLING", "running": "POLLING", "submission_unknown": "PENDING", "completed": "POLLING",
                       "downloaded": "DONE", "result_saved": "DONE", "provider_error": "FAILED", "cancelled": "CANCELLED", "abandoned": "CANCELLED"}

    def _adopt(self, r: dict) -> Job:
        """A Job built from a receipt: what the Client's queue shows after a restart. Nothing runs; ``recover`` resumes what can be resumed by provider job id."""
        existing = self.jobs.get(r.get("job_id") or "")
        if existing is not None:
            existing.receipt = r
            return existing
        job = Job(r.get("job_id") or str(uuid.uuid4()), "image_gen", r["model"], {}, r["key"], r.get("origin") or "user")
        job.status = self._RECEIPT_STATUS[r["state"]]
        job.recovered, job.receipt = True, r
        job.created = r.get("created_at") or job.created
        if r["state"] == "submission_unknown":
            job.note = "Maybe sent: check the provider's own history, then Acknowledge (it did not run) or Link (paste its job id). It is never resubmitted by itself."
        elif job.status == "FAILED":
            job.error = r.get("error_text") or "the provider reported an error"
        elif job.status == "DONE":
            job.result = {"recovered": True, "outputs": [o["path"] for o in r.get("outputs", [])], "saved": [o["path"] for o in r.get("outputs", [])]}
        self.jobs[job.job_id] = job
        self._by_key[r["key"]] = job.job_id
        return job

    async def recover(self, adapters: Optional[dict] = None) -> dict:
        """At server start: pending receipts become submission_unknown, submitted/running ones resume through the provider's adapter by id, and every receipt comes back as a job."""
        if self.receipts is None:
            return {}
        ad = adapters if adapters is not None else (self.video.receipt_adapters() if self.video is not None and hasattr(self.video, "receipt_adapters") else {})
        out = await asyncio.to_thread(self.receipts.reconcile, ad)
        for r in self.receipts.list():
            if r.get("job_id") and r["job_id"] not in self.jobs:
                self._adopt(r)
            elif r.get("job_id") in self.jobs and self.jobs[r["job_id"]].recovered:
                job = self.jobs[r["job_id"]]
                self.jobs.pop(job.job_id)
                self._adopt(r)
        return out

    async def _guarded(self, job: Job, fn, *args):
        """A provider call behind its receipt: pending BEFORE the call, submitted after; a failure that cannot have reached the provider is a plain error, any other is unknown."""
        r = job.receipt
        if r is None or self.receipts is None:
            return await asyncio.to_thread(fn, *args)
        self.receipts.mark_pending(r)
        try:
            out = await asyncio.to_thread(fn, *args)
        except (JR.NotSent, ValueError) as exc:
            self.receipts.mark_error(r, f"not sent: {exc}", "not_sent")
            raise
        except Exception as exc:  # noqa: BLE001
            self.receipts.mark_unknown(r, type(exc).__name__, str(exc))
            raise
        self.receipts.mark_submitted(r, job.job_id)
        return out

    def _hooks(self, job: Job):
        r = job.receipt
        if r is None or self.receipts is None:
            return None
        store = self.receipts

        class Hooks:
            @staticmethod
            def sending():
                if store._load(store._dir(r["provider"], r["key"]))["state"] == "planned":
                    store.mark_pending(r)

            @staticmethod
            def submitted(provider_job_id, urls=None):
                store.mark_submitted(r, provider_job_id, urls)
        return Hooks

    def _receipt_failed(self, job: Job, exc: BaseException) -> None:
        r = job.receipt
        if r is None or self.receipts is None:
            return
        try:
            state = self.receipts._load(self.receipts._dir(r["provider"], r["key"]))["state"]
            if state == "planned":
                self.receipts.cancel(r, f"nothing was sent: {exc}"[:300])
            elif state == "submission_pending":
                self.receipts.mark_unknown(r, type(exc).__name__, str(exc))
            elif state in ("submitted", "running"):
                job.error = (job.error + " (the provider job may still be running: it resumes by id after a restart and is not resubmitted)")[:600]
        except Exception:  # noqa: BLE001 - the bookkeeping must never mask the job's own error
            log.warning("could not settle the receipt of job %s", job.job_id, exc_info=True)

    def _receipt_done(self, job: Job, paths=(), summary=None) -> None:
        r = job.receipt
        if r is None or self.receipts is None:
            return
        try:
            state = self.receipts._load(self.receipts._dir(r["provider"], r["key"]))["state"]
            if state not in ("submitted", "running"):
                return
            self.receipts.save_result(r, {"job_id": job.job_id, "model": job.model, **(summary or {})})
            self.receipts.attach_outputs(r, paths)
            self.receipts.mark_downloaded(r)
        except Exception:  # noqa: BLE001
            log.warning("could not settle the receipt of job %s", job.job_id, exc_info=True)

    def _prune(self) -> None:
        terminal = [j for j in self.jobs.values() if j.status in ("DONE", "FAILED", "CANCELLED")]
        for old in sorted(terminal, key=lambda j: j.created)[:-_KEEP_TERMINAL] if len(terminal) > _KEEP_TERMINAL else []:
            self.jobs.pop(old.job_id, None)
            self._by_key.pop(old.idempotency_key, None)

    # ------------------------------------------------------------------ the confirm gate
    async def _await_approval(self, job: Job, approval) -> object:
        """The job waits (PENDING, with a note) for the user's click on ``approval``; returns his answer (True/False or the
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
        """Called by the Studio service when the user confirms or rejects an approval a job waits on."""
        for job in self.jobs.values():
            if job.awaiting == approval_id and job.decision is not None and not job.decision.done():
                job.decision.get_loop().call_soon_threadsafe(job.decision.set_result, (answer if answer is not None else confirmed) if confirmed else False)
                return True
        return False

    async def _run_registered(self, job: Job):
        """A registered service: a spend service waits for the user's click on a price first (the backend is not called before it)."""
        svc = self.registry.get(job.service)
        if svc.spend:
            if self.approvals is None:
                raise RuntimeError("this server has no approvals store: a spend service cannot be confirmed")
            price = await asyncio.to_thread(svc.confirm_price, job.payload)
            job.note = f"Needs the user's confirm of {price:g} in the Studios panel before {job.service} runs."
            a = self.approvals.propose(action="service.job", studio=job.service, label=f"{svc.row.get('label') or job.service}: {price:g}",
                                       args={"job_id": job.job_id}, price=price, requested_by=job.origin, settings={"unit": "credits", "service": job.service})
            if not await self._await_approval(job, a):
                job.status = "CANCELLED"
                job.note = "Rejected."
                await self.push(job)
                return None
            job.note = ""
            job.status = "POLLING"
            await self.push(job)
        return await self._guarded(job, svc.backend, job.model, job.payload)

    def service_report(self) -> dict:
        """What this server backs of the Client's job types (read-only; no credentials)."""
        backed = {}
        for key in self.registry.keys():
            s = self.registry.get(key)
            backed[key] = {"key": key, "available": True, "spend": s.spend, "backend": s.backend_name or getattr(s.backend, "__name__", type(s.backend).__name__),
                           "models": [m.get("slug") for m in s.row["models"]]}
        for key in self.backends:
            backed.setdefault(key, {"key": key, "available": True, "spend": False, "backend": "builtin", "models": ["default"]})
        if self.video is not None:
            for cap in self.video.capabilities():
                for s in cap["services"]:
                    backed.setdefault(s["key"], {"key": s["key"], "available": True, "spend": False, "backend": "video", "models": [m["slug"] for m in s["models"]]})
        active = {}
        for j in self.jobs.values():
            if j.status in ("PENDING", "POLLING"):
                active[j.service] = active.get(j.service, 0) + 1
        for key, row in backed.items():
            row["queue_length"] = active.get(key, 0)
        return {"services": [backed[k] for k in sorted(backed)], "unbacked": [k for k in WIRE_KEYS if k not in backed]}

    async def _run_video(self, job: Job):
        plan = await asyncio.to_thread(self.video.plan, job.service, job.model, job.payload)
        provider = plan["provider"]
        higgs = provider == "higgsfield"
        price = plan["credits"] if higgs else (plan.get("plan") or {}).get("estimate_usd")
        if higgs or plan.get("ok"):
            self.policy.check(provider, price)                                            # the per-job and session caps (SpendRefused fails the job before anything is sent)
            if self.policy.needs_click(provider, price):
                if self.approvals is None:
                    raise RuntimeError("this server has no approvals store: a click-gated spend cannot be confirmed")
                unit = "credits" if higgs else "usd"
                what = f"{price:g} {unit}" if price is not None else "an unknown price"
                job.note = f"Waiting for your confirmation: {what} on {provider}. Confirm it in the Studios panel."
                label = plan.get("label") or f"{provider} {job.model}: {what}"
                a = self.approvals.propose(action=f"{provider}.job", studio=provider, label=label, args={"job_id": job.job_id},
                                           price=price if price is not None else 0.0, requested_by=job.origin,
                                           settings={"unit": unit, "model": plan.get("model"), "tool": plan.get("tool"), "service": job.service})
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
        out = await asyncio.to_thread(self.video.run, job.service, job.model, job.payload, plan, ask, self._hooks(job))
        self.policy.record(provider, (out.extra.get("credits") if higgs else out.extra.get("actual_usd")) if hasattr(out, "extra") else price)
        return out

    @staticmethod
    def _prompt_fields(job: Job) -> dict:
        out = {"prompt": job.rendered_prompt}
        if job.rendered:
            out.update(template=job.rendered["template"], variables=job.rendered["variables"])
        return out

    def _log(self, job: Job, ok: bool) -> None:
        if self.prompts is None or job.service not in ("image_gen", "video_gen", "video_upscale"):
            return
        r = job.result or {}
        cost = r.get("actual_usd") if r.get("actual_usd") is not None else r.get("credits")
        out = (r.get("saved") or [None])[0] or ((r.get("images") or [{}])[0].get("url") if r.get("images") else None)
        try:
            self.prompts.record_job(job, job.rendered, output=out, cost=cost, extra={"ok": ok, "error": job.error or None, "provider": r.get("provider")})
        except Exception:  # noqa: BLE001 - the log must never fail a job
            log.warning("could not record the run of job %s", job.job_id, exc_info=True)

    async def run(self, job: Job) -> None:
        job.status = "POLLING"
        await self.push(job)
        try:
            if self.video is not None and self.video.handles(job.service, job.model):
                out = await self._run_video(job)
                if out is None:
                    return
            elif job.service not in self.backends and self.registry.get(job.service) is not None:
                out = await self._run_registered(job)
                if out is None:
                    return
            else:
                est = IMAGE_USD_ESTIMATE * max(1, int(((job.payload or {}).get("params") or {}).get("number_of_images") or 1))      # the model sets the price: an estimate per image (cloud D1 click above $0.25)
                if job.service == "image_gen" and self.policy.needs_click("openrouter", est) and self.approvals is not None:
                    a = self.approvals.propose(action="openrouter.job", studio="openrouter", label=f"Image generation ({job.model}): price set by the model", args={"job_id": job.job_id},
                                               price=0.0, requested_by=job.origin, settings={"unit": "usd", "service": job.service})
                    job.note = "Waiting for your confirmation: an image generation on openrouter. Confirm it in the Studios panel."
                    if not await self._await_approval(job, a):
                        job.status, job.note = "CANCELLED", "Rejected."
                        await self.push(job)
                        return
                    job.note, job.status = "", "POLLING"
                out = await self._guarded(job, self.backends[job.service], job.model, job.payload)
            if job.status == "CANCELLED":
                return
            if job.receipt is not None and not hasattr(out, "files") and not isinstance(out, FilesOutput):
                self._receipt_done(job, (), {"images": len(getattr(out, "images", []) or [])})
            if isinstance(out, FilesOutput):
                files = []
                for i, (data, media_type, name) in enumerate(out.files, 1):
                    name = name or f"{i}.bin"
                    job.files[name] = (data, media_type)
                    files.append({"type": out.kind, "url": f"{self.base_url}/api/v1/jobs/files/{job.token}/{name}"})
                job.result = {"result_files": files, **out.extra}
                self._receipt_done(job, (), {"files": len(files)})
                job.status = "DONE"
                await self.push(job)
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
                job.result = {"result_files": files, "saved": paths, **out.extra, **self._prompt_fields(job)}
                self._receipt_done(job, paths, {"saved": [str(p) for p in paths], "extra": {k: v for k, v in out.extra.items() if isinstance(v, (str, int, float, bool))}})
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
            job.result = {"images": images, **self._prompt_fields(job)}
            if out.image_name:
                job.result["image_name"] = out.image_name
            job.status = "DONE"
        except asyncio.CancelledError:
            job.status = "CANCELLED"
            raise
        except Exception as exc:  # noqa: BLE001 - the job carries the reason to the client
            job.status = "FAILED"
            job.error = f"{type(exc).__name__}: {exc}"[:600]
            self._receipt_failed(job, exc)
        finally:
            if self.provenance is not None and job.status in ("DONE", "FAILED"):
                try:
                    self.provenance(job, job.status == "DONE", self._provider_of(job.service, job.model))
                except Exception:  # noqa: BLE001 - provenance must never fail a generation
                    log.warning("provenance hook failed for job %s", job.job_id, exc_info=True)
            job.payload = {}
            if job.status in ("DONE", "FAILED"):
                self._log(job, job.status == "DONE")
        await self.push(job)

    # ------------------------------------------------------------------- read
    def get(self, job_id: str) -> Optional[Job]:
        job = self.jobs.get(job_id)
        if job is None and self.receipts is not None:
            r = self.receipts.find_job(job_id)
            if r is not None:
                job = self._adopt(r)
        return job

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
        if job.receipt is not None:
            snap["receipt_state"] = job.receipt["state"]
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
