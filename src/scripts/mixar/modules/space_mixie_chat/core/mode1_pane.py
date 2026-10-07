# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway Agent's pane in the island (docs/reports/agent-modes-spec.md A2, A3, Q15), the Client's half.

Mode 1 runs Hermes's own TUI in a herdr pane, and Lampway's server is a second client of that pane's ``hermes serve``
(``server/lampway_server/engine/front.py``). Two things reach a tab from the pane rather than from the island:

- **A turn the user types in the pane** comes as ``agent.turn.started {origin: "pane", user_text}`` with a ``pane_<hex>`` turn id
  and a run of its own, then ordinary ``agent.turn.event`` frames and ``agent.turn.ended``. Unlike a Your agent tab's observed turn
  (``byoa_view.py``, B4), it runs Lampway's tools in the scene, so ``turn_events`` takes it as **the tab's turn**, exactly as an
  island turn: the user's bubble (``user_text``, read by the server from Hermes's history), the run, BUSY, the executor's undo
  turn (the pane turn's edits are one undo step), the rendered cursor, the slots, its end and the History upsert. Only a Mode 1 tab
  that is not already in a turn takes it (``refusal``): a tab in Your agent mode, a tab BUSY or MODIFYING (an island send in flight,
  an MCP operation's lease) or a tab with a live turn of its own ignores it with a log line. One Hermes session runs one turn at a
  time, so such a start is stale, never a second turn to show. The rest of a turn whose question the pane answered carries the
  open run's id and joins it as a wake-up (``turn_events``), with no user bubble. A pane turn takes no checkpoint: its "before"
  snapshot would be a save on the main thread from the event pump, not the user's click (a decision for the captain).
- **Its Blender calls** are ``blender.execute_script`` with the pane turn's id in ``agent_ctx.turn_id``. They pass the same gates as
  an island turn's (the MCP lease, the per-scene routing, the render guard, the sandbox and ``human_gate``), plus one: a script
  that names a pane turn runs only while that turn is live in its own tab (``script_refusal``, main thread). An unknown turn (one
  this tab ignored, or the server's scratch id for a call no shown turn owns) or an ended one is refused, ``unknown_turn``, and
  nothing runs. The receive thread leaves those scripts to that check (``pane_turn_id``): the tab is IDLE until the main thread
  has rendered the start, and the check renders the tab's queued frames first (``turn_events.drain_session``).
- **``/new`` in the pane** moves the unit to a new Hermes session; the tab's session id stays (it is the unit, Lampway Agent's pane
  for this tab), and the server sends ``agent.pane.new_conversation {session_id, origin: "pane"}``. ``apply_new_conversation``
  fences the old conversation's turns (late frames are dropped), answers its queued scripts, files the old chat in History under a
  new id (its transcript, ``chat_history.refile``, and its checkpoint timeline, ``checkpoint_store.refile``, so the new chat starts
  an empty timeline under the same id), empties the island and adds one line. Reopening the filed chat shows its transcript; its
  Hermes session is not followed back (a message from it opens a pane of its own, as after New Chat).
"""
import uuid

from mixar.config.logging_config import get_logger

logger = get_logger(__name__)

PANE_TURN_PREFIX = "pane_"          # front.py's pane turn ids (and its scratch id for a call no shown turn owns)
NEW_CONVERSATION = "agent.pane.new_conversation"
NEW_CONVERSATION_NOTICE = "Lampway Agent's pane started a new conversation (/new). The previous chat is in History."
UNKNOWN_TURN = "unknown_turn"


def pane_turn_id(agent_ctx) -> str:
    """The pane turn a script for a scene tab names (``agent_ctx.turn_id``), or "" for any other script. A swarm worker's
    script carries its parent turn's id but routes by the worker's ``agent:`` (or a lane's ``agentlane:``) session on a Lampway
    that never saw that turn: it keeps its own gates. Safe on any thread."""
    if not isinstance(agent_ctx, dict):
        return ""
    tid, sid = agent_ctx.get("turn_id"), agent_ctx.get("chat_session_id")
    if not (isinstance(tid, str) and tid.startswith(PANE_TURN_PREFIX)) or not isinstance(sid, str):
        return ""
    from ..constants import AGENT_LANE_SESSION_PREFIX, is_non_scene_routing_session
    return "" if is_non_scene_routing_session(sid) or sid.startswith(AGENT_LANE_SESSION_PREFIX) else tid


# ---------------------------------------------------------------------------------------------------------------- pane turns
def refusal(scene, session_id: str, turn_id: str) -> str:
    """Why a pane turn's start is not this tab's turn ("" when it is). Main thread."""
    from ..constants import SessionState
    from .agent_mode import is_byoa
    from .session import SessionManager
    from . import turn_events as TE
    if is_byoa(scene):
        return "the tab is in Your agent mode"
    if SessionManager.get_state(scene) in (SessionState.BUSY, SessionState.MODIFYING):
        return "the tab is in a turn of its own (or an MCP operation holds it)"
    live = next((t.turn_id for t in TE._turns.values()
                 if t.session_id == session_id and not t.complete and not t.observed and t.turn_id != turn_id), "")
    if live:
        return f"turn {live} is still live in the tab"
    return ""


def add_prompt(scene, params: dict) -> None:
    """The user's bubble for a turn typed in the pane (the server read its text from Hermes's history)."""
    text = str(params.get("user_text") or "").strip()
    if not text:
        return                                       # a turn found running after a reconnect may have no text
    msg = scene.mixie_chat_messages.add()
    msg.sender = "USER"
    msg.text = text
    msg.bubble_id = str(params.get("turn_id") or "")
    if hasattr(scene, "mixie_chat_user_has_engaged"):
        scene.mixie_chat_user_has_engaged = True


# ---------------------------------------------------------------------------------------------------------------- its scripts
def script_refusal(session_id: str, agent_ctx):
    """None when a script may run; a refusal for one naming a pane turn that is not live in its own tab. Main thread, before the
    executor's session check (``main_thread_executor._execute_dequeued_request``)."""
    tid = pane_turn_id(agent_ctx)
    if not tid:
        return None
    from . import turn_events as TE
    turn = TE._turns.get(tid)
    if turn is None:
        TE.drain_session(session_id)                 # its start may still wait in the inbox behind the receive thread
        turn = TE._turns.get(tid)
    if turn is not None and turn.session_id == session_id and not turn.complete and not turn.observed:
        return None
    what = "ended" if turn is not None and turn.complete else "unknown"
    logger.warning("Refusing a script for the %s pane turn %s of session %s: nothing was run", what, tid, (session_id or "")[:8])
    return {"success": False, "error_type": UNKNOWN_TURN,
            "error": f"Lampway is not showing this turn ({what} turn {tid}) in its scene tab, so nothing was run"}


# ---------------------------------------------------------------------------------------------------------------- /new (Q15)
def apply_new_conversation(params: dict) -> None:
    """``agent.pane.new_conversation``, on the main thread (``turn_events._consume``, in order with the tab's turn frames)."""
    from . import turn_events as TE
    sid = str((params or {}).get("session_id") or "")
    if not sid or sid in TE._blocked:
        return
    scene = TE._resolve(sid)
    if scene is None:
        logger.info("The pane's /new for session %s has no scene tab here: ignored", sid[:8])
        return
    from .agent_mode import is_byoa
    if is_byoa(scene):
        logger.info("The pane's /new (agent.pane.new_conversation) for a tab in Your agent mode: ignored")
        return
    live = False
    for turn in TE._turns.values():
        if turn.session_id == sid:
            live = live or (not turn.complete and not turn.observed)
            turn.complete = True                     # the old conversation's late frames are dropped
            turn.pending.clear()
    try:
        from .main_thread_executor import cleanup
        cleanup(session_id=sid)                      # its queued scripts are answered, never run
    except Exception:  # noqa: BLE001 - nothing queued is a fine outcome
        logger.debug("no queued scripts to flush for the pane's /new", exc_info=True)
    from .executor import get_executor
    from .queue_processor import get_event_processor
    processor = get_event_processor()
    if live:
        get_executor().end_agent_turn(sid)
        try:
            from .slot_processor import finalize_turn
            finalize_turn(scene)
        except Exception:  # noqa: BLE001
            logger.debug("finalize_turn before the pane's /new skipped", exc_info=True)
    processor._clear_loader_bubbles(scene)
    filed = _file_old_chat(scene, sid)
    _empty(scene)
    from ..constants import SessionState
    from .session import SessionManager
    SessionManager.set_run(scene, "", False)
    SessionManager.set_state(scene, SessionState.IDLE)
    from .message_helpers import add_agent_message
    add_agent_message(scene, NEW_CONVERSATION_NOTICE)
    logger.info("Lampway Agent's pane started a new conversation for session %s; the old chat is filed as %s",
                sid[:8], (filed or "nothing")[:8])
    processor._redraw_ui()


def _file_old_chat(scene, sid: str) -> str:
    """The old chat in History under a new id, its checkpoint timeline with it; the new chat keeps ``sid``."""
    new_id = str(uuid.uuid4())
    filed = ""
    try:
        from .chat_history import archive_current, refile
        archive_current(scene)                       # the last state, upserted under the tab's id
        filed = new_id if refile(sid, new_id) else ""
    except Exception:  # noqa: BLE001 - a failed archive never blocks the new chat
        logger.exception("The chat before the pane's /new could not be filed in History")
    try:
        from .checkpoint_store import refile as refile_checkpoints
        refile_checkpoints(sid, new_id)
    except Exception:  # noqa: BLE001
        logger.exception("The checkpoints before the pane's /new could not be moved with the old chat")
    return filed


def _empty(scene) -> None:
    scene.mixie_chat_messages.clear()
    for key in ("mixie_ws_resume",):                 # turn_cursor's key: the old conversation's cursor
        try:
            if key in scene:
                del scene[key]
        except (TypeError, KeyError):
            pass
    try:
        from .markdown_parser import clear_incremental_cache
        clear_incremental_cache()
    except Exception:  # noqa: BLE001
        pass
    if hasattr(scene, "mixie_chat_layout_epoch"):
        scene.mixie_chat_layout_epoch += 1
