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


def apply_to_objects(material, object_names, layer_name="", apply_to_existing=False):
    """Apply a registered procedural material to the named objects. Onto the active Mixar Paint layer stack when the object has one
    (the layer operator), otherwise as the object's surface material: a Group node of the generated node group into the Material
    Output. Returns (applied names, missing names, route per object)."""
    import bpy
    from . import material_registry
    group = material_registry.get_node_group(material.material_id)
    if group is None:
        raise MatgenUnavailable(f"the node group {material.node_group_name!r} could not be built from the script")
    applied, missing, routes = [], [], {}
    for name in object_names:
        ob = bpy.data.objects.get(name)
        if ob is None or ob.type != "MESH":
            missing.append(name)
            continue
        route = "surface"
        try:
            from mixar.modules.paint.core.node.node_utils import get_active_mpaint_node
            view = bpy.context.view_layer
            view.objects.active = ob
            if get_active_mpaint_node():
                bpy.ops.layers.add_custom_procedural_layer(material_id=material.material_id, apply_to_existing=bool(apply_to_existing))
                route = "layer"
        except Exception:  # noqa: BLE001 - no paint stack on this object (or headless): the surface route below
            route = "surface"
        if route == "surface":
            mat = bpy.data.materials.new(layer_name or material.name)
            mat.use_nodes = True
            t = mat.node_tree
            for n in list(t.nodes):
                t.nodes.remove(n)
            out = t.nodes.new("ShaderNodeOutputMaterial")
            node = t.nodes.new("ShaderNodeGroup")
            node.node_tree = group
            shader = next((o for o in node.outputs if o.type == "SHADER"), None)
            if shader is not None:
                t.links.new(shader, out.inputs["Surface"])
            ob.data.materials.clear()
            ob.data.materials.append(mat)
        applied.append(name)
        routes[name] = route
    return applied, missing, routes


class MatgenJob:
    def __init__(self, prompt: str, pipeline: str):
        self.id = f"matgen-{uuid.uuid4().hex[:8]}"
        self.prompt = prompt
        self.pipeline = pipeline
        self.state = JobState.QUEUED
        self.material_id = ""
        self.error = ""
        self.applied = []
        self.apply_missing = []
        self.apply_routes = {}


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
    """Start a generation; returns the job (``id``, ``state``) or None for a prompt already in flight. The result lands in the library
    ("Add to Layer" applies it); with ``apply_to_object_names`` it is also applied to those objects (``job.applied``,
    ``job.apply_missing``, ``job.apply_routes``): onto their Mixar Paint layer stack when they have one, else as the surface material."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise MatgenUnavailable("a material description is required")
    if prompt in _in_flight:
        return None
    job = MatgenJob(prompt, pipeline or "fast")
    targets = [str(n) for n in (apply_to_object_names or [])]
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
                if hasattr(wm, "mixar_matgen_recent"):                   # the paint panel's list; absent in a headless run
                    item = wm.mixar_matgen_recent.add()
                    item.material_id = material.material_id
                    item.display_name = material.name
                job.material_id, job.state = material.material_id, JobState.DONE
                if targets:
                    job.applied, job.apply_missing, job.apply_routes = apply_to_objects(material, targets, layer_name, apply_to_existing)
                if hasattr(wm, "mixar_matgen_status"):
                    wm.mixar_matgen_status = f"done:{material.name}"
            except Exception as exc:  # noqa: BLE001 - shown in the panel, never raised into the timer
                job.state, job.error = JobState.FAILED, str(exc)
                if hasattr(wm, "mixar_matgen_status"):
                    wm.mixar_matgen_status = f"error:{exc}"
            return None

        _on_main_thread(land)

    _run_in_thread(work)
    return job
