# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A pane's /new keeps old journals without replaying them into its new island."""
import asyncio
from types import SimpleNamespace

from lampway_server.agent.swarm_island import SwarmIsland
from lampway_server.agent.turns import AgentHub, Turn, TurnStream


class Socket:
    def __init__(self):
        self.frames = []

    async def notify(self, method, params):
        self.frames.append((method, params))


class Engine:
    def __init__(self):
        self.cid = "old-conversation"
        self.links = {}
        self.rebound = []

    def conversation_of(self, unit):
        return self.cid

    async def conversations(self, units):
        return {unit: self.cid for unit in units}

    def reattach(self, unit, socket):
        self.rebound.append((unit, socket))


def test_new_conversation_discovers_neither_old_normal_nor_card_journals_and_cannot_attach_them():
    async def exercise():
        hub = AgentHub(None)
        hub.engine = Engine()
        socket, restored = Socket(), Socket()
        hub.client_sockets["unit"] = socket
        normal = Turn("unit", "pane-old", "run-old")
        normal.conversation_id = "old-conversation"
        normal.detached = True
        normal.stream = TurnStream(socket, normal)
        normal.events = [{"type": "turn_end", "status": "completed"}]
        session = hub._session("unit")
        session.turns[normal.turn_id] = normal
        session.last_turn_id = normal.turn_id
        island = SwarmIsland(hub)
        swarm = SimpleNamespace(id="old", parent_session="unit", mode="runtime", owner="", harness_id=None, collected=False, retried=False)
        await island.report(swarm, [{"id": "worker", "status": "DONE"}], final=True)
        card = island.cards["old"].turn
        before = await hub._status(restored, {"session_ids": ["unit"]})
        assert before["turns"]["unit"]["turn_id"] == normal.turn_id
        assert before["swarm_cards"]["unit"][0]["turn_id"] == card.turn_id
        hub.engine.cid = "new-conversation"
        after = await hub._status(restored, {"session_ids": ["unit"]})
        assert after["turns"] == {} and after["swarm_cards"] == {}, "old journals must not resurrect after /new"
        assert after["conversations"] == {"unit": "new-conversation"}
        for turn in (normal, card):
            assert await hub._attach(restored, {"session_id": "unit", "turn_id": turn.turn_id}) == {"status": "unavailable"}
            assert turn.turn_id in session.turns, "the existing server journal is retained"
        assert restored.frames == [] and normal.stream.socket is socket and hub.engine.rebound == []
    asyncio.run(exercise())


def test_old_swarm_cannot_report_into_new_live_sink_even_if_it_never_needed_a_card():
    async def exercise():
        hub = AgentHub(None)
        hub.engine = Engine()
        old_socket, new_socket = Socket(), Socket()
        hub.client_sockets["unit"] = old_socket
        old_turn = Turn("unit", "pane-old", "old-run")
        hub.engine.links["unit"] = SimpleNamespace(sink=SimpleNamespace(
            pending=False, bubble_id="old-bubble", stream=TurnStream(old_socket, old_turn)))
        island = SwarmIsland(hub)
        swarm = SimpleNamespace(id="old", parent_session="unit", mode="runtime", owner="", harness_id=None, collected=False, retried=False)
        await island.report(swarm, [{"id": "worker", "status": "IN_PROGRESS"}])
        assert old_socket.frames and island.cards == {}
        hub.engine.cid = "new-conversation"
        new_turn = Turn("unit", "pane-new", "new-run")
        hub.engine.links["unit"].sink = SimpleNamespace(
            pending=False, bubble_id="new-bubble", stream=TurnStream(new_socket, new_turn))
        hub.client_sockets["unit"] = new_socket
        await island.report(swarm, [{"id": "worker", "status": "DONE"}], final=True)
        assert new_socket.frames == [] and new_turn.events == [], "old workers stay in herdr, never migrate into the new chat"
    asyncio.run(exercise())


def test_new_conversation_during_attach_never_rebinds_the_old_stream():
    async def exercise():
        hub = AgentHub(None)
        hub.engine = Engine()
        original = Socket()
        class MovingSocket(Socket):
            async def notify(self, method, params):
                await super().notify(method, params)
                hub.engine.cid = "new-conversation"
        restored = MovingSocket()
        turn = Turn("unit", "pane-old", "old-run")
        turn.conversation_id = "old-conversation"
        turn.detached = True
        turn.stream = TurnStream(original, turn)
        turn.events = [{"bubble_id": "old", "content": {"set": "Old response"}}]
        hub._session("unit").turns[turn.turn_id] = turn
        result = await hub._attach(restored, {"session_id": "unit", "turn_id": turn.turn_id})
        assert result == {"status": "unavailable"} and turn.stream.socket is original
        assert turn.detached and hub.engine.rebound == [], "/new during replay must not attach the old sink to the new unit"
    asyncio.run(exercise())


def test_old_card_keeps_journaling_without_delivery_and_new_cards_recover_normally():
    async def exercise():
        hub = AgentHub(None)
        hub.engine = Engine()
        socket = Socket()
        hub.client_sockets["unit"] = socket
        island = SwarmIsland(hub)
        old = SimpleNamespace(id="old", parent_session="unit", mode="runtime", owner="", harness_id=None,
                              collected=False, retried=False)
        await island.report(old, [{"id": "worker", "status": "IN_PROGRESS"}])
        old_card = island.cards[old.id].turn
        assert old_card.card_start["conversation_id"] == "old-conversation"
        socket.frames.clear()
        hub.engine.cid = "new-conversation"
        await island.report(old, [{"id": "worker", "status": "DONE"}], final=True)
        assert not socket.frames and old_card.status == "ended"
        assert old_card.events[-2]["todo"][0]["status"] == "DONE" and old_card.events[-1]["type"] == "turn_end"
        new = SimpleNamespace(id="new", parent_session="unit", mode="runtime", owner="", harness_id=None,
                              collected=False, retried=False)
        await island.report(new, [{"id": "worker", "status": "IN_PROGRESS"}])
        current = island.cards[new.id].turn
        assert current.card_start["conversation_id"] == "new-conversation"
        status = await hub._status(socket, {"session_ids": ["unit"]})
        assert [card["turn_id"] for card in status["swarm_cards"]["unit"]] == [current.turn_id]
        restored = Socket()
        assert (await hub._attach(restored, {"session_id": "unit", "turn_id": current.turn_id}))["status"] == "ok"
        assert restored.frames[0][1]["conversation_id"] == "new-conversation"
    asyncio.run(exercise())
