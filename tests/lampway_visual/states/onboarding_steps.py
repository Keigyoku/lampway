# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cloud audit F23 (2026-10-06): the first-run setup walked by real clicks. Step 2 opens under the pointer; the run clicks its
Continue, then the next step's Continue, recording each step's dialog from the QA dump: where Continue and Back are, which
step's words are on screen (an earlier step still drawn is the bug), and whether a label's text is wider than its row (cut).
Fake server: the walk is built here with the 24 routes the server ships, all off."""

import json

SETTLE_TICKS = 40          # three steps, each opened by a click and read one second later
STEPS = []
STATE = {"phase": 0, "clicks": []}
ROUTES = [{"id": f"route_{i}", "label": f"Route {i} with a longer name", "enabled": False, "hosts": [f"host{i}.example"],
           "privacy_class": "unknown", "retention": "unknown", "training": "unknown"} for i in range(22)]
ROUTES += [{"id": "openrouter", "label": "OpenRouter", "enabled": False, "hosts": ["openrouter.ai"], "privacy_class": "conditional",
            "retention": "per model", "training": "per model"},
           {"id": "chatgpt_plan", "label": "ChatGPT plan", "enabled": False, "hosts": ["chatgpt.com"], "privacy_class": "unknown",
            "retention": "unknown", "training": "unknown"}]
WORDS = {2: "The agent thinks with the provider", 3: "Every route is off until", 4: "OpenRouter, in dollars"}


def _popup(bpy):
    dump = json.loads(bpy.context.window_manager.mixar_qa_ui_dump)
    return [w for w in dump["widgets"] if w.get("popup")]


def _read(bpy, step):
    import blf
    widgets = _popup(bpy)
    cont = next((w["rect"] for w in widgets if (w.get("text") or "").startswith("Continue")), None)
    back = next((w["rect"] for w in widgets if w.get("text") == "Back"), None)
    texts = [w.get("text") or "" for w in widgets]
    shown = sorted(n for n, words in WORDS.items() if any(t.startswith(words) for t in texts))
    cut = []
    ui = bpy.context.preferences.system.ui_scale
    blf.size(0, 11 * ui)
    for w in widgets:
        if w.get("type") == "LABEL" or (w.get("text") and not w.get("op") and not w.get("prop")):
            width = w["rect"][2] - w["rect"][0]
            if blf.dimensions(0, w.get("text") or "")[0] > width + 2:
                cut.append(w.get("text"))
    STEPS.append({"step": step, "continue": cont, "back": back, "shown": shown, "cut": cut,
                  "labels": [[w.get("text"), w["rect"], round(blf.dimensions(0, w.get("text") or "")[0])] for w in widgets
                             if w.get("text") and not w.get("op") and not w.get("prop")]})
    import os
    import sys
    out = sys.argv[sys.argv.index("--") + 2]      # the run's own directory (driver.py's out dir)
    if os.path.isdir(out):
        win = bpy.context.window_manager.windows[0]
        win.mixar_qa_capture_frame(filepath=os.path.join(out, f"step{step}.png"), x=0, y=0, width=win.width, height=win.height)
    return cont


def _click(bpy, rect):
    win = bpy.context.window_manager.windows[0]
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    STATE["clicks"].append([x, y])
    with bpy.context.temp_override(window=win):
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
        win.event_simulate(type='LEFTMOUSE', value='PRESS', x=x, y=y)
        win.event_simulate(type='LEFTMOUSE', value='RELEASE', x=x, y=y)


def _walk(bpy):
    step = 2 + STATE["phase"]
    cont = _read(bpy, step)
    STATE["phase"] += 1
    if step < 4 and cont is not None:
        _click(bpy, cont)
        return 1.0
    return None


def setup(bpy):
    import sys
    from mixar.modules.lampway_tools import onboarding as ob
    ui = sys.modules["mixar.modules.lampway_tools.ui.onboarding"]
    walk = ob.Walk(routes=ROUTES, provider="mock")
    ui.WALK["walk"] = walk
    wm = bpy.context.window_manager
    wm.lampway_onboarding_routes.clear()
    for route in walk.routes:
        item = wm.lampway_onboarding_routes.add()
        item.route_id = route["id"]
    walk.clicks.clear()
    wm.lampway_onboarding_provider = "mock"
    walk.next()
    win = wm.windows[0]
    x, y = win.width // 2, win.height // 2
    with bpy.context.temp_override(window=win):
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    area = max(win.screen.areas, key=lambda a: a.width * a.height)
    with bpy.context.temp_override(window=win, area=area):
        bpy.ops.lampway.onboarding('INVOKE_DEFAULT')
    bpy.app.timers.register(lambda: _walk(bpy), first_interval=1.5)


def surfaces(bpy, dump):
    return {}


def regions(bpy):
    return {}


def facts(bpy, dump):
    return {"steps": STEPS, "clicks": STATE["clicks"]}
