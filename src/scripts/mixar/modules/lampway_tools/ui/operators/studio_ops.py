# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Studios panel's operators. Planning, reading and importing are ordinary buttons. CONFIRMING a credit spend is the captain's
click only: ``lampway.studio_confirm`` refuses while any script is running (human_gate.py) - the agent's scripts, a swarm worker's and
the bridge's - and it carries the price the card showed, which the server compares with what Studio read back."""

import os
import re

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy.types import Operator

from mixar.modules.lampway_tools import human_gate, studio_client, studio_landing, studio_state

CLIENT_FACTORY = lambda: studio_client.StudioClient()  # noqa: E731  (tests swap it)
OPEN_URL = lambda url: __import__("webbrowser").open(url)  # noqa: E731  (tests swap it)
_MESH_EXT = (".glb", ".gltf", ".fbx", ".obj")
_POLL_S = 4.0


def _redraw():
    wm = getattr(bpy.context, "window_manager", None)
    for window in getattr(wm, "windows", []) or []:
        for area in window.screen.areas:
            area.tag_redraw()


def refresh_state() -> None:
    try:
        studio_state.update(CLIENT_FACTORY().home())
    except studio_client.StudioError as exc:
        studio_state.fail(str(exc))
    _redraw()


def _poll():
    """While something is pending or running, keep the card fresh (the captain should see a job finish without pressing Refresh)."""
    try:
        if studio_state.busy():
            refresh_state()
    except Exception:  # noqa: BLE001
        pass
    return _POLL_S if studio_state.busy() else None        # idle: stop; the next plan/confirm starts it again


def ensure_poll() -> None:
    if not bpy.app.background and not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=_POLL_S, persistent=True)


class _StudioOp(Operator):
    bl_options = {"REGISTER"}

    def _done(self, context, message, ok=True):
        context.scene.lampway_tools.last_message = message
        self.report({"INFO" if ok else "ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}


class LAMPWAY_OT_studio_refresh(_StudioOp):
    """Read the Studios state from the server: pending confirmations, jobs, the engine"""
    bl_idname = "lampway.studio_refresh"
    bl_label = "Refresh Studios"

    def execute(self, context):
        refresh_state()
        if studio_state.STATE["error"]:
            return self._done(context, studio_state.STATE["error"], ok=False)
        ensure_poll()
        return self._done(context, f"{len(studio_state.pending())} waiting for you, {len(studio_state.STATE['jobs'])} jobs")


class LAMPWAY_OT_studio_plan(_StudioOp):
    """Ask a Studio to read back an action's settings and price (nothing is clicked or spent); a spend then waits for your confirmation"""
    bl_idname = "lampway.studio_plan"
    bl_label = "Plan"

    action: StringProperty(name="Action")
    args_json: StringProperty(name="Arguments", default="{}")

    def execute(self, context):
        import json
        try:
            args = json.loads(self.args_json or "{}")
            if not isinstance(args, dict):
                raise ValueError("not an object")
        except ValueError:
            return self._done(context, "Arguments must be a JSON object, e.g. {\"front\": \"plates/front.png\"}", ok=False)
        try:
            out = CLIENT_FACTORY().plan(self.action, args)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        refresh_state()
        ensure_poll()
        if out.get("state") == "refused":
            return self._done(context, f"{self.action} refused: {out.get('reason')}", ok=False)
        if out.get("state") == "needs_approval":
            ap = out["approval"]
            return self._done(context, f"{ap['label']} reads back {ap['price']} credits: confirm it in the Studios panel")
        return self._done(context, f"{self.action} started")


class LAMPWAY_OT_studio_confirm(_StudioOp):
    """Spend the credits: confirm this Studio action at the price shown. Only your own click can do this"""
    bl_idname = "lampway.studio_confirm"
    bl_label = "Confirm and spend"

    approval_id: StringProperty(options={"HIDDEN"})
    price: FloatProperty(name="Price", min=0.0, precision=2)
    label: StringProperty(name="Action", options={"HIDDEN"})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_confirm(self, event, title="Spend credits?",
                                                           message=f"{self.label}: {self.price} credits, read back from Studio.",
                                                           confirm_text="Spend")

    def execute(self, context):
        if human_gate.script_running():
            return self._done(context, "A script cannot confirm a credit spend: click Confirm in the Studios panel yourself", ok=False)
        try:
            job = CLIENT_FACTORY().confirm(self.approval_id, round(float(self.price), 2))      # a FloatProperty is single precision: 9.6 -> 9.60000038
        except studio_client.StudioError as exc:
            refresh_state()
            return self._done(context, str(exc), ok=False)
        refresh_state()
        ensure_poll()
        return self._done(context, f"confirmed: job {job.get('id')} is running on the server")


class LAMPWAY_OT_studio_answer(_StudioOp):
    """Answer a question Higgsfield (or a Studio) asks you. Only your own click can"""
    bl_idname = "lampway.studio_answer"
    bl_label = "Answer"

    approval_id: StringProperty(options={"HIDDEN"})
    answer: BoolProperty(name="Answer")

    def execute(self, context):
        if human_gate.script_running():
            return self._done(context, "A script cannot answer for you: click the answer in the Studios panel yourself", ok=False)
        try:
            CLIENT_FACTORY().confirm(self.approval_id, 0, answer=bool(self.answer))
        except studio_client.StudioError as exc:
            refresh_state()
            return self._done(context, str(exc), ok=False)
        refresh_state()
        ensure_poll()
        return self._done(context, "answered: " + ("yes" if self.answer else "no"))


class LAMPWAY_OT_higgsfield_signin(_StudioOp):
    """Open the server's Higgsfield sign-in page in your browser (one consent; the tokens stay on this machine)"""
    bl_idname = "lampway.higgsfield_signin"
    bl_label = "Sign in to Higgsfield"

    def execute(self, context):
        url = CLIENT_FACTORY().base() + "/app/higgsfield"
        OPEN_URL(url)
        return self._done(context, f"opened {url}")


class LAMPWAY_OT_studio_reject(_StudioOp):
    """Turn this Studio action down; nothing is spent"""
    bl_idname = "lampway.studio_reject"
    bl_label = "Reject"

    approval_id: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        try:
            CLIENT_FACTORY().reject(self.approval_id)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        refresh_state()
        return self._done(context, "rejected")


class LAMPWAY_OT_studio_import(_StudioOp):
    """Bring one of a finished job's files into the scene (collection Studio)"""
    bl_idname = "lampway.studio_import"
    bl_label = "Import"

    job_id: StringProperty(options={"HIDDEN"})
    name: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        from mixar.modules.lampway_tools import api
        if not re.fullmatch(r"[\w.\-]+", self.name or "") or not self.name.lower().endswith(_MESH_EXT):
            return self._done(context, f"{self.name!r} is not a mesh file", ok=False)
        try:
            blob = CLIENT_FACTORY().download(self.job_id, self.name)
            root = api._settings().project_root
            dest = os.path.join(str(root), "studio", self.job_id)
            os.makedirs(dest, exist_ok=True)
            path = os.path.join(dest, self.name)
            with open(path, "wb") as fh:
                fh.write(blob)
            res = studio_landing.import_file(path, prefix=f"{self.job_id}_")
        except (studio_client.StudioError, ValueError, RuntimeError, OSError) as exc:
            return self._done(context, f"import failed: {exc}", ok=False)
        return self._done(context, f"imported {len(res['objects'])} object(s) into {res['collection']}")


# ---- provider setup: main agent, swarm workers, image backend (saved on the server; the environment is only the default)
_PROVIDER_FIELDS = {          # operator prop -> the server's setting
    "main_provider": "provider", "chatgpt_model": "chatgpt_model", "chatgpt_effort": "chatgpt_effort", "swarm_provider": "swarm_provider",
    "claude_swarm_model": "claude_swarm_model", "openrouter_swarm_model": "openrouter_swarm_model", "image_backend": "image_backend",
    "image_model": "openrouter_image_model", "image_size": "openrouter_image_size", "image_quality": "openrouter_image_quality",
    # one image model per purpose: plates / mesh-paint, material-ID masks, concepts, seamless tiles
    "plates_model": ("image_purposes", "plates", "model"), "plates_size": ("image_purposes", "plates", "size"),
    "mask_model": ("image_purposes", "mask", "model"), "concept_model": ("image_purposes", "concept", "model"),
    "concept_resolution": ("image_purposes", "concept", "resolution"), "tile_model": ("image_purposes", "tile", "model"),
    "tile_size": ("image_purposes", "tile", "size"),
    # one video model per purpose and the per-job cost cap
    "video_bulk_model": ("video_purposes", "bulk", "model"), "video_bulk_resolution": ("video_purposes", "bulk", "resolution"),
    "video_bulk_duration": ("video_purposes", "bulk", "duration"), "video_loop_model": ("video_purposes", "loop", "model"),
    "video_loop_resolution": ("video_purposes", "loop", "resolution"), "video_motion_model": ("video_purposes", "motion", "model"),
    "video_motion_resolution": ("video_purposes", "motion", "resolution"), "video_max_job_usd": "video_max_job_usd"}
for _p in ("openrouter", "higgsfield", "studios", "hyper3d"):          # spend policy per provider: click off|above|always, the price above which a click is needed, the caps
    for _f in ("click", "above", "job_cap", "session_cap"):
        _PROVIDER_FIELDS[f"{_p}_{_f}"] = ("spend_policy", _p, _f)
_INT_PROPS = {"video_bulk_duration"}
_SPEND_AMOUNTS = {"above", "job_cap", "session_cap"}
_CHOICES = {"main_provider": "main_providers", "swarm_provider": "swarm_providers", "chatgpt_effort": "efforts",
            "image_backend": "image_backends", "image_quality": "image_qualities"}
DEFAULT_WORD = "default"     # typed for a setting whose server value is the empty default


def _spend_props():
    """The Providers dialog's spend-policy fields as one StringProperty each (empty = unchanged; a cap 'none' removes it)."""
    out = {}
    for p in ("openrouter", "higgsfield", "studios", "hyper3d"):
        unit = "USD" if p == "openrouter" else "credits"
        out[f"{p}_click"] = StringProperty(name=f"{p.title()} click", description="Does a job wait for your click? off | above | always (the agent and swarm can never click)")
        out[f"{p}_above"] = StringProperty(name=f"{p.title()} click above", description=f"With 'above': the price ({unit}) over which your click is needed")
        out[f"{p}_job_cap"] = StringProperty(name=f"{p.title()} job cap", description=f"One job above this price ({unit}) is refused before it is sent; 'none' removes the cap")
        out[f"{p}_session_cap"] = StringProperty(name=f"{p.title()} session cap", description=f"Total {unit} this session; 'none' removes the cap")
    return out


def _suggest(prop):
    def search(self, context, edit_text):
        return [(c or DEFAULT_WORD) for c in studio_state.PROVIDERS.get("choices", {}).get(_CHOICES[prop], [])]
    return search


class _ProviderProps:
    main_provider: StringProperty(name="Main agent", description="Provider for the main agent (the chat)", search=_suggest("main_provider"))
    chatgpt_model: StringProperty(name="Model (ChatGPT plan)", description="Model when the main agent runs on your ChatGPT plan")
    chatgpt_effort: StringProperty(name="Effort", description="Reasoning effort on your ChatGPT plan (default = the model's)", search=_suggest("chatgpt_effort"))
    swarm_provider: StringProperty(name="Swarm workers", description="Provider for the swarm's workers (default = the main provider's own)", search=_suggest("swarm_provider"))
    claude_swarm_model: StringProperty(name="Claude model", description="Model for workers on your own claude CLI")
    openrouter_swarm_model: StringProperty(name="OpenRouter worker model", description="Model for workers on OpenRouter")
    image_backend: StringProperty(name="Images", description="Image backend: tripo, codex_cli or openrouter", search=_suggest("image_backend"))
    image_model: StringProperty(name="Image model", description="OpenRouter image model, e.g. openai/gpt-image-2.5-sunburst (precision) or -flare (speed)")
    image_size: StringProperty(name="Image size", description="WIDTHxHEIGHT within the pixel budget (2880x2880 works), or default")
    image_quality: StringProperty(name="Image quality", description="auto, low, medium, high, xhigh, max, or default", search=_suggest("image_quality"))
    plates_model: StringProperty(name="Plates model", description="Mesh-paint plates, e.g. openai/gpt-image-2.5-flare (or sourceful/riverflow-v2.5-pro: flattest albedo, slower, dearer)")
    plates_size: StringProperty(name="Plates size", description="WIDTHxHEIGHT, e.g. 2880x2880 or 2160x3840 for a tall plate (at most 3840 per edge, ~8.3 MP)")
    mask_model: StringProperty(name="Mask model", description="Material-ID / mask drafts: flat colour regions, e.g. google/gemini-3.1-flash-image")
    concept_model: StringProperty(name="Concept model", description="Concepts / moodboard, e.g. black-forest-labs/flux-3-image. It redesigns the piece: never for projection")
    concept_resolution: StringProperty(name="Concept resolution", description="1K, 2K or 4K for models that take resolution, or default")
    tile_model: StringProperty(name="Tile model", description="Seamless tiles, e.g. openai/gpt-image-2.5-flare")
    tile_size: StringProperty(name="Tile size", description="WIDTHxHEIGHT of a seamless tile, e.g. 2048x2048")
    video_bulk_model: StringProperty(name="Bulk video", description="Bulk clips, e.g. heygen/heygen-video-1")
    video_bulk_resolution: StringProperty(name="Bulk resolution", description="e.g. 768p")
    video_bulk_duration: StringProperty(name="Bulk seconds", description="Seconds, e.g. 10")
    video_loop_model: StringProperty(name="Loop video", description="Loops (first = last frame), e.g. bytedance/seedance-1-5-pro")
    video_loop_resolution: StringProperty(name="Loop resolution", description="e.g. 720p")
    video_motion_model: StringProperty(name="Motion video", description="Motion transfer with a reference video, e.g. bytedance/seedance-2.0-mini")
    video_motion_resolution: StringProperty(name="Motion resolution", description="e.g. 480p")
    video_max_job_usd: FloatProperty(name="Video cap (USD)", description="One video job above this estimate is refused before it is sent (0 = unchanged)", min=0.0, max=100.0)


_ProviderProps.__annotations__.update(_spend_props())


def _server_values():
    cur = CLIENT_FACTORY().provider_settings()
    studio_state.PROVIDERS.clear()
    studio_state.PROVIDERS.update(cur)
    return cur["values"]


def _save_changes(op, context):
    """Send only what differs from the server's current values; the server refuses a bad choice with the reason and changes nothing."""
    try:
        current = _server_values()
        changed = {}
        for prop, key in _PROVIDER_FIELDS.items():
            wanted = getattr(op, prop)
            if wanted == "" or (prop == "video_max_job_usd" and not wanted):
                continue                                           # not given: unchanged
            wanted = "" if wanted == DEFAULT_WORD else wanted
            if isinstance(key, tuple) and key[0] == "spend_policy" and key[2] in _SPEND_AMOUNTS:
                if wanted in ("none", "None") and key[2] != "above":
                    wanted = None
                else:
                    try:
                        wanted = float(wanted)
                    except ValueError:
                        raise studio_client.StudioError(f"{prop} must be an amount (or 'none' to remove a cap)")
            if prop in _INT_PROPS:
                try:
                    wanted = int(wanted)
                except ValueError:
                    raise studio_client.StudioError(f"{prop} must be a whole number")
            if isinstance(key, tuple):                             # <group> -> purpose -> setting
                group, purpose, name = key
                if wanted != (current.get(group, {}).get(purpose) or {}).get(name):
                    changed.setdefault(group, {}).setdefault(purpose, {})[name] = wanted
            elif wanted != current.get(key):
                changed[key] = wanted
        if not changed:
            return op._done(context, "nothing changed")
        view = CLIENT_FACTORY().save_provider_settings(changed)
        studio_state.PROVIDERS.clear()
        studio_state.PROVIDERS.update(view)
    except studio_client.StudioError as exc:
        return op._done(context, str(exc), ok=False)
    return op._done(context, "saved: " + ", ".join(sorted(changed)))


class LAMPWAY_OT_providers_save(_ProviderProps, _StudioOp):
    """Save provider choices on the server (fields left empty are unchanged)"""
    bl_idname = "lampway.providers_save"
    bl_label = "Save provider settings"

    def execute(self, context):
        return _save_changes(self, context)


class LAMPWAY_OT_providers_open(_ProviderProps, _StudioOp):
    """Choose the main agent, the swarm workers and the image model; saved on the server"""
    bl_idname = "lampway.providers_open"
    bl_label = "Providers"

    def invoke(self, context, event):
        try:
            values = _server_values()
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        for prop, key in _PROVIDER_FIELDS.items():
            if isinstance(key, tuple):
                got = (values.get(key[0], {}).get(key[1]) or {}).get(key[2], "")
                setattr(self, prop, str(got) if got != "" else (DEFAULT_WORD if key[2] == "resolution" and key[0] == "image_purposes" else ""))
            else:
                setattr(self, prop, values.get(key) or DEFAULT_WORD if prop in _CHOICES else values.get(key, ""))
        return context.window_manager.invoke_props_dialog(self, width=520)

    def execute(self, context):
        return _save_changes(self, context)


classes = [LAMPWAY_OT_providers_open, LAMPWAY_OT_providers_save, LAMPWAY_OT_studio_answer, LAMPWAY_OT_higgsfield_signin, LAMPWAY_OT_studio_refresh, LAMPWAY_OT_studio_plan, LAMPWAY_OT_studio_confirm, LAMPWAY_OT_studio_reject, LAMPWAY_OT_studio_import]
