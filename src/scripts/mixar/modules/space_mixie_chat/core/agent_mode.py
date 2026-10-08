# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One agent mode per scene tab (docs/reports/agent-modes-spec.md M0), the Client's half. No bpy and no network here: the
switch is given the server client, and the menu rows are built from a cache the refresh operator fills.

- ``Scene.lampway_agent_mode``: ``runtime`` (Lampway Agent, Mode 1) or ``byoa`` (Your agent, Mode 2); ``Scene.lampway_byoa_pane``:
  the herdr session bound to the tab. Both are saved with the .blend (``ui/properties/chat_props.py``); the harness the pane runs
  is kept beside them as the ID property ``lampway_byoa_harness`` (the menu marks it).
- Switching is refused while the tab is BUSY, MODIFYING or AWAITING_INPUT, holds an open run, or holds an MCP operation
  (``code: scene_busy``). A switch starts a fresh chat session (the old chat goes to History): the two runtimes do not share a
  transcript, and the island says so. The server binds or unbinds the tab's pane first (``POST /app/workbench/mode``); when it
  refuses, nothing changes here.
- The island's separate mode chip opens ``MIXIE_CHAT_MT_agent_mode`` beside the Model chip; ``draw_rows`` draws its cached choices.
"""
import uuid
from collections import namedtuple

RUNTIME = "runtime"
BYOA = "byoa"
MODES = (RUNTIME, BYOA)
LABELS = {RUNTIME: "Lampway Agent", BYOA: "Your agent"}
HARNESS_KEY = "lampway_byoa_harness"

#: What the server listed (GET /app/workbench/harnesses), filled only by the refresh operator; the menu reads it, never the network.
HARNESSES = {"rows": [], "enabled": False, "loaded": False, "error": ""}

SCENE_BUSY_HELP = "Let the agent finish, or press Stop in the island, then switch: a tab changes agents only while nothing is working in it"
SWITCH_FAILED_HELP = "Check the cockpit (Lampway > Agents): the herdr server must be running, your own agents switched on and the harness's route on in Privacy"
BYOA_OFF = "Your own agents are off: switch them on (LAMPWAY_LOCAL_CLI=1) to run one here"
MODEL_NOTE = "The model is your agent's own: change it in its pane"
NO_TOOLS_SUFFIX = " (no Lampway tools)"

Row = namedtuple("Row", "kind label enabled active mode harness tip")


def get_mode(scene) -> str:
    mode = getattr(scene, "lampway_agent_mode", RUNTIME) if scene is not None else RUNTIME
    return mode if mode in MODES else RUNTIME


def is_byoa(scene) -> bool:
    return get_mode(scene) == BYOA


def _harness(scene) -> str:
    try:
        return str(scene.get(HARNESS_KEY) or "")
    except AttributeError:
        return ""


def _mcp_held(session_id: str) -> bool:
    if not session_id:
        return False
    try:
        from mixar.modules.mcp_bridge.core.lease import has_active_operation
        return bool(has_active_operation(session_id))
    except Exception:  # noqa: BLE001 - no lease module: no operation
        return False


def switch_refusal(scene):
    """``{"ok": False, "code": "scene_busy", ...}`` while something works in the tab, else None."""
    from ..constants import SessionState
    from .session import SessionManager
    state = SessionManager.get_state(scene)
    busy = state in (SessionState.BUSY, SessionState.MODIFYING, SessionState.AWAITING_INPUT)
    if busy or SessionManager.run_open(scene) or _mcp_held(getattr(scene, "mixie_session_id", "") or ""):
        return {"ok": False, "code": "scene_busy", "error": "An agent is working in this scene tab: it cannot change agents now",
                "help": [SCENE_BUSY_HELP]}
    return None


def notice(mode: str, label: str = "") -> str:
    """The island's line after a switch (M0: the conversation does not carry across)."""
    who = f"{LABELS[BYOA]} ({label})" if mode == BYOA and label else LABELS.get(mode, LABELS[RUNTIME])
    return (f"This tab now talks to {who}. The conversation does not carry across: the two runtimes do not share a transcript. "
            "The previous chat is in History.")


def _start_fresh_chat(scene, session_id: str) -> None:
    """The old chat to History, an empty transcript, a new chat session for the tab (as New Chat does)."""
    try:
        from .chat_history import archive_current
        archive_current(scene)
    except Exception:  # noqa: BLE001 - a failed archive never blocks the switch
        pass
    scene.mixie_chat_messages.clear()
    scene.mixie_session_id = session_id
    from .session import SessionManager
    SessionManager.set_run(scene, "", False)
    for key in ("lampway_byoa_cursor", "mixie_ws_resume"):
        try:
            if key in scene:
                del scene[key]
        except (TypeError, KeyError):
            pass


def _label_of(harness: str) -> str:
    row = next((r for r in HARNESSES["rows"] if r.get("id") == harness), None)
    return (row or {}).get("label") or harness


def prepare(scene, mode: str, harness, pane=None):
    """The main-thread half before the server is asked: a result dict (refused, or nothing to do), else the plan to send."""
    if mode not in MODES:
        return {"ok": False, "code": "invalid_mode", "error": f"unknown agent mode {mode!r}", "help": ["Pick Lampway Agent or Your agent"]}
    current = get_mode(scene)
    if mode == current and (mode == RUNTIME or (not pane and harness == _harness(scene) and getattr(scene, "lampway_byoa_pane", ""))):
        return {"ok": True, "unchanged": True}
    if (refused := switch_refusal(scene)) is not None:
        return refused
    return {"plan": True, "mode": mode, "harness": harness if mode == BYOA else None, "pane": pane, "new": str(uuid.uuid4()),
            "old": getattr(scene, "mixie_session_id", "") or "", "name": getattr(scene, "name", "") or None}


def ask_server(plan: dict, client) -> dict:
    """The server's half (no bpy: safe on a worker thread): bind or unbind the pane for the tab's new chat session."""
    from mixar.modules.lampway_tools.studio_client import StudioError
    try:
        return {"ok": True, "answer": client.set_mode(plan["new"], plan["mode"], harness=plan["harness"], pane=plan["pane"],
                                                      previous=plan["old"] or None, name=plan["name"]) or {}}
    except StudioError as exc:
        return {"ok": False, "code": "switch_failed", "error": str(exc), "help": [SWITCH_FAILED_HELP]}


def apply(scene, plan: dict, asked: dict) -> dict:
    """The main-thread half after the server answered: nothing changes when it refused, or when the tab moved on meanwhile."""
    if not asked.get("ok"):
        return asked
    if (getattr(scene, "mixie_session_id", "") or "") != plan["old"]:
        return {"ok": False, "code": "scene_changed", "error": "The tab started another chat while switching", "help": ["Switch again"]}
    if (refused := switch_refusal(scene)) is not None:
        return refused
    mode, out = plan["mode"], asked.get("answer") or {}
    rec = out.get("pane") or {}
    _start_fresh_chat(scene, plan["new"])
    scene.lampway_agent_mode = mode
    scene.lampway_byoa_pane = str(rec.get("id") or "") if mode == BYOA else ""
    scene[HARNESS_KEY] = str(rec.get("harness") or plan["harness"] or "") if mode == BYOA else ""
    from .message_helpers import add_agent_message
    add_agent_message(scene, notice(mode, _label_of(scene[HARNESS_KEY]) if mode == BYOA else ""))
    return {"ok": True, "mode": mode, "pane": scene.lampway_byoa_pane, "view": out.get("view", "")}


def switch(scene, mode: str, harness, client, pane=None) -> dict:
    """Switch the tab to ``mode`` (and, for Your agent, ``harness`` or an existing ``pane``) in one go: ``prepare``, ``ask_server``
    and ``apply``. The operator runs the same three with the server's half on a worker thread."""
    plan = prepare(scene, mode, harness, pane)
    if not plan.get("plan"):
        return plan
    return apply(scene, plan, ask_server(plan, client))


def after_new_chat(scene, old_session_id: str, client):
    """New Chat in Your agent mode: the tab keeps its pane, handed to the new chat session (the pane's binding follows the
    tab's session id). None in Lampway Agent mode."""
    pane = getattr(scene, "lampway_byoa_pane", "") or ""
    if not is_byoa(scene) or not pane:
        return None
    if not getattr(scene, "mixie_session_id", ""):
        scene.mixie_session_id = str(uuid.uuid4())
    from mixar.modules.lampway_tools.studio_client import StudioError
    try:
        client.set_mode(scene.mixie_session_id, BYOA, pane=pane, previous=old_session_id or None)
    except StudioError as exc:
        return {"ok": False, "code": "switch_failed", "error": str(exc), "help": [SWITCH_FAILED_HELP]}
    return {"ok": True, "pane": pane}


def menu_rows(scene) -> list:
    """The separate mode chip's menu rows: Lampway Agent, then one Your agent row per listed harness (a missing one
    greyed with how to install it), or a row that looks for them; in Your agent mode a note stands for the model list."""
    mode, harness = get_mode(scene), _harness(scene)
    rows = [Row("MODE", LABELS[RUNTIME], True, mode == RUNTIME, RUNTIME, "", "Lampway's own agent, on the provider you configured")]
    if not HARNESSES["loaded"]:
        rows.append(Row("REFRESH", f"{LABELS[BYOA]}: find the agents on this machine", True, False, BYOA, "",
                        "Ask the Lampway server which agent CLIs are installed"))
    for h in HARNESSES["rows"]:
        installed = bool(h.get("installed"))
        no_tools = h.get("tools") is False                    # the server says this harness cannot reach Lampway's tools from its pane
        label = (f"{LABELS[BYOA]}: {h.get('label') or h.get('id')}" + ("" if installed else " (not installed)")
                 + (NO_TOOLS_SUFFIX if installed and no_tools else ""))
        tip = (h.get("tools_note") if installed else h.get("install")) or "Your own agent, on its own login, in a pane bound to this tab"
        rows.append(Row("MODE", label, installed and bool(HARNESSES["enabled"]), mode == BYOA and harness == h.get("id"), BYOA,
                        str(h.get("id") or ""), tip))
    if HARNESSES["loaded"] and not HARNESSES["enabled"]:
        rows.append(Row("NOTE", BYOA_OFF, False, False, "", "", ""))
    if HARNESSES.get("error"):
        rows.append(Row("NOTE", HARNESSES["error"][:120], False, False, "", "", ""))
    if mode == BYOA:
        rows.append(Row("NOTE", MODEL_NOTE, False, False, "", "", ""))
    return rows


def draw_rows(layout, scene) -> bool:
    """Draw the separate mode menu from the cache. Return whether this tab uses Your agent."""
    for row in menu_rows(scene):
        line = layout.row()
        line.enabled = row.enabled
        if row.kind == "NOTE":
            line.label(text=row.label)
        elif row.kind == "REFRESH":
            line.operator("mixie_chat.agent_mode_refresh", text=row.label, icon='VIEWZOOM')
        else:
            props = line.operator("mixie_chat.agent_mode_set", text=row.label, icon='RADIOBUT_ON' if row.active else 'RADIOBUT_OFF')
            try:
                props.mode = row.mode
                props.harness = row.harness
            except (AttributeError, TypeError):
                pass
    layout.separator()
    return is_byoa(scene)
