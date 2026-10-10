# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The island's agent-mode switch (agent-modes spec M0): the separate mode chip's menu runs these.

Switching a tab, and so starting the user's own agent in a pane bound to it, is the user's click: both operators refuse while
a script runs (``human_gate``: the agent's script, a swarm worker's or the bridge's). The server's half (a version probe of each
harness, or starting one) can take seconds, so it runs on a worker thread and its answer is applied by a main-thread timer;
a draw never reaches the server (``core/agent_mode.py`` builds the rows from a cache)."""

import queue
import threading

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator

from ...core import agent_mode as AM

_ANSWERS: "queue.Queue" = queue.Queue()
_PENDING = [0]
_TICK_S = 0.2
SCRIPT_REFUSAL = "A script cannot switch a tab's agent: switch it yourself in the island's agent menu"


def CLIENT_FACTORY():
    """The server's workbench client (tests swap this)."""
    from mixar.modules.lampway_tools.workbench_client import WorkbenchClient
    return WorkbenchClient()


def _redraw():
    wm = getattr(bpy.context, "window_manager", None)
    for window in getattr(wm, "windows", []) or []:
        for area in window.screen.areas:
            area.tag_redraw()


def _apply_answers():
    """Main-thread timer: apply what the server answered, then stop when nothing is pending."""
    from ...core import byoa_view
    from ...core.message_helpers import add_agent_message
    while True:
        try:
            kind, scene_name, plan, asked = _ANSWERS.get_nowait()
        except queue.Empty:
            break
        if kind == "harnesses":
            if asked.get("ok"):
                AM.HARNESSES.update(rows=asked["answer"].get("harnesses") or [], enabled=bool(asked["answer"].get("enabled")),
                                    loaded=True, error="")
            else:
                AM.HARNESSES.update(error=asked.get("error") or "", loaded=False)
            continue
        scene = bpy.data.scenes.get(scene_name)
        if scene is None:
            continue
        out = AM.apply(scene, plan, asked)
        if not out.get("ok"):
            add_agent_message(scene, " ".join([out.get("error") or "The switch did not happen.", *out.get("help", [])]))
        elif out.get("mode") == AM.BYOA:
            byoa_view.observe(scene)
    _redraw()
    return _TICK_S if _ANSWERS.qsize() or _PENDING[0] else None


def _run(job, *args):
    def work():
        try:
            _ANSWERS.put(job(*args))
        finally:
            _PENDING[0] -= 1
    _PENDING[0] += 1
    threading.Thread(target=work, name="lampway-agent-mode", daemon=True).start()
    if not bpy.app.timers.is_registered(_apply_answers):
        bpy.app.timers.register(_apply_answers, first_interval=_TICK_S)


def _ask(scene_name, plan, client):
    return ("switch", scene_name, plan, AM.ask_server(plan, client))


def _list(client):
    from mixar.modules.lampway_tools.studio_client import StudioError
    try:
        return ("harnesses", "", None, {"ok": True, "answer": client.harnesses()})
    except StudioError as exc:
        return ("harnesses", "", None, {"ok": False, "error": str(exc)})


class MIXIE_CHAT_OT_agent_mode_set(Operator):
    """Switch this scene tab between Lampway Agent and your own agent. The conversation does not carry across"""
    bl_idname = "mixie_chat.agent_mode_set"
    bl_label = "Switch Agent"
    bl_options = {'REGISTER'}

    mode: EnumProperty(items=[('runtime', "Lampway Agent", ""), ('byoa', "Your agent", "")], default='runtime')
    harness: StringProperty(default="")

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        from mixar.modules.lampway_tools.human_gate import script_running
        if script_running():
            self.report({'ERROR'}, SCRIPT_REFUSAL)
            return {'CANCELLED'}
        scene = context.scene
        plan = AM.prepare(scene, self.mode, self.harness or None)
        if not plan.get("plan"):
            if not plan.get("ok"):
                self.report({'ERROR'}, " ".join([plan.get("error") or "", *plan.get("help", [])]).strip())
                return {'CANCELLED'}
            return {'FINISHED'}
        client = CLIENT_FACTORY()
        if self.mode == AM.BYOA:
            from mixar.modules.lampway_tools.ui import launch_notice
            scene_name = scene.name
            def done(asked, error):
                _ANSWERS.put(('switch', scene_name, plan, asked if not error else {'ok': False, 'error': error}))
                _apply_answers()
            def valid():
                current = bpy.data.scenes.get(scene_name)
                return current is not None and getattr(current, 'mixie_session_id', '') == plan['old']
            launch_notice.request(
                lambda: client.mode_notice(plan['new'], plan['mode'], harness=plan['harness'], pane=plan['pane'],
                                           previous=plan['old'] or None, name=plan['name']),
                lambda nonce: AM.ask_server(plan, client, notice_nonce=nonce), done, valid)
        else:
            _run(_ask, scene.name, plan, client)
        self.report({'INFO'}, "Starting your agent…" if self.mode == AM.BYOA else "Switching to Lampway Agent…")
        return {'FINISHED'}


class MIXIE_CHAT_OT_agent_mode_refresh(Operator):
    """Ask the Lampway server which agent CLIs are installed on this machine"""
    bl_idname = "mixie_chat.agent_mode_refresh"
    bl_label = "Find Your Agents"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from mixar.modules.lampway_tools.human_gate import script_running
        if script_running():
            self.report({'ERROR'}, SCRIPT_REFUSAL)
            return {'CANCELLED'}
        _run(_list, CLIENT_FACTORY())
        return {'FINISHED'}


classes = (
    MIXIE_CHAT_OT_agent_mode_set,
    MIXIE_CHAT_OT_agent_mode_refresh,
)
