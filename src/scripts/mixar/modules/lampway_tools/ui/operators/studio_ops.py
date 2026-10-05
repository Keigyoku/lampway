# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Studios panel's operators. Planning, reading and importing are ordinary buttons. CONFIRMING a credit spend is the captain's
click only: ``lampway.studio_confirm`` refuses while any script is running (human_gate.py) - the agent's scripts, a swarm worker's and
the bridge's - and it carries the price the card showed, which the server compares with what Studio read back."""

import os
import re

import bpy
from bpy.props import IntProperty, StringProperty
from bpy.types import Operator

from mixar.modules.lampway_tools import human_gate, studio_client, studio_landing, studio_state

CLIENT_FACTORY = lambda: studio_client.StudioClient()  # noqa: E731  (tests swap it)
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
    price: IntProperty(name="Credits", min=0)
    label: StringProperty(name="Action", options={"HIDDEN"})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_confirm(self, event, title="Spend credits?",
                                                           message=f"{self.label}: {self.price} credits, read back from Studio.",
                                                           confirm_text="Spend")

    def execute(self, context):
        if human_gate.script_running():
            return self._done(context, "A script cannot confirm a credit spend: click Confirm in the Studios panel yourself", ok=False)
        try:
            job = CLIENT_FACTORY().confirm(self.approval_id, self.price)
        except studio_client.StudioError as exc:
            refresh_state()
            return self._done(context, str(exc), ok=False)
        refresh_state()
        ensure_poll()
        return self._done(context, f"confirmed: job {job.get('id')} is running on the server")


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


classes = [LAMPWAY_OT_studio_refresh, LAMPWAY_OT_studio_plan, LAMPWAY_OT_studio_confirm, LAMPWAY_OT_studio_reject, LAMPWAY_OT_studio_import]
