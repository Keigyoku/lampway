# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BYOA B4 (docs/reports/agent-modes-spec.md): a harness's own session file, record by record, becomes the turn stream the
island already renders for Mode 1 (``run_status``, ``content.set``, ``steps``, then the turn's end), read-only.

The converter is pure: it is fed records and returns operations; the hub (agent/byoa.py) numbers and sends them. Fixtures are
the session files in tests/byoa_fixtures.py; no harness binary and no real file is involved."""
import pytest
from lampway_server.herdr.observers import mirror as M

from .byoa_fixtures import CLAUDE_TURNS, CODEX_TURNS


def run(m, records):
    ops = []
    for at, rec in enumerate(records):
        ops += m.feed(rec, at)
    return ops


def kinds(ops):
    return [op[0] for op in ops]


def turns(ops):
    """[(user_text, final text, [(label, status)...], end status or None)] per turn, as the island ends up showing it."""
    out, cur = [], None
    for kind, tid, data in ops:
        if kind == "start":
            cur = {"tid": tid, "user": data["user_text"], "text": "", "steps": [], "end": None}
            out.append(cur)
            continue
        assert cur is not None and tid == cur["tid"], (kind, tid)
        if kind == "end":
            cur["end"] = data["status"]
        elif "content" in data:
            cur["text"] = data["content"]["set"]
        elif "steps" in data:
            cur["steps"] = [(s["label"], s["status"]) for s in data["steps"]["items"]]
    return [(t["user"], t["text"], t["steps"], t["end"]) for t in out]


def test_a_claude_code_session_file_renders_as_turns_bubbles_and_steps():
    ops = run(M.ClaudeMirror("pane1"), CLAUDE_TURNS)
    assert turns(ops) == [
        ("Add a cube and tell me its name", "I'll add the cube.\n\nThe cube is called Cube.",
         [("lampway_scene", "done"), ("Bash", "failed")], "completed"),
        ("Now bevel it", "", [("lampway_scene", "failed")], "cancelled"),
        ("Try again", "The agent reported an API error.", [], None),
    ]


def test_every_turn_opens_with_run_status_and_its_ids_are_stable_and_never_another_pane():
    ops = run(M.ClaudeMirror("pane1"), CLAUDE_TURNS)
    starts = [(i, op) for i, op in enumerate(ops) if op[0] == "start"]
    for i, (_, tid, _) in starts:
        assert ops[i + 1] == ("event", tid, {"type": "run_status", "run_id": tid, "status": "in_progress"})
        assert tid.startswith("byoa-pane1-")
    again = run(M.ClaudeMirror("pane1"), CLAUDE_TURNS)
    assert [op[1] for op in again if op[0] == "start"] == [op[1] for _, op in starts]                # the same file gives the same turn ids
    assert {op[1] for op in run(M.ClaudeMirror("pane2"), CLAUDE_TURNS)}.isdisjoint({op[1] for op in ops})
    for kind, tid, data in ops:
        if kind == "event" and "bubble_id" in data:
            assert data["bubble_id"] == f"{tid}:agent"


def test_sidechains_metadata_thinking_and_command_echoes_never_reach_the_island():
    ops = run(M.ClaudeMirror("p"), CLAUDE_TURNS)
    text = repr(ops)
    for hidden in ("subagent chatter", "Caveat", "/clear", "The scene tool can add it"):
        assert hidden not in text, hidden


def test_a_step_names_its_tool_without_the_lampway_prefix_and_carries_a_one_line_detail():
    ops = run(M.ClaudeMirror("p"), CLAUDE_TURNS[:10])
    steps = [d["steps"]["items"] for k, _, d in ops if k == "event" and "steps" in d][-1]
    assert steps[0]["label"] == "lampway_scene" and steps[0]["kind"] == "tool" and steps[0]["id"] == "toolu_01"
    assert steps[1]["label"] == "Bash" and steps[1]["detail"] == "ls renders"


def test_records_after_the_observation_started_mid_turn_open_a_turn_with_no_prompt():
    ops = run(M.ClaudeMirror("p"), CLAUDE_TURNS[5:12])                                            # starts at the assistant's text
    assert turns(ops)[0][0] == "" and turns(ops)[0][3] == "completed"


def test_a_codex_rollout_renders_as_turns_bubbles_and_steps():
    ops = run(M.CodexMirror("pane9"), CODEX_TURNS)
    assert turns(ops) == [
        ("Add a sphere", "Adding a sphere.\n\nThe sphere is in.", [("lampway_scene", "done"), ("shell", "failed")], "completed"),
        ("Make it red", "", [], "cancelled"),
    ]
    assert "environment_context" not in repr(ops) and "thinking" not in repr(ops)


def test_codex_0159_response_messages_render_the_recorded_commentary_and_final_once():
    # Shape from the supplied sanitized Codex 0.159 audit rollout; text/ids are synthetic.
    records = [
        {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-current"}},
        {"type": "response_item", "payload": {"type": "message", "id": "msg-comment", "role": "assistant",
            "content": [{"type": "output_text", "text": "I will inspect the scene."}], "phase": "commentary",
            "internal_chat_message_metadata_passthrough": {"turn_id": "turn-current"}}},
        {"type": "response_item", "payload": {"type": "message", "id": "msg-final", "role": "assistant",
            "content": [{"type": "output_text", "text": "The scene is unchanged."}], "phase": "final_answer",
            "internal_chat_message_metadata_passthrough": {"turn_id": "turn-current"}}},
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "turn-current",
            "last_agent_message": "The scene is unchanged."}},
    ]
    ops = run(M.CodexMirror("current"), records)
    assert turns(ops) == [("", "I will inspect the scene.\n\nThe scene is unchanged.", [], "completed")]
    assert kinds(ops).count("start") == kinds(ops).count("end") == 1
    assert len([d for k, _, d in ops if k == "event" and "content" in d]) == 2


def test_a_pi_session_file_renders_as_turns_bubbles_and_steps():
    from .byoa_fixtures import PI_TURNS
    ops = run(M.PiMirror("pane7"), PI_TURNS)
    assert turns(ops) == [
        ("Add a cone", "Adding a cone.\n\nThe cone is in.", [("lampway_scene", "done")], "completed"),
        ("Make it red", "", [("bash", "failed")], "cancelled"),                                    # Esc: stopReason "aborted"
        ("Try again", "429 rate limited", [], "failed"),
    ]
    assert "expert coding assistant" not in repr(ops) and "the scene tool" not in repr(ops)      # system prompt and thinking stay out


def test_codex_current_and_legacy_echoes_do_not_duplicate_turns():
    # Optional TurnItem forms follow official rust-v0.159.0, not recorded paginated-history acceptance.
    def event(kind, **data):
        return {"type": "event_msg", "payload": {"type": kind, "turn_id": "turn-one", **data}}
    def response(kind, **data):
        return {"type": "response_item", "payload": {"type": kind, **data}}
    records = [
        event("task_started"),
        response("message", id="user-one", role="user", content=[{"type": "input_text", "text": "Inspect the scene"}]),
        event("user_message", message="Inspect the scene"),
        event("item_completed", item={"type": "UserMessage", "id": "user-one", "content": [{"type": "text", "text": "Inspect the scene", "text_elements": []}]}),
        response("function_call", call_id="call-one", name="lampway__scene_summary", arguments="{}"),
        response("function_call", call_id="call-one", name="lampway__scene_summary", arguments="{}"),
        response("function_call_output", call_id="call-one", output="{}"),
        event("item_completed", item={"type": "FunctionCallOutput", "id": "call-one", "name": "lampway__scene_summary", "output": "{}"}),
        response("message", id="answer-one", role="assistant", content=[{"type": "output_text", "text": "Scene inspected."}], phase="final_answer"),
        event("agent_message", message="Scene inspected."),
        event("item_completed", item={"type": "AgentMessage", "id": "answer-one", "content": [{"type": "Text", "text": "Scene inspected."}], "phase": "final_answer"}),
        event("task_complete", last_agent_message="Scene inspected."),
        event("task_complete", last_agent_message="Scene inspected."),
    ]
    ops = run(M.CodexMirror("mixed"), records)
    assert turns(ops) == [("Inspect the scene", "Scene inspected.", [("scene_summary", "done")], "completed")]
    assert kinds(ops).count("start") == kinds(ops).count("end") == 1
    assert len([d for k, _, d in ops if k == "event" and "content" in d]) == 1
    assert len([d for k, _, d in ops if k == "event" and "steps" in d]) == 2


def test_codex_item_only_messages_and_task_fallback_preserve_completion():
    def event(kind, **data):
        return {"type": "event_msg", "payload": {"type": kind, "turn_id": "only", **data}}
    records = [
        event("task_started"),
        event("item_completed", item={"type": "UserMessage", "id": "u", "content": [{"type": "text", "text": "Inspect", "text_elements": []}]}),
        event("item_completed", item={"type": "AgentMessage", "id": "a", "content": [{"type": "Text", "text": "Inspecting."}], "phase": "commentary"}),
        event("task_complete", last_agent_message="Done."),
        event("item_completed", item={"type": "AgentMessage", "id": "final", "content": [{"type": "Text", "text": "Done."}], "phase": "final_answer"}),
    ]
    ops = run(M.CodexMirror("only"), records)
    assert turns(ops) == [("Inspect", "Inspecting.\n\nDone.", [], "completed")]
    assert kinds(ops).count("start") == kinds(ops).count("end") == 1


@pytest.mark.parametrize("failed", [False, True])
def test_codex_native_tool_items_share_the_raw_call_identity_and_complete_once(failed):
    # Official core tools/events.rs and mcp_tool_call.rs map item.id from native call_id.
    tool = {"type": "McpToolCall", "id": "call-mcp", "server": "lampway", "tool": "scene_summary", "arguments": {}, "status": "inProgress"}
    command = {"type": "CommandExecution", "id": "call-shell", "command": ["echo", "synthetic"], "cwd": "/synthetic", "source": "agent", "parsed_cmd": [], "status": "inProgress"}
    records = [{"type": "event_msg", "payload": {"type": "user_message", "message": "Inspect"}}]
    for item, name, args in [(tool, "lampway__scene_summary", "{}"), (command, "shell", '{"command":["echo","synthetic"]}')]:
        records += [
            {"type": "response_item", "payload": {"type": "function_call", "call_id": item["id"], "name": name, "arguments": args}},
            {"type": "event_msg", "payload": {"type": "item_started", "item": item}},
            {"type": "event_msg", "payload": {"type": "item_completed", "item": {**item, "status": "failed" if failed else "completed", "exit_code": 1 if failed else 0}}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": item["id"], "output": "{}"}},
        ]
    records += [{"type": "event_msg", "payload": {"type": "task_complete"}}]
    ops = run(M.CodexMirror("tools"), records)
    status = "failed" if failed else "done"
    assert turns(ops) == [("Inspect", "", [("scene_summary", status), ("shell", status)], "completed")]
    assert len([d for k, _, d in ops if k == "event" and "steps" in d]) == 4


def test_codex_distinct_equal_messages_and_user_before_task_start_stay_separate():
    def response(item_id, role, text):
        return {"type": "response_item", "payload": {"type": "message", "id": item_id, "role": role,
            "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}]}}
    records = [response("u1", "user", "Inspect"),
        {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "t1"}},
        response("a1", "assistant", "Same text."), response("a2", "assistant", "Same text."),
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "t1", "last_agent_message": "Same text."}},
        response("u2", "user", "Inspect"),
        {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "t2"}},
        {"type": "event_msg", "payload": {"type": "turn_aborted", "turn_id": "t2"}}]
    ops = run(M.CodexMirror("repeat"), records)
    assert turns(ops) == [("Inspect", "Same text.\n\nSame text.", [], "completed"), ("Inspect", "", [], "cancelled")]
    assert kinds(ops).count("start") == kinds(ops).count("end") == 2


def test_codex_completed_output_item_does_not_invent_a_second_tool_from_its_own_id():
    records = [
        {"type": "response_item", "payload": {"type": "function_call", "call_id": "call", "name": "shell", "arguments": "{}"}},
        {"type": "response_item", "payload": {"type": "function_call_output", "id": "output-item", "call_id": "call", "output": "{}"}},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "FunctionCallOutput", "id": "output-item", "name": "shell", "output": "{}"}}},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "FunctionCallOutput", "id": "unrelated-output", "name": "shell", "output": "{}"}}},
        {"type": "event_msg", "payload": {"type": "task_complete"}},
    ]
    ops = run(M.CodexMirror("output"), records)
    assert turns(ops) == [("", "", [("shell", "done")], "completed")]
    assert len([d for k, _, d in ops if k == "event" and "steps" in d]) == 2


def test_codex_new_task_with_the_same_prompt_can_change_message_format():
    def item(turn, role, text):
        return {"type": "event_msg", "payload": {"type": "item_completed", "turn_id": turn,
            "item": {"type": "UserMessage" if role == "user" else "AgentMessage", "id": turn + role,
                     "content": [{"type": "text" if role == "user" else "Text", "text": text}]}}}
    records = [
        {"type": "event_msg", "payload": {"type": "user_message", "message": "Inspect"}},
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "first"}},
        {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "second"}},
        item("second", "user", "Inspect"), item("second", "assistant", "Done."),
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "second"}},
    ]
    assert turns(run(M.CodexMirror("format"), records)) == [("Inspect", "", [], "completed"), ("Inspect", "Done.", [], "completed")]


def test_pis_session_file_is_found_by_its_folder_and_the_id_lampway_chose(tmp_path):
    from lampway_server.herdr.observers import native as N
    cwd = "/work/projects/my-scene"
    assert N.pi_session_folder(cwd) == "--work-projects-my-scene--"     # what Pi 1.0.4's get_state named for such a folder
    folder = tmp_path / N.pi_session_folder(cwd)
    folder.mkdir()
    (folder / "2026-10-07T18-25-32-383Z_other-id.jsonl").write_text("{}\n")
    assert N.pi_find_session(str(tmp_path), cwd, "1b2c3d4e-0000-4000-8000-00000000abcd") is None
    mine = folder / "2026-10-07T18-25-32-383Z_1b2c3d4e-0000-4000-8000-00000000abcd.jsonl"
    mine.write_text("{}\n")
    assert N.pi_find_session(str(tmp_path), cwd, "1b2c3d4e-0000-4000-8000-00000000abcd") == str(mine)
    assert N.pi_find_session(str(tmp_path), cwd, None) is None


def test_the_mirror_for_each_harness_and_none_for_a_harness_without_a_readable_file():
    assert isinstance(M.for_harness("claude", "k"), M.ClaudeMirror)
    assert isinstance(M.for_harness("codex", "k"), M.CodexMirror)
    assert isinstance(M.for_harness("pi", "k"), M.PiMirror)                    # Pi 1.0.4 keeps a session file (docs/session-format.md)
    for hid in ("opencode", "hermes", "grok", "cursor", "shell", None):
        assert M.for_harness(hid, "k") is None, hid
