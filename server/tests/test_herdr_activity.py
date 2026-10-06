"""Native activity of the user's real CLIs, read from THEIR transcripts (specs/mrmak/01 section 6.3 and 6.4): working / waiting / unread from the CLI's own records, never from the screen. Ported in
shape from the vendored activity tests; the code is new."""
import json
from pathlib import Path

import pytest

from lampway_server.herdr.observers import activity as ACT
from lampway_server.herdr.observers import native as NAT


def rec(**kw):
    return kw


def test_claude_records_classify_into_started_completed_interrupted_and_nothing():
    c = lambda r: NAT.native_activity(r, "claude")
    assert c(rec(type="user", message={"content": "Please review this."}))["kind"] == "turn-started"
    assert c(rec(type="user", isMeta=True, message={"content": "Context loaded."})) is None
    assert c(rec(type="assistant", isSidechain=True, message={"stop_reason": "tool_use"})) is None
    assert c(rec(type="assistant", message={"stop_reason": "tool_use"}))["kind"] == "turn-started"
    assert c(rec(type="user", message={"content": [{"type": "tool_result", "content": "Command finished."}]}))["kind"] == "turn-started"
    assert c(rec(type="assistant", message={"stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": "Internal reasoning."}]})) is None
    done = c(rec(type="assistant", message={"id": "msg-1", "stop_reason": "end_turn", "content": [{"type": "text", "text": "Done."}]}))
    assert done["kind"] == "turn-completed" and done["id"] == "msg-1" and done["preview"] == "Done."
    assert c(rec(type="user", message={"content": "[Request interrupted by user]"}))["kind"] == "turn-interrupted"
    assert c(rec(type="user", message={"content": [{"type": "text", "text": "[Request interrupted by user for tool use]"}]}))["kind"] == "turn-interrupted"
    assert c(rec(type="system", subtype="api_error"))["kind"] == "attention"
    assert NAT.native_activity(rec(type="assistant", message={"stop_reason": "end_turn"}), "kimi") is None


def test_a_sidechain_end_turn_never_completes_the_falsifier():
    sidechain = rec(type="assistant", isSidechain=True, message={"id": "m", "stop_reason": "end_turn", "content": [{"type": "text", "text": "sub-agent answer"}]})
    assert NAT.native_activity(sidechain, "claude") is None
    assert NAT.native_activity({**sidechain, "isSidechain": False}, "claude")["kind"] == "turn-completed"


def test_codex_events_classify_and_the_preview_is_the_last_agent_message():
    c = lambda r: NAT.native_activity(r, "codex")
    assert c({"type": "event_msg", "payload": {"type": "task_started"}})["kind"] == "turn-started"
    assert c({"type": "event_msg", "payload": {"type": "token_count"}}) is None
    assert c({"type": "event_msg", "payload": {"type": "turn_aborted"}})["kind"] == "turn-interrupted"
    done = c({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "t1", "last_agent_message": "Ready"}})
    assert done["kind"] == "turn-completed" and done["id"] == "t1" and done["preview"] == "Ready"


def test_the_tail_starts_after_the_boundary_and_a_record_split_inside_an_emoji_waits_for_its_second_half(tmp_path):
    f = tmp_path / "native.jsonl"
    old = json.dumps({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "old"}}) + "\n"
    f.write_text(old)
    tail = NAT.Tailer(str(f), "codex", from_offset=len(old.encode()))
    assert tail.poll() == []                                                                 # history before the boundary is never replayed
    with f.open("a") as fh:
        fh.write(json.dumps({"type": "event_msg", "payload": {"type": "task_started"}}) + "\n")
    assert [e["kind"] for e in tail.poll()] == ["turn-started"]
    nxt = (json.dumps({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "new", "last_agent_message": "Ready 🐽"}}, ensure_ascii=False) + "\n").encode()
    cut = nxt.index("🐽".encode()) + 2                                                       # the middle of a 4-byte character
    with f.open("ab") as fh:
        fh.write(nxt[:cut])
    assert tail.poll() == []
    with f.open("ab") as fh:
        fh.write(nxt[cut:])
    ev = tail.poll()
    assert [e["kind"] for e in ev] == ["turn-completed"] and ev[0]["id"] == "new" and ev[0]["preview"] == "Ready 🐽"
    assert tail.poll() == []                                                                 # nothing completes from silence


def test_claude_transcript_path_follows_the_folder_rule_and_the_config_dir(tmp_path):
    p = NAT.claude_transcript(str(tmp_path / "my.proj"), "abc-123", config_dir=str(tmp_path / "cfg"))
    assert p == str(tmp_path / "cfg" / "projects" / __import__("re").sub(r"[^A-Za-z0-9]", "-", str(tmp_path / "my.proj")) / "abc-123.jsonl")


def test_codex_binding_needs_the_originator_marker_and_a_unique_match(tmp_path):
    base = tmp_path / "codex" / "sessions" / "2026" / "10" / "05"
    base.mkdir(parents=True)
    def rollout(name, originator, cwd, source="cli"):
        (base / name).write_text(json.dumps({"type": "session_meta", "payload": {"id": name, "originator": originator, "cwd": cwd, "source": source}}) + "\n")
    cwd = str(tmp_path / "proj")
    rollout("a.jsonl", "lampway_chat_one", cwd)
    rollout("b.jsonl", "someone_else", cwd)
    assert NAT.codex_find_session(str(tmp_path / "codex"), "lampway_chat_one", cwd)["id"] == "a.jsonl"
    rollout("c.jsonl", "lampway_chat_one", cwd)                                              # two marked files: bind none
    assert NAT.codex_find_session(str(tmp_path / "codex"), "lampway_chat_one", cwd) is None
    assert NAT.codex_find_session(str(tmp_path / "codex"), "lampway_chat_missing", cwd) is None
    (base / "c.jsonl").unlink()
    rollout("d.jsonl", "lampway_chat_one", cwd + "/other")                                   # wrong folder: not a match either
    assert NAT.codex_find_session(str(tmp_path / "codex"), "lampway_chat_one", cwd)["id"] == "a.jsonl"
    rollout("e.jsonl", "lampway_chat_one", cwd, source="exec")
    assert NAT.codex_find_session(str(tmp_path / "codex"), "lampway_chat_one", cwd)["id"] == "a.jsonl"


# ----------------------------------------------------------------------------------------------------- unread / seen
def answer(i):
    return {"kind": "turn-completed", "id": i, "preview": "done " + i}


def test_unread_survives_new_work_and_stale_acknowledgements_and_duplicate_completions_are_ignored():
    s = ACT.SessionActivity()
    assert s.activity == "idle"                                                              # a live process is not a working agent
    s.apply({"kind": "turn-started"})
    assert s.activity == "working" and s.unread is False
    s.apply(answer("turn-1"))
    assert s.activity == "idle" and s.unread is True
    v1 = s.completion_version
    s.apply(answer("turn-1"))
    assert s.completion_version == v1                                                        # a duplicate id is ignored
    s.apply({"kind": "turn-started"})
    assert s.unread is True                                                                  # new work does not hide the unread answer
    s.apply(answer("turn-2"))
    assert s.seen(v1, focused=True, subscribed=True) is False and s.unread is True            # a stale acknowledgement does not consume the newer answer
    assert s.seen(s.completion_version, focused=True, subscribed=True) is True and s.unread is False


def test_only_the_focused_subscribed_window_can_acknowledge_never_the_blender_panel():
    s = ACT.SessionActivity()
    s.apply(answer("t"))
    assert s.seen(s.completion_version, focused=False, subscribed=True) is False and s.unread is True
    assert s.seen(s.completion_version, focused=True, subscribed=False) is False and s.unread is True
    assert s.unread is True and s.peek()["unread"] is True                                   # reading through a tool never acknowledges


def test_restore_after_a_restart_is_idle_and_stopped_but_keeps_the_unread_answer():
    s = ACT.SessionActivity()
    s.apply({"kind": "turn-started"})
    s.apply(answer("t"))
    s.apply({"kind": "turn-started"})
    restored = ACT.SessionActivity.restore(s.to_dict())
    assert restored.activity == "idle" and restored.unread is True and restored.status == "stopped"
    restored.seen(restored.completion_version, focused=True, subscribed=True)
    restored.apply(answer("t"))                                                              # the same answer replayed does not make it unread again
    assert restored.unread is False
    restored.apply({"kind": "turn-started"})
    restored.apply({"kind": "turn-interrupted"})
    assert restored.activity == "idle" and restored.unread is False


def test_attention_marks_waiting_until_the_next_event():
    s = ACT.SessionActivity()
    s.apply({"kind": "attention", "text": "the agent reported an API error"})
    assert s.activity == "waiting" and s.attention == "the agent reported an API error"
    s.apply({"kind": "turn-started"})
    assert s.activity == "working" and s.attention == ""
