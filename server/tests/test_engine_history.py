# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The client's agent archive is served from Hermes's own sessions (docs/reports/agent-modes-spec.md R2): ``agent.history_sync``
(version 1) answers from the unit's ``hermes serve`` (``session.list``, ``session.history``), against the scripted serve
(``serve_support.FakeServe``) and the real server on a real port, with the client's own frames. Lampway keeps no conversation:
only which prefix the client acknowledged (``engine/history.py``). The handshake advertises only what is served."""

import asyncio
import hashlib
import json
import re

import pytest
import websockets

from .serve_support import chat, run, stack  # noqa: F401  (stack: the fixture)

pytestmark = pytest.mark.timeout(120)


def canonical(value) -> bytes:
    """The client's canonical JSON (src/scripts/mixar/modules/common/agent_history/core/store.py)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


async def sync(island, session_ids, acks=()):
    rid = await island.send("agent.history_sync", {"acknowledgements": list(acks), "session_ids": list(session_ids)})
    reply = await island.reply(rid)
    assert "result" in reply, reply
    return reply["result"]


def ack_of(packet):
    return {"session_id": packet["session_id"], "epoch": packet["epoch"], "seq": packet["records"][-1]["seq"]}


def check_packet(p):
    """What the client's store requires of a packet (store.write_batch): a 32-hex epoch, version-1 records with string run and
    task ids, each event_id the sha256 of the record's canonical bytes."""
    assert re.fullmatch(r"[a-f0-9]{32}", p["epoch"]) and p["status"] == "available"
    for row in p["records"]:
        r = row["record"]
        assert r["version"] == 1 and isinstance(r["run_id"], str) and isinstance(r["task_id"], str) and r["kind"] == "message"
        assert row["event_id"] == hashlib.sha256(canonical(r)).hexdigest()


def test_history_sync_serves_the_units_hermes_session_and_only_what_was_not_acknowledged(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Hi there.")])
        cid, _ = await chat(island, "Hello", "scene-1")
        await island.ended(cid)
        first = await sync(island, ["scene-1", "a-tab-with-no-pane"])
        again = await sync(island, ["scene-1"], [ack_of(first["sessions"][0])])
        serve.scripts.append([("say", "A chair.")])
        cid2, _ = await chat(island, "Make a chair", "scene-1")
        await island.ended(cid2)
        later = await sync(island, ["scene-1"])
        return first, again, later, [m for m, _ in serve.calls]

    first, again, later, methods = run(stack, scenario)
    assert first["version"] == 1 and first["owner_id"] == "lampway-local"
    assert [p["session_id"] for p in first["sessions"]] == ["scene-1"], "a tab with no pane has nothing to archive"
    p = first["sessions"][0]
    check_packet(p)
    assert [(r["seq"], r["record"]["payload"]["role"], r["record"]["payload"]["text"]) for r in p["records"]] == \
        [(1, "user", "Hello"), (2, "assistant", "Hi there.")]
    assert again["sessions"] == [], "the acknowledged prefix is not sent again"
    q = later["sessions"][0]
    check_packet(q)
    assert q["epoch"] == p["epoch"] and [(r["seq"], r["record"]["payload"]["text"]) for r in q["records"]] == \
        [(3, "Make a chair"), (4, "A chair.")]
    assert "session.history" in methods and "session.list" in methods


def test_a_rewritten_history_is_delivered_again_under_a_new_epoch(stack):
    """An undo or a rewind drops turns from Hermes's session: the acknowledged prefix no longer matches, so the surviving history
    goes again under a new epoch (the client records an epoch change, never a replay conflict)."""
    async def scenario(serve, units, island, front):
        for text, reply in (("one", "1."), ("two", "2.")):
            serve.scripts.append([("say", reply)])
            cid, _ = await chat(island, text, "scene-1")
            await island.ended(cid)
        first = await sync(island, ["scene-1"])
        await sync(island, ["scene-1"], [ack_of(first["sessions"][0])])
        del serve.only().history[-2:]                                   # Hermes's undo dropped the last turn
        serve.scripts.append([("say", "3.")])
        cid, _ = await chat(island, "three", "scene-1")
        await island.ended(cid)
        return first, await sync(island, ["scene-1"])

    first, after = run(stack, scenario)
    old, new = first["sessions"][0], after["sessions"][0]
    check_packet(new)
    assert new["epoch"] != old["epoch"]
    assert [(r["seq"], r["record"]["payload"]["text"]) for r in new["records"]] == [(1, "one"), (2, "1."), (3, "three"), (4, "3.")]


def test_after_the_panes_new_the_old_conversation_is_finished_then_the_new_one_goes(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Old reply.")])
        cid, _ = await chat(island, "Old words", "scene-1")
        await island.ended(cid)
        old = serve.only()
        await serve.pane_prompt(old, "typed after the island looked", [("say", "Old tail.")])
        await island.wait(lambda f: f.get("method") == "agent.turn.ended" and f["params"]["turn_id"].startswith("pane_"))
        new = await serve.pane_new(old)
        await island.wait(lambda f: f.get("method") == "agent.pane.new_conversation")
        serve.scripts.append([("say", "New reply.")])
        cid2, _ = await chat(island, "New words", "scene-1")
        await island.ended(cid2)
        a = await sync(island, ["scene-1"])
        b = await sync(island, ["scene-1"], [ack_of(a["sessions"][0])])
        c = await sync(island, ["scene-1"], [ack_of(b["sessions"][0])])
        return a, b, c, old, new

    a, b, c, old, new = run(stack, scenario)
    pa, pb = a["sessions"][0], b["sessions"][0]
    assert [r["record"]["run_id"] for r in pa["records"]] == [old.stored_id] * 4, "the old conversation first, whole"
    assert [r["record"]["payload"]["text"] for r in pa["records"]][-1] == "Old tail."
    assert [r["record"]["run_id"] for r in pb["records"]] == [new.stored_id] * 2 and pb["epoch"] != pa["epoch"]
    assert c["sessions"] == []
    assert old.closed, "the old session read for the archive was closed again"


def test_the_handshake_advertises_only_the_archive_it_serves(stack):
    async def handshake(stack, engine):
        from .fake_client import FakeMixarClient
        import httpx
        with httpx.Client(base_url=stack.base) as http:
            fake = FakeMixarClient(http, password=stack.settings.user_password)
            fake.login()
        hub = stack.app.state.agent
        saved, hub.engine = hub.engine, engine
        try:
            url = stack.base.replace("http://", "ws://") + f"/api/agent/ws/{fake.instance_id}"
            async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {fake.access_token}"}) as ws:
                await ws.send(json.dumps(fake.handshake_frame()))
                return json.loads(await asyncio.wait_for(ws.recv(), 10))["result"]["server_capabilities"]
        finally:
            hub.engine = saved

    with_engine = asyncio.run(handshake(stack, object()))
    without = asyncio.run(handshake(stack, None))
    assert with_engine == ["agent_history_v1"], "v1 is served from Hermes's sessions; v2's image route does not exist"
    assert without == [], "no engine: no conversation to serve, so nothing is advertised"
