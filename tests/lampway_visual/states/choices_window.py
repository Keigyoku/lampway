# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Choices window as a pop-out: Plates served by a fallback (Tripo's route is off), an agent's proposal waiting, an
option whose provider keeps what it is sent, acknowledged (the eye). Fake cache: nothing reaches a server."""

SETTLE_TICKS = 12


def _opt(oid, rank, **kw):
    o = {"id": oid, "label": oid.split(":", 1)[-1], "provider": oid.split(":")[0], "runs": "openrouter.ai",
         "connection": {"id": "openrouter", "state": "connected"}, "route": {"id": "openrouter", "on": True},
         "cost": {"basis": "measured", "amount": 0.14, "unit": "USD", "per": "image", "measured_at": "2026-10-05"},
         "retention": "zdr", "acknowledged": None, "quality": [{"metric": "IoU", "value": 0.987}], "verdict": "ok", "rank": rank}
    o.update(kw)
    return o


PLATES = {"id": "images.plates", "label": "Plates", "group": "images", "cue": "fallback", "why": "studio:tripo is off",
          "now": {"option": "openrouter:openai/gpt-image-2.5-flare", "label": "openai/gpt-image-2.5-flare", "scope": "global", "reason": "fallback"},
          "chain": [_opt("studio:tripo", 0, runs="tripo3d.ai", connection={"id": "studio:tripo", "state": "connected"},
                         route={"id": "studio:tripo", "on": False}, retention="kept", verdict="skipped",
                         skipped={"constraint": "route", "text": "route studio:tripo is off"}),
                    _opt("openrouter:openai/gpt-image-2.5-flare", 1),
                    _opt("openrouter:sourceful/riverflow-v2.5-pro", 2, retention="kept", acknowledged="2026-10-06T10:00:00Z")],
          "scopes": {"global": {}}, "params": {}}
LISTING = {"groups": [{"id": "agents", "label": "Agents", "purposes": [{"id": "agent.main", "label": "Main agent", "group": "agents", "cue": "preferred",
                                                                         "now": {"option": "chatgpt_plan:gpt-5.5", "label": "gpt-5.5", "scope": "global"}}]},
                      {"id": "images", "label": "Images", "purposes": [PLATES]},
                      {"id": "tracking", "label": "Tracking and motion", "purposes": [{"id": "track.body_3d", "label": "Body tracking", "group": "tracking", "cue": "unset", "now": None}]}]}
PROPOSALS = [{"id": "p1", "purpose": "images.plates", "option": "openrouter:sourceful/riverflow-v2.5-pro", "state": "open", "why": "flatter albedo"}]


def setup(bpy):
    from mixar.modules.lampway_tools import choices_state
    choices_state.update(LISTING, PROPOSALS)
    choices_state.STATE["selected"] = "images.plates"
    choices_state.STATE["detail"] = PLATES
    win = bpy.context.window_manager.windows[0]
    view = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in view.regions if r.type == 'WINDOW')

    def pop():
        with bpy.context.temp_override(window=win, area=view, region=region):
            bpy.ops.wm.call_panel(name="LAMPWAY_PT_choices_popout", keep_open=True)
        return None

    bpy.app.timers.register(pop, first_interval=0.5)


def surfaces(bpy, dump):
    return {}


def regions(bpy):
    return {}


def facts(bpy, dump):
    popup = [w for w in dump["widgets"] if w.get("popup")]
    return {"texts": [w.get("text") for w in popup if w.get("text")], "ops": [(w.get("op"), w.get("text")) for w in popup if w.get("op")]}
