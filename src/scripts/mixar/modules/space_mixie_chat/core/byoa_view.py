# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Showing a BYOA session in the island (docs/reports/agent-modes-spec.md B4), the Client's half.

A tab in Your agent mode (``core/agent_mode.py``) asks the server to observe its bound pane (``agent.byoa.observe``): when it
switches, when the socket comes back (``turn_events.reconnect``) and after a file load. The answer travels the turn ingress as
``agent.byoa.view`` (the receive thread never touches bpy). Then:

- **transcript** (Claude Code, Codex): the server streams the harness's own session file as observed turns, Mode 1's own frames
  with ``observed: true``. ``turn_events`` hands them here. They render through the same slot pipeline (bubbles, steps) but never
  take the tab's turn state: no BUSY, no open run, no executor undo turn. A harness's MCP operation on the tab (R7) needs the tab
  IDLE and sets BUSY itself; an observed turn must not lift or block it. A turn's end settles the bubbles, upserts the chat archive
  (``chat_history.archive_current``: the observed transcript is kept for reopening; the harness's file stays the source of truth)
  and keeps the file offset in the scene (``lampway_byoa_cursor``), so a reopened .blend resumes where it was rendered.
- **screen** (OpenCode, the user's own Hermes, Pi, Grok, Cursor): one code-block bubble holding the pane's screen text, refreshed
  by a main-thread timer that asks again every ``SCREEN_POLL_S`` seconds.
- **ended**: a bubble saying so, with **Resume** (when the server recorded the harness's own session id) and **Unbind** buttons
  (``byoa_pane:resume`` / ``byoa_pane:unbind``, ``ui/operators/chat_special_ops.py``). Both are the user's click, refused while a
  script runs (``human_gate``); nothing resumes when a .blend is opened (B2, law 5). **none**: one line with the server's help.

While an observed turn runs (or herdr reads a screen-shown pane as ``working``) the tab's ``mixie_chat_is_busy`` is set, which
is what the island's pill lights and its STOP button shows from (the C++ ``status_busy``); the tab's turn state stays IDLE, so a
harness's MCP operation is never blocked. The observed turn's end (or herdr's next ``idle``) clears it. **Stop** in this mode
(``abort_session``) is ``agent.byoa.interrupt``: the server types the harness's own interrupt keys into its pane; the island stops
showing running when the observed turn ends.

The composer in Your agent mode types into the pane (``send``). No ``by`` or origin field is sent, because the server decides who
typed from the socket (B6). The island's images go along (``images``, encoded as Mode 1 encodes them) for a harness that takes an
image by its path; for one that cannot, Send is refused with the harness's reason before anything leaves. The user's bubble shows
at once, and the observed prompt that echoes it (with the image paths the server put before the text) is not drawn twice.
"""
import uuid

from mixar.config.logging_config import get_logger
from mixar.modules.common.i18n import n_

logger = get_logger(__name__)

CURSOR_KEY = "lampway_byoa_cursor"
SCREEN_POLL_S = 1.5
SCREEN_LINES = 40
VIEWS: dict = {}          # session id -> the last observe answer for it
SCREENS: dict = {}        # session id -> the screen text last drawn
ACTIVITY: dict = {}       # session id -> "working" | "idle", from the observed run_status
_ECHOES: dict = {}        # session id -> texts the island sent that the transcript has not echoed yet
NO_PANE = "No agent is bound to this tab: pick Your agent in the island's agent menu"
RESUME_ACTION = "byoa_pane:resume"
UNBIND_ACTION = "byoa_pane:unbind"
ENDED_BUBBLE = "byoa-ended:"
SCRIPT_REFUSAL = "A script cannot do this: it is your own click in the island"
MODEL_FILES_NOT_SENT = "3D model files are already in the scene: only images go to your agent's pane"
UNDELIVERED = n_('could not be delivered')   # display: the chat renderer translates the token


def _byoa(scene) -> bool:
    from .agent_mode import is_byoa
    return is_byoa(scene)


def _redraw():
    try:
        from .queue_processor import get_event_processor
        get_event_processor()._redraw_ui()
    except Exception:  # noqa: BLE001 - a redraw is never worth an error
        pass


def set_working(scene, on: bool) -> None:
    """The island shows the pane's agent as running (the pill's dot, the cat and STOP: C++ ``status_busy`` reads
    ``mixie_chat_is_busy``). Only the display flag: the tab's turn state is never touched (an MCP operation's BUSY is its own)."""
    sid = getattr(scene, "mixie_session_id", "") or ""
    ACTIVITY[sid] = "working" if on else "idle"
    if not hasattr(scene, "mixie_chat_is_busy"):
        return
    if on:
        scene.mixie_chat_is_busy = True
    elif str(getattr(scene, "mixie_chat_state", "") or "").upper() != "BUSY":
        scene.mixie_chat_is_busy = False


def harness_row(scene) -> dict:
    """The listed harness row of this tab's pane (``agent_mode.HARNESSES``), or {} when not listed yet."""
    from .agent_mode import HARNESSES, _harness
    hid = _harness(scene)
    return next((r for r in HARNESSES.get("rows") or [] if r.get("id") == hid), {})


# ---------------------------------------------------------------------------------------------------------------- observe
def observe(scene) -> bool:
    """Ask the server to show this tab's pane (nonblocking). The answer comes back through the turn ingress."""
    sid = getattr(scene, "mixie_session_id", "") or ""
    if not _byoa(scene) or not sid:
        return False
    params = {"session_id": sid}
    try:
        cursor = scene.get(CURSOR_KEY)
    except AttributeError:
        cursor = None
    if cursor and cursor.get("pane") == getattr(scene, "lampway_byoa_pane", "") and isinstance(cursor.get("offset"), int):
        params["after_offset"] = int(cursor["offset"])
    from . import turn_events
    from mixar.modules.common.agent_rpc import client as rpc
    turn_events.bind(scene)

    def answered(result):
        if isinstance(result, dict) and "view" in result:
            turn_events.handle_turn_notification("agent.byoa.view", {"session_id": sid, **result})
    try:
        rpc.call("agent.byoa.observe", params, answered)
        return True
    except Exception as exc:  # noqa: BLE001 - not connected: the reconnect asks again
        logger.debug("byoa observe waits for the socket: %s", exc)
        return False


def observe_all() -> int:
    """Every tab in Your agent mode asks again (after a reconnect or a file load). Main thread."""
    import bpy
    n = 0
    for scene in list(getattr(bpy.data, "scenes", []) or []):
        try:
            n += bool(observe(scene))
        except Exception:  # noqa: BLE001
            logger.debug("byoa observe skipped for a scene", exc_info=True)
    return n


def apply_view(params: dict) -> None:
    """The observe answer, on the main thread (turn_events._consume)."""
    from .turn_events import _resolve
    sid = str(params.get("session_id") or "")
    scene = _resolve(sid)
    if scene is None or not _byoa(scene):
        return
    previous = VIEWS.get(sid) or {}
    VIEWS[sid] = {k: params.get(k) for k in ("view", "pane", "harness", "state", "code", "resumable")}
    view = params.get("view")
    if view == "screen":
        apply_screen(scene, str(params.get("screen") or ""), str(params.get("pane") or ""))
        status = str(params.get("agent_status") or "")
        if status in ("working", "idle", "done", "blocked"):
            set_working(scene, status == "working")                    # herdr's own reading of the pane's agent
        _ensure_screen_timer()
    elif view in ("ended", "none"):
        set_working(scene, False)
        if (previous.get("view"), previous.get("pane")) != (view, params.get("pane")):
            if view == "ended":
                ended_bubble(scene, str(params.get("pane") or ""), bool(params.get("resumable")), [str(h) for h in params.get("help") or []])
            else:
                from .message_helpers import add_agent_message
                add_agent_message(scene, " ".join(["No agent pane is bound to this tab.", *[str(h) for h in params.get("help") or []]]))
        _redraw()


def ended_bubble(scene, pane: str, resumable: bool, help_lines: list) -> None:
    """The ended pane's bubble: what happened, and the user's two choices as buttons (B2). One per pane: an older one is replaced."""
    try:
        from bpy.app.translations import pgettext_iface as iface_
    except Exception:  # noqa: BLE001 - outside Blender
        iface_ = str
    bubble_id = f"{ENDED_BUBBLE}{pane}"
    msgs = scene.mixie_chat_messages
    for i in reversed(range(len(msgs))):
        if getattr(msgs[i], "bubble_id", "") == bubble_id:
            msgs.remove(i)
    msg = msgs.add()
    msg.sender = "AGENT"
    msg.bubble_id = bubble_id
    msg.text = " ".join(["Your agent's pane has ended.", *help_lines])[:4096]
    if hasattr(msg, "content"):
        msg.content = msg.text
    msg.action_items.clear()
    if resumable:
        resume = msg.action_items.add()
        resume.label = iface_("Resume")
        resume.value = RESUME_ACTION
        resume.style = "PRIMARY"
    unbind = msg.action_items.add()
    unbind.label = iface_("Unbind")
    unbind.value = UNBIND_ACTION
    unbind.style = "DEFAULT"


def _clear_ended_bubbles(scene) -> None:
    msgs = scene.mixie_chat_messages
    for i in reversed(range(len(msgs))):
        if str(getattr(msgs[i], "bubble_id", "")).startswith(ENDED_BUBBLE):
            msgs[i].action_items.clear()


def _control(scene, method: str, params: dict) -> bool:
    """Ask the server for one of the island's pane controls (nonblocking); the answer comes back through the turn ingress as
    ``agent.byoa.control`` (the receive thread never touches bpy)."""
    sid = getattr(scene, "mixie_session_id", "") or ""
    if not sid:
        return False
    from . import turn_events
    from mixar.modules.common.agent_rpc import client as rpc

    def answered(result):
        out = (result.get("result") or {}) if isinstance(result, dict) and isinstance(result.get("result"), dict) else (result or {})
        turn_events.handle_turn_notification("agent.byoa.control", {"session_id": sid, "method": method, **dict(out)})
    try:
        rpc.call(method, {"session_id": sid, **params}, answered)
        return True
    except Exception as exc:  # noqa: BLE001 - not connected
        logger.debug("byoa control %s waits for the socket: %s", method, exc)
        return False


def resume(scene) -> bool:
    """The user's Resume of the tab's ended pane (B2): never automatic."""
    _clear_ended_bubbles(scene)
    return _control(scene, "agent.byoa.resume", {"name": getattr(scene, "name", "") or ""})


def unbind(scene) -> bool:
    """The user's Unbind of the tab's ended pane: the tab lets it go; the pane's record stays on the server."""
    _clear_ended_bubbles(scene)
    return _control(scene, "agent.byoa.unbind", {})


def stop(scene) -> bool:
    """The island's Stop in Your agent mode: the harness's own interrupt keys into its pane (the server sends them)."""
    return _control(scene, "agent.byoa.interrupt", {})


def apply_control(params: dict) -> None:
    """A control's answer, on the main thread (turn_events._consume)."""
    from .turn_events import _resolve
    scene = _resolve(str(params.get("session_id") or ""))
    if scene is None or not _byoa(scene):
        return
    method = params.get("method")
    from .message_helpers import add_agent_message
    if not params.get("ok"):
        add_agent_message(scene, " ".join([str(params.get("message") or "Your agent's pane refused that."),
                                           *[str(h) for h in params.get("help") or []]]))
    elif method == "agent.byoa.resume":
        pane = str(params.get("pane") or "")
        scene.lampway_byoa_pane = pane
        if params.get("harness"):
            from .agent_mode import HARNESS_KEY
            scene[HARNESS_KEY] = str(params["harness"])
        VIEWS.pop(getattr(scene, "mixie_session_id", "") or "", None)
        add_agent_message(scene, "Your agent's conversation goes on in a new pane." if not params.get("running") else
                          "Your agent's pane is running.")
        observe(scene)
    elif method == "agent.byoa.unbind":
        scene.lampway_byoa_pane = ""
        VIEWS.pop(getattr(scene, "mixie_session_id", "") or "", None)
        add_agent_message(scene, "This tab let its agent's pane go. Pick Your agent in the island's agent menu to start a new one.")
    _redraw()


def apply_screen(scene, text: str, pane: str = "") -> None:
    """The pane's screen, as one code-block bubble; rewritten only when the screen changed."""
    sid = getattr(scene, "mixie_session_id", "") or ""
    if SCREENS.get(sid) == text:
        return
    SCREENS[sid] = text
    lines = "\n".join(text.replace("```", "'''").splitlines()[-SCREEN_LINES:])
    from .slot_processor import get_slot_processor
    get_slot_processor().apply_event({"bubble_id": f"byoa-screen:{pane or getattr(scene, 'lampway_byoa_pane', '')}",
                                      "content": {"set": f"```text\n{lines}\n```"}}, scene)
    _redraw()


def _screen_tick():
    """Main-thread timer: ask again for every tab whose pane is shown as its screen; stops when there is none."""
    import bpy
    asked = 0
    for scene in list(getattr(bpy.data, "scenes", []) or []):
        sid = getattr(scene, "mixie_session_id", "") or ""
        if _byoa(scene) and (VIEWS.get(sid) or {}).get("view") == "screen":
            asked += bool(observe(scene))
    return SCREEN_POLL_S if asked else None


def _ensure_screen_timer() -> None:
    import bpy
    try:
        if not bpy.app.timers.is_registered(_screen_tick):
            bpy.app.timers.register(_screen_tick, first_interval=SCREEN_POLL_S)
    except Exception:  # noqa: BLE001
        logger.debug("byoa screen timer not registered", exc_info=True)


# ---------------------------------------------------------------------------------------------------------------- observed turns
def _take_echo(sid: str, text: str) -> bool:
    """Whether an observed prompt is the island's own send coming back: the same text, or the same text after the image paths
    the server typed before it."""
    pending = _ECHOES.get(sid) or []
    key = (text or "").strip()
    for sent in pending:
        if key == sent or (sent and key.endswith(" " + sent)) or (not sent and key):
            pending.remove(sent)
            return True
    return False


def _images(scene):
    """The pending image attachments, encoded as Mode 1 encodes them (``image_utils.encode_attachment_for_upload``): a list of
    ``{"data": <base64>}`` (the server decides the type from the bytes), the attachments themselves, and how many model files were
    left out. Main thread (a Blender image reads bpy.data). None when one could not be encoded."""
    pending = list(getattr(scene, "mixie_chat_pending_attachments", None) or [])
    from .image_utils import encode_attachment_for_upload
    out, kept, models = [], [], 0
    for att in pending:
        source = getattr(att, "image_source", "FILE")
        if source == "MODEL_FILE":
            models += 1
            continue
        encoded = encode_attachment_for_upload(getattr(att, "image_path", ""), source)
        if encoded is None:
            return None, pending, models
        out.append({"data": encoded[0]})
        kept.append(att)
    return out, kept, models


def begin_observed_turn(scene, params: dict) -> None:
    """An observed turn starts: the prompt as the user's bubble (unless the island just sent it). The tab's state is not touched."""
    sid = getattr(scene, "mixie_session_id", "") or ""
    text = str(params.get("user_text") or "").strip()
    if text and not _take_echo(sid, text):
        msg = scene.mixie_chat_messages.add()
        msg.sender = "USER"
        msg.text = text
    set_working(scene, True)
    _redraw()


def apply_observed(scene, turn, payload: dict) -> None:
    """One observed payload, on the main thread. Slots render as Mode 1's do; nothing here sets the tab's state or run."""
    if turn.swarm_card:
        apply_swarm_card(scene, turn, payload)
        return
    kind = payload.get("type")
    if kind == "turn_end":
        from .slot_processor import finalize_turn
        finalize_turn(scene)
        try:
            from .queue_processor import get_event_processor
            get_event_processor()._clear_loader_bubbles(scene)
        except Exception:  # noqa: BLE001
            pass
        try:
            from .chat_history import archive_current
            archive_current(scene)
        except Exception:  # noqa: BLE001 - the archive never blocks the view
            logger.debug("byoa archive skipped", exc_info=True)
        if isinstance(payload.get("offset"), int):
            scene[CURSOR_KEY] = {"pane": getattr(scene, "lampway_byoa_pane", "") or "", "offset": int(payload["offset"])}
        set_working(scene, False)                        # the observed turn ended: the island stops showing running
        turn.complete = True
    elif kind == "run_status":
        set_working(scene, payload.get("status") == "in_progress")
        return
    elif kind == "resume_unavailable":
        from .slot_processor import finalize_turn
        finalize_turn(scene)
        turn.complete = True
    elif "bubble_id" in payload:
        from .slot_processor import get_slot_processor
        get_slot_processor().apply_event(payload, scene)
    elif kind == "error":
        from .message_helpers import add_agent_message
        add_agent_message(scene, str(payload.get("message") or "Your agent's view reported an error."))
    _redraw()


def apply_swarm_card(scene, turn, payload: dict) -> None:
    """S3's worker cards in either mode. Their status and end belong only to the card, never the pane's activity or cursors.

    Card slots already carry the workers' final statuses. Finalizing the entire transcript here would hide a concurrent
    pane turn's loaders and settle its live steps, so a card end only archives the rendered cards and closes their delivery.
    """
    kind = payload.get("type")
    if kind in ("turn_end", "resume_unavailable"):
        if kind == "turn_end":
            try:
                from .chat_history import archive_current
                archive_current(scene)
            except Exception:  # noqa: BLE001 - the archive never blocks the cards
                logger.debug("swarm card archive skipped", exc_info=True)
        turn.complete = True
    elif "bubble_id" in payload:
        from .slot_processor import get_slot_processor
        get_slot_processor().apply_event(payload, scene)
    _redraw()


# ---------------------------------------------------------------------------------------------------------------- the composer
def send(scene, text: str, images=None, attachments=()):
    """Type the user's text into the tab's pane (``agent.byoa.send``), with the island's images when given. Returns (ok, reason)."""
    text = (text or "").strip()
    sid = getattr(scene, "mixie_session_id", "") or ""
    if not text and not images:
        return False, "Type a message first"
    if not sid or not getattr(scene, "lampway_byoa_pane", ""):
        return False, NO_PANE
    from . import turn_events
    from mixar.modules.common.agent_rpc import client as rpc
    user_msg = scene.mixie_chat_messages.add()
    user_msg.sender = "USER"
    user_msg.text = text
    for att in attachments or ():
        try:
            msg_att = user_msg.attachments.add()
            msg_att.image_path = att.image_path
            msg_att.image_source = att.image_source
            msg_att.display_name = getattr(att, "display_name", "") or ""
        except AttributeError:                       # a bubble without attachments (tests' fakes)
            break
    command_id = str(uuid.uuid4())
    user_msg.bubble_id = command_id
    _ECHOES.setdefault(sid, []).append(text)

    def settled(target, result):
        if result.get("ok", True):
            return
        _take_echo(sid, text)
        for item in target.mixie_chat_messages:
            if getattr(item, "sender", "") == "USER" and getattr(item, "bubble_id", "") == command_id:
                item.delivery_hint = UNDELIVERED
                break
        from .message_helpers import add_agent_message
        add_agent_message(target, " ".join([str(result.get("message") or "Your agent's pane refused the message."),
                                            *[str(h) for h in result.get("help") or []]]))
        _redraw()

    def ack(result):
        if isinstance(result, dict) and isinstance(result.get("code"), int):
            turn_events.handle_turn_notification("agent.command.result", {
                "session_id": sid, "command_id": command_id, "ok": False, "message": result.get("message")})
        elif isinstance(result, dict) and result.get("state") == "complete":
            turn_events.handle_turn_notification("agent.command.result", {
                "session_id": sid, "command_id": command_id, **(result.get("result") or {})})

    turn_events.expect(scene, command_id, settled)
    try:
        rpc.command("byoa.send", {"session_id": sid, "text": text, **({"images": list(images)} if images else {})}, ack, command_id=command_id)
    except Exception as exc:  # noqa: BLE001 - not connected
        turn_events._commands.pop(command_id, None)
        _take_echo(sid, text)
        user_msg.delivery_hint = UNDELIVERED
        return False, str(exc)
    return True, ""


def execute_send(op, context):
    """The send operator's Your agent branch (ui/operators/chat_ops.py)."""
    scene = context.scene
    text = (getattr(op, "message_override", "") or scene.mixie_chat_input).strip()
    images, attachments = None, ()
    if len(getattr(scene, "mixie_chat_pending_attachments", None) or []):
        row = harness_row(scene)
        if row and row.get("images") is False:       # the harness cannot take an image: say why, keep the attachments
            op.report({'ERROR'}, str(row.get("images_note") or "Your agent cannot take an image"))
            return {'CANCELLED'}
        images, attachments, models = _images(scene)
        if images is None:
            op.report({'ERROR'}, "An attached image could not be read, so nothing was sent")
            return {'CANCELLED'}
        if models:
            op.report({'WARNING'}, MODEL_FILES_NOT_SENT)
    ok, reason = send(scene, text, images, attachments)
    if not ok:
        op.report({'ERROR'}, reason)
        return {'CANCELLED'}
    if images is not None:
        scene.mixie_chat_pending_attachments.clear()
    if not getattr(op, "message_override", ""):
        scene.mixie_chat_input = ""
    if hasattr(scene, "mixie_chat_user_has_engaged"):
        scene.mixie_chat_user_has_engaged = True
    _redraw()
    return {'FINISHED'}


def execute_stop(op, context):
    """The Stop operator's Your agent branch (ui/operators/session_ops.py): the user's click only."""
    from mixar.modules.lampway_tools.human_gate import script_running
    if script_running():
        op.report({'ERROR'}, SCRIPT_REFUSAL)
        return {'CANCELLED'}
    if not getattr(context.scene, "lampway_byoa_pane", ""):
        op.report({'WARNING'}, NO_PANE)
        return {'CANCELLED'}
    if not stop(context.scene):
        op.report({'ERROR'}, "Not connected to Lampway's server: your agent's pane was not stopped")
        return {'CANCELLED'}
    return {'FINISHED'}


def execute_pane_action(op, context, value: str):
    """The ended pane's Resume / Unbind buttons (ui/operators/chat_special_ops.py): the user's click only."""
    from mixar.modules.lampway_tools.human_gate import script_running
    if script_running():
        op.report({'ERROR'}, SCRIPT_REFUSAL)
        return {'CANCELLED'}
    scene = context.scene
    if not _byoa(scene):
        return {'CANCELLED'}
    done = resume(scene) if value == RESUME_ACTION else unbind(scene) if value == UNBIND_ACTION else False
    if not done:
        op.report({'ERROR'}, "Not connected to Lampway's server")
        return {'CANCELLED'}
    _redraw()
    return {'FINISHED'}
