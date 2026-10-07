# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The first run's steps 2-5 (facelift contract 02, P1, DESIGN.md 13): a dialog per step on the lit path. Step 1 (language and keys) is the
splash's Quick Setup, whose Continue opens this; the last button names the outcome ("Continue with 1 route on"), saves the preferences as
Quick Setup always did and writes the routes, the capabilities and the caps to Lampway's server. A server without Capabilities has no step 4:
the walk is the four steps it was.

Every route row is one line: the shield (its policy is the hover text), the name with its host, the switch. The switch alone says on or off.
The capabilities step ("What may your agent do?", E2) is one line per capability under its risk: an info button (its sentence is the hover
text), the name, the tick, with the server's defaults ticked; a ticked one that runs code or acts outside Lampway says what it allows, and a
ticked one whose route is off says where to switch it.
Nothing here reaches the network in a draw: the walk is read once, when the dialog opens."""

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Operator, PropertyGroup

from mixar.modules.lampway_tools import capabilities_face as face
from mixar.modules.lampway_tools import onboarding as ob

WALK = {"walk": None}
SHIELD = {"ok": 'LAMPWAY_SHIELD', "conditional": 'LAMPWAY_SHIELD_HALF', "retains": 'LAMPWAY_SHIELD_OPEN', "unknown": 'LAMPWAY_SHIELD_UNKNOWN'}
PROVIDERS = (("chatgpt_plan", "ChatGPT plan", "Your ChatGPT subscription, signed in from Providers"),
             ("openrouter", "OpenRouter", "Pay per use with your OpenRouter key"),
             ("anthropic", "Anthropic API key", "Pay per use with your Anthropic key"),
             ("openai", "OpenAI API key", "Pay per use with your OpenAI key"),
             ("mock", "No agent", "A stand-in that answers on this machine and thinks nothing"))


def _door():
    from mixar.modules.lampway_tools.capabilities_client import CapabilitiesClient
    from mixar.modules.lampway_tools.egress_client import EgressClient

    class Door(EgressClient, CapabilitiesClient):
        def egress(self):
            return self._call("GET", "/app/egress", timeout=5)

    return Door()


def policy_text(route) -> str:
    hosts = ", ".join(route.get("hosts") or []) or "a host you configure"
    return f"{route['label']} ({hosts}). Keeps: {route.get('retention') or 'unknown'}. Trains on it: {route.get('training') or 'unknown'}."


def _route(walk, route_id):
    return next(r for r in walk.routes if r["id"] == route_id)


def capability_text(row) -> str:
    """What a capability's info button says: its sentence."""
    return row.get("does") or row.get("label") or row["id"]


def draw_rail(layout, walk):
    col = layout.column(align=True)
    for i, name in enumerate(walk.steps, start=1):
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


def draw_capabilities(layout, walk, cap_rows):
    """One tick per capability, grouped by risk; the warning and the route note sit under the ones that are ticked."""
    items = {r.cap_id: r for r in cap_rows}
    layout.label(text="Your agent can do only what you tick here. Change it any time in Choices and privacy.")
    for group in face.groups(walk.capability_rows):
        layout.separator()
        layout.label(text=group["title"])
        for cap in group["rows"]:
            item = items.get(cap["id"])
            if item is None:
                continue
            row = layout.row(align=True)
            row.operator("lampway.onboarding_capability_info", text="", icon='INFO', emboss=False).cap_id = cap["id"]
            row.label(text=cap.get("label") or cap["id"])
            row.prop(item, "enabled", text="")
            for text, icon in ((walk.capability_warning(cap["id"]), 'ERROR'), (walk.capability_note(cap["id"]), 'INFO')):
                if text:
                    layout.label(text=text, icon=icon)


def draw_step(layout, walk, rows, cap_rows=()):
    split = layout.split(factor=0.34)
    draw_rail(split.column(), walk)
    body = split.column()
    if walk.step >= 2 and not walk.online:
        body.label(text=ob.OFFLINE, icon='ERROR')
        body.label(text="Continue saves your language and keys only")
        return
    wm = getattr(bpy.context, "window_manager", None)
    kind = walk.kind
    if kind == "agent":
        body.label(text="The agent thinks with the provider you pick here; nothing is sent until you use it")
        body.prop(wm, "lampway_onboarding_provider", text="")
        if why := walk.refusal():
            body.label(text=why, icon='ERROR')
    elif kind == "routes":
        body.label(text="Every route is off until you switch it on")
        draw_routes(body, walk, rows)
    elif kind == "capabilities":
        draw_capabilities(body, walk, cap_rows)
    elif kind == "spending":
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


def _capability_switched(self, context):
    walk = WALK["walk"]
    if walk is not None and walk.capability_chosen.get(self.cap_id) != self.enabled:
        walk.click_capability(self.cap_id, self.enabled)


def _caps_changed(self, context):
    if WALK["walk"] is not None:
        WALK["walk"].caps = {"job_cap": self.lampway_onboarding_job_cap, "session_cap": self.lampway_onboarding_session_cap,
                             "above": self.lampway_onboarding_above}


class LampwayOnboardingRoute(PropertyGroup):
    route_id: StringProperty()
    enabled: BoolProperty(name="On", description="Let data go over this route", update=_route_switched)


class LampwayOnboardingCapability(PropertyGroup):
    cap_id: StringProperty()
    enabled: BoolProperty(name="On", description="Let your agent do this", update=_capability_switched)


def _begin(context):
    walk = ob.Walk.read(_door())
    WALK["walk"] = walk
    wm = context.window_manager
    wm.lampway_onboarding_routes.clear()
    for route in walk.routes:
        item = wm.lampway_onboarding_routes.add()
        item.route_id = route["id"]
        item.enabled = walk.chosen[route["id"]]
    wm.lampway_onboarding_caps.clear()
    for cap in walk.capability_rows or []:
        item = wm.lampway_onboarding_caps.add()
        item.cap_id = cap["id"]
        item.enabled = walk.capability_chosen[cap["id"]]
    walk.clicks.clear()   # mirroring the server's state is not a click
    walk.capability_clicks.clear()
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
        text = walk.continue_label() if walk.step == len(walk.steps) and walk.online else "Continue"
        return context.window_manager.invoke_props_dialog(self, width=640, title=walk.steps[walk.step - 1], confirm_text=text)

    def draw(self, context):
        walk = WALK["walk"]
        if walk is not None:
            draw_step(self.layout, walk, context.window_manager.lampway_onboarding_routes, context.window_manager.lampway_onboarding_caps)
            if walk.step > 2:
                self.layout.operator("lampway.onboarding_back", text="Back")

    def execute(self, context):
        walk = WALK["walk"]
        if walk is None:
            return {'CANCELLED'}
        if walk.step < len(walk.steps):
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


class LAMPWAY_OT_onboarding_capability_info(Operator):
    """What this capability lets your agent do"""
    bl_idname = "lampway.onboarding_capability_info"
    bl_label = "What it does"
    cap_id: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        walk = WALK["walk"]
        try:
            return capability_text(walk._capability(properties.cap_id))
        except (AttributeError, StopIteration, TypeError):
            return cls.__doc__

    def execute(self, context):
        return {'FINISHED'}


classes = (LampwayOnboardingRoute, LampwayOnboardingCapability, LAMPWAY_OT_onboarding, LAMPWAY_OT_onboarding_back, LAMPWAY_OT_onboarding_policy,
           LAMPWAY_OT_onboarding_capability_info)
_PROPS = ("lampway_onboarding_routes", "lampway_onboarding_caps", "lampway_onboarding_provider", "lampway_onboarding_job_cap", "lampway_onboarding_session_cap",
          "lampway_onboarding_above")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.lampway_onboarding_routes = CollectionProperty(type=LampwayOnboardingRoute)
    wm.lampway_onboarding_caps = CollectionProperty(type=LampwayOnboardingCapability)
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
