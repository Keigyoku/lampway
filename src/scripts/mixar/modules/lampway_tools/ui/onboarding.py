# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The first run's steps 2-4 (facelift contract 02, P1, DESIGN.md 13): a dialog per step on the lit path. Step 1 (language and keys) is the
splash's Quick Setup, whose Continue opens this; the last button names the outcome ("Continue with 1 route on"), saves the preferences as
Quick Setup always did and writes the routes and caps to Lampway's server.

Every route row is one line: the shield (its policy is the hover text), the name with its host, the switch. The switch alone says on or off.
Nothing here reaches the network in a draw: the walk is read once, when the dialog opens."""

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Operator, PropertyGroup

from mixar.modules.lampway_tools import onboarding as ob

WALK = {"walk": None}
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
    if walk.step >= 2 and not walk.online:
        body.label(text=ob.OFFLINE, icon='ERROR')
        body.label(text="Continue saves your language and keys only")
        return
    wm = getattr(bpy.context, "window_manager", None)
    if walk.step == 2:
        body.label(text="The agent thinks with the provider you pick here; nothing is sent until you use it")
        body.prop(wm, "lampway_onboarding_provider", text="")
        if why := walk.refusal():
            body.label(text=why, icon='ERROR')
    elif walk.step == 3:
        body.label(text="Every route is off until you switch it on")
        draw_routes(body, walk, rows)
    elif walk.step == 4:
        body.label(text="OpenRouter, in dollars: a click above the first amount, never past the caps")
        body.prop(wm, "lampway_onboarding_above", text="Click above")
        body.prop(wm, "lampway_onboarding_job_cap", text="Per job")
        body.prop(wm, "lampway_onboarding_session_cap", text="Per session")


def _route_switched(self, context):
    walk = WALK["walk"]
    if walk is not None and walk.chosen.get(self.route_id) != self.enabled:
        walk.click_route(self.route_id, self.enabled)


def _provider_picked(self, context):
    if WALK["walk"] is not None:
        WALK["walk"].provider = self.lampway_onboarding_provider


def _caps_changed(self, context):
    if WALK["walk"] is not None:
        WALK["walk"].caps = {"job_cap": self.lampway_onboarding_job_cap, "session_cap": self.lampway_onboarding_session_cap,
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
        text = walk.continue_label() if walk.step == len(ob.STEPS) and walk.online else "Continue"
        return context.window_manager.invoke_props_dialog(self, width=640, title=ob.STEPS[walk.step - 1], confirm_text=text)

    def draw(self, context):
        walk = WALK["walk"]
        if walk is not None:
            draw_step(self.layout, walk, context.window_manager.lampway_onboarding_routes)
            if walk.step > 2:
                self.layout.operator("lampway.onboarding_back", text="Back")

    def execute(self, context):
        walk = WALK["walk"]
        if walk is None:
            return {'CANCELLED'}
        if walk.step < len(ob.STEPS):
            why = walk.next()
            if why:
                self.report({'ERROR'}, why)
            return bpy.ops.lampway.onboarding('INVOKE_DEFAULT')
        try:
            saved = walk.finish(_door() if walk.online else None)
        except Exception as exc:  # noqa: BLE001  (the server refused or went away: say so, keep the walk to try again)
            self.report({'ERROR'}, f"Lampway's server did not take the setup: {exc}")
            return bpy.ops.lampway.onboarding('INVOKE_DEFAULT')
        bpy.ops.wm.save_userpref()
        WALK["walk"] = None
        self.report({'INFO'}, "Saved: " + ", ".join(saved))
        return {'FINISHED'}


class LAMPWAY_OT_onboarding_back(Operator):
    """The step before"""
    bl_idname = "lampway.onboarding_back"
    bl_label = "Back"

    def execute(self, context):
        if WALK["walk"] is not None:
            WALK["walk"].back()
        return bpy.ops.lampway.onboarding('INVOKE_DEFAULT')


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


classes = (LampwayOnboardingRoute, LAMPWAY_OT_onboarding, LAMPWAY_OT_onboarding_back, LAMPWAY_OT_onboarding_policy)
_PROPS = ("lampway_onboarding_routes", "lampway_onboarding_provider", "lampway_onboarding_job_cap", "lampway_onboarding_session_cap",
          "lampway_onboarding_above")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.lampway_onboarding_routes = CollectionProperty(type=LampwayOnboardingRoute)
    wm.lampway_onboarding_provider = EnumProperty(name="Main agent", items=PROVIDERS, default="chatgpt_plan", update=_provider_picked)
    caps = ob.DEFAULT_CAPS
    wm.lampway_onboarding_job_cap = FloatProperty(name="Per job", default=caps["job_cap"], min=0.0, precision=2, unit='NONE', update=_caps_changed)
    wm.lampway_onboarding_session_cap = FloatProperty(name="Per session", default=caps["session_cap"], min=0.0, precision=2, update=_caps_changed)
    wm.lampway_onboarding_above = FloatProperty(name="Click above", default=caps["above"], min=0.0, precision=2, update=_caps_changed)


def unregister():
    for name in _PROPS:
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    WALK["walk"] = None
