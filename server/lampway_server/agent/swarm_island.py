# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Parallel Agents cards of every swarm, whoever started it (docs/reports/agent-modes-spec.md S1, S3, A4; the captain,
2026-10-07: nothing is hidden from the user or the agent).

The client shows a swarm's workers as the cards its chat's ``todo`` slot feeds (``slot_processor._apply_todo_slot`` mirrors the rows
into the Parallel Agents panel) and offers "Retry failed tasks" as an ``actions`` chip on the same bubble. A swarm reports there in
those frames, to the island of its UNIT's scene tab (the swarm's parent session):

* a Mode 1 swarm (Lampway Agent's Hermes pane, over its engine endpoint, from a turn the island sent or one typed in the pane)
  while the front has a live island turn for the unit (its ``Sink``): on that turn's own bubble, read at each report, so the
  cards follow the swarm into the turn that collects it;
* started inside a turn that handed it the turn's stream (``SwarmContext.emit_todo``) on a server with no front: on that turn;
* otherwise (a Mode 2 swarm a bound pane started over MCP; a Mode 1 swarm between island turns): on a **card turn** of its own,
  opened on the scene tab's current Client socket (``AgentHub.socket_for``, else the socket the swarm's harness drives): an observed
  turn (``agent.turn.started`` with ``observed: true``, the ``swarm`` id and the parent ``pane``, no user text), its ``run_status``,
  the ``todo`` rows on one bubble, and at the end the Retry chip when a task failed, ``turn_end`` (no ``offset``: the pane's own
  transcript cursor is not touched) and ``agent.turn.ended``. A Your agent tab renders an observed turn's slots as Mode 1's; a
  Lampway Agent tab today takes only its own turns and their wakeups (for the client lane: accept a ``swarm`` card turn there too).

The turn is journalled in the hub's session like any other, so ``agent.attach`` replays it. Nothing here starts, stops or retries
anything: the swarm (``SwarmManager``) reports, and a Retry is the user's own click (``SwarmManager.retry``).
"""
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from . import questions as Q

log = logging.getLogger("lampway.swarm.island")

RETRY_ACTIONS = ({"label": Q.RETRY_LABEL, "value": Q.RETRY_ACTION, "style": "primary"},)


def retry_offered(swarm) -> bool:
    """The cards offer Retry once a swarm is collected with a failed or cancelled task that was not retried yet."""
    return bool(swarm.collected and not swarm.retried and any(w.status in ("failed", "cancelled") for w in swarm.workers))


@dataclass
class Card:
    turn: object
    socket: object
    bubble_id: str
    ended: bool = False


class SwarmIsland:
    def __init__(self, hub):
        self.hub = hub
        self.cards: dict = {}                  # swarm id -> its Card (the card turn), while the server runs

    # ------------------------------------------------------------------------------------------------- where the frames go
    def takes_over(self, swarm) -> bool:
        """A Mode 1 swarm on a server running Lampway Agent's front reports here even when a turn handed it its stream: the turn
        that started it may have ended, and the island turn running NOW (or a card turn) is where the user looks."""
        return getattr(swarm, "mode", "runtime") != "byoa" and getattr(self.hub, "engine", None) is not None

    def _sink(self, swarm):
        """Lampway Agent's live island turn for the swarm's unit (Mode 1 only), else None."""
        if getattr(swarm, "mode", "runtime") == "byoa":
            return None
        link = (getattr(getattr(self.hub, "engine", None), "links", None) or {}).get(swarm.parent_session)
        sink = getattr(link, "sink", None)
        if sink is None or getattr(sink, "pending", False) or getattr(sink, "stream", None) is None or not getattr(sink, "bubble_id", ""):
            return None
        return sink

    def _socket(self, swarm):
        socket_for = getattr(self.hub, "socket_for", None)
        socket = socket_for(swarm.parent_session) if socket_for is not None else None
        return socket or getattr(getattr(swarm, "harness", None), "socket", None)

    # ------------------------------------------------------------------------------------------------- the frames
    async def report(self, swarm, rows: list, *, final: bool = False) -> None:
        """The swarm's rows (the whole list each time: the slot replaces it); ``final`` once it is collected: the Retry chip when a
        task failed, and the card turn's end."""
        frame = {"todo": rows}
        if final and retry_offered(swarm):
            frame["actions"] = [dict(a) for a in RETRY_ACTIONS]
        sink = self._sink(swarm)
        if sink is not None:
            await sink.stream.emit_quietly({"bubble_id": sink.bubble_id, **frame})
        else:
            card = await self._card(swarm)
            if card is not None:
                await self._emit(card, {"bubble_id": card.bubble_id, **frame})
        if final:
            await self.finish(swarm)

    async def finish(self, swarm) -> None:
        """End the swarm's card turn, if it has one still open."""
        card = self.cards.get(swarm.id)
        if card is None or card.ended:
            return
        card.ended = True
        await self._emit(card, {"type": "turn_end", "status": "completed", "run_id": card.turn.run_id})
        card.turn.status = "ended"
        await self._notify(card.socket, "agent.turn.ended", {"session_id": card.turn.session_id, "turn_id": card.turn.turn_id,
                                                             "last_seq": card.turn.last_seq})

    async def _card(self, swarm) -> Optional[Card]:
        socket = self._socket(swarm)
        card = self.cards.get(swarm.id)
        if card is not None and not card.ended:
            if socket is not None:
                card.socket = socket                   # the tab's current socket: a reconnected island goes on getting the cards
            return card
        if socket is None:
            return None                                # no Lampway window speaks for the tab: nothing to show it on
        from .turns import Turn
        unit = swarm.parent_session
        tid = f"swarm_{swarm.id}_{uuid.uuid4().hex[:8]}"
        turn = Turn(unit, tid, tid)
        turn.observed = True                           # type: ignore[attr-defined]
        turn.socket = socket                           # type: ignore[attr-defined]
        self.hub._session(unit).turns[tid] = turn
        card = self.cards[swarm.id] = Card(turn, socket, f"swarm-{swarm.id}-{uuid.uuid4().hex[:8]}")
        owner = str(getattr(swarm, "owner", "") or "")
        await self._notify(socket, "agent.turn.started", {
            "session_id": unit, "turn_id": tid, "run_id": tid, "observed": True, "swarm": swarm.id,
            "pane": owner[len("pane:"):] if owner.startswith("pane:") else None, "harness": getattr(swarm, "harness_id", None),
            "user_text": ""})
        await self._emit(card, {"type": "run_status", "run_id": tid, "status": "in_progress"})
        return card

    @staticmethod
    async def _emit(card: Card, payload: dict) -> None:
        from .turns import TurnStream
        await TurnStream(card.socket, card.turn).emit_quietly(payload)

    @staticmethod
    async def _notify(socket, method: str, params: dict) -> None:
        try:
            await socket.notify(method, params)
        except Exception:  # noqa: BLE001 - the socket is gone; the journal keeps the turn for agent.attach
            log.debug("the swarm's cards could not deliver %s", method, exc_info=True)
