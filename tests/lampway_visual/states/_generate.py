# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared by the generation states (facelift contract 08): the island on its Image tab, the pump fed a fake server
answer (its client is swapped, and the status bar's refresh is stopped: nothing reaches a network, nothing is spent).
The request the pump reads from the tab is fixed here, so the states do not depend on a loaded catalogue."""

import os
import sys

ROUTES = [{"id": "openrouter", "label": "OpenRouter", "hosts": ["openrouter.ai"]}]
POLICY = {"click": "above", "above": 0.25, "job_cap": 1.0, "session_cap": 3.0, "spent": 0.31}
OWNER = "MixieMoodboardTabImageGenProps"
OUT = {"island": None}


def answer(amount, needs_click):
    return {"provider": "openrouter", "route": "openrouter", "basis": "1 x $0.07 per image", "policy": dict(POLICY),
            "price": {"kind": "estimate", "amount": amount, "unit": "USD", "source": "about $0.07 per image (measured), not read back",
                      "basis": "1 x $0.07 per image"}, "needs_click": needs_click, "refused": None}


class FakeClient:
    calls = []

    def __init__(self, reply):
        self.reply = reply

    def generate_estimate(self, service, model, params, references):
        FakeClient.calls.append(model)
        return self.reply


def feed(bpy, reply, route_on=True):
    statusbar = sys.modules["mixar.modules.lampway_tools.ui.statusbar"]
    pump = sys.modules["mixar.modules.lampway_tools.ui.generate_pump"]
    from mixar.modules.lampway_tools import statusbar_state as S
    if bpy.app.timers.is_registered(statusbar._tick):
        bpy.app.timers.unregister(statusbar._tick)
    S.update(egress={"routes": [dict(r, enabled=route_on) for r in ROUTES], "indicator": {}}, spend={}, studio={})
    pump.CLIENT_FACTORY = lambda: FakeClient(reply)
    pump._request = lambda context: (OWNER, "image_gen", "openai/gpt-5-image-mini", {"number_of_images": 1}, 0)
    bpy.context.window_manager.mixar_bubble_tab = 'IMAGE'


def _island(bpy):
    return next((w for w in bpy.context.window_manager.windows if w.parent is not None and w.width > 200), None)


def surfaces(bpy, dump):
    isl = _island(bpy)
    if isl is None:
        return {}
    out_dir = sys.argv[sys.argv.index("--") + 2]
    isl.mixar_qa_capture_frame(filepath=os.path.join(out_dir, "frame.png"), x=0, y=0, width=isl.width, height=isl.height)
    OUT["island"] = [isl.width, isl.height]
    ptr = next((w["ptr"] for w in dump.get("windows", []) if w["size"] == [isl.width, isl.height]), None)
    gen = next((w["rect"] for w in dump["widgets"] if w.get("w") == ptr and w.get("op") == "MIXIE_OT_moodboard_prompt_generate"), None)
    if not gen:
        return {}
    return {"generate_bed": (gen[0] + 6, (gen[1] + gen[3]) // 2)}


def regions(bpy):
    return {}


def facts(bpy, dump):
    wm = bpy.context.window_manager
    isl = _island(bpy)
    ptr = next((w["ptr"] for w in dump.get("windows", []) if isl and w["size"] == [isl.width, isl.height]), None)
    gen = [w for w in dump["widgets"] if w.get("w") == ptr and w.get("op") == "MIXIE_OT_moodboard_prompt_generate"]
    face = {k: getattr(wm, "lampway_gen_" + k, None) for k in ("estimate", "cap_job", "cap_session", "route", "content", "button",
                                                             "button_kind", "policy", "refusal", "owner")}
    return dict(OUT, face=face, generate=[{k: w.get(k) for k in ("text", "rect", "enabled", "tip", "mixar_variant") if k in w} for w in gen],
                estimate_calls=len(FakeClient.calls))
