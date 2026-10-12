# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The first run's steps 2-4 (facelift contract 02, P1, DESIGN.md 13): a dialog per step on the lit path. Step 1 (language and keys) is the
splash's Quick Setup, whose Continue opens this; the last button names the outcome ("Continue with 1 route on"), saves the preferences as
Quick Setup always did and writes the routes and caps to Lampway's server.

Every route row is one line: the shield (its policy is the hover text), the name with its host, the switch. The switch alone says on or off.
Nothing here reaches the network in a draw: the walk is read once, when the dialog opens."""

import textwrap

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Operator, PropertyGroup

from mixar.modules.lampway_tools import onboarding as ob

def n_(msgid):
    """Marks a message for the catalogue; it is translated where it is drawn."""
    return msgid


def iface_(msgid):
    out = bpy.app.translations.pgettext_iface(msgid)
    return out if isinstance(out, str) else msgid      # a stubbed bpy (the unit tests) translates nothing


WALK = {"walk": None, "anchor": None}
WRAP = 60              # characters per body line: the body column holds about 78 at any UI scale (it scales with the text)
STEP_TEXT = {ob.PROVIDER_STEP: n_("The agent thinks with the provider you pick here; nothing is sent until you use it"),
             ob.ROUTES_STEP: n_("Every route is off until you switch it on"),
             ob.CAPS_STEP: n_("OpenRouter, in dollars: a click above the first amount, never past the caps")}
OFFLINE_NEXT = n_("Continue saves your language and keys only")
SHIELD = {"ok": 'LAMPWAY_SHIELD', "conditional": 'LAMPWAY_SHIELD_HALF', "retains": 'LAMPWAY_SHIELD_OPEN', "unknown": 'LAMPWAY_SHIELD_UNKNOWN'}
PROVIDERS = (("chatgpt_plan", "ChatGPT plan", "Your ChatGPT subscription, signed in from Providers"),
             ("codex_cli", "Codex CLI", "The Codex command line on this machine, on your ChatGPT plan"),
             ("claude_cli", "Claude Code", "The Claude command line on this machine, on your Claude plan"),
             ("openrouter", "OpenRouter", "Pay per use with your OpenRouter key"),
             ("anthropic", "Anthropic API key", "Pay per use with your Anthropic key"),
             ("openai", "OpenAI API key", "Pay per use with your OpenAI key"),
             ("codex_app_server", "Codex app server", "The Codex app server on this machine, on your ChatGPT plan"),
             ("mock", "No agent", "A stand-in that answers on this machine and thinks nothing"))


def _door():
    from mixar.modules.lampway_tools.egress_client import EgressClient

    class Door(EgressClient):
        def egress(self):
            return self._call("GET", "/app/egress", timeout=5)

    return Door()


def policy_text(route) -> str:
    hosts = ", ".join(route.get("hosts") or []) or "a host you configure"
    return f"{route['label']} ({hosts}). Keeps: {route.get('retention') or 'unknown'}. Trains on it: {route.get('training') or 'unknown'}."


def _route(walk, route_id):
    return next(r for r in walk.routes if r["id"] == route_id)


def draw_rail(layout, walk):
    col = layout.column(align=True)
    for i, name in enumerate(ob.STEPS, start=1):
        icon = 'LAMPWAY_NODE_LIT' if i < walk.step else 'LAMPWAY_NODE_HALF' if i == walk.step else 'LAMPWAY_NODE'
        col.label(text=name, icon=icon)
    col.separator()
    col.label(text="")


def wrapped(layout, text, icon='NONE'):
    """A sentence as whole lines: a label never cuts it to an ellipsis (audit F23). Translated whole, then wrapped."""
    for i, line in enumerate(textwrap.wrap(iface_(text), WRAP)):
        layout.label(text=line, icon=icon if i == 0 else 'NONE', translate=False)


def _lines(text) -> int:
    return len(textwrap.wrap(iface_(text), WRAP))


def body_rows(walk) -> int:
    """The tallest step's rows: every step is padded to it, so the dialog keeps one size and Continue one place (audit F23)."""
    if not walk.online:
        return 1 + _lines(ob.OFFLINE) + _lines(OFFLINE_NEXT)
    refusal = max((_lines(why) for why in [walk.refusal()] if why), default=0)
    return max(_lines(STEP_TEXT[ob.PROVIDER_STEP]) + 1 + max(refusal, 1), _lines(STEP_TEXT[ob.ROUTES_STEP]) + len(walk.routes), _lines(STEP_TEXT[ob.CAPS_STEP]) + 3)


def draw_routes(layout, walk, rows):
    for row_data in rows:
        route = _route(walk, row_data.route_id)
        row = layout.row(align=True)
        op = row.operator("lampway.onboarding_policy", text="", icon=SHIELD.get(route.get("privacy_class"), 'LAMPWAY_SHIELD_UNKNOWN'), emboss=False)
        op.route_id = route["id"]
        hosts = route.get("hosts") or []
        row.label(text=f"{route['label']}   {hosts[0]}" if hosts else route["label"])
        row.prop(row_data, "enabled", text="")


def draw_step(layout, walk, rows):
    split = layout.split(factor=0.34)
    draw_rail(split.column(), walk)
    body = split.column()
    drawn = _draw_body(body, walk, rows)
    for _ in range(body_rows(walk) - drawn):
        body.label(text="")


def _draw_body(body, walk, rows) -> int:
    """Draw the step's body; return how many rows it took."""
    if walk.step >= 2 and not walk.online:
        wrapped(body, ob.OFFLINE, icon='ERROR')
        wrapped(body, OFFLINE_NEXT)
        return _lines(ob.OFFLINE) + _lines(OFFLINE_NEXT)
    wm = getattr(bpy.context, "window_manager", None)
    if walk.step == ob.PROVIDER_STEP:
        wrapped(body, STEP_TEXT[ob.PROVIDER_STEP])
        body.prop(wm, "lampway_onboarding_provider", text="")
        why = walk.refusal()
        if why:
            wrapped(body, why, icon='ERROR')
        return _lines(STEP_TEXT[ob.PROVIDER_STEP]) + 1 + (_lines(why) if why else 0)
    if walk.step == ob.ROUTES_STEP:
        wrapped(body, STEP_TEXT[ob.ROUTES_STEP])
        draw_routes(body, walk, rows)
        return _lines(STEP_TEXT[ob.ROUTES_STEP]) + len(rows)
    if walk.step == ob.CAPS_STEP:
        wrapped(body, STEP_TEXT[ob.CAPS_STEP])
        body.prop(wm, "lampway_onboarding_above", text="Click above")
        body.prop(wm, "lampway_onboarding_job_cap", text="Per job")
        body.prop(wm, "lampway_onboarding_day_cap", text="Per day")
        return _lines(STEP_TEXT[ob.CAPS_STEP]) + 3
    return 0


def _redraw_all(context):
    """Refresh surrounding editors after setup content changes."""
    if getattr(context, "window", None) is None:
        return
    for area in [*context.window.screen.areas, *context.window.global_areas]:
        area.tag_redraw()


def _route_switched(self, context):
    walk = WALK["walk"]
    if walk is not None and walk.chosen.get(self.route_id) != self.enabled:
        walk.click_route(self.route_id, self.enabled)


def _provider_picked(self, context):
    if WALK["walk"] is not None:
        WALK["walk"].provider = self.lampway_onboarding_provider


def _caps_changed(self, context):
    if WALK["walk"] is not None:
        WALK["walk"].caps = {"job_cap": self.lampway_onboarding_job_cap, "day_cap": self.lampway_onboarding_day_cap,
                             "above": self.lampway_onboarding_above}


class LampwayOnboardingRoute(PropertyGroup):
    route_id: StringProperty()
    enabled: BoolProperty(name="On", description="Let data go over this route", update=_route_switched)


def _begin(context):
    walk = ob.Walk.read(_door())
    WALK["walk"] = walk
    wm = context.window_manager
    wm.lampway_onboarding_routes.clear()
    for route in walk.routes:
        item = wm.lampway_onboarding_routes.add()
        item.route_id = route["id"]
        item.enabled = walk.chosen[route["id"]]
    walk.clicks.clear()   # mirroring the server's state is not a click
    if walk.provider in {p[0] for p in PROVIDERS}:   # the list shows the provider as it is; an unlisted one is kept, never replaced unasked
        wm.lampway_onboarding_provider = walk.provider
    _caps_changed(wm, context)
    walk.next()   # step 1 is the splash's
    return walk


class LAMPWAY_OT_onboarding(Operator):
    """Set up where the agent thinks, what may leave this machine and what may be spent"""
    bl_idname = "lampway.onboarding"
    bl_label = "Lampway setup"

    def invoke(self, context, event):
        walk = WALK["walk"] or _begin(context)
        # every step opens where the first did: one size, one place, so Continue never moves (audit F23)
        if WALK["anchor"] is None:
            WALK["anchor"] = (event.mouse_x, event.mouse_y)
        elif (event.mouse_x, event.mouse_y) != WALK["anchor"]:
            context.window.cursor_warp(*WALK["anchor"])
        _redraw_all(context)
        return context.window_manager.invoke_popup(self, width=640)

    def draw(self, context):
        walk = WALK["walk"]
        if walk is not None:
            self.layout.label(text=ob.STEPS[walk.step - 1])
            draw_step(self.layout, walk, context.window_manager.lampway_onboarding_routes)
            self.layout.separator()
            footer = self.layout.row(align=True)
            back = footer.row()
            back.enabled = walk.step > 2
            back.operator("lampway.onboarding_back", text="Back")
            text = walk.continue_label() if walk.step == len(ob.STEPS) and walk.online else "Continue"
            footer.operator("lampway.onboarding_next", text=text)

    def execute(self, context):
        walk = WALK["walk"]
        if walk is None:
            return {'CANCELLED'}
        if walk.step < len(ob.STEPS):
            why = walk.next()
            if why:
                self.report({'ERROR'}, why)
            _refresh_step(context)
            return {'FINISHED'}
        try:
            saved = walk.finish(_door() if walk.online else None)
        except Exception as exc:  # noqa: BLE001  (the server refused or went away: say so, keep the walk to try again)
            self.report({'ERROR'}, f"Lampway's server did not take the setup: {exc}")
            _refresh_step(context)
            return {'FINISHED'}
        bpy.ops.wm.save_userpref()
        WALK.update(walk=None, anchor=None)
        self.report({'INFO'}, "Saved: " + ", ".join(saved))
        return {'FINISHED'}


def _refresh_step(context):
    """Rebuild the existing popup's layout, then redraw it and its editor."""
    # Button operators retain the editor as context.region. Its redraw does
    # not set the temporary popup's RGN_REFRESH_UI flag; request that rebuild
    # explicitly rather than relying on the next unrelated UI event.
    popup = getattr(context, "region_popup", None)
    if popup is not None and popup.type == 'TEMPORARY':
        popup.tag_refresh_ui()
        popup.tag_redraw()
    region = getattr(context, "region", None)
    if region is not None:
        region.tag_redraw()
    _redraw_all(context)


class LAMPWAY_OT_onboarding_next(Operator):
    """Continue to the next setup step"""
    bl_idname = "lampway.onboarding_next"
    bl_label = "Continue"

    def execute(self, context):
        return LAMPWAY_OT_onboarding.execute(self, context)


class LAMPWAY_OT_onboarding_back(Operator):
    """The step before"""
    bl_idname = "lampway.onboarding_back"
    bl_label = "Back"

    def execute(self, context):
        if WALK["walk"] is not None:
            WALK["walk"].back()
        _refresh_step(context)
        return {'FINISHED'}


class LAMPWAY_OT_onboarding_policy(Operator):
    """What this route keeps and whether it trains on what you send"""
    bl_idname = "lampway.onboarding_policy"
    bl_label = "Route policy"
    route_id: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        walk = WALK["walk"]
        try:
            return policy_text(_route(walk, properties.route_id))
        except (AttributeError, StopIteration, TypeError):
            return cls.__doc__

    def execute(self, context):
        return {'FINISHED'}


classes = (LampwayOnboardingRoute, LAMPWAY_OT_onboarding, LAMPWAY_OT_onboarding_back, LAMPWAY_OT_onboarding_next, LAMPWAY_OT_onboarding_policy)
_PROPS = ("lampway_onboarding_routes", "lampway_onboarding_provider", "lampway_onboarding_job_cap", "lampway_onboarding_day_cap",
          "lampway_onboarding_above")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.lampway_onboarding_routes = CollectionProperty(type=LampwayOnboardingRoute)
    wm.lampway_onboarding_provider = EnumProperty(name="Main agent", items=PROVIDERS, default="chatgpt_plan", update=_provider_picked)
    caps = ob.DEFAULT_CAPS
    wm.lampway_onboarding_job_cap = FloatProperty(name="Per job", default=caps["job_cap"], min=0.0, precision=2, unit='NONE', update=_caps_changed)
    wm.lampway_onboarding_day_cap = FloatProperty(name="Per day", default=caps["day_cap"], min=0.0, precision=2, update=_caps_changed)
    wm.lampway_onboarding_above = FloatProperty(name="Click above", default=caps["above"], min=0.0, precision=2, update=_caps_changed)


def unregister():
    for name in _PROPS:
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    WALK.update(walk=None, anchor=None)
