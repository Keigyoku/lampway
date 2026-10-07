# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A scene tab in Your agent mode, the hub's half (docs/reports/agent-modes-spec.md M0 and B4).

**How the server learns a tab's mode (M0).** Two sources, either one enough: the chat payload's ``agent_mode`` (the client sends
the tab's saved ``Scene.lampway_agent_mode`` with every ``agent.chat``), and the cockpit's B2 binding table: a harness pane bound
to the tab's scene session (``Cockpit.find_by_scene``) means the tab is in Your agent mode. The binding table is the server's own
record and covers a client that does not send the field; the payload covers a tab whose pane was never bound. Switching a tab back
to Lampway Agent unbinds its panes (``POST /app/workbench/mode``), so the table never holds a tab the user took back. A tab in
Your agent mode has its ``agent.chat`` and ``agent.input`` refused with ``code: wrong_mode`` before any turn starts.

**The island view (B4).** ``agent.byoa.observe`` finds the pane from the binding table (never from a body field) and, for a harness
whose own session file Lampway reads (Claude Code, Codex: ``herdr/observers/mirror.py``), tails that file read-only and streams it
as observed turns over the asking socket: ``agent.turn.started`` with ``observed: true`` and the prompt, the same numbered
``agent.turn.event`` payloads Mode 1 sends (``run_status``, ``content.set``, ``steps``), a ``turn_end`` carrying the file offset
the client may resume from, and ``agent.turn.ended``. The turns are journalled in the hub's session like Mode 1's, so
``agent.status`` and ``agent.attach`` work unchanged. History written before the first observation is never replayed, unless the
client names the offset it rendered up to (``after_offset``). A harness with no readable file (OpenCode, the user's own Hermes,
whose home Lampway never reads (E1.10), Pi, Grok, Cursor) is answered with its pane's screen text (``view: screen``), which the
client polls.

**Typing into the pane (B4, B6).** ``agent.byoa.send`` types the island composer's text into the tab's bound pane. Who typed is
decided from the socket, never from the body: a worker socket, an agent or MCP token, or a cross-origin socket is an agent, and an
agent send passes the cockpit's checks (agent sends switched on for the pane, and the 2.5 s quiet window after the user's own
last send from the island).
"""
import asyncio
import json
import logging
import os
import time

from ..herdr import harnesses as HN
from ..herdr.observers import mirror as MR
from ..herdr.observers.native import codex_find_rollout

log = logging.getLogger("lampway.byoa")

POLL_S = 0.5               # how often a watched session file is read
RESOLVE_EVERY = 4          # polls between two looks for a rollout that has not appeared yet
READ_CHUNK = 1 << 20       # at most this much of a file per poll
SCREEN_LINES = 70

SWITCH_HELP = ("Switch this tab to Lampway Agent in the island's agent menu (the mode switch above the model list), "
               "or keep talking to your agent: in Your agent mode the composer types into its pane")
BIND_HELP = "Pick Your agent in the island's agent menu: it starts your agent in a pane bound to this tab, or binds one you already run"
RESUME_HELP = "Your agent's pane has ended: resume it from the cockpit (Lampway > Agents), or pick Your agent again to start a new one"


def _result(ok: bool, **fields) -> dict:
    return {"state": "complete", "result": {"ok": ok, **fields}}


def origin_of(socket) -> str:
    """Who is behind this socket: "user" for the user's own Client, else "agent" (agent-modes spec B6, the same rule as the
    workbench input route): a worker socket, a token minted for an agent or an MCP client, or a cross-origin socket."""
    if getattr(socket, "role", ""):
        return "agent"
    ws = getattr(socket, "ws", None)
    if ws is not None:
        from ..connections.routes import _cross_origin
        if _cross_origin(ws):
            return "agent"
        from ..ws import bearer_from
        claims = (socket.auth.verify_access(bearer_from(ws) or "") or {}) if getattr(socket, "auth", None) else {}
        if str(claims.get("origin") or "").lower() in ("agent", "mcp") or str(claims.get("aud") or "").lower() == "mcp":
            return "agent"
    return "user"


def _read_new(path: str, offset: int):
    """The complete records appended after ``offset``: ([(at, next_offset, record)], new offset). A record still being written
    (no newline yet) waits for the next poll; a line that is not JSON is passed over."""
    try:
        size = os.stat(path).st_size
    except OSError:
        return [], offset
    if size < offset:                     # the file was replaced: start again from its beginning
        offset = 0
    if size == offset:
        return [], offset
    with open(path, "rb") as fh:
        fh.seek(offset)
        chunk = fh.read(min(size - offset, READ_CHUNK))
    end = chunk.rfind(b"\n")
    if end < 0:
        return [], offset
    out, pos = [], offset
    for line in chunk[:end + 1].split(b"\n")[:-1]:
        at, pos = pos, pos + len(line) + 1
        if not line.strip():
            continue
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        out.append((at, pos, record))
    return out, pos


class _Watch:
    """One scene tab's observation of its pane: where the file is, how far it was read, the open turns."""

    def __init__(self, rec: dict, conv, after):
        self.rec = rec
        self.rec_id = rec["id"]
        self.harness = rec.get("harness")
        self.conv = conv
        self.after = after
        self.path = None
        self.offset = 0
        self.socket = None
        self.task = None
        self.polls = 0
        self.turns = {}


class ByoaView:
    def __init__(self, hub):
        self.hub = hub
        self.mirrors: dict = {}          # scene session id -> _Watch
        self.user_sent: dict = {}        # pane id -> when the user last typed into it from the island

    # ------------------------------------------------------------------------------------------------- the mode (M0)
    def _cockpit(self):
        return getattr(self.hub, "cockpit", None)

    def bound(self, session_id: str) -> list:
        """The harness panes bound to this scene tab, live or ended, from the cockpit's B2 table."""
        find = getattr(self._cockpit(), "find_by_scene", None)
        if not session_id or find is None:
            return []
        try:                                            # a user's harness only: Lampway's own pane is Mode 1's (spec A1), never a binding
            return [r for r in find(session_id) if r.get("harness") in HN.ADAPTERS]
        except Exception:  # noqa: BLE001 - an unreadable table is no binding
            log.debug("binding table unreadable", exc_info=True)
            return []

    def pane_for(self, session_id: str):
        """The tab's pane: a live one first (the most recently changed), else the most recent ended one (for its resume)."""
        recs = sorted(self.bound(session_id), key=lambda r: r.get("updated_at") or 0, reverse=True)
        return next((r for r in recs if r.get("state") == "live"), recs[0] if recs else None)

    def mode_of(self, session_id: str, payload=None) -> str:
        if isinstance(payload, dict) and str(payload.get("agent_mode") or "").lower() == "byoa":
            return "byoa"
        return "byoa" if self.bound(session_id) else "runtime"

    def refusal(self, session_id: str, payload=None):
        """``wrong_mode`` for a Mode 1 command into a tab in Your agent mode, else None."""
        if self.mode_of(session_id, payload) != "byoa":
            return None
        return _result(False, code="wrong_mode", status_code=409, help=[SWITCH_HELP],
                       message="This scene tab is in Your agent mode: Lampway Agent does not run here, so this message was not sent to it.")

    # ------------------------------------------------------------------------------------------------- the island view (B4)
    def _path(self, rec: dict):
        ad = HN.ADAPTERS.get(rec.get("harness"))
        obs = ad.observe(rec) if ad is not None else None
        if obs is None or not obs.path:
            return None
        if obs.kind == "session_file":
            return obs.path
        if obs.kind == "rollout":
            return codex_find_rollout(obs.path, rec.get("cwd") or "", float(rec.get("created_at") or 0), rec.get("native_id"))
        return None

    @staticmethod
    def _start_offset(path, after) -> int:
        try:
            size = os.stat(path).st_size if path else None
        except OSError:
            size = None
        if size is None:
            return 0                                    # the file does not exist yet: everything in it will be this pane's
        if isinstance(after, int) and not isinstance(after, bool) and 0 <= after <= size:
            return after                                # the client's own cursor
        return size                                     # history is never replayed

    async def observe(self, socket, params: dict) -> dict:
        from .turns import InvalidParams
        session_id = str(params.get("session_id") or "")
        if not session_id:
            raise InvalidParams("session_id is required")
        rec = self.pane_for(session_id)
        if rec is None:
            return {"view": "none", "code": "not_bound", "help": [BIND_HELP]}
        base = {"pane": rec["id"], "harness": rec.get("harness"), "state": rec.get("state"), "name": rec.get("name")}
        if rec.get("state") != "live":
            return {**base, "view": "ended", "help": [RESUME_HELP]}
        conv = MR.for_harness(rec.get("harness"), rec["id"])
        if conv is None:
            try:
                screen = await asyncio.to_thread(self._cockpit().read_screen, rec["id"], SCREEN_LINES)
            except Exception as exc:  # noqa: BLE001 - herdr down or the pane gone: say so, the client keeps polling
                return {**base, "view": "screen", "screen": "", "error": str(exc)}
            return {**base, "view": "screen", "screen": screen}
        watch = self.mirrors.get(session_id)
        if watch is None or watch.rec_id != rec["id"]:
            if watch is not None and watch.task is not None:
                watch.task.cancel()
            watch = self.mirrors[session_id] = _Watch(rec, conv, params.get("after_offset"))
            watch.path = await asyncio.to_thread(self._path, rec)
            if watch.path is not None:
                watch.offset = self._start_offset(watch.path, watch.after)
        watch.socket = socket
        if watch.task is None or watch.task.done():
            watch.task = socket.spawn(self._loop(session_id, watch))
        return {**base, "view": "transcript"}

    def forget(self, *session_ids) -> None:
        """Stop watching these tabs' panes (the tab switched away or handed its pane to a new chat session)."""
        for sid in session_ids:
            watch = self.mirrors.pop(sid, None) if sid else None
            if watch is not None and watch.task is not None:
                watch.task.cancel()

    async def _loop(self, session_id: str, watch: _Watch):
        while True:
            try:
                await self._poll(session_id, watch)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - one bad poll never ends the view
                log.debug("byoa view poll failed for %s", watch.rec_id, exc_info=True)
            await asyncio.sleep(POLL_S)

    async def _poll(self, session_id: str, watch: _Watch):
        if watch.path is None:
            watch.polls += 1
            if watch.polls % RESOLVE_EVERY != 1:
                return
            watch.path = await asyncio.to_thread(self._path, watch.rec)
            if watch.path is None:
                return
            after = watch.after
            watch.offset = after if isinstance(after, int) and not isinstance(after, bool) and after >= 0 else 0
        records, watch.offset = await asyncio.to_thread(_read_new, watch.path, watch.offset)
        for at, nxt, record in records:
            ops = watch.conv.feed(record, at)
            if ops:
                await self._apply(session_id, watch, ops, at, nxt)

    async def _apply(self, session_id: str, watch: _Watch, ops: list, at: int, nxt: int):
        from .turns import Turn, TurnStream
        socket = watch.socket
        for i, (kind, tid, data) in enumerate(ops):
            if kind == "start":
                session = self.hub._session(session_id)
                turn = Turn(session_id, tid, tid)
                turn.observed = True               # type: ignore[attr-defined]
                turn.socket = socket               # type: ignore[attr-defined]
                session.turns[tid] = turn
                session.last_turn_id = tid
                watch.turns[tid] = turn
                await self._notify(socket, "agent.turn.started", {
                    "session_id": session_id, "turn_id": tid, "run_id": tid, "observed": True, "harness": watch.harness,
                    "pane": watch.rec_id, "user_text": data.get("user_text", "")})
            elif kind == "event":
                turn = watch.turns.get(tid)
                if turn is not None:
                    await TurnStream(socket, turn).emit_quietly(data)
            elif kind == "end":
                turn = watch.turns.pop(tid, None)
                if turn is None:
                    continue
                # Ended by the next prompt (a start follows in the same record): resume from that prompt; else after this record.
                offset = at if any(k == "start" for k, _, _ in ops[i + 1:]) else nxt
                await TurnStream(socket, turn).emit_quietly({"type": "turn_end", "status": data.get("status", "completed"),
                                                             "run_id": turn.run_id, "offset": offset})
                turn.status = "ended"
                await self._notify(socket, "agent.turn.ended", {"session_id": session_id, "turn_id": tid, "last_seq": turn.last_seq})

    @staticmethod
    async def _notify(socket, method: str, params: dict):
        try:
            await socket.notify(method, params)
        except Exception:  # noqa: BLE001 - the socket is gone; the journal keeps the turn for attach
            log.debug("byoa view could not deliver %s", method, exc_info=True)

    # ------------------------------------------------------------------------------------------------- typing into the pane
    async def send(self, socket, params: dict) -> dict:
        from .turns import InvalidParams, _command_parts
        _command_id, payload = _command_parts(params)
        session_id = str(payload.get("session_id") or "")
        text = payload.get("text")
        if not session_id or not isinstance(text, str) or not text.strip():
            raise InvalidParams("payload.session_id and a non-empty payload.text are required")
        rec = self.pane_for(session_id)
        if rec is None or rec.get("state") != "live":
            return _result(False, code="not_bound", status_code=409, help=[BIND_HELP if rec is None else RESUME_HELP],
                           message="No running agent pane is bound to this scene tab, so nothing was typed.")
        by = origin_of(socket)
        typed_at = self.user_sent.get(rec["id"]) if by != "user" else None
        try:
            await asyncio.to_thread(self._cockpit().send_input, rec["id"], text, True, by, typed_at)
        except Exception as exc:  # noqa: BLE001 - the cockpit's refusals (CockpitError, HerdrError) carry their reason
            return _result(False, code="pane_refused", status_code=409, message=str(exc),
                           help=["Check the pane in the cockpit (Lampway > Agents); an agent's sends are the user's switch there"])
        if by == "user":
            self.user_sent[rec["id"]] = time.time()
        return _result(True, pane=rec["id"])
