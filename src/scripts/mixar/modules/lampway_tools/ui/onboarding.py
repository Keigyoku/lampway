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

import textwrap

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator, PropertyGroup

from mixar.modules.lampway_tools import capabilities_face as face
from mixar.modules.lampway_tools import onboarding as ob

def n_(msgid):
    """Marks a message for the catalogue; it is translated where it is drawn."""
    return msgid


def iface_(msgid):
    out = bpy.app.translations.pgettext_iface(msgid)
    return out if isinstance(out, str) else msgid      # a stubbed bpy (the unit tests) translates nothing


WALK = {"walk": None, "anchor": None, "capability_page": 0}
WRAP = 60              # characters per body line: the body column holds about 78 at any UI scale (it scales with the text)
CAPABILITY_PAGE_ROWS = 24  # content rows, leaving room for the introduction, page controls and dialog navigation at 1000px
STEP_TEXT = {"agent": n_("The agent thinks with the provider you pick here; nothing is sent until you use it"),
             "routes": n_("Every route is off until you switch it on"),
             "capabilities": n_("Your agent can do only what you tick here. Change it any time in Choices and privacy."),
             "spending": n_("OpenRouter, in dollars: a click above the first amount, never past the caps")}
OFFLINE_NEXT = n_("Continue saves your language and keys only")
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
    col.separator()
    if walk.step > 2:    # Back lives under the steps, never on the bottom row where the step before had Continue (audit F23)
        col.operator("lampway.onboarding_back", text="Back")
    else:
        col.label(text="")


def wrapped(layout, text, icon='NONE'):
    """A sentence as whole lines: a label never cuts it to an ellipsis (audit F23). Translated whole, then wrapped."""
    for i, line in enumerate(textwrap.wrap(iface_(text), WRAP)):
        layout.label(text=line, icon=icon if i == 0 else 'NONE', translate=False)


def _lines(text) -> int:
    return len(textwrap.wrap(iface_(text), WRAP))


def body_rows(walk) -> int:
    """Legacy walks keep their size; capability-enabled walks size each step to its actual content."""
    if not walk.online:
        return 1 + _lines(ob.OFFLINE) + _lines(OFFLINE_NEXT)
    refusal = max((_lines(why) for why in [walk.refusal()] if why), default=0)
    if walk.capability_rows is not None:
        return {"agent": _lines(STEP_TEXT["agent"]) + 1 + refusal,
                "routes": _lines(STEP_TEXT["routes"]) + len(walk.routes),
                "spending": _lines(STEP_TEXT["spending"]) + 3,
                "capabilities": capability_rows(walk)}.get(walk.kind, 0)
    return max(_lines(STEP_TEXT["agent"]) + 1 + max(refusal, 1), _lines(STEP_TEXT["routes"]) + len(walk.routes),
               _lines(STEP_TEXT["spending"]) + 3)


def capability_pages(walk) -> list:
    """Stable risk-ordered pages reserve possible warnings, without drawing empty padding.

    Page membership depends on metadata, not ticks, so enabling a row cannot
    move that row or another row onto a different page beneath the pointer.
    """
    pages, page, rows, risk = [], [], 0, None
    for group in face.groups(walk.capability_rows):
        for cap in group["rows"]:
            cost = 1 + int(face.needs_confirm(cap)) + int(bool(cap.get("routes")))
            heading = 2 if risk != group["risk"] else 0
            if page and rows + heading + cost > CAPABILITY_PAGE_ROWS:
                pages.append(page)
                page, rows, risk = [], 0, None
                heading = 2
            page.append(cap)
            rows += heading + cost
            risk = group["risk"]
    if page:
        pages.append(page)
    return pages


def _capability_page(walk):
    pages = capability_pages(walk)
    index = max(0, min(int(WALK.get("capability_page", 0)), max(len(pages) - 1, 0)))
    return pages, index, pages[index] if pages else []


def capability_rows(walk) -> int:
    """Rows actually shown on this page; unticked warnings reserve no dialog height."""
    if walk.capability_rows is None:
        return 0
    pages, _, caps = _capability_page(walk)
    return (_lines(STEP_TEXT["capabilities"]) + 2 * len(face.groups(caps)) + len(caps)
            + sum(bool(walk.capability_warning(c["id"])) + bool(walk.capability_note(c["id"])) for c in caps)
            + int(len(pages) > 1))


def draw_routes(layout, walk, rows):
    for row_data in rows:
        route = _route(walk, row_data.route_id)
        row = layout.row(align=True)
        op = row.operator("lampway.onboarding_policy", text="", icon=SHIELD.get(route.get("privacy_class"), 'LAMPWAY_SHIELD_UNKNOWN'), emboss=False)
        op.route_id = route["id"]
        hosts = route.get("hosts") or []
        row.label(text=f"{route['label']}   {hosts[0]}" if hosts else route["label"])
        row.prop(row_data, "enabled", text="")


def draw_capabilities(layout, walk, cap_rows) -> int:
    """One tick per capability, grouped by risk; the warning and the route note sit under the ones that are ticked. Returns its rows."""
    items = {r.cap_id: r for r in cap_rows}
    wrapped(layout, STEP_TEXT["capabilities"])
    drawn = _lines(STEP_TEXT["capabilities"])
    pages, page, caps = _capability_page(walk)
    for group in face.groups(caps):
        layout.separator()
        layout.label(text=group["title"])
        drawn += 2
        for cap in group["rows"]:
            item = items.get(cap["id"])
            if item is None:
                continue
            row = layout.row(align=True)
            row.operator("lampway.onboarding_capability_info", text="", icon='INFO', emboss=False).cap_id = cap["id"]
            row.label(text=cap.get("label") or cap["id"])
            row.prop(item, "enabled", text="")
            drawn += 1
            for text, icon in ((walk.capability_warning(cap["id"]), 'ERROR'), (walk.capability_note(cap["id"]), 'INFO')):
                if text:
                    layout.label(text=text, icon=icon)
                    drawn += 1
    if len(pages) > 1:
        row = layout.row(align=True)
        previous = row.row(align=True)
        previous.enabled = page > 0
        previous.operator("lampway.onboarding_capability_page", text="Previous").direction = -1
        row.label(text=iface_(n_("Page {page} of {pages}")).format(page=page + 1, pages=len(pages)), translate=False)
        following = row.row(align=True)
        following.enabled = page + 1 < len(pages)
        following.operator("lampway.onboarding_capability_page", text="Next").direction = 1
        drawn += 1
    return drawn


def draw_step(layout, walk, rows, cap_rows=()):
    split = layout.split(factor=0.34)
    draw_rail(split.column(), walk)
    body = split.column()
    drawn = _draw_body(body, walk, rows, cap_rows)
    for _ in range(body_rows(walk) - drawn):
        body.label(text="")


def _draw_body(body, walk, rows, cap_rows=()) -> int:
    """Draw the step's body; return how many rows it took."""
    if walk.step >= 2 and not walk.online:
        wrapped(body, ob.OFFLINE, icon='ERROR')
        wrapped(body, OFFLINE_NEXT)
        return _lines(ob.OFFLINE) + _lines(OFFLINE_NEXT)
    wm = getattr(bpy.context, "window_manager", None)
    kind = walk.kind
    if kind == "agent":
        wrapped(body, STEP_TEXT["agent"])
        body.prop(wm, "lampway_onboarding_provider", text="")
        why = walk.refusal()
        if why:
            wrapped(body, why, icon='ERROR')
        return _lines(STEP_TEXT["agent"]) + 1 + (_lines(why) if why else 0)
    if kind == "routes":
        wrapped(body, STEP_TEXT["routes"])
        draw_routes(body, walk, rows)
        return _lines(STEP_TEXT["routes"]) + len(rows)
    if kind == "capabilities":
        return draw_capabilities(body, walk, cap_rows)
    if kind == "spending":
        wrapped(body, STEP_TEXT["spending"])
        body.prop(wm, "lampway_onboarding_above", text="Click above")
        body.prop(wm, "lampway_onboarding_job_cap", text="Per job")
        body.prop(wm, "lampway_onboarding_day_cap", text="Per day")
        return _lines(STEP_TEXT["spending"]) + 3
    return 0


def _redraw_all(context):
    """The step before's dialog must not stay painted behind this one (audit F23)."""
    for area in [*context.window.screen.areas, *context.window.global_areas]:
        area.tag_redraw()


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
        WALK["walk"].caps = {"job_cap": self.lampway_onboarding_job_cap, "day_cap": self.lampway_onboarding_day_cap,
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
    WALK["capability_page"] = 0
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
        # every step opens where the first did: one size, one place, so Continue never moves (audit F23)
        if WALK["anchor"] is None:
            WALK["anchor"] = (event.mouse_x, event.mouse_y)
        elif (event.mouse_x, event.mouse_y) != WALK["anchor"]:
            context.window.cursor_warp(*WALK["anchor"])
        _redraw_all(context)
        text = walk.continue_label() if walk.step == len(walk.steps) and walk.online else "Continue"
        return context.window_manager.invoke_props_dialog(self, width=640, title=walk.steps[walk.step - 1], confirm_text=text)

    def draw(self, context):
        walk = WALK["walk"]
        if walk is not None:
            draw_step(self.layout, walk, context.window_manager.lampway_onboarding_routes, context.window_manager.lampway_onboarding_caps)

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
        WALK.update(walk=None, anchor=None, capability_page=0)
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


class LAMPWAY_OT_onboarding_capability_page(Operator):
    """Show another page of capabilities without changing any choices"""
    bl_idname = "lampway.onboarding_capability_page"
    bl_label = "More capabilities"
    direction: IntProperty(default=1, min=-1, max=1, options={'SKIP_SAVE'})

    def execute(self, context):
        walk = WALK["walk"]
        if walk is None or walk.kind != "capabilities":
            return {'CANCELLED'}
        pages, index, _ = _capability_page(walk)
        WALK["capability_page"] = max(0, min(index + self.direction, len(pages) - 1))
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


classes = (LampwayOnboardingRoute, LampwayOnboardingCapability, LAMPWAY_OT_onboarding, LAMPWAY_OT_onboarding_back, LAMPWAY_OT_onboarding_capability_page, LAMPWAY_OT_onboarding_policy,
           LAMPWAY_OT_onboarding_capability_info)
_PROPS = ("lampway_onboarding_routes", "lampway_onboarding_caps", "lampway_onboarding_provider", "lampway_onboarding_job_cap", "lampway_onboarding_day_cap",
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
    wm.lampway_onboarding_day_cap = FloatProperty(name="Per day", default=caps["day_cap"], min=0.0, precision=2, update=_caps_changed)
    wm.lampway_onboarding_above = FloatProperty(name="Click above", default=caps["above"], min=0.0, precision=2, update=_caps_changed)


def unregister():
    for name in _PROPS:
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    WALK.update(walk=None, anchor=None, capability_page=0)
