# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared by the Connections states: the window as a pop-out over a fake cache (nothing reaches a server)."""

SETTLE_TICKS = 12
VIEWS = [
    {"id": "chatgpt_plan", "label": "ChatGPT plan", "group": "Agents", "kind": "oauth", "state": "connected", "qualifiers": [],
     "route": {"id": "chatgpt_plan", "on": True}, "active_source": {"mode": "signin", "label": "your login"},
     "identity": {"masked": "c•••@g•••.com", "plan": "Plus plan"}, "check_age_s": 40, "fingerprint": {}, "next_step": ""},
    {"id": "openrouter", "label": "OpenRouter", "group": "Agents", "kind": "key", "state": "connected", "qualifiers": ["warning"],
     "route": {"id": "openrouter", "on": True}, "active_source": {"mode": "env", "label": "OPENROUTER_API_KEY"}, "identity": {},
     "check_age_s": 300, "fingerprint": {"last4": "7f3a"}, "next_step": ""},
    {"id": "studio:meshy", "label": "Meshy", "group": "Studios", "kind": "key", "state": "missing", "qualifiers": [],
     "route": {"id": "studio:meshy", "on": False}, "active_source": {}, "identity": {}, "check_age_s": None, "fingerprint": {},
     "next_step": "Meshy is not connected: connect it in Connections"},
    {"id": "higgsfield", "label": "Higgsfield", "group": "Video and images", "kind": "oauth", "state": "signed_out", "qualifiers": [],
     "route": {"id": "higgsfield", "on": False}, "active_source": {}, "identity": {}, "check_age_s": None, "fingerprint": {},
     "next_step": "Higgsfield is signed out: sign in again in Connections"},
]


def open_window(bpy, selected, waiting=()):
    from mixar.modules.lampway_tools import connections_state
    connections_state.update({"store": {"kind": "keyring"}, "connections": VIEWS})
    connections_state.STATE["selected"] = selected
    connections_state.STATE["waiting"] = set(waiting)
    bpy.context.window_manager.lampway_conn_mode = "manual"
    win = bpy.context.window_manager.windows[0]
    view = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in view.regions if r.type == 'WINDOW')

    def pop():
        with bpy.context.temp_override(window=win, area=view, region=region):
            bpy.ops.wm.call_panel(name="LAMPWAY_PT_connections_popout", keep_open=True)
        return None

    bpy.app.timers.register(pop, first_interval=0.5)


def surfaces(bpy, dump):
    return {}


def regions(bpy):
    return {}


def facts(bpy, dump):
    popup = [w for w in dump["widgets"] if w.get("popup")]
    return {"texts": [w.get("text") for w in popup if w.get("text")],
            "props": [w.get("prop") for w in popup if w.get("prop")],
            "secret": [w.get("secret") for w in popup if w.get("prop") == "lampway_conn_secret"]}
