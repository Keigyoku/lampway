# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BYOA B4 (docs/reports/agent-modes-spec.md): a harness's own session file, record by record, becomes the turn stream the
island already renders for Mode 1 (``run_status``, ``content.set``, ``steps``, then the turn's end), read-only.

The converter is pure: it is fed records and returns operations; the hub (agent/byoa.py) numbers and sends them. Fixtures are
the session files in tests/byoa_fixtures.py; no harness binary and no real file is involved."""
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


def test_a_pi_session_file_renders_as_turns_bubbles_and_steps():
    from .byoa_fixtures import PI_TURNS
    ops = run(M.PiMirror("pane7"), PI_TURNS)
    assert turns(ops) == [
        ("Add a cone", "Adding a cone.\n\nThe cone is in.", [("lampway_scene", "done")], "completed"),
        ("Make it red", "", [("bash", "failed")], "cancelled"),                                    # Esc: stopReason "aborted"
        ("Try again", "429 rate limited", [], "failed"),
    ]
    assert "expert coding assistant" not in repr(ops) and "the scene tool" not in repr(ops)      # system prompt and thinking stay out


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
