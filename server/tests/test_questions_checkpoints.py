"""Questions and checkpoints as the client sends them (docs: "Questions and planning", "Go back with checkpoints"), in Mode 1 on
Hermes (docs/reports/agent-modes-spec.md A2, A5).

Questions: the pane's Hermes asks with ``clarify`` (the island's question card, ``test_engine_front.py``); the client answers with
``agent.input`` {action, text, answers, interrupt_id} (composer_send.py / turn_transport.start_input_stream), and a click on a choice
card sends the option's value as ``action`` with empty text (chat_special_ops' generic dispatch).

Checkpoints: ``agent.checkpoint.mark {session_id, request_id}`` and ``agent.checkpoint.rewind {session_id, request_id}``
(checkpoint_backend.py:55-85, turn_checkpoints.py). Mode 1's conversation is Hermes's, in its pane: a mark bookmarks nothing here
(``has_conversation: false``), and a rewind is refused saying so, so the client tells the user the agent still remembers the undone
turns instead of claiming they were forgotten.
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


def test_a_mark_bookmarks_nothing_and_a_rewind_says_hermes_keeps_the_conversation(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        marked = _reply(ws, fake.request(ws, "agent.checkpoint.mark",
                                         {"command_id": "c1", "payload": {"session_id": "s4", "request_id": "r1"}}))
        rewound = _reply(ws, fake.request(ws, "agent.checkpoint.rewind",
                                          {"command_id": "c2", "payload": {"session_id": "s4", "request_id": "r1"}}))
    assert marked == {"ok": True, "has_conversation": False}
    assert rewound["ok"] is False and rewound["code"] == "rewind_unsupported", rewound
    assert "Hermes" in rewound["message"] and "does not rewind" in rewound["message"]


def test_a_mark_on_an_unknown_session_has_no_conversation(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        reply = _reply(ws, fake.request(ws, "agent.checkpoint.mark",
                                        {"command_id": "c9", "payload": {"session_id": "never", "request_id": "r"}}))
    assert reply == {"ok": True, "has_conversation": False}
