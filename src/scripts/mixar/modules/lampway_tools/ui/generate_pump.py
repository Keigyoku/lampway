# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The pump behind the island's Image and Video tabs (facelift contract 08). It computes nothing itself: on a change of
the tab's request (service, model, parameters, reference count) it waits 300 ms, asks the server's
/app/generate/estimate off the main thread, and a timer turns the answer and the status bar's last egress answer into
the WindowManager strings the native media pane draws (``generate_face.face``). A route that is off is refused without
asking anything."""

import json
import threading
import time

import bpy
from bpy.props import FloatProperty, StringProperty

from mixar.modules.lampway_tools import generate_face as G
from mixar.modules.lampway_tools import statusbar_state as S
from mixar.modules.lampway_tools import status_client, studio_client

CLIENT_FACTORY = lambda: status_client.StatusClient()  # noqa: E731  (tests swap it)
DEBOUNCE_S = 0.3
TICK_S = 0.1
STRINGS = ("estimate", "estimate_kind", "estimate_tip", "cap_job", "cap_job_level", "cap_session", "route", "content",
           "button", "button_kind", "policy", "refusal", "last_run")
FLOATS = ("cap_job_fill", "cap_session_fill")
PUMP = {"key": None, "changed": 0.0, "asked": None, "answer": None, "inflight": False, "result": None, "owner": ""}


def _request(context):
    """(owner, service, model, params, references) of the tab the island shows, or None when it has no model yet."""
    wm, scene = context.window_manager, context.scene
    sidebar = getattr(scene, "mixie_moodboard_sidebar", None)
    if sidebar is None:
        return None
    video = getattr(wm, "mixar_bubble_tab", "IMAGE") == "VIDEO"
    tab = getattr(sidebar, "tab_video_gen" if video else "tab_imagegen", None)
    model = getattr(tab, "model", "") if tab is not None else ""
    if not model or model in ("NONE", "LOADING", "none"):
        return None
    base = "video_gen" if video else "image_gen"
    service = base
    try:
        from mixar.modules.common.generation_params import resolve_service_key
        service = resolve_service_key(base, getattr(tab, "mode", "")) or base
    except Exception:  # noqa: BLE001  (catalogue not loaded: the tab's own service)
        pass
    try:
        from mixar.modules.common.generation_params.core.engine import collect_params
        params = collect_params(service, model)
    except Exception:  # noqa: BLE001
        params = {}
    owner = G.OWNERS["video_gen" if video else "image_gen"]
    return owner, service, model, params, _references(scene, tab, video)


def _references(scene, tab, video) -> int:
    """The reference images this half submits, counted the way the pane previews them (agent_ui_tabmedia_util.cc)."""
    if not video and tab is not None and not getattr(tab, "use_reference_images", True):
        return sum(1 for r in getattr(tab, "reference_images", ()) if getattr(r, "image", None) is not None)
    return sum(1 for it in getattr(scene, "mixie_moodboard_images", ()) if getattr(it, "selected", False)
               and getattr(it, "image", None) is not None and getattr(it.image, "source", "") not in ("MOVIE", "SEQUENCE"))


def _ask(request, egress):
    _owner, service, model, params, refs = request
    try:
        PUMP["result"] = ("ok", G.ask(CLIENT_FACTORY(), service, model, params, refs, egress))
    except studio_client.StudioError:
        PUMP["result"] = ("ok", None)          # the server is not answering: the face says so
    finally:
        PUMP["inflight"] = False


def _write(wm, face, owner) -> bool:
    changed = False
    for key in STRINGS:
        name = "lampway_gen_" + key
        if getattr(wm, name, None) != face.get(key, ""):
            setattr(wm, name, face.get(key, ""))
            changed = True
    for key in FLOATS:
        name = "lampway_gen_" + key
        if abs(getattr(wm, name, 0.0) - float(face.get(key) or 0.0)) > 1e-6:
            setattr(wm, name, float(face.get(key) or 0.0))
            changed = True
    if wm.lampway_gen_owner != owner:
        wm.lampway_gen_owner = owner
        changed = True
    return changed


def _redraw():
    for window in getattr(bpy.context.window_manager, "windows", ()):
        for area in window.screen.areas:
            if area.type == 'AGENT_BUBBLE':
                area.tag_redraw()


def tick():
    context = bpy.context
    wm = getattr(context, "window_manager", None)
    if wm is None or not hasattr(wm, "lampway_gen_button"):
        return TICK_S
    request = _request(context)
    if request is None:
        if _write(wm, {"button": "Generate", "button_kind": "generate"}, ""):
            _redraw()
        return TICK_S
    now = time.monotonic()
    key = json.dumps([request[1:], [r.get("enabled") for r in (S.STATE["egress"] or {}).get("routes") or []]], sort_keys=True, default=str)
    if key != PUMP["key"]:
        PUMP.update(key=key, changed=now)
    if PUMP["result"] is not None:
        PUMP["answer"], PUMP["result"] = PUMP["result"][1], None
    if PUMP["asked"] != PUMP["key"] and not PUMP["inflight"] and now - PUMP["changed"] >= DEBOUNCE_S:
        PUMP.update(asked=PUMP["key"], inflight=True, answer=None)
        threading.Thread(target=_ask, args=(request, S.STATE["egress"] if S.STATE["ok"] else None), daemon=True).start()
    egress = S.STATE["egress"] if S.STATE["ok"] else None
    face = G.face(request[2], PUMP["answer"], egress, request[4])
    if _write(wm, face, request[0]):
        _redraw()
    return TICK_S


def register():
    wm = bpy.types.WindowManager
    for key in STRINGS:
        setattr(wm, "lampway_gen_" + key, StringProperty(name=key.replace("_", " ").capitalize(), options={'SKIP_SAVE'}))
    for key in FLOATS:
        setattr(wm, "lampway_gen_" + key, FloatProperty(name=key.replace("_", " ").capitalize(), options={'SKIP_SAVE'}))
    wm.lampway_gen_owner = StringProperty(name="Tab of the face", options={'SKIP_SAVE'})
    if not bpy.app.background and not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, first_interval=0.5, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for key in (*STRINGS, *FLOATS, "owner"):
        if hasattr(bpy.types.WindowManager, "lampway_gen_" + key):
            delattr(bpy.types.WindowManager, "lampway_gen_" + key)
