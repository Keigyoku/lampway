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
last send from the island). Images ride with the text for a harness that takes an image by its path (``Adapter.takes_image_paths``):
the server writes them into a Lampway-owned folder inside the pane's project root (``Cockpit.write_pane_images``) and types their
paths the way the harness reads them; a harness that cannot take one is refused with its reason (``images_unsupported``).

**Stop (B4).** ``agent.byoa.interrupt``, and ``agent.cancel`` for a tab in Your agent mode, type the harness's own interrupt keys
into the tab's pane (``Adapter.interrupt_keys``, ``Cockpit.interrupt``): only from the user's own socket (an agent never stops a
user's pane from here), only into a live pane Lampway started and bound to that tab. The observed turn's end is what tells the
island the agent stopped.

**An ended pane (B2).** ``agent.byoa.observe`` answers ``view: ended`` with whether it can be resumed (a native session id was
recorded). ``agent.byoa.resume`` is the user's Resume: a new pane runs the adapter's resume with that id, bound to the tab; never
automatic (law 5), never from an agent. ``agent.byoa.unbind`` is the user's Unbind: the ended pane leaves the tab, nothing else.

**Retry from the swarm's cards.** A swarm the bound pane started shows its Parallel Agents cards on a card turn of its own
(``swarm_island.py``). Its "Retry failed tasks" chip sends the user's "continue" here: from the user's own socket, with failed tasks
on offer, the tasks run again (``SwarmManager.retry``, in the background; the reply says ``retry: true``), and then the pane is
typed the user's "continue" with one line saying what ran (``swarm.retry_note``). Any other "continue" is typed as it is.
"""
import asyncio
import base64
import binascii
import json
import logging
import os
import time

from ..herdr import harnesses as HN
from ..herdr.observers import mirror as MR
from ..herdr.observers.native import codex_find_rollout, codex_rollout_id, pi_find_session

log = logging.getLogger("lampway.byoa")

POLL_S = 0.5               # how often a watched session file is read
RESOLVE_EVERY = 4          # polls between two looks for a rollout that has not appeared yet
READ_CHUNK = 1 << 20       # at most this much of a file per poll
SCREEN_LINES = 70

SWITCH_HELP = ("Switch this tab to Lampway Agent in the island's agent menu (the mode switch above the model list), "
               "or keep talking to your agent: in Your agent mode the composer types into its pane")
BIND_HELP = "Pick Your agent in the island's agent menu: it starts your agent in a pane bound to this tab, or binds one you already run"
RESUME_HELP = "Your agent's pane has ended: press Resume to continue its conversation in a new pane, or Unbind to let this tab go"
NO_RESUME_HELP = ("Your agent's pane has ended and no session id was recorded for it, so it cannot be resumed: Unbind it, then pick "
                  "Your agent again to start a new one")
USER_ONLY = "Only your own click in Lampway does this: an agent cannot"


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
    @property
    def state_dir(self):
        return getattr(self.hub, "switch_dir", None)

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
            path = codex_find_rollout(obs.path, rec.get("cwd") or "", float(rec.get("created_at") or 0), rec.get("native_id"))
            if path and not rec.get("native_id"):
                # Codex picks its own session id: the rollout that is this pane's names it, and the record keeps it, so an ended
                # pane can be resumed (spec B2). Only the record changes; never the pane.
                nid = codex_rollout_id(path)
                note = getattr(self._cockpit(), "note_native_id", None)
                if nid and note is not None:
                    try:
                        note(rec["id"], nid)
                        rec["native_id"] = nid
                    except Exception:  # noqa: BLE001 - the record is the server's own; a failed write only costs the resume
                        log.debug("native id not recorded for %s", rec["id"], exc_info=True)
            return path
        if obs.kind == "pi_session":
            return pi_find_session(obs.path, rec.get("cwd") or "", rec.get("native_id"))
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
            resumable = bool(rec.get("native_id")) and rec.get("harness") in HN.ADAPTERS
            return {**base, "view": "ended", "resumable": resumable, "help": [RESUME_HELP if resumable else NO_RESUME_HELP]}
        conv = MR.for_harness(rec.get("harness"), rec["id"])
        if conv is None:
            try:
                screen = await asyncio.to_thread(self._cockpit().read_screen, rec["id"], SCREEN_LINES)
            except Exception as exc:  # noqa: BLE001 - herdr down or the pane gone: say so, the client keeps polling
                return {**base, "view": "screen", "screen": "", "error": str(exc), "agent_status": "unknown"}
            status = await asyncio.to_thread(self._cockpit().agent_status, rec["id"])
            return {**base, "view": "screen", "screen": screen, "agent_status": status}     # herdr's own working/idle reading
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
    @staticmethod
    def _images(payload: dict) -> list:
        """The island's images as bytes: ``images`` is a list of ``{"data": <base64>}`` (any name or type the client sends is
        ignored: the bytes decide)."""
        from .turns import InvalidParams
        out = []
        for item in payload.get("images") or []:
            data = item.get("data") if isinstance(item, dict) else None
            if not isinstance(data, str) or not data:
                raise InvalidParams("each payload.images item needs its base64 data")
            try:
                out.append(base64.b64decode(data, validate=True))
            except (binascii.Error, ValueError):
                raise InvalidParams("an image's data is not base64") from None
        return out

    async def send(self, socket, params: dict) -> dict:
        from .turns import InvalidParams, _command_parts
        _command_id, payload = _command_parts(params)
        session_id = str(payload.get("session_id") or "")
        text = payload.get("text")
        images = self._images(payload)
        if not session_id or not isinstance(text, str) or not (text.strip() or images):
            raise InvalidParams("payload.session_id and a non-empty payload.text (or images) are required")
        rec = self.pane_for(session_id)
        if self._retry_click(socket, session_id, text):
            # The cards' "Retry failed tasks" chip (agent/swarm_island.py): in a Your agent tab it sends the user's "continue" here.
            # From the user's own Client socket only (B6); the failed tasks run again, then the pane's agent is told (one typed line).
            spawn = getattr(socket, "spawn", None) or asyncio.ensure_future
            spawn(self._retry(session_id, socket, rec["id"] if rec is not None and rec.get("state") == "live" else None))
            return _result(True, pane=rec["id"] if rec is not None else None, retry=True)
        if rec is None or rec.get("state") != "live":
            return _result(False, code="not_bound", status_code=409, help=[BIND_HELP if rec is None else RESUME_HELP],
                           message="No running agent pane is bound to this scene tab, so nothing was typed.")
        by = origin_of(socket)
        typed_at = self.user_sent.get(rec["id"]) if by != "user" else None
        if images:
            ad = HN.ADAPTERS.get(rec.get("harness"))
            if ad is None or not ad.takes_image_paths:
                return _result(False, code="images_unsupported", status_code=409,
                               message=(ad.images_note if ad is not None else "") or "This agent cannot take an image, so nothing was typed.",
                               help=["Send the message without the image, or describe what it shows"])
            if by != "user":
                return _result(False, code="agent_origin", status_code=403, message="Only your own message carries images into your agent's pane.",
                               help=[USER_ONLY])
            try:
                paths = await asyncio.to_thread(self._cockpit().write_pane_images, rec["id"], images)
            except Exception as exc:  # noqa: BLE001 - CockpitError carries the reason (no project root, not an image, too large)
                return _result(False, code="images_refused", status_code=409, message=str(exc),
                               help=["Attach a PNG, JPEG, GIF or WebP image, or send the text alone"])
            text = ad.with_images(text, paths)
        try:
            await asyncio.to_thread(self._cockpit().send_input, rec["id"], text, True, by, typed_at)
        except Exception as exc:  # noqa: BLE001 - the cockpit's refusals (CockpitError, HerdrError) carry their reason
            return _result(False, code="pane_refused", status_code=409, message=str(exc),
                           help=["Check the pane in the cockpit (Lampway > Agents); an agent's sends are the user's switch there"])
        if by == "user":
            self.user_sent[rec["id"]] = time.time()
        return _result(True, pane=rec["id"])

    def _retry_click(self, socket, session_id: str, text: str) -> bool:
        """The user's own "continue" while the tab's cards offer Retry failed tasks (the same rule as Lampway Agent's tab)."""
        from . import questions as Q
        swarm = getattr(self.hub, "swarm", None)
        return (text.strip().lower() == Q.CONTINUE_MESSAGE and swarm is not None and swarm.retryable(session_id)
                and origin_of(socket) == "user")

    async def _retry(self, session_id: str, socket, pane_id) -> None:
        """Run the failed tasks again (``SwarmManager.retry``: its cards show in the island), then tell the pane's agent: the user's
        "continue" with what ran, as one line typed by the user's click."""
        from .swarm import retry_note
        try:
            result = await self.hub.swarm.retry(session_id, socket)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported to the pane below
            log.warning("the user's retry of failed swarm tasks did not run: %s", exc)
            result = {"tasks": [], "retried_from": [], "error": str(exc)}
        note = retry_note(result)
        if not note or pane_id is None:
            return
        try:
            await asyncio.to_thread(self._cockpit().send_input, pane_id, f"continue {note}", True, "user", None)
        except Exception as exc:  # noqa: BLE001 - the pane ended or herdr is gone: the island's cards still show what ran
            log.warning("the pane could not be told about the retry: %s", exc)

    # ------------------------------------------------------------------------------------------------- Stop, Resume, Unbind
    @staticmethod
    def _session_of(params: dict) -> str:
        from .turns import InvalidParams, _command_parts
        _command_id, payload = _command_parts(params)
        session_id = str(payload.get("session_id") or params.get("session_id") or "")
        if not session_id:
            raise InvalidParams("session_id is required")
        return session_id

    async def interrupt(self, socket, params: dict) -> dict:
        """The island's Stop for a tab in Your agent mode: the harness's own interrupt keys into the tab's live pane. Only the user's
        own socket: an agent never stops the user's pane from here (the cockpit tool's interrupt has its own request rule)."""
        session_id = self._session_of(params)
        if origin_of(socket) != "user":
            return _result(False, code="agent_origin", status_code=403, message="Only your own Stop interrupts your agent's pane.", help=[USER_ONLY])
        rec = self.pane_for(session_id)
        if rec is None or rec.get("state") != "live":
            return _result(False, code="not_bound", status_code=409, help=[BIND_HELP if rec is None else RESUME_HELP],
                           message="No running agent pane is bound to this scene tab, so there is nothing to stop.")
        try:
            keys = await asyncio.to_thread(self._cockpit().interrupt, rec["id"])
        except Exception as exc:  # noqa: BLE001 - CockpitError, HerdrError: their reason
            return _result(False, code="pane_refused", status_code=409, message=str(exc),
                           help=["Stop it in its own pane (Lampway > Agents)"])
        return _result(True, pane=rec["id"], keys=keys, cancelled=True)

    async def resume(self, socket, params: dict) -> dict:
        """The user's Resume of the tab's ended pane (spec B2, law 5): never automatic, never an agent's."""
        session_id = self._session_of(params)
        if origin_of(socket) != "user":
            return _result(False, code="agent_origin", status_code=403, message="Only your own click resumes your agent's pane.", help=[USER_ONLY])
        rec = self.pane_for(session_id)
        if rec is None:
            return _result(False, code="not_bound", status_code=409, help=[BIND_HELP], message="No agent pane is bound to this scene tab.")
        if rec.get("state") == "live":
            return _result(True, pane=rec["id"], running=True)
        payload = params.get("payload") if isinstance(params.get("payload"), dict) else params
        try:
            HN.require_enabled(self.state_dir)
            new = await asyncio.to_thread(self._cockpit().resume_bound, rec["id"], session_id, str(payload.get("name") or "") or None)
        except PermissionError as exc:                  # the harness's byoa route is off (spec B5)
            return _result(False, code="route_off", status_code=403, message=str(exc), help=["Switch the harness's route on in Privacy"])
        except Exception as exc:  # noqa: BLE001 - the BYOA switch off, herdr not running, no session id: the reason
            return _result(False, code="resume_refused", status_code=409, message=str(exc),
                           help=["Check the cockpit (Lampway > Agents): the herdr server must be running and your own agents switched on"])
        self.forget(session_id)                         # the next observe watches the new pane, from now on (no replay)
        return _result(True, pane=new["id"], harness=new.get("harness"), resumed=rec["id"])

    async def unbind(self, socket, params: dict) -> dict:
        """The user's Unbind of the tab's ended pane: the binding goes, the pane's record stays (law 5: nothing is closed)."""
        session_id = self._session_of(params)
        if origin_of(socket) != "user":
            return _result(False, code="agent_origin", status_code=403, message="Only your own click unbinds your agent's pane.", help=[USER_ONLY])
        done = []
        for rec in self.bound(session_id):
            if rec.get("state") != "live":
                await asyncio.to_thread(self._cockpit().unbind, rec["id"])
                done.append(rec["id"])
        if not done:
            return _result(False, code="nothing_to_unbind", status_code=409,
                           message="No ended agent pane is bound to this scene tab (a running one is unbound by switching the tab's agent).")
        self.forget(session_id)
        return _result(True, unbound=done)
