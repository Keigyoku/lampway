# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Capabilities page (docs/reports/agent-modes-spec.md E2): what the user lets their agent do, drawn in the Choices window beside the
link to Routes. One page, one drawing (``draw_capabilities``, called by ``ui/choices.py`` for its Capabilities row); the words are
``capabilities_face``, the cache is ``capabilities_state``, the transport is ``capabilities_client``.

Rows are grouped by risk. Each has a switch, its label and sentence, its state (on, off, waiting for a route, with Open Routes when a route
it needs is off) and, when it is on, its approval setting and its options. Turning on something that runs code or acts outside Lampway opens
one plain warning with its own button first; "This project only" makes the page's writes apply to the open project. An agent's proposal is a
card the user accepts or declines.

draw reads the cache only: a read runs on a worker thread (``request_refresh``) and a timer applies its answer on the main thread. Every write is
the user's click and refuses while a script runs (``human_gate``): an agent never changes what an agent may do. The server has no route that
declines a proposal, so a decline hides the card here only. The page never switches a route; it links to Routes (Privacy)."""

import textwrap
import time

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from mixar.modules.lampway_tools import capabilities_client, capabilities_face as face, capabilities_state as state, human_gate, studio_client

from . import context_settings

CLIENT_FACTORY = lambda: capabilities_client.CapabilitiesClient()  # noqa: E731  (tests swap it)
SCRIPT_REFUSAL = "this is the user's click: a script cannot press it"
POLL_S = 30.0    # an agent's proposal shows up on the page without a click
APPLY_S = 0.2    # while a read is out, how often the main thread looks for its answer
WRAP = 64        # characters of a sentence per line in the Choices window's right column


def _redraw():
    for window in getattr(bpy.context.window_manager, "windows", []) or []:
        for area in window.screen.areas:
            area.tag_redraw()


def _arm(fn, first) -> None:
    if not bpy.app.background and not bpy.app.timers.is_registered(fn):
        bpy.app.timers.register(fn, first_interval=first, persistent=True)


def _apply():
    """Timer, main thread: move a finished read's answer into the page."""
    if state.take():
        _redraw()
    return APPLY_S if state.STATE["inflight"] else None


def _tick():
    request_refresh()
    return POLL_S


def request_refresh() -> None:
    """Read the listing off the main thread (a click or the poll: the network is allowed here, never in a draw)."""
    context_settings.request_refresh()
    if state.request(CLIENT_FACTORY, state.STATE["project"]):
        _arm(_apply, APPLY_S)
    _arm(_tick, POLL_S)


def _row(cid: str) -> dict:
    row = next((r for r in state.STATE["rows"] if r.get("id") == cid), None)
    if row is None:
        raise studio_client.StudioError(f"{cid} is not on this page: Refresh, then try again")
    return row


class _Write(Operator):
    """A change to what an agent may do: the user's click only."""
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        if human_gate.script_running():
            return self._done(context, SCRIPT_REFUSAL, ok=False)
        cid = self.cap_id if hasattr(self, "cap_id") else ""
        try:
            said, wrote = self.write(CLIENT_FACTORY())
        except studio_client.StudioError as exc:
            state.STATE["refusal"][cid] = str(exc)
            _redraw()
            return self._done(context, str(exc), ok=False)
        if wrote:
            state.STATE["refusal"].pop(cid, None)
            request_refresh()   # a route it needs may have changed, and so may what is in force
        _redraw()
        return self._done(context, said)

    def _done(self, context, message, ok=True):
        props = getattr(context.scene, "lampway_tools", None)
        if props is not None:
            props.last_message = message
        self.report({"INFO" if ok else "ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}

    def write(self, client):
        """(what to say, whether the server was written)."""
        raise NotImplementedError


def _put(client, cid, **kw) -> dict:
    answer = client.set_capability(cid, project=state.write_project(), **kw)
    state.merge_row(answer)
    return answer


def _said(answer: dict, project) -> str:
    v = face.line(answer) if answer.get("label") else {"enabled": bool(answer.get("enabled")), "label": answer.get("id"), "state": "on"}
    where = " for this project" if project else ""
    if not v["enabled"]:
        return f"{v['label']} is off{where}"
    if v["state"] == "waiting":
        return f"{v['label']} is on{where}, waiting for a route: switch it on in Routes"
    return f"{v['label']} is on{where}"


class LAMPWAY_OT_capability_switch(_Write):
    """Turn a capability on or off. One that runs code or acts outside Lampway shows what it allows first, and its button turns it on"""
    bl_idname = "lampway.capability_switch"
    bl_label = "Switch capability"
    cap_id: StringProperty(options={"SKIP_SAVE"})
    enabled: BoolProperty(options={"SKIP_SAVE"})
    confirm: BoolProperty(description="The confirm row's own button", options={"SKIP_SAVE"})

    def write(self, client):
        row = _row(self.cap_id)
        if self.enabled and face.needs_confirm(row) and not (self.confirm and state.STATE["pending"] == self.cap_id):
            state.STATE["pending"] = self.cap_id
            return f"Read the warning below and confirm to let your agent use {row.get('label') or self.cap_id}", False
        project = state.write_project()
        answer = _put(client, self.cap_id, enabled=self.enabled)
        state.STATE["pending"] = ""
        return _said(answer, project), True


class LAMPWAY_OT_capability_cancel(Operator):
    """Close the confirm row: the capability stays off"""
    bl_idname = "lampway.capability_cancel"
    bl_label = "Not now"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        state.STATE["pending"] = ""
        _redraw()
        return {"FINISHED"}


class LAMPWAY_OT_capability_approval(_Write):
    """Choose when the agent asks you before it uses this capability"""
    bl_idname = "lampway.capability_approval"
    bl_label = "Approval"
    cap_id: StringProperty(options={"SKIP_SAVE"})
    approval: StringProperty(options={"SKIP_SAVE"})

    def write(self, client):
        row = _row(self.cap_id)
        _put(client, self.cap_id, approval=self.approval)
        word = next((w for v, w in face.APPROVAL_LABEL if v == self.approval), self.approval)
        return f"{row.get('label') or self.cap_id}: {word.lower()}", True


class LAMPWAY_OT_capability_option(_Write):
    """Choose an option of this capability, such as where commands run"""
    bl_idname = "lampway.capability_option"
    bl_label = "Option"
    cap_id: StringProperty(options={"SKIP_SAVE"})
    key: StringProperty(options={"SKIP_SAVE"})
    value: StringProperty(options={"SKIP_SAVE"})

    def write(self, client):
        row = _row(self.cap_id)
        _put(client, self.cap_id, options={**(row.get("chosen_options") or {}), self.key: self.value})
        return f"{row.get('label') or self.cap_id}: {self.key} is now {self.value}", True


class LAMPWAY_OT_capability_project_only(Operator):
    """Make the changes you click here apply to this project only"""
    bl_idname = "lampway.capability_project_only"
    bl_label = "This project only"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        if not state.STATE["project"]:
            state.STATE["project_only"] = False
            self.report({"ERROR"}, "This file has no Lampway project: changes here apply to every project")
            return {"CANCELLED"}
        state.STATE["project_only"] = not state.STATE["project_only"]
        _redraw()
        return {"FINISHED"}


class LAMPWAY_OT_capability_proposal_accept(_Write):
    """Accept what the agent proposed: the change is made, for this project or for all of them"""
    bl_idname = "lampway.capability_proposal_accept"
    bl_label = "Accept"
    pid: StringProperty(options={"SKIP_SAVE"})
    scope: StringProperty(default="project", options={"SKIP_SAVE"})

    def write(self, client):
        card = next((c for c in state.cards() if c["pid"] == self.pid), None)
        if card is None:
            raise studio_client.StudioError("that proposal is not on this page any more: Refresh")
        if not card["put"]:
            raise studio_client.StudioError("that proposal asks for nothing to change")
        project = state.STATE["project"] if self.scope == "project" else None
        if self.scope == "project" and not project:
            raise studio_client.StudioError("this file has no Lampway project: accept for all projects instead")
        answer = client.set_capability(card["id"], project=project, **card["put"])
        state.merge_row(answer)
        state.dismiss(self.pid)
        return _said(answer, project), True


class LAMPWAY_OT_capability_proposal_decline(_Write):
    """Decline what the agent proposed; nothing changes. The card is hidden on this screen: the server keeps no record of a decline"""
    bl_idname = "lampway.capability_proposal_decline"
    bl_label = "Decline"
    pid: StringProperty(options={"SKIP_SAVE"})

    def write(self, client):
        state.dismiss(self.pid)
        return "declined: nothing changed", False


class LAMPWAY_OT_capabilities_refresh(Operator):
    """Read the capabilities again"""
    bl_idname = "lampway.capabilities_refresh"
    bl_label = "Refresh"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        request_refresh()
        return {"FINISHED"}


# ---------------------------------------------------------------------------------------------------------- drawing: the cache only
def _wrapped(layout, text, icon="NONE", width=WRAP) -> None:
    for i, part in enumerate(textwrap.wrap(text, width) or [""]):
        layout.label(text=part, icon=icon if i == 0 else "NONE")


def _info(layout, text, hover) -> None:
    op = layout.operator("lampway.choices_info", text=text, emboss=False)
    op.hover = hover


def _choices(layout, caption, op_id, value_attr, choices, **props) -> None:
    """A caption and one button per choice, the current one pressed in; ``props`` are set on every button, the choice's value on ``value_attr``."""
    line = layout.row(align=True)
    if caption:
        line.label(text=caption)
    for c in choices:
        op = line.operator(op_id, text=c["label"], depress=bool(c["on"]))
        for k, v in props.items():
            setattr(op, k, v)
        setattr(op, value_attr, c["value"])


def _confirm(layout, r) -> None:
    box = layout.box()
    _wrapped(box, face.warning(r), icon="ERROR")
    buttons = box.row(align=True)
    go = buttons.operator("lampway.capability_switch", text="Turn on", depress=True)
    go.cap_id, go.enabled, go.confirm = r["id"], True, True
    buttons.operator("lampway.capability_cancel", text="Not now")


def _draw_row(layout, r, st) -> None:
    v = face.line(r)
    line = layout.row(align=True)
    sw = line.operator("lampway.capability_switch", text="", icon="CHECKBOX_HLT" if v["enabled"] else "CHECKBOX_DEHLT", emboss=False)
    sw.cap_id, sw.enabled, sw.confirm = v["id"], not v["enabled"], False
    _info(line, v["label"], v["does"])
    line.label(text=v["word"])
    if v["scope_tag"]:
        line.label(text=v["scope_tag"])
    _wrapped(layout, v["does"])
    if r.get("id") in face.HERMES_LAYERING:
        _wrapped(layout, face.LAYERING_WARNING, icon="ERROR")
    if v["route_note"]:
        note = layout.row(align=True)
        note.label(text=v["route_note"], icon="INFO")
        note.operator(v["route_fix"]["op"], text=v["route_fix"]["label"], emboss=False)
    if st["refusal"].get(v["id"]):
        bad = layout.row()
        bad.alert = True
        bad.label(text=st["refusal"][v["id"]])
    if st["pending"] == v["id"]:
        _confirm(layout, r)
    if v["enabled"]:
        if v["approval"]["shown"]:
            _choices(layout, "", "lampway.capability_approval", "approval", v["approval"]["choices"], cap_id=v["id"])
        if v["options"]:
            _choices(layout, v["options"]["label"] + ":", "lampway.capability_option", "value", v["options"]["choices"], cap_id=v["id"],
                     key=v["options"]["key"])


def _draw_card(layout, card, st) -> None:
    box = layout.box()
    _wrapped(box, card["line"], icon="LAMPWAY_SPARK")
    if card["warning"]:
        _wrapped(box, card["warning"], icon="ERROR")
    buttons = box.row(align=True)
    if st["project"]:
        acc = buttons.operator("lampway.capability_proposal_accept", text="Accept for this project", depress=True)
        acc.pid, acc.scope = card["pid"], "project"
        allp = buttons.operator("lampway.capability_proposal_accept", text="Accept for all projects")
        allp.pid, allp.scope = card["pid"], "global"
    else:
        acc = buttons.operator("lampway.capability_proposal_accept", text="Accept", depress=True)
        acc.pid, acc.scope = card["pid"], "global"
    buttons.operator("lampway.capability_proposal_decline", text="Decline").pid = card["pid"]


def draw_agent_features(layout) -> None:
    """Agent preferences reuse the server's cached feature rows and human-confirmed switches."""
    box = layout.box()
    top = box.row()
    top.label(text="Hermes features")
    top.operator("lampway.capabilities_refresh", text="Refresh", icon="FILE_REFRESH")
    _wrapped(box, face.LAYERING_WARNING, icon="ERROR")
    _wrapped(box, "After upgrading, close and reopen existing agent panes to apply the native feature controls.", icon="INFO")
    st = state.STATE
    if not st["ok"] or st["inflight"]:
        box.label(text="Refresh to read the server's Agent feature settings")
        if st["error"]:
            _wrapped(box, st["error"], icon="ERROR")
        return
    if st["project"]:
        scope = box.row()
        scope.operator("lampway.capability_project_only", text="This project only",
                       icon="CHECKBOX_HLT" if st["project_only"] else "CHECKBOX_DEHLT")
    box.label(text="Changes apply to this project only" if st["project"] and st["project_only"] else
                   "Changes apply to every project")
    rows = {r.get("id"): r for r in st["rows"]}
    for cid in face.HERMES_LAYERING:
        if cid in rows:
            _draw_row(box, rows[cid], st)
        else:
            box.label(text=cid + ": not listed by this server")


def draw_capabilities(layout, context=None) -> None:
    """The one drawing (the Choices window's Capabilities row). Reads the cache only."""
    st = state.STATE
    top = layout.row()
    if st["rows"]:
        top.label(text=face.summary(st["rows"]))
    top.operator("lampway.capabilities_refresh", text="Refresh", icon="FILE_REFRESH")
    context_settings.draw_context(layout, context)
    if st["missing"]:
        layout.label(text="This Lampway server has no Capabilities yet: update it, then Refresh")
        return
    if not st["rows"]:
        if st["inflight"]:
            layout.label(text="Reading capabilities...")
        elif st["ok"]:
            layout.label(text="This server lists no capabilities")
        else:
            layout.label(text="Lampway's server is not running: start it, then Refresh", icon="ERROR")
            if st["error"]:
                _wrapped(layout, st["error"])
        return
    if not st["ok"]:
        layout.label(text="as of " + time.strftime("%H:%M", time.localtime(st["as_of"])) + ", server stopped", icon="ERROR")
    project = layout.row(align=True)
    on = bool(st["project_only"] and st["project"])
    project.enabled = bool(st["project"])
    project.operator("lampway.capability_project_only", text="This project only", icon="CHECKBOX_HLT" if on else "CHECKBOX_DEHLT", depress=on)
    if not st["project"]:
        layout.label(text="This file has no Lampway project: changes here apply to every project")
    elif on:
        layout.label(text="Changes you make here apply to this project only")
    for card in state.cards():
        _draw_card(layout, card, st)
    for group in face.groups(st["rows"]):
        layout.separator()
        layout.label(text=group["title"])
        for r in group["rows"]:
            _draw_row(layout, r, st)


classes = [LAMPWAY_OT_capability_switch, LAMPWAY_OT_capability_cancel, LAMPWAY_OT_capability_approval, LAMPWAY_OT_capability_option,
           LAMPWAY_OT_capability_project_only, LAMPWAY_OT_capability_proposal_accept, LAMPWAY_OT_capability_proposal_decline,
           LAMPWAY_OT_capabilities_refresh]
