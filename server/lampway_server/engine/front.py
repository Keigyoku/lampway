# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The island is a second client of the pane's ``hermes serve`` (docs/reports/agent-modes-spec.md A2, A3): the hub's Mode 1 front
end. ``AgentHub.engine`` is a ``HermesFront``; the hub keeps the client protocol (``agent.chat/input/cancel/attach``, the
``TurnStream`` journal) and this module maps it onto the unit's serve, as A2's table says:

* **a scene tab's first ``agent.chat``** opens the unit's pane when it has none (``Mode1Units.open``; only the user's own Client
  may, ``precheck``), then this server attaches as a client: ``client.capabilities {server_requests}``, ``session.resume`` of the
  stored session. Nothing else runs Mode 1 (A5): with no engine build or prebuilt TUI (``engine_not_built``), no Node.js
  (``node_missing``), no herdr (``herdr_not_built``) or no running herdr server (``herdr_not_running``) the chat is refused before
  any turn starts, with the exact build command or setting (and the switch to Your agent where that would help);
* **``agent.chat``** -> ``image.attach_bytes`` per image, then ``prompt.submit`` with R3's context blocks (``turn_context``);
* **a chat while a turn runs** -> ``session.steer`` (the hub answers ``{ok: true, joined: true}``, R4);
* **``agent.cancel``** -> ``session.interrupt``;
* **events** -> the turn's slots: ``message.delta`` and ``reasoning.delta`` -> ``ephemeral.append``; ``tool.start`` /
  ``tool.complete`` -> ``steps`` (the label is the Lampway tool's name without ``mcp__lampway__``; Hermes's own bridge tools are
  not steps); ``message.complete`` -> ``content.set`` and the turn's end (``complete`` -> ``completed``, ``interrupted`` ->
  ``cancelled``, ``error`` -> ``failed``);
* **``clarify``** (a server request) -> the island's question (``interrupt_id``, ``actions``); ``agent.input`` answers it with
  ``{answer}``. **``approval``** -> the island's permission card (``input_type: approval``); the answer is ``{choice}``. Both reach
  every client and the first answer wins with NO ``request.cancel`` to the others, so when the turn moves on without the island's
  answer (the pane answered), the island's card is closed and the turn goes on in the island;
* **a turn the user types in the pane** -> an island turn of its own (``agent.turn.started`` with ``origin: pane``), its user text
  from ``session.history`` (no event carries it, measured);
* **``/new`` in the pane** closes the session for every client (``sessions.changed``, then ``4001``): the island follows the pane to
  its new session (spec Q15, proposed) and tells the tab's client (``agent.pane.new_conversation``), whose session id stays;
* **a dropped connection to serve** is re-made, and missed events are caught up with ``session.events.since`` (same replay epoch),
  else from ``session.history``;
* **the island's socket closing** stops nothing in Hermes: the hub keeps the running turn as a survivor and ``agent.attach``
  replays its journal.

**The swarm's cards and Retry.** A swarm the unit's Hermes starts shows its Parallel Agents cards on the island turn running when it
reports (``agent/swarm_island.py`` reads the live ``Sink``); the chip's "continue" (the user's own socket, failed tasks on offer)
runs those tasks again inside the island turn first (``_retry``: steps and cards on its bubble), and Hermes gets the user's
"continue" with one line saying what ran (``swarm.retry_note``).

**A3: tools reach the scene whoever started the turn.** ``/engine/mcp/<unit>`` (``mcp_endpoint.py``) calls ``call_tool``: the call
runs through ``AgentHub._run_tool`` (Capabilities at call time, E2) on the scene tab's CURRENT client socket (``hub.socket_for``),
with or without an island turn; with no client connected it is refused ("Lampway is not open"). Its step comes from serve's
``tool.start``/``tool.complete``, never from the MCP side.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import turn_context as TC
from .serve_client import SESSION_NOT_FOUND, ServeClient, ServeClosed, ServeError

log = logging.getLogger("lampway.engine.front")

MCP_PREFIX = "mcp__lampway__"
#: Hermes's own plumbing, not the agent's work: no step rows (the clarify call is the island's question instead).
HIDDEN_TOOLS = frozenset({"tool_search", "tool_describe", "clarify"})
STATUS = {"complete": "completed", "interrupted": "cancelled", "error": "failed"}
APPROVAL_LABELS = {"once": "Allow once", "session": "Allow for this session", "always": "Always allow", "deny": "Deny"}
RECONNECT_S = (0.5, 1, 2, 5, 10, 30)
KNOWN_CONNECT_S = 15.0            # a recorded pane's serve answers at once; one that does not may have ended with its pane
ANSWERED_ELSEWHERE = "(Answered in Lampway Agent's pane.)"
NOT_ANSWERED = "(Not answered: Lampway Agent went on to a new turn.)"
TURN_WAIT_S = 20.0                # how long a tool call waits for the island turn that shows it (``_shown_turn``)
MARKS_FILE = "checkpoints.json"   # the unit's checkpoint bookmarks (0600 in its home): request id -> {session, user turns}
MAX_MARKS = 500
BUSY = 4009                       # serve's "session busy" (session.undo while a turn runs)


@dataclass
class Sink:
    """Where a running Hermes turn's events go: an island turn. ``pending``: the turn is being opened, events wait in ``buffer``."""
    socket: object = None
    session: object = None
    turn: object = None
    stream: object = None
    bubble_id: str = ""
    steps: list = field(default_factory=list)
    text: list = field(default_factory=list)
    done: Optional[asyncio.Future] = None
    asked: Optional[asyncio.Event] = None
    pending: bool = False
    buffer: list = field(default_factory=list)


@dataclass
class Question:
    request_id: str
    kind: str                         # clarify | approval
    interrupt_id: str
    body: str
    choices: list
    bubble_id: str = ""
    run_id: str = ""
    answered: bool = False            # by the island


@dataclass
class Link:
    unit: str
    info: object = None               # units.UnitInfo
    client: Optional[ServeClient] = None
    live_id: str = ""
    epoch: str = ""
    last_seq: int = -1
    running: bool = False
    sink: Optional[Sink] = None
    island_prompts: int = 0           # prompts the island submitted whose message.start has not come
    absorb: int = 0                   # turn ends nobody shows (a cancelled island turn)
    question: Optional[Question] = None
    rules_key: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    watcher: Optional[asyncio.Task] = None
    closing: bool = False
    carried: list = field(default_factory=list)   # steps still running when the turn stopped for a question
    stale: Optional["Question"] = None            # a question nobody can answer now, its card still open in the island
    marks: Optional[dict] = None                  # checkpoint bookmarks: request id -> {session, turns} (``checkpoints.json``)


def tool_name(payload: dict) -> str:
    """The real tool's name: a deferred MCP tool's ``tool.start`` already carries it; a failed bridge call names it in its labels."""
    name = str(payload.get("name") or "")
    if name == "tool_call":
        label = next((lb.get("name") for lb in payload.get("labels") or [] if isinstance(lb, dict) and lb.get("name")), None)
        name = label or str((payload.get("args") or {}).get("name") or name)
    return name


def step_label(name: str) -> str:
    return name[len(MCP_PREFIX):] if name.startswith(MCP_PREFIX) else name


def failed(payload: dict) -> bool:
    result = payload.get("result")
    return bool(payload.get("error")) or (isinstance(result, dict) and bool(result.get("error")))


def approval_choice(text: str, choices: list) -> str:
    """The island's answer to a permission card: a choice id, a choice's label, else deny."""
    text = str(text or "").strip().lower()
    for c in choices:
        if text in (str(c).lower(), APPROVAL_LABELS.get(str(c), "").lower()):
            return str(c)
    return "deny"


class HermesFront:
    def __init__(self, hub, units):
        self.hub = hub
        self.units = units
        self.links: dict = {}
        self.feed = None                                     # history.Feed: the client's archive (R2), made on its first poll

    # ------------------------------------------------------------------------------------------------- the hub's side
    def _link(self, unit: str) -> Link:
        link = self.links.get(unit)
        if link is None:
            link = self.links[unit] = Link(unit)
        return link

    def is_running(self, session_id: str) -> bool:
        link = self.links.get(session_id)
        return link is not None and link.running

    def connected(self, session_id: str) -> bool:
        link = self.links.get(session_id)
        return link is not None and link.client is not None and not link.client.closed.is_set()

    async def precheck(self, socket, session_id: str) -> Optional[dict]:
        """Before a Mode 1 turn is admitted: a refusal (the client's ``{ok: false}`` shape) when the unit has no pane and none may be
        opened, else None. Opening Lampway Agent's pane is the user's own chat (law 5 and the human gate: an agent's socket never
        opens one), with the engine, its TUI and Node here, on a running herdr server the user started (it is never started
        implicitly). Each refusal names the exact build command or setting, and the switch to Your agent where that would help
        (spec A5: nothing else runs Mode 1)."""
        if self.connected(session_id) or await asyncio.to_thread(self.units.known, session_id) is not None:
            return None
        from ..agent.byoa import origin_of
        if origin_of(socket) != "user":
            return _refusal("agent_origin", "Only your own message in Lampway opens Lampway Agent's pane; an agent cannot.",
                            ["Ask from the island of the scene tab"])
        from ..agent.turns import YOUR_AGENT_HELP
        missing = self.units.missing()                      # spec A5: no other loop stands in; refused, saying what to build
        if missing:
            code, why, fix = missing
            return _refusal(code, f"{why}, so this message was not sent.", [fix, YOUR_AGENT_HELP])
        from ..herdr import launcher as L
        try:
            await asyncio.to_thread(L.bin_path)
        except L.HerdrError:
            return _refusal("herdr_not_built", "Lampway Agent runs in a pane on Lampway's herdr server, and no herdr was found here, so "
                            "this message was not sent.", ["Build Lampway's pinned herdr: scripts/lampway/herdr_env.py (or set "
                                                           "LAMPWAY_HERDR_BIN to a herdr 0.9.3), then start its server from the cockpit"])
        running = await asyncio.to_thread(lambda: bool(L.server_status(self.units.cockpit.root).get("running")))
        if not running:
            return _refusal("herdr_not_running", "Lampway Agent runs in a pane on Lampway's herdr server, which is not running, so "
                            "this message was not sent.", ["Start the herdr server from the cockpit (Lampway > Agents), then send again"])
        return None

    async def drive(self, socket, session, turn, stream, bubble_id, steps, user_text: Optional[str], context=None) -> str:
        """Run (or continue, ``user_text`` None after the island answered) the unit's Hermes turn for this island turn. Returns the
        turn's status; returns early, the Hermes turn still running, when it stops for a question (``turn.asked``)."""
        link = await self._ensure(session.session_id, open_pane=user_text is not None, label=(context or {}).get("scene_name"))
        turn.conversation_id = self.conversation_of(session.session_id) or ""
        sink = Sink(socket, session, turn, stream, bubble_id, steps, done=asyncio.get_running_loop().create_future(),
                    asked=asyncio.Event())
        if user_text is not None and self._retry_click(socket, session.session_id, user_text):
            link.sink = sink                                  # the retried swarm's cards and Retry chip land on this turn's bubble
            try:
                note = await self._retry(socket, session, turn, stream, bubble_id, steps)
            except BaseException:
                if link.sink is sink:
                    link.sink = None
                raise
            user_text = f"{user_text}\n\n{note}" if note else user_text
        if user_text is None:
            held = link.sink
            if held is not None and held.pending:          # events after the island's answer, held for this turn
                self._bind(link, sink)
                await self._flush(link, held)
            elif link.running:
                self._bind(link, sink)
            else:
                return "completed"
        else:
            link.sink = sink
            if link.stale is not None:
                await self._close_stale(link, sink)
            settled = getattr(self.units, "settled", None)
            if settled is not None:
                await settled()                             # a Capabilities change in flight reaches the pane first (E2)
            await self._bookmark(link, turn.turn_id)        # the client's checkpoint before this turn is bound to its command id
            try:
                for name, data in TC.attachments(context):
                    await link.client.call("image.attach_bytes", {"session_id": link.live_id, "content_base64": data, "filename": name})
                text, link.rules_key = TC.prompt_text(user_text, context, link.rules_key)
                link.island_prompts += 1
                try:
                    await link.client.call("prompt.submit", {"session_id": link.live_id, "text": text})
                except BaseException:
                    link.island_prompts -= 1
                    raise
            except BaseException:
                if link.sink is sink:
                    link.sink = None
                raise
        return await self._wait(link, sink)

    def _retry_click(self, socket, unit: str, text: str) -> bool:
        """The cards' "Retry failed tasks" chip sends the user's "continue" (``agent.chat``): with failed tasks on offer and from the
        user's own Client socket, it is the user's retry (the same rule the built-in turn had; ``agent/swarm_island.py``)."""
        from ..agent import questions as Q
        from ..agent.byoa import origin_of
        swarm = getattr(self.hub, "swarm", None)
        return (str(text).strip().lower() == Q.CONTINUE_MESSAGE and swarm is not None and swarm.retryable(unit)
                and origin_of(socket) == "user")

    async def _retry(self, socket, session, turn, stream, bubble_id, steps) -> str:
        """Run the unit's failed tasks again inside this island turn (its steps and cards on this turn's bubble), and return the one
        line the pane's Hermes gets with the user's "continue" (``swarm.retry_note``)."""
        from ..agent.swarm import retry_note
        rows = [{"id": f"retry_{uuid.uuid4().hex[:8]}", "kind": "tool", "label": name, "target": "", "detail": "retry failed tasks",
                 "status": "running"} for name in ("swarm_start", "swarm_collect")]
        steps.extend(rows)
        await stream.emit_quietly({"bubble_id": bubble_id, "steps": {"items": list(steps)}})

        def progress(text: str):
            rows[0]["detail"] = f"retry failed tasks: {text}"[:160]

        async def emit_todo(todo):
            await stream.emit_quietly({"bubble_id": bubble_id, "todo": todo})
        try:
            result = await self.hub.swarm.retry(session.session_id, socket, emit_todo=emit_todo, progress=progress,
                                                turn_id=turn.turn_id, run_id=turn.run_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - told to the island and to Hermes, the turn goes on
            log.warning("the user's retry of failed swarm tasks did not run: %s", exc)
            result = {"tasks": [], "retried_from": [], "error": str(exc)}
        failed_start = bool(result and result.get("error") and not result.get("swarm_id"))
        rows[0]["status"] = "failed" if failed_start else "done"
        rows[1]["status"] = "failed" if (not result or result.get("error")) else "done"
        await stream.emit_quietly({"bubble_id": bubble_id, "steps": {"items": list(steps)}})
        return retry_note(result)

    async def _wait(self, link: Link, sink: Sink) -> str:
        asked = asyncio.ensure_future(sink.asked.wait())
        try:
            await asyncio.wait({sink.done, asked}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            asked.cancel()
            if link.sink is sink:
                link.sink = None
            if link.running:                                # agent.cancel: Hermes stops; its end is nobody's now
                link.absorb += 1
                asyncio.ensure_future(self._interrupt(link))
            raise
        asked.cancel()
        if sink.done.done():
            return sink.done.result()
        return "completed"                                  # a question: the hub ends the island turn as in progress

    async def steer(self, session_id: str, text: str) -> None:
        link = self.links[session_id]
        await link.client.call("session.steer", {"session_id": link.live_id, "text": text.strip()})

    async def interrupt(self, session_id: str) -> bool:
        link = self.links.get(session_id)
        if link is None or not link.running:
            return False
        await self._interrupt(link)
        return True

    async def _interrupt(self, link: Link) -> None:
        try:
            await link.client.call("session.interrupt", {"session_id": link.live_id}, timeout=15)
        except Exception:  # noqa: BLE001 - serve gone: nothing to stop
            log.debug("session.interrupt failed", exc_info=True)

    def has_question(self, session_id: str) -> bool:
        link = self.links.get(session_id)
        return link is not None and link.question is not None and not link.question.answered

    def answer(self, session_id: str, text: str) -> None:
        """The island's answer: the response frame to serve's request. The turn's next events wait for the island's continuation turn
        (the hub admits it right after this)."""
        link = self.links.get(session_id)
        q = link.question if link is not None else None
        if q is None or q.answered:
            return
        q.answered = True
        link.question = None
        result = {"answer": str(text)} if q.kind == "clarify" else {"choice": approval_choice(text, q.choices)}
        if link.sink is None:
            link.sink = Sink(pending=True)
        asyncio.ensure_future(self._respond(link, q, result))

    async def _respond(self, link: Link, q: Question, result: dict) -> None:
        try:
            await link.client.respond(q.request_id, result)
        except Exception:  # noqa: BLE001 - serve gone: the pane answers instead, or the turn ends with it
            log.warning("the island's answer could not reach Lampway Agent's pane", exc_info=True)

    def reattach(self, session_id: str, socket) -> None:
        link = self.links.get(session_id)
        if link is not None and link.sink is not None and not link.sink.pending:
            link.sink.socket = socket

    async def close(self) -> None:
        """Server shutdown: this server's connections close; every pane and its serve run on (law 5)."""
        for link in list(self.links.values()):
            link.closing = True
            if link.watcher is not None:
                link.watcher.cancel()
            if link.client is not None:
                await link.client.close()

    async def adopt(self, recs: list) -> None:
        """After a restart: re-attach to every live main pane, so a turn typed in it reaches the island again."""
        for rec in recs:
            if rec.get("role") == "main" and rec.get("unit"):
                link = self._link(rec["unit"])
                if link.watcher is None or link.watcher.done():
                    link.watcher = asyncio.ensure_future(self._reconnect(link, first=True))

    # ------------------------------------------------------------------------------------------------- the archive (R2)
    async def history_sync(self, params: dict) -> dict:
        """``agent.history_sync``: the client's archive, from the units' Hermes sessions (``history.Feed``)."""
        if self.feed is None:
            from .history import Feed
            self.feed = Feed(self)
        return await self.feed.sync(params)

    async def archive_link(self, unit: str) -> Optional[Link]:
        """The unit's connection to its pane's serve, when this server holds one (a chat or a restart's adoption made it); the
        archive never opens a pane and never waits for a serve to start."""
        link = self.links.get(unit)
        if link is None or link.client is None or link.client.closed.is_set() or not link.live_id:
            return None
        return link

    # ------------------------------------------------------------------------------------------------- checkpoints
    async def checkpoint_mark(self, session_id: str, request_id: str) -> bool:
        """``agent.checkpoint.mark``: the conversation's point now (the user turns Hermes's session holds) under the client's id."""
        link = await self.archive_link(session_id)
        return link is not None and await self._bookmark(link, request_id)

    async def checkpoint_rewind(self, session_id: str, request_id: str) -> dict:
        """``agent.checkpoint.rewind``: the scene went back to a bookmark, and Hermes's conversation follows it. serve's
        ``session.undo`` drops the last user turn and what followed, durably (``state.db``), and refuses while a turn runs
        (measured 2026-10-07); it is called until the session holds the bookmark's user turns, counted again after each undo.
        Hermes cannot bring undone turns back, so a rewind forward is refused, saying so, as is one into a conversation the pane
        left (``/new``) and one while the agent works."""
        link = await self.archive_link(session_id)
        if link is None:
            return _rewind_refusal("rewind_unavailable", "Lampway Agent's pane is not connected to Lampway now, so its conversation "
                                   "could not be rewound")
        mark = self._marks(link).get(str(request_id))
        if mark is None:
            return _rewind_refusal("rewind_unknown", "Lampway has no bookmark of Lampway Agent's conversation for that checkpoint")
        if mark.get("session") != (link.info.stored_id if link.info is not None else None):
            return _rewind_refusal("rewind_other_conversation", "that checkpoint belongs to an earlier conversation of Lampway Agent's "
                                   "pane (it started a new one since), which stays as it was")
        if link.running:
            return _rewind_refusal("rewind_busy", "Lampway Agent is working on a turn; stop it, then restore the checkpoint again")
        want = int(mark.get("turns") or 0)
        users = await self._user_rows(link)
        have = len(users)
        if have < want or (want and _turn_key(users[want - 1]) != mark.get("last")):
            # Fewer turns than the bookmark, or its last turn is not there any more (undone, then the conversation went on):
            # the turns this checkpoint holds were undone, and Hermes cannot bring them back.
            return _rewind_refusal("rewind_forward", "Hermes cannot bring back turns it already undid, so Lampway Agent does not "
                                   "remember the turns this checkpoint restores")
        start = have
        while have > want:
            try:
                removed = int((await link.client.call("session.undo", {"session_id": link.live_id})).get("removed") or 0)
            except ServeError as exc:
                if exc.code == BUSY:
                    return _rewind_refusal("rewind_busy", "Lampway Agent started a turn; stop it, then restore the checkpoint again")
                raise
            if removed <= 0:
                break
            have = len(await self._user_rows(link))
        if self.feed is not None:
            self.feed.forget(link.unit)                      # the archive reads the shortened history at its next poll
        log.info("Lampway Agent's conversation for %s rewound by %d turn(s) to a checkpoint", link.unit, start - have)
        return {"ok": True, "has_conversation": True, "removed_turns": start - have}

    async def _user_rows(self, link: Link) -> list:
        msgs = (await link.client.call("session.history", {"session_id": link.live_id})).get("messages") or []
        return [m for m in msgs if m.get("role") == "user"]

    def _marks(self, link: Link) -> dict:
        if link.marks is None:
            link.marks = {}
            path = self._marks_path(link)
            if path is not None:
                try:
                    link.marks = dict(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError, TypeError):
                    link.marks = {}
        return link.marks

    @staticmethod
    def _marks_path(link: Link):
        home = getattr(link.info, "home", None) if link.info is not None else None
        return Path(home) / MARKS_FILE if home else None

    async def _bookmark(self, link: Link, request_id: str) -> bool:
        if not request_id or link.client is None:
            return False
        try:
            users = await self._user_rows(link)
        except Exception:  # noqa: BLE001 - a bookmark never stops a turn
            log.debug("the checkpoint bookmark %s could not be taken", request_id, exc_info=True)
            return False
        marks = self._marks(link)
        marks[str(request_id)] = {"session": link.info.stored_id if link.info is not None else None, "turns": len(users),
                                  "last": _turn_key(users[-1]) if users else ""}
        while len(marks) > MAX_MARKS:
            marks.pop(next(iter(marks)))
        path = self._marks_path(link)
        if path is not None:
            from .units import write_private
            try:
                await asyncio.to_thread(write_private, path, json.dumps(marks))
            except OSError:
                log.warning("the checkpoint bookmarks of %s could not be saved", link.unit)
        return True

    # ------------------------------------------------------------------------------------------------- tools (A3)
    def session_for_token(self, unit: str, token: str):
        return unit if self.units.check_mcp(unit, token) else None

    def tool_specs(self, unit: Optional[str] = None) -> list:
        from .. import capabilities as CAP
        from ..agent.swarm import SWARM_SPECS
        from ..agent.tools import TOOLS
        return [t for t in list(TOOLS) + list(SWARM_SPECS) if CAP.tool_offered(t.name)]

    async def call_tool(self, unit: str, name: str, arguments: dict) -> tuple:
        """One of Lampway's tools from the unit's Hermes, whoever started its turn: on the scene tab's current client socket."""
        from ..agent.providers.base import ToolCall
        from ..agent.turns import Turn, clip_result
        socket = self.hub.socket_for(unit)
        if socket is None:
            return ("refused: Lampway is not open on this scene (no Lampway window is connected to this conversation), so its "
                    "tools cannot reach the scene. Ask the user to open the .blend in Lampway, then try again."), True
        link = self.links.get(unit)
        sink = await self._shown_turn(link)
        session = sink.session if sink is not None else self.hub._session(unit)
        turn = sink.turn if sink is not None else Turn(unit, f"pane_{uuid.uuid4().hex[:12]}", "")
        call = ToolCall(id=f"eng_{uuid.uuid4().hex[:12]}", name=name, arguments=arguments if isinstance(arguments, dict) else {})
        # The island turn showing this call (if any) is where a swarm's todo cards and progress go (the Parallel Agents panel); the
        # call's own step row is serve's (tool.start), the last one in the turn's steps.
        content, is_error = await self.hub._run_tool(socket, session, turn, call, *((sink.stream, sink.bubble_id, sink.steps)
                                                                                    if sink is not None else (None, None, None)))
        return clip_result(content), is_error

    async def _shown_turn(self, link: Optional[Link]) -> Optional[Sink]:
        """The island turn that shows the Hermes turn making this call. A call can overtake its turn: the pane turn is still being
        opened (its user text read from the history, its start sent to the client) or the island's answer has not been admitted
        yet (``Sink.pending``), or serve's ``message.start`` is still on its way. The call waits for that turn, up to
        ``TURN_WAIT_S``, so it runs under the turn id the client shows (a scratch id is refused there as ``unknown_turn``). Only a
        call no turn ever owns gets a scratch turn."""
        if link is None:
            return None
        deadline = asyncio.get_running_loop().time() + TURN_WAIT_S
        while True:
            sink = link.sink
            if sink is not None and not sink.pending:
                return sink
            if sink is None and link.absorb > 0:
                return None                                  # the user stopped the island's turn: no turn will show this call
            if asyncio.get_running_loop().time() >= deadline:
                log.warning("a tool call from Lampway Agent's pane for %s found no turn shown in the island within %.0fs", link.unit,
                            TURN_WAIT_S)
                return None
            await asyncio.sleep(0.05)

    # ------------------------------------------------------------------------------------------------- the connection
    async def _ensure(self, unit: str, open_pane: bool = False, label=None) -> Link:
        link = self._link(unit)
        async with link.lock:
            if link.client is not None and not link.client.closed.is_set():
                return link
            info = await asyncio.to_thread(self.units.known, unit)
            if info is not None:
                try:
                    await self._connect(link, info, timeout=KNOWN_CONNECT_S)
                    return link
                except Exception:  # noqa: BLE001 - its serve does not answer: is the pane still there?
                    if await asyncio.to_thread(self.units.alive, info):
                        raise
                    info = None                          # the pane ended: the user's chat opens a new one (it resumes the session)
            if not open_pane:
                raise RuntimeError("Lampway Agent's pane is not open for this scene tab")
            info = await self.units.open(unit, label)
            await self._connect(link, info)
            return link

    async def _connect(self, link: Link, info, timeout: Optional[float] = None) -> None:
        from .units import START_TIMEOUT_S, connect_when_up
        link.info = info

        async def on_event(params):
            await self._on_event(link, params)

        async def on_request(frame):
            await self._on_request(link, frame)
        client = await connect_when_up(info, on_event=on_event, on_request=on_request, timeout=timeout or START_TIMEOUT_S)
        same_epoch = bool(link.epoch) and link.epoch == client.epoch
        link.client, link.epoch = client, client.epoch
        if not same_epoch:
            self._stale_question(link)                      # serve restarted: its waiting request died with it
        moved = await self._moved_while_away(link, client)
        info = link.info
        res = await client.call("session.resume", {"session_id": info.stored_id})
        link.live_id = str(res.get("session_id") or "")
        running = bool(res.get("running"))
        if same_epoch and link.last_seq >= 0:
            await self._catch_up(link, running)
        else:
            link.last_seq = -1
            await self._settle(link, running, res)
        if moved:
            await self._tell_new_conversation(link)
        if link.watcher is None or link.watcher.done():
            link.watcher = asyncio.ensure_future(self._watch(link, client))

    async def _watch(self, link: Link, client: ServeClient) -> None:
        await client.closed.wait()
        if link.client is client and not link.closing:
            link.client = None
            await self._reconnect(link)

    async def _reconnect(self, link: Link, first: bool = False) -> None:
        """Re-make a dropped connection while the pane lives (and, after a restart, the first one)."""
        for n in range(10_000):
            if link.closing:
                return
            if not first or n:
                await asyncio.sleep(RECONNECT_S[min(n, len(RECONNECT_S) - 1)])
            info = await asyncio.to_thread(self.units.known, link.unit)
            if info is None:
                return                                       # the pane ended: the next chat opens one
            try:
                async with link.lock:
                    if link.client is not None and not link.client.closed.is_set():
                        return
                    link.watcher = None
                    await self._connect(link, info, timeout=KNOWN_CONNECT_S)
                return
            except Exception:  # noqa: BLE001 - serve not up yet (restarting) or the pane gone
                if n >= len(RECONNECT_S) and not await asyncio.to_thread(self.units.alive, info):
                    log.info("Lampway Agent's pane for %s is gone; the next chat opens a new one", link.unit)
                    return

    async def _catch_up(self, link: Link, running: bool) -> None:
        """Missed events, from serve's replay ring; past it (``truncated``), the history fills in."""
        try:
            res = await link.client.call("session.events.since", {"session_id": link.live_id, "last_seen": link.last_seq})
        except ServeError:
            res = {"truncated": True}
        if res.get("truncated"):
            await self._settle(link, running, {})
            return
        for ev in res.get("events") or []:
            await self._on_event(link, ev)

    async def _settle(self, link: Link, running: bool, resumed: dict) -> None:
        """No replay (a new epoch, or past the ring): a turn the island waits on that is over takes its end from the history; a turn
        running that nobody shows becomes the pane's own island turn."""
        link.running = running
        sink = link.sink
        if not running and sink is not None and not sink.pending and sink.done is not None and not sink.done.done():
            text, ended = await self._last_reply(link)
            await self._end(link, sink, "completed" if ended else "failed",
                            text or "The turn ended while Lampway was away from it, and its reply was not kept.")
        elif running and sink is None:
            user = str(((resumed or {}).get("inflight") or {}).get("user") or "")
            self._open_pane_turn(link, user_text=user)

    async def _last_reply(self, link: Link) -> tuple:
        try:
            msgs = (await link.client.call("session.history", {"session_id": link.live_id})).get("messages") or []
        except Exception:  # noqa: BLE001
            return "", False
        last_user = max((i for i, m in enumerate(msgs) if m.get("role") == "user"), default=-1)
        after = [m for m in msgs[last_user + 1:] if m.get("role") == "assistant" and m.get("text")]
        return (str(after[-1]["text"]), True) if after else ("", False)

    async def _last_user_text(self, link: Link) -> str:
        try:
            msgs = (await link.client.call("session.history", {"session_id": link.live_id})).get("messages") or []
        except Exception:  # noqa: BLE001
            return ""
        return next((str(m.get("text") or "") for m in reversed(msgs) if m.get("role") == "user"), "")

    async def _check_session(self, link: Link) -> None:
        """``sessions.changed``: when the island's session is closed (``/new`` in the pane), follow the pane (Q15)."""
        live = link.live_id
        if not live or link.client is None:
            return
        try:
            await link.client.call("session.status", {"session_id": live})
            return
        except ServeError as exc:
            if exc.code != SESSION_NOT_FOUND:
                return
        except (ServeClosed, asyncio.TimeoutError):
            return
        await self._follow(link)

    async def _follow(self, link: Link) -> None:
        old = link.live_id
        try:
            rows = (await link.client.call("session.active_list", {})).get("sessions") or []
        except Exception:  # noqa: BLE001
            return
        rows = [r for r in rows if r.get("id") != old and r.get("session_key")]
        if not rows:
            return
        newest = max(rows, key=lambda r: float(r.get("started_at") or 0))
        res = await link.client.call("session.resume", {"session_id": newest["session_key"]})
        if link.live_id != old:
            return                                           # serve says sessions.changed twice: another check followed it
        link.live_id = str(res.get("session_id") or newest["id"])
        link.last_seq = -1                                   # serve numbers each session's events from 1
        info = link.info
        if info is not None:
            from .units import UnitInfo
            link.info = UnitInfo(info.unit, info.record_id, info.home, info.port, info.token, str(newest["session_key"]))
            await asyncio.to_thread(self.units.record_session, link.info, str(newest["session_key"]))
        q, link.question, link.carried = link.question, None, []
        if q is not None:                                    # a question of the closed session: no answer can reach it now
            self._release_question(link, q)
        sink, link.sink = link.sink, None
        if sink is not None and not sink.pending and sink.done is not None and not sink.done.done():
            await self._end(link, sink, "cancelled", "The pane started a new conversation (/new); this one is in History.")
        link.running = bool(res.get("running"))
        log.info("Lampway Agent's pane for %s moved to a new session; the island follows it", link.unit)
        await self._tell_new_conversation(link)

    async def _tell_new_conversation(self, link: Link) -> None:
        """The tab's session id (the unit) stays: only this frame tells its current client to start a new chat and file the old one.
        A client that is not connected learns it from ``agent.status`` (``conversations``) when it comes back."""
        socket = self.hub.socket_for(link.unit)
        if socket is None:
            return
        try:
            await socket.notify("agent.pane.new_conversation", {"session_id": link.unit, "origin": "pane",
                                                                "conversation_id": self.conversation_of(link.unit)})
        except Exception:  # noqa: BLE001 - the client went away: agent.status tells it when it comes back
            log.debug("the island could not be told of the pane's /new", exc_info=True)

    async def _moved_while_away(self, link: Link, client: ServeClient) -> bool:
        """Before attaching: the pane's ``/new`` while this server was away (or not connected) left the record naming the closed
        session. serve's live sessions say which one the pane shows; the record follows it, and no closed session is reopened."""
        info = link.info
        try:
            rows = (await client.call("session.active_list", {})).get("sessions") or []
        except Exception:  # noqa: BLE001 - an older serve: attach to the recorded session
            return False
        rows = [r for r in rows if r.get("session_key")]
        if info is None or not rows or info.stored_id in {str(r["session_key"]) for r in rows}:
            return False
        newest = str(max(rows, key=lambda r: float(r.get("started_at") or 0))["session_key"])
        from .units import UnitInfo
        link.info = UnitInfo(info.unit, info.record_id, info.home, info.port, info.token, newest)
        await asyncio.to_thread(self.units.record_session, link.info, newest)
        link.last_seq = -1
        log.info("Lampway Agent's pane for %s moved to a new session while Lampway was away; the island follows it", link.unit)
        return True

    def conversation_of(self, unit: str) -> Optional[str]:
        """The Hermes session the unit's pane shows, as this server knows it (its connection)."""
        link = self.links.get(unit)
        return str(link.info.stored_id) if link is not None and link.info is not None and link.info.stored_id else None

    async def conversations(self, session_ids) -> dict:
        """``agent.status``'s ``conversations``: each Mode 1 tab's current conversation, from the connection or the pane's record."""
        out = {}
        for sid in session_ids:
            cid = self.conversation_of(sid)
            if cid is None:
                info = await asyncio.to_thread(self.units.known, sid)
                cid = str(info.stored_id) if info is not None and info.stored_id else None
            if cid:
                out[sid] = cid
        return out

    # ------------------------------------------------------------------------------------------------- serve's events
    async def _on_event(self, link: Link, params: dict) -> None:
        kind = params.get("type")
        if kind == "sessions.changed":
            if link.live_id:                                 # not while the connection is still resuming its session
                asyncio.ensure_future(self._check_session(link))
            return
        if params.get("session_id") and params.get("session_id") != link.live_id:
            return                                           # another session's (its seq counts its own events)
        seq = params.get("seq")
        if isinstance(seq, int):
            if seq <= link.last_seq:
                return
            link.last_seq = seq
        payload = params.get("payload") or {}
        if kind == "message.start":
            link.running = True
            self._stale_question(link)                      # a new Hermes turn: a question still open belongs to an earlier one
            if link.island_prompts > 0:
                link.island_prompts -= 1
            elif link.sink is None:
                self._open_pane_turn(link)                  # a turn typed in the pane (A2)
            return
        if kind not in ("message.delta", "reasoning.delta", "tool.start", "tool.complete", "message.complete", "error"):
            return
        q = link.question
        if q is not None and not q.answered and kind != "error":
            # The turn moved on without the island's answer: the pane answered. No request.cancel comes (measured): close the
            # island's card and show the rest of the turn in the island.
            link.question = None
            self._release_question(link, q)
            if link.sink is None:
                self._open_pane_turn(link, run_id=q.run_id, close=q)
        if kind == "message.complete":
            link.running = False
            if link.absorb > 0 and link.sink is None:
                link.absorb -= 1
                return
        sink = link.sink
        if sink is None:
            return
        if sink.pending:
            sink.buffer.append(("event", params))
            return
        await self._apply(link, sink, kind, payload)

    async def _apply(self, link: Link, sink: Sink, kind: str, payload: dict) -> None:
        emit = sink.stream.emit_quietly
        if kind in ("message.delta", "reasoning.delta"):
            text = str(payload.get("text") or "")
            if text:
                if kind == "message.delta":
                    sink.text.append(text)
                await emit({"bubble_id": sink.bubble_id, "ephemeral": {"append": text}})
        elif kind == "tool.start":
            name = tool_name(payload)
            if name in HIDDEN_TOOLS:
                return
            sink.steps.append({"id": str(payload.get("tool_id") or uuid.uuid4().hex[:8]), "kind": "tool", "label": step_label(name),
                               "target": "", "detail": "", "status": "running"})
            await emit({"bubble_id": sink.bubble_id, "steps": {"items": list(sink.steps)}})
        elif kind == "tool.complete":
            tid = str(payload.get("tool_id") or "")
            for step in sink.steps:
                if step["id"] == tid and step["status"] == "running":
                    step["status"] = "failed" if failed(payload) else "done"
                    await emit({"bubble_id": sink.bubble_id, "steps": {"items": list(sink.steps)}})
                    break
        elif kind == "error":
            message = str(payload.get("message") or payload.get("error") or "")
            if message:
                await emit({"type": "error", "message": f"Lampway Agent: {message}"})
        elif kind == "message.complete":
            status = STATUS.get(str(payload.get("status") or "complete"), "completed")
            text = str(payload.get("text") or "").strip() or "".join(sink.text).strip()
            if status == "failed" and not text:
                text = "The agent's turn failed in Hermes; its pane shows why."
            await self._end(link, sink, status, text)

    async def _end(self, link: Link, sink: Sink, status: str, text: str) -> None:
        if link.sink is sink:
            link.sink = None
        if text:
            await sink.stream.emit_quietly({"bubble_id": sink.bubble_id, "content": {"set": text}})
        if sink.done is not None and not sink.done.done():
            sink.done.set_result(status)

    async def _flush(self, link: Link, held: Sink) -> None:
        sink = link.sink
        for what, item in held.buffer:
            if link.sink is not sink:
                return
            if what == "event":
                await self._apply(link, sink, item.get("type"), item.get("payload") or {})
            else:
                await self._ask(link, sink, item)

    # ------------------------------------------------------------------------------------------------- serve's requests
    async def _on_request(self, link: Link, frame: dict) -> None:
        method = frame.get("method")
        params = frame.get("params") or {}
        if method not in ("clarify", "approval"):
            return                                           # the pane's own (secrets, sudo, ...): the TUI answers them
        if params.get("session_id") and params.get("session_id") != link.live_id:
            return
        if method == "clarify":
            choices = [str(c) for c in params.get("choices") or [] if str(c).strip()][:6]
            body = str(params.get("question") or "").strip() or "Which do you want?"
        else:
            choices = [str(c) for c in params.get("choices") or ["once", "deny"]]
            command = str(params.get("command") or params.get("description") or "this")
            why = str(params.get("description") or "").strip()
            body = f"Allow the agent to run this?\n\n{command}" + (f"\n\n({why})" if why and why != command else "")
        q = Question(str(frame.get("id")), method, f"q_{uuid.uuid4().hex[:12]}", body, choices)
        link.question = q
        sink = link.sink
        if sink is None:
            self._open_pane_turn(link)
            sink = link.sink
        if sink.pending:
            sink.buffer.append(("request", q))
            return
        await self._ask(link, sink, q)

    async def _ask(self, link: Link, sink: Sink, q: Question) -> None:
        """The island's question card on this turn's bubble; the hub routes the answer (``agent.input``) to ``answer``."""
        if q.answered or link.question is not q:
            return
        text = "".join(sink.text).strip()
        body = f"{text}\n\n{q.body}" if text else q.body
        q.body, q.bubble_id, q.run_id = body, sink.bubble_id, sink.turn.run_id
        sink.session.pending_question = {"interrupt_id": q.interrupt_id, "call_id": q.request_id, "question": q.body, "engine": q.kind}
        sink.turn.asked = True
        event = {"bubble_id": sink.bubble_id, "content": {"set": body}, "interrupt_id": q.interrupt_id}
        if q.kind == "clarify":
            event["input_type"] = "choice" if q.choices else "text"
            if q.choices:
                event["actions"] = [{"label": c, "value": c, "style": "primary" if i == 0 else "default"} for i, c in enumerate(q.choices)]
        else:
            event["input_type"] = "approval"
            event["actions"] = [{"label": APPROVAL_LABELS.get(c, c), "value": c, "style": "danger" if c == "deny" else
                                 ("primary" if i == 0 else "default")} for i, c in enumerate(q.choices)]
        sink.text.clear()
        await sink.stream.emit_quietly(event)
        # The tool waiting on this answer (a command needing approval) completes in the continuation turn: its step goes along.
        link.carried = [dict(s) for s in sink.steps if s["status"] == "running"]
        if link.sink is sink:
            link.sink = None                                 # the rest of the turn is the answer's continuation turn
        sink.asked.set()

    @staticmethod
    def _bind(link: Link, sink: Sink) -> None:
        """This island turn shows the running Hermes turn from now on, with the steps still running from before its question."""
        sink.steps.extend(link.carried)
        link.carried = []
        link.sink = sink

    def _release_question(self, link: Link, q: Question) -> None:
        session = self.hub.sessions.get(link.unit)
        if session is not None and (session.pending_question or {}).get("interrupt_id") == q.interrupt_id:
            session.pending_question = None

    def _stale_question(self, link: Link) -> None:
        """The island's question can no longer be answered: Hermes started another turn, or serve restarted and its request died
        with it. It is released (the tab's next chat is a prompt, never an answer to a request nobody waits on), and its card is
        closed in the turn that shows Hermes now, else in the next one the island shows (``_close_stale``)."""
        q, link.question = link.question, None
        if q is None or q.answered:
            return
        self._release_question(link, q)
        if not q.bubble_id:
            return                                          # never shown: nothing to close
        link.stale = q
        sink = link.sink
        if sink is not None and not sink.pending:
            asyncio.ensure_future(self._close_stale(link, sink))

    async def _close_stale(self, link: Link, sink: Sink) -> None:
        q, link.stale = link.stale, None
        if q is not None:
            await sink.stream.emit_quietly({"bubble_id": q.bubble_id, "input_type": "", "actions": [],
                                            "content": {"set": f"{q.body}\n\n{NOT_ANSWERED}"}})

    # ------------------------------------------------------------------------------------------------- the pane's own turns
    def _open_pane_turn(self, link: Link, user_text: Optional[str] = None, run_id: str = "", close: Optional[Question] = None) -> None:
        """An island turn for a Hermes turn the island did not start: typed in the pane (its user text from the history), or the
        rest of a turn whose question the pane answered (the same run, so the island takes it as its continuation)."""
        held = Sink(pending=True)
        link.sink = held
        asyncio.ensure_future(self._pane_turn(link, held, user_text, run_id, close))

    async def _pane_turn(self, link: Link, held: Sink, user_text: Optional[str], run_id: str, close: Optional[Question]) -> None:
        from ..agent.turns import Turn, TurnStream
        hub = self.hub
        unit = link.unit
        if user_text is None and close is None:
            user_text = await self._last_user_text(link)
        socket = hub.socket_for(unit)
        session = hub._session(unit)
        if user_text:
            session.last_user = user_text                   # the user's words, typed in the pane
        tid = f"pane_{uuid.uuid4().hex[:12]}"
        turn = Turn(unit, tid, run_id or str(uuid.uuid4()))
        turn.conversation_id = self.conversation_of(unit) or ""
        turn.socket = socket  # type: ignore[attr-defined]
        turn.detached = socket is None
        turn.task = asyncio.current_task()
        stream = TurnStream(socket, turn)
        turn.stream = stream
        session.turns[tid] = turn
        session.last_turn_id = tid
        previous, session.current = session.current, turn
        bubble_id = f"{tid}:agent"
        steps: list = []
        sink = Sink(socket, session, turn, stream, bubble_id, steps, done=asyncio.get_running_loop().create_future(),
                    asked=asyncio.Event())
        status = "completed"
        try:
            if socket is not None:
                try:
                    await socket.notify("agent.turn.started", {"session_id": unit, "turn_id": tid, "run_id": turn.run_id,
                                                               "origin": "pane", "user_text": user_text or "",
                                                               "conversation_id": self.conversation_of(unit)})
                except Exception:  # noqa: BLE001 - the client went away: the journal keeps the turn for attach
                    turn.detached = True
            await stream.emit_quietly({"type": "run_status", "run_id": turn.run_id, "status": "in_progress"})
            if close is not None:
                await stream.emit_quietly({"bubble_id": close.bubble_id, "input_type": "", "actions": [],
                                           "content": {"set": f"{close.body}\n\n{ANSWERED_ELSEWHERE}"}})
            if link.stale is not None:
                await self._close_stale(link, sink)
            await stream.emit_quietly({"bubble_id": bubble_id, "loader": {"visible": True, "texts": ["Thinking..."], "rotate_ms": 2000}})
            if link.sink is held:
                self._bind(link, sink)
                await self._flush(link, held)
            elif not held.buffer:
                sink.done.set_result("completed")
            status = await self._wait(link, sink)
        except asyncio.CancelledError:
            status = "cancelled"
        except Exception:  # noqa: BLE001 - the turn must end for the client
            log.exception("the pane's turn %s could not be shown", tid)
            status = "failed"
        finally:
            if session.current is turn and previous is not None and previous.status == "running":
                session.current = previous
            await hub._finish(turn.stream.socket if turn.stream.socket is not None else _NoSocket(), session, turn, stream,
                              bubble_id, steps, status)


class _NoSocket:
    async def notify(self, method, params):
        raise ConnectionError("no client")


def _turn_key(message: dict) -> str:
    """Which user turn this is: its durable row id and its words (a row id alone may be given again after an undo)."""
    import hashlib
    return hashlib.sha256(f"{message.get('row_id')}:{message.get('text')}".encode("utf-8")).hexdigest()[:24]


def _rewind_refusal(code: str, message: str) -> dict:
    return {"ok": False, "code": code, "message": message}


def _refusal(code: str, message: str, help_: list) -> dict:
    return {"state": "complete", "result": {"ok": False, "code": code, "status_code": 409, "message": message, "help": help_}}


__all__ = ["HermesFront", "Link", "Question", "Sink", "approval_choice", "step_label", "tool_name"]
