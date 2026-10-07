# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Choices window (specs/choices/choices_face.md, P0: native widgets): what Lampway uses for each thing now, and why.
One drawing, two entry points: a pop-out (the Providers button now opens it, on Agents) and Preferences > Interface >
Choices. Left the purposes by group and a Spending row; right the selected purpose: what serves it now, the chain with each
option's facts, the proposal card, the scope.

draw reads the cache (choices_state) only. Every write is the user's click and refuses while a script runs. The window
never switches a route (it links to Privacy) and never connects an account (it links to Connections). A server that has
no Choices yet answers 404: the window then offers the old Providers dialog, so nothing is lost before the server lands."""

import time

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Operator, Panel

from mixar.modules.lampway_tools import choices_client, choices_face, choices_state, human_gate, studio_client

CLIENT_FACTORY = lambda: choices_client.ChoicesClient()  # noqa: E731  (tests swap it)
SCRIPT_REFUSAL = "this is the user's click: a script cannot press it"
POLL_S = 60.0
SPENDING = "spending"


def _preview(name):
    if not name:
        return 0
    try:
        from mixar.modules.common.lampway_icons import icon_id
        return icon_id(name.removeprefix("LAMPWAY_").lower())
    except Exception:  # noqa: BLE001  (no previews in a headless run)
        return 0


def _redraw():
    for window in getattr(bpy.context.window_manager, "windows", []) or []:
        for area in window.screen.areas:
            area.tag_redraw()


def refresh() -> None:
    client = CLIENT_FACTORY()
    try:
        listing = client.list(choices_state.STATE["project"] or None)
        proposals = client.proposals("open").get("proposals") or []
        choices_state.update(listing, proposals)
    except studio_client.StudioError as exc:
        choices_state.fail(str(exc))
    _redraw()


REFRESH = refresh   # tests swap it


def select(pid: str) -> None:
    """Choose a purpose and read its view (a click: the network is allowed here, never in draw)."""
    choices_state.STATE["selected"] = pid
    if pid and pid != SPENDING:
        try:
            choices_state.STATE["detail"] = CLIENT_FACTORY().one(pid, choices_state.STATE["project"] or None)
        except studio_client.StudioError as exc:
            choices_state.STATE["refusal"][pid] = str(exc)
    _redraw()


def _tick():
    refresh()
    return POLL_S


class _Write(Operator):
    bl_options = {"REGISTER", "INTERNAL"}

    def _done(self, context, message, ok=True):
        props = getattr(context.scene, "lampway_tools", None)
        if props is not None:
            props.last_message = message
        self.report({"INFO" if ok else "ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}

    def execute(self, context):
        if human_gate.script_running():
            return self._done(context, SCRIPT_REFUSAL, ok=False)
        pid = choices_state.STATE["selected"]
        try:
            answer = self.write(CLIENT_FACTORY(), pid)
        except studio_client.StudioError as exc:
            choices_state.STATE["refusal"][pid] = str(exc)
            _redraw()
            return self._done(context, str(exc), ok=False)
        choices_state.STATE["refusal"].pop(pid, None)
        if isinstance(answer, dict) and answer.get("chain") is not None:
            choices_state.STATE["detail"] = answer
        REFRESH()
        return self._done(context, self.said())

    def write(self, client, pid):
        raise NotImplementedError

    def said(self):
        return "saved"


class LAMPWAY_OT_choices_move(_Write):
    """Move this option up or down the chain (the first that can run serves the purpose)"""
    bl_idname = "lampway.choices_move"
    bl_label = "Move"
    option: StringProperty(options={"SKIP_SAVE"})
    step: IntProperty(default=-1, options={"SKIP_SAVE"})

    def write(self, client, pid):
        chain = [o["id"] for o in (choices_state.STATE["detail"] or {}).get("chain") or []]
        if self.option not in chain:
            raise studio_client.StudioError(f"{self.option} is not in this purpose's chain")
        i = chain.index(self.option)
        j = max(0, min(len(chain) - 1, i + self.step))
        chain.insert(j, chain.pop(i))
        project = choices_state.STATE["project"]
        body = {"preferred": chain[0], "fallbacks": chain[1:], "scope": "project" if project and self._project_scope() else "global"}
        if body["scope"] == "project":
            body["project"] = project
        return client.put(pid, body)

    def _project_scope(self):
        return "project" in ((choices_state.STATE["detail"] or {}).get("scopes") or {})

    def said(self):
        return "the chain is reordered"


class LAMPWAY_OT_choices_clear_override(_Write):
    """Use yours again: drop this project's choice for this purpose"""
    bl_idname = "lampway.choices_clear_override"
    bl_label = "Use yours again"

    def write(self, client, pid):
        return client.clear(pid, choices_state.STATE["project"] or None)

    def said(self):
        return "this project uses yours again"


class LAMPWAY_OT_choices_acknowledge(_Write):
    """Allow (or take back) private content to an option whose provider may keep it; logged by the server"""
    bl_idname = "lampway.choices_acknowledge"
    bl_label = "Allow private content"
    option: StringProperty(options={"SKIP_SAVE"})
    private: BoolProperty(default=True, options={"SKIP_SAVE"})

    def write(self, client, pid):
        client.acknowledge(self.option, self.private)
        return client.one(pid, choices_state.STATE["project"] or None) if pid and pid != SPENDING else None

    def said(self):
        return f"private content to {self.option}: {'allowed' if self.private else 'taken back'}"


class LAMPWAY_OT_choices_proposal_accept(_Write):
    """Accept what the agent proposed"""
    bl_idname = "lampway.choices_proposal_accept"
    bl_label = "Accept"
    proposal: StringProperty(options={"SKIP_SAVE"})
    scope: StringProperty(default="project", options={"SKIP_SAVE"})

    def write(self, client, pid):
        project = choices_state.STATE["project"]
        if self.scope == "project" and not project:
            raise studio_client.StudioError("this file has no Lampway project: accept for all projects instead")
        return client.accept(self.proposal, self.scope, project or None)

    def said(self):
        return "accepted"


class LAMPWAY_OT_choices_proposal_decline(_Write):
    """Decline what the agent proposed; nothing changes"""
    bl_idname = "lampway.choices_proposal_decline"
    bl_label = "Decline"
    proposal: StringProperty(options={"SKIP_SAVE"})

    def write(self, client, pid):
        return client.decline(self.proposal)

    def said(self):
        return "declined"


class LAMPWAY_OT_choices_select(Operator):
    """Show this purpose"""
    bl_idname = "lampway.choices_select"
    bl_label = "Select"
    bl_options = {"INTERNAL"}
    purpose: StringProperty(options={"SKIP_SAVE"})
    hover: StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        return properties.hover or "Show this purpose"

    def execute(self, context):
        select(self.purpose)
        return {"FINISHED"}


class LAMPWAY_OT_choices_refresh(Operator):
    """Read the choices again"""
    bl_idname = "lampway.choices_refresh"
    bl_label = "Refresh"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        REFRESH()
        return {"FINISHED"}


class LAMPWAY_OT_choices_info(Operator):
    """What this says in full"""
    bl_idname = "lampway.choices_info"
    bl_label = "Details"
    bl_options = {"INTERNAL"}
    hover: StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        return properties.hover or "No details"

    def execute(self, context):
        self.report({"INFO"}, self.hover or "No details")
        return {"FINISHED"}


def _open(group: str = "", purpose: str = "") -> None:
    REFRESH()
    if group:
        choices_state.STATE["group"] = group
        first = next((p for g in choices_state.STATE["groups"] if g.get("id") == group for p in g.get("purposes") or []), None)
        if first and not purpose:
            purpose = first["id"]
    if purpose:
        select(purpose)
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=POLL_S, persistent=True)
    if not bpy.app.background:
        bpy.ops.wm.call_panel(name="LAMPWAY_PT_choices_popout", keep_open=True)


class LAMPWAY_OT_choices_open(Operator):
    """Choices: what Lampway uses for each thing now, and why"""
    bl_idname = "lampway.choices_open"
    bl_label = "Choices"
    group: StringProperty(options={"SKIP_SAVE"})
    purpose: StringProperty(options={"SKIP_SAVE"})

    def execute(self, context):
        _open(self.group, self.purpose)
        return {"FINISHED"}


class LAMPWAY_OT_providers_open(Operator):
    """Providers are Choices now: the main agent, the workers, images, video and spending"""
    bl_idname = "lampway.providers_open"
    bl_label = "Choices"

    def execute(self, context):
        _open("agents")
        return {"FINISHED"}


def _info(layout, text, hover, icon_value=0):
    op = layout.operator("lampway.choices_info", text=text, icon_value=icon_value, emboss=False)
    op.hover = hover


def _list(layout):
    st = choices_state.STATE
    waiting = choices_state.waiting()
    for g in st["groups"]:
        layout.label(text=g.get("label") or g.get("id"))
        for s in g.get("purposes") or []:
            c = choices_face.cue(s, waiting)
            row = layout.row(align=True)
            op = row.operator("lampway.choices_select", text=s.get("label") or s["id"], icon_value=_preview(c["glyph"]),
                              emboss=s["id"] == st["selected"], depress=c["glows"])
            op.purpose = s["id"]
            op.hover = f"{c['word']}; {choices_face.now_line(s)}; scope: {(s.get('now') or {}).get('scope') or 'none'}"
            row.label(text=((s.get("now") or {}).get("label") or "")[:22])
    op = layout.operator("lampway.choices_select", text="Spending", icon="LAMPWAY_COIN", emboss=st["selected"] == SPENDING)
    op.purpose = SPENDING


def _spending(layout):
    from mixar.modules.lampway_tools import statusbar_state
    layout.label(text="Spending: what may spend without your click, and the caps")
    for row in (statusbar_state.STATE.get("spend") or {}).get("providers") or []:
        unit = "$" if row.get("unit") == "USD" else ""
        caps = ", ".join(x for x in (f"job cap {unit}{row['job_cap']:g}" if row.get("job_cap") is not None else "",
                                    f"day cap {unit}{row['day_cap']:g}" if row.get("day_cap") is not None else "") if x) or "no caps"
        ask = {"off": "never asks", "always": "asks before every job", "above": f"asks above {unit}{(row.get('above') or 0):g}"}.get(row.get("click"), row.get("click") or "")
        layout.label(text=f"{row['provider']}: {ask}; {caps}; spent today {unit}{float(row.get('spent') or 0):g}")
    layout.operator("lampway.providers_dialog", text="Change spending", icon="PREFERENCES")


def _detail(layout):
    st = choices_state.STATE
    pid = st["selected"]
    if pid == SPENDING:
        _spending(layout)
        return
    view = st["detail"] or {}
    if not pid or view.get("id") != pid:
        layout.label(text="Choose a purpose on the left")
        return
    waiting = choices_state.waiting()
    c = choices_face.cue(view, waiting)
    head = layout.row()
    head.label(text=view.get("label") or pid, icon_value=_preview(c["glyph"]))
    layout.label(text=f"{choices_face.now_line(view)} ({c['word']})")
    chain = view.get("chain") or []
    proposals = [p for p in st["proposals"] if p.get("purpose") == pid and p.get("state") == "open"]
    for p in proposals:
        box = layout.box()
        box.label(text=choices_face.proposal_line(p), icon_value=_preview("conn_waiting"))
        row = box.row(align=True)
        acc = row.operator("lampway.choices_proposal_accept", text="Accept for this project", depress=True)
        acc.proposal, acc.scope = p["id"], "project"
        allp = row.operator("lampway.choices_proposal_accept", text="Accept for all projects")
        allp.proposal, allp.scope = p["id"], "global"
        row.operator("lampway.choices_proposal_decline", text="Decline").proposal = p["id"]
    act = choices_face.action(view, proposal=False, chain=chain)
    if act and act.get("op") != "lampway.choices_select":
        op = layout.operator(act["op"], text=act["label"])
        if act.get("connection"):
            op.connection = act["connection"]
    refusal = st["refusal"].get(pid)
    if refusal:
        r = layout.row()
        r.alert = True
        r.label(text=refusal)
    layout.label(text="The chain: the first option that can run serves it")
    for o in chain:
        row = choices_face.option_row(o)
        line = layout.row(align=True)
        line.label(text=f"{(row['rank'] or 0) + 1}.")
        _info(line, row["name"], f"{row['runs']['text']}; {row['connection_tip']}; {row['cost_tip']}; {row['retention_tip']}"
              + (f"; {row['quality']}" if row["quality"] else ""), _preview(row["runs"]["icon"]))
        if row["connection"]:
            line.label(text="", icon_value=_preview(row["connection"]))
        line.label(text="", icon_value=_preview(row["retention"]))
        if row["ack"]:
            take = line.operator("lampway.choices_acknowledge", text="", icon_value=_preview(row["ack"]["glyph"]), emboss=False)
            take.option, take.private = row["id"], False
        up = line.operator("lampway.choices_move", text="", icon="TRIA_UP")
        up.option, up.step = row["id"], -1
        down = line.operator("lampway.choices_move", text="", icon="TRIA_DOWN")
        down.option, down.step = row["id"], 1
        if row["skipped"]:
            sk = layout.row(align=True)
            sk.enabled = True
            sk.label(text=row["skipped"])
            if row["fix"]:
                op = sk.operator(row["fix"]["op"], text=row["fix"]["label"], emboss=False)
                if row["fix"].get("connection"):
                    op.connection = row["fix"]["connection"]
        elif choices_face.kept(o.get("retention") or "") and not row["ack"]:
            allow = layout.operator("lampway.choices_acknowledge", text=f"Allow private content to {row['name']}", emboss=False)
            allow.option, allow.private = row["id"], True
    if "project" in (view.get("scopes") or {}):
        layout.label(text="this project overrides yours")
        layout.operator("lampway.choices_clear_override", text="Use yours again", emboss=False)


def draw_choices(layout, context):
    """The one drawing (pop-out, preferences). Reads the cache only."""
    st = choices_state.STATE
    top = layout.row()
    top.operator("lampway.choices_refresh", text="Refresh", icon="FILE_REFRESH")
    if st["missing"]:
        layout.label(text="This Lampway server has no Choices yet: the Providers dialog still sets the agent, images, video and spending")
        layout.operator("lampway.providers_dialog", text="Providers", icon="PREFERENCES")
        return
    if not st["ok"]:
        top.label(text="Lampway's server is not running: start it, then Refresh", icon="ERROR")
        if st["groups"]:
            layout.label(text="as of " + time.strftime("%H:%M", time.localtime(st["as_of"])) + ", server stopped")
    split = layout.split(factor=0.36)
    _list(split.column())
    _detail(split.column())


class LAMPWAY_PT_choices_popout(Panel):
    bl_idname = "LAMPWAY_PT_choices_popout"
    bl_label = "Choices"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_ui_units_x = 38

    def draw(self, context):
        draw_choices(self.layout, context)


class LAMPWAY_PT_choices_preferences(Panel):
    bl_space_type = "PREFERENCES"
    bl_region_type = "WINDOW"
    bl_context = "interface"
    bl_label = "Choices"

    def draw(self, context):
        draw_choices(self.layout, context)


classes = [LAMPWAY_OT_choices_move, LAMPWAY_OT_choices_clear_override, LAMPWAY_OT_choices_acknowledge, LAMPWAY_OT_choices_proposal_accept,
           LAMPWAY_OT_choices_proposal_decline, LAMPWAY_OT_choices_select, LAMPWAY_OT_choices_refresh, LAMPWAY_OT_choices_info,
           LAMPWAY_OT_choices_open, LAMPWAY_OT_providers_open, LAMPWAY_PT_choices_popout, LAMPWAY_PT_choices_preferences]
