"""Questions and checkpoints as the client sends them (docs: "Questions and planning", "Go back with checkpoints"), in Mode 1 on
Hermes (docs/reports/agent-modes-spec.md A2, A5).

Questions: the pane's Hermes asks with ``clarify`` (the island's question card, ``test_engine_front.py``); the client answers with
``agent.input`` {action, text, answers, interrupt_id} (composer_send.py / turn_transport.start_input_stream), and a click on a choice
card sends the option's value as ``action`` with empty text (chat_special_ops' generic dispatch).

Checkpoints: ``agent.checkpoint.mark {session_id, request_id}`` and ``agent.checkpoint.rewind {session_id, request_id}``
(checkpoint_backend.py:55-85, turn_checkpoints.py). The snapshot before turn N is bound to that turn's command id; a jump marks the
tip, then rewinds to the record the scene landed on. Mode 1's conversation is Hermes's: a rewind drops the undone turns from it with
serve's ``session.undo`` (one user turn per call, durable in ``state.db``, measured), down to the user-turn count the bookmark
recorded. Hermes cannot bring undone turns back, so a rewind forward is refused saying so, as is one into a conversation the pane
left (``/new``). With no engine a mark bookmarks nothing and a rewind is refused.
"""

import uuid

import pytest

from .serve_support import chat, final_text, run, stack  # noqa: F401  (stack: the fixture)

pytestmark = pytest.mark.timeout(120)


def _reply(ws, request_id):
    for _ in range(50):
        frame = ws.receive_json()
        if frame.get("id") == request_id:
            return frame["result"]
    raise AssertionError(f"no reply to {request_id}")


def test_a_choice_click_from_the_client_answers_the_panes_question_with_the_clicked_value(stack):
    """The real client's click on a choice card sends agent.input {action: <the option's value>, text: ''}, not text."""
    async def scenario(serve, units, island, front):
        serve.scripts.append([("clarify", "Round or square?", ["Round", "Square"]), ("say", "Square it is.")])
        session_id = str(uuid.uuid4())
        cid, _ = await chat(island, "make a table", session_id)
        await island.ended(cid)
        click, _ = await island.command("agent.input", {"session_id": session_id, "action": "Square", "text": ""})
        await island.ended(click)
        return serve.only().answers, island.events(click)

    answers, events = run(stack, scenario)
    assert answers == [("clarify", {"answer": "Square"})]
    assert final_text(events) == "Square it is."


def test_with_no_engine_a_mark_bookmarks_nothing_and_a_rewind_is_refused_saying_why(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        marked = _reply(ws, fake.request(ws, "agent.checkpoint.mark",
                                         {"command_id": "c1", "payload": {"session_id": "s4", "request_id": "r1"}}))
        rewound = _reply(ws, fake.request(ws, "agent.checkpoint.rewind",
                                          {"command_id": "c2", "payload": {"session_id": "s4", "request_id": "r1"}}))
    assert marked == {"ok": True, "has_conversation": False}
    assert rewound["ok"] is False and rewound["code"] == "rewind_unavailable", rewound
    assert "Lampway Agent" in rewound["message"]


async def _rpc(island, method, payload):
    _, rid = await island.command(method, payload)
    return (await island.reply(rid))["result"]


async def _turn(serve, island, text, reply, sid="scene-1"):
    serve.scripts.append([("say", reply)])
    cid, _ = await chat(island, text, sid)
    await island.ended(cid)
    return cid


def _users(history):
    return [m["text"] for m in history if m["role"] == "user"]


def test_a_rewind_drops_the_undone_turns_from_hermess_conversation(stack):
    """The scene went back to before turn two: Hermes's session keeps turn one only (two serve undos), the next chat continues
    from there, and the tip's bookmark (marked before the jump) cannot bring the undone turns back."""
    async def scenario(serve, units, island, front):
        await _turn(serve, island, "one", "1.")
        two = await _turn(serve, island, "two", "2.")
        await _turn(serve, island, "three", "3.")
        tip = await _rpc(island, "agent.checkpoint.mark", {"session_id": "scene-1", "request_id": "tip-1"})
        back = await _rpc(island, "agent.checkpoint.rewind", {"session_id": "scene-1", "request_id": two})
        after = list(serve.only().history)
        await _turn(serve, island, "four", "4.")
        forward = await _rpc(island, "agent.checkpoint.rewind", {"session_id": "scene-1", "request_id": "tip-1"})
        unknown = await _rpc(island, "agent.checkpoint.rewind", {"session_id": "scene-1", "request_id": "never-marked"})
        return tip, back, after, list(serve.only().history), forward, unknown, [m for m, _ in serve.calls]

    tip, back, after, final, forward, unknown, methods = run(stack, scenario)
    assert tip == {"ok": True, "has_conversation": True}
    assert back["ok"] is True and back["has_conversation"] is True and back["removed_turns"] == 2, back
    assert _users(after) == ["one"] and methods.count("session.undo") == 2
    assert _users(final) == ["one", "four"], "the next chat goes on from the restored point"
    assert forward["ok"] is False and forward["code"] == "rewind_forward" and "cannot bring" in forward["message"], forward
    assert unknown["ok"] is False and unknown["code"] == "rewind_unknown", unknown


def test_a_bookmark_whose_turn_was_undone_is_refused_even_when_as_many_turns_followed(stack):
    """The tip after two turns, back to before the second, one new turn: Hermes again holds two user turns, but not the tip's, so
    going to the tip is a rewind forward (refused), not a no-op that would claim the agent remembers the restored turn."""
    async def scenario(serve, units, island, front):
        await _turn(serve, island, "one", "1.")
        two = await _turn(serve, island, "two", "2.")
        await _rpc(island, "agent.checkpoint.mark", {"session_id": "scene-1", "request_id": "tip-2"})
        await _rpc(island, "agent.checkpoint.rewind", {"session_id": "scene-1", "request_id": two})
        await _turn(serve, island, "two again, differently", "2b.")
        reply = await _rpc(island, "agent.checkpoint.rewind", {"session_id": "scene-1", "request_id": "tip-2"})
        return reply, list(serve.only().history)

    reply, history = run(stack, scenario)
    assert reply["ok"] is False and reply["code"] == "rewind_forward", reply
    assert _users(history) == ["one", "two again, differently"], "nothing undone"


def test_a_rewind_into_a_conversation_the_pane_left_is_refused_and_nothing_is_undone(stack):
    async def scenario(serve, units, island, front):
        first = await _turn(serve, island, "one", "1.")
        await _turn(serve, island, "two", "2.")
        new = await serve.pane_new(serve.only())
        await island.wait(lambda f: f.get("method") == "agent.pane.new_conversation")
        await _turn(serve, island, "fresh", "F.")
        reply = await _rpc(island, "agent.checkpoint.rewind", {"session_id": "scene-1", "request_id": first})
        return reply, new.history, [m for m, _ in serve.calls]

    reply, history, methods = run(stack, scenario)
    assert reply["ok"] is False and reply["code"] == "rewind_other_conversation", reply
    assert "session.undo" not in methods and _users(history) == ["fresh"]


def test_a_rewind_while_the_agent_works_is_refused_and_undoes_nothing(stack):
    import asyncio
    async def scenario(serve, units, island, front):
        first = await _turn(serve, island, "one", "1.")
        gate = asyncio.Event()
        serve.scripts.append([("say", "working"), ("gate", gate), ("say", "done")])
        cid, _ = await chat(island, "long one", "scene-1")
        await island.wait(lambda f: f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == cid
                          and "append" in (f["params"]["event"].get("ephemeral") or {}))
        reply = await _rpc(island, "agent.checkpoint.rewind", {"session_id": "scene-1", "request_id": first})
        gate.set()
        await island.ended(cid)
        return reply, [m for m, _ in serve.calls]

    reply, methods = run(stack, scenario)
    assert reply["ok"] is False and reply["code"] == "rewind_busy" and "session.undo" not in methods


def test_a_mark_on_an_unknown_session_has_no_conversation(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        reply = _reply(ws, fake.request(ws, "agent.checkpoint.mark",
                                        {"command_id": "c9", "payload": {"session_id": "never", "request_id": "r"}}))
    assert reply == {"ok": True, "has_conversation": False}
