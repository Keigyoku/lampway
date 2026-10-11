# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The client's agent archive, served from Hermes's own sessions (docs/reports/agent-modes-spec.md R2, R1, A2).

The client keeps a local archive of each scene tab's conversation (``common/agent_history``): it polls ``agent.history_sync``
(version 1) with the scene session ids it knows and its acknowledgements, writes each packet's records to disk and acknowledges
them after fsync. Lampway builds no conversation store of its own (captain, R1/R2): Mode 1's conversation is Hermes's, in
``state.db`` under the unit's home, and the records come from the unit's ``hermes serve`` (``session.list``,
``session.history``; ``front.HermesFront.history_sync``). This module is the pure half, standard library only (the client's own
test loads it by path and feeds its packets to the client's store):

* a unit's archive (the client's ``session_id`` is the unit, the scene tab's session id) holds one **epoch** per Hermes session
  and rewrite: ``epoch(stored_id, gen)``, 32 hex, as the client requires;
* each message of the session's history (user, assistant, tool rows, in order) is one record ``{version: 1, run_id: <stored id>,
  task_id: "main", kind: "message", payload: {id, role, text, ...}}`` at ``seq`` = its 1-based position, ``event_id`` the sha256
  of its canonical JSON (the client's ``store.canonical``);
* **delivery state, not a store:** ``Ledger`` keeps, per Hermes session, the acknowledged prefix's length and digest in the unit's
  home (``archive.json``, 0600). A history that no longer starts with that prefix (an undo, a rewind) gets a new ``gen``, so the
  whole surviving history is delivered again under a new epoch (the client records the epoch change as a gap, never a conflict).

``agent_history_v2`` (images fetched over HTTP) is not served: no record carries an image, and the handshake advertises only v1.
"""

import hashlib
import json
import os
from pathlib import Path

VERSION = 1
OWNER_ID = "lampway-local"        # one local account: stable, so the client's archive never sees its owner change
LIMIT = 200                       # records per session per poll
TEXT_CLIP = 65_536                # characters of one message kept in its record
LEDGER_FILE = "archive.json"
LIST_EVERY_S = 30.0               # how often a unit's session list is asked again
TASK_ID = "main"


def canonical(value) -> bytes:
    """The client's canonical JSON (``agent_history/core/store.py`` ``canonical``): the bytes an ``event_id`` hashes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def epoch(stored_id: str, gen: int) -> str:
    return hashlib.md5(f"{stored_id}:{int(gen)}".encode("utf-8")).hexdigest()


def _text(message: dict) -> str:
    text = message.get("text")
    if text is None:
        text = message.get("content")
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, default=str) if text is not None else ""
    return text[:TEXT_CLIP]


def records(stored_id: str, messages: list) -> list:
    """One record per history message, in order (``session.history`` rows: role, text, row_id, timestamp; a tool row has its
    name and context instead of a row id)."""
    out = []
    for i, m in enumerate(messages or [], 1):
        if not isinstance(m, dict):
            continue
        payload = {"id": f"{stored_id}-{m.get('row_id') if m.get('row_id') is not None else 'p' + str(i)}"[:128],
                   "role": str(m.get("role") or ""), "text": _text(m), "session": stored_id}
        if isinstance(m.get("timestamp"), (int, float)):
            payload["timestamp"] = m["timestamp"]
        if m.get("role") == "tool":
            payload["tool"] = str(m.get("name") or "")[:200]
            if m.get("context"):
                payload["context"] = str(m["context"])[:500]
        out.append({"version": VERSION, "run_id": str(stored_id)[:256], "task_id": TASK_ID, "kind": "message", "payload": payload})
    return out


def event_id(record: dict) -> str:
    return hashlib.sha256(canonical(record)).hexdigest()


def prefix_digest(event_ids) -> str:
    h = hashlib.sha256()
    for e in event_ids:
        h.update(e.encode("ascii"))
    return h.hexdigest()


class Ledger:
    """One unit's delivery state: per Hermes session, ``{gen, acked, digest}``. 0600 in the unit's home (or memory only)."""

    def __init__(self, home=None):
        self.path = Path(home) / LEDGER_FILE if home else None
        self.sessions: dict = {}
        if self.path is not None:
            try:
                self.sessions = dict(json.loads(self.path.read_text(encoding="utf-8")).get("sessions") or {})
            except (OSError, ValueError, AttributeError):
                self.sessions = {}

    def save(self) -> None:
        if self.path is None:
            return
        tmp = self.path.with_name(f".{LEDGER_FILE}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"sessions": self.sessions}, sort_keys=True))
        os.replace(tmp, self.path)

    def state(self, stored_id: str) -> dict:
        return self.sessions.setdefault(stored_id, {"gen": 0, "acked": 0, "digest": prefix_digest([])})

    def settle(self, stored_id: str, ids: list) -> dict:
        """The session's state against its current history (``ids``: its records' event ids): a history that no longer starts
        with the acknowledged prefix is a rewrite, delivered again from the start under the next gen."""
        st = self.state(stored_id)
        if st["acked"] > len(ids) or prefix_digest(ids[:st["acked"]]) != st["digest"]:
            st.update(gen=int(st["gen"]) + 1, acked=0, digest=prefix_digest([]))
        return st

    def acknowledge(self, stored_id: str, gen: int, seq: int, ids: list) -> bool:
        """The client wrote records up to ``seq`` of (``stored_id``, ``gen``), whose delivered ids were ``ids``."""
        st = self.state(stored_id)
        if int(st["gen"]) != int(gen) or not (0 < seq <= len(ids)) or seq <= st["acked"]:
            return False
        st.update(acked=seq, digest=prefix_digest(ids[:seq]))
        return True


def packet(unit: str, stored_id: str, st: dict, recs: list, limit: int = LIMIT) -> tuple:
    """(the packet for the client, the event ids of every record up to its last) for what follows the acknowledged prefix; the
    packet is None when nothing is new."""
    ids = [event_id(r) for r in recs]
    start = int(st["acked"])
    chunk = recs[start:start + limit]
    if not chunk:
        return None, ids
    rows = [{"seq": start + i + 1, "event_id": ids[start + i], "record": r} for i, r in enumerate(chunk)]
    return {"session_id": unit, "epoch": epoch(stored_id, st["gen"]), "status": "available", "records": rows}, ids


class Feed:
    """``agent.history_sync`` for the hub (``AgentHub._history_sync``): the server half, through the units' serves (``front``, a
    ``HermesFront``). Per poll and requested unit with a live pane: first a previous Hermes session of the unit (``session.list``)
    that still has records the client never acknowledged (the pane's ``/new`` while Lampway was away), read by resuming it and
    closing it again; else the session the pane shows (``session.history`` on the live session). One packet per unit per poll."""

    def __init__(self, front):
        self.front = front
        self.ledgers: dict = {}               # unit -> Ledger
        self.delivered: dict = {}             # epoch -> (unit, stored id, gen, event ids up to the last record sent)
        self.cache: dict = {}                 # unit -> ((live id, last seq), messages): the pane's history, until its next event
        self.done: dict = {}                  # (unit, stored id) -> message count already delivered whole (a previous session)
        self.dirty: set = set()               # units whose ledger changed (an acknowledgement, a rewrite's new gen)
        self.listed: dict = {}                # unit -> (live id, when, session.list rows)

    def forget(self, unit: str) -> None:
        """The unit's history changed without an event (an undo): read it again at the next poll."""
        self.cache.pop(unit, None)

    def _ledger(self, unit: str, home) -> Ledger:
        led = self.ledgers.get(unit)
        if led is None:
            led = self.ledgers[unit] = Ledger(home)
        return led

    async def sync(self, params: dict) -> dict:
        import asyncio
        import logging
        log = logging.getLogger("lampway.engine.history")
        for ack in params.get("acknowledgements") or []:
            if not isinstance(ack, dict):
                continue
            known = self.delivered.get(str(ack.get("epoch") or ""))
            seq = ack.get("seq")
            if known is None or known[0] != ack.get("session_id") or not isinstance(seq, int) or isinstance(seq, bool):
                continue                                   # delivered before a restart: it is sent again, and the client replays it
            unit, stored, gen, ids = known
            if self.ledgers.get(unit) is not None and self.ledgers[unit].acknowledge(stored, gen, seq, ids):
                self.dirty.add(unit)
        out = []
        for unit in [s for s in (params.get("session_ids") or [])[:32] if isinstance(s, str) and s]:
            try:
                pk = await self._packet(unit)
            except Exception:  # noqa: BLE001 - one unit's serve not answering never fails the poll
                log.debug("the archive could not read the pane of %s", unit, exc_info=True)
                continue
            if pk is not None:
                out.append(pk)
        dirty, self.dirty = self.dirty, set()
        for unit in dirty:
            try:
                await asyncio.to_thread(self.ledgers[unit].save)
            except OSError:
                log.warning("the archive's delivery state for %s could not be saved", unit)
        return {"version": VERSION, "owner_id": OWNER_ID, "sessions": out}

    async def _packet(self, unit: str):
        link = await self.front.archive_link(unit)
        if link is None or link.info is None:
            return None
        led = self._ledger(unit, getattr(link.info, "home", None))
        current = str(link.info.stored_id or "")
        rows = await self._listing(unit, link)
        for row in sorted((r for r in rows if r.get("id") and r.get("id") != current), key=lambda r: float(r.get("started_at") or 0)):
            stored, count = str(row["id"]), int(row.get("message_count") or 0)
            if self.done.get((unit, stored)) == count or count <= int(led.state(stored)["acked"]):
                continue
            msgs = await self._read_previous(link, stored)
            pk = self._make(unit, stored, led, msgs)
            if pk is not None:
                return pk
            self.done[(unit, stored)] = count
        key = (link.live_id, link.last_seq)
        cached = self.cache.get(unit)
        if cached is not None and cached[0] == key:
            msgs = cached[1]
        else:
            msgs = (await link.client.call("session.history", {"session_id": link.live_id})).get("messages") or []
            self.cache[unit] = (key, msgs)
        return self._make(unit, current, led, msgs)

    async def _listing(self, unit: str, link) -> list:
        """The unit's Hermes sessions (``session.list``), asked again at most every ``LIST_EVERY_S`` (the client polls every 2 s)
        or when the pane moved to another session."""
        import time
        now = time.monotonic()
        held = self.listed.get(unit)
        if held is not None and held[0] == link.live_id and now - held[1] < LIST_EVERY_S:
            return held[2]
        rows = (await link.client.call("session.list", {"limit": 50})).get("sessions") or []
        self.listed[unit] = (link.live_id, now, rows)
        return rows

    @staticmethod
    async def _read_previous(link, stored: str) -> list:
        """A previous session of the unit, read from Hermes: resumed (state.db keeps it), its history, closed again."""
        res = await link.client.call("session.resume", {"session_id": stored})
        sid = str(res.get("session_id") or "")
        try:
            return (await link.client.call("session.history", {"session_id": sid})).get("messages") or []
        finally:
            if sid and sid != link.live_id:
                await link.client.call("session.close", {"session_id": sid})

    def _make(self, unit: str, stored: str, led: Ledger, msgs: list):
        recs = records(stored, msgs)
        gen = int(led.state(stored)["gen"])
        st = led.settle(stored, [event_id(r) for r in recs])
        if int(st["gen"]) != gen:
            self.dirty.add(unit)
        pk, ids = packet(unit, stored, st, recs)
        if pk is not None:
            self.delivered[pk["epoch"]] = (unit, stored, int(st["gen"]), ids[:pk["records"][-1]["seq"]])
        return pk


__all__ = ["Feed", "LIMIT", "Ledger", "OWNER_ID", "VERSION", "canonical", "epoch", "event_id", "packet", "records"]
