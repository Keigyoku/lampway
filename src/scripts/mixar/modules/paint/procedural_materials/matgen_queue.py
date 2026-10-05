# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""AI material generation, against Lampway's own server (the paint library's "AI Generate" box and the agent's
material tools). Upstream sent the prompt to a withheld hosted service through the job queue; here
``enqueue_matgen_job`` posts it to ``POST /api/v1/matgen`` on a worker thread (the server's model writes a node-group
script and checks it), and on the main thread registers and saves the material the server returns, sets
``wm.mixar_matgen_status`` to ``done:<name>`` and lists it under "Just Generated". A refusal or a network failure lands
in the status as ``error:<reason>``; a prompt already in flight is refused (``None``), as upstream did for a duplicate.
"""

import json
import threading
import urllib.error
import urllib.request
import uuid
from enum import Enum

from . import matgen_persistence
from .material_registry import ProceduralMaterial, register_material


class MatgenUnavailable(RuntimeError):
    pass


class JobState(Enum):
    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"


class MatgenJob:
    def __init__(self, prompt: str, pipeline: str):
        self.id = f"matgen-{uuid.uuid4().hex[:8]}"
        self.prompt = prompt
        self.pipeline = pipeline
        self.state = JobState.QUEUED
        self.material_id = ""
        self.error = ""


_in_flight: dict = {}


def _server_url() -> str:
    from mixar.config.config import get_server_url
    return get_server_url().rstrip("/")


def _access_token() -> str:
    from mixar.modules.auth.core.auth import get_access_token
    return get_access_token()


def _post(path: str, body: dict) -> dict:
    token = _access_token()
    if not token:
        raise MatgenUnavailable("not signed in: log in to the Lampway server first")
    req = urllib.request.Request(_server_url() + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail") or ""
        except Exception:  # noqa: BLE001
            detail = ""
        raise MatgenUnavailable(detail or f"the server answered HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise MatgenUnavailable(f"the server could not be reached: {exc}") from None


def _run_in_thread(fn) -> None:
    threading.Thread(target=fn, name="lampway-matgen", daemon=True).start()


def _on_main_thread(fn) -> None:
    import bpy
    bpy.app.timers.register(fn, first_interval=0.0)


def _window_manager():
    import bpy
    return bpy.context.window_manager


def enqueue_matgen_job(prompt: str = "", pipeline: str = "fast", apply_to_object_names=(), layer_name: str = "",
                       apply_to_existing: bool = False, **_ignored):
    """Start a generation; returns the job (``id``, ``state``) or None for a prompt already in flight. The result lands
    in the library ("Add to Layer" applies it); ``apply_to_object_names`` is accepted for the agent tool's signature but
    the material is not auto-applied, which the tool's answer states."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise MatgenUnavailable("a material description is required")
    if prompt in _in_flight:
        return None
    job = MatgenJob(prompt, pipeline or "fast")
    _in_flight[prompt] = job

    def work():
        try:
            reply, error = _post("/api/v1/matgen", {"prompt": prompt, "pipeline": job.pipeline}), ""
        except MatgenUnavailable as exc:
            reply, error = None, str(exc)

        def land():
            _in_flight.pop(prompt, None)
            wm = _window_manager()
            if error or not isinstance(reply, dict) or not reply.get("script"):
                job.state, job.error = JobState.FAILED, error or "the server returned no material"
                wm.mixar_matgen_status = f"error:{job.error}"
                return None
            try:
                material = ProceduralMaterial(
                    material_id=str(reply.get("material_id") or f"matgen_{uuid.uuid4().hex[:10]}"),
                    name=str(reply.get("name") or prompt[:40]), category=str(reply.get("category") or "ai_generated"),
                    script=str(reply["script"]), node_group_name=str(reply.get("node_group_name") or ""),
                    description=str(reply.get("description") or prompt))
                matgen_persistence.save_material(material)
                register_material(material)
                item = wm.mixar_matgen_recent.add()
                item.material_id = material.material_id
                item.display_name = material.name
                job.material_id, job.state = material.material_id, JobState.DONE
                wm.mixar_matgen_status = f"done:{material.name}"
            except Exception as exc:  # noqa: BLE001 - shown in the panel, never raised into the timer
                job.state, job.error = JobState.FAILED, str(exc)
                wm.mixar_matgen_status = f"error:{exc}"
            return None

        _on_main_thread(land)

    _run_in_thread(work)
    return job
