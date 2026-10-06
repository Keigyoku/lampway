"""codex_app_server (specs/mrmak/02): one persistent `codex app-server` child per session over JSON-RPC lines; Lampway's tools as dynamic tools; the turn inverted into Lampway's stream() loop.
The fake app-server speaks the same lines; the real `codex` is only used for the schema probe (local, no network, no model call)."""
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from lampway_server.agent.providers import codex_app_server as CA
from lampway_server.agent.providers.base import Message, ModelRequest, Stop, Text, ToolCall, ToolSpec

FAKE = str(Path(__file__).parent / "fixtures" / "fake_codex_app_server.py")
pytestmark = pytest.mark.anyio

TOOLS = [ToolSpec("scene_summary", "the scene", {"type": "object", "properties": {}}), ToolSpec("lampway_status", "status", {"type": "object", "properties": {}})]


def schema_dir(tmp_path, with_dynamic=True):
    d = tmp_path / "schema"
    d.mkdir()
    names = ["initialize", "thread/start", "turn/start", "turn/interrupt", "item/tool/call", "item/agentMessage/delta", "item/completed", "turn/completed", "DynamicToolCallParams", "DynamicToolCallResponse"]
    (d / "ClientRequest.json").write_text(json.dumps({"oneOf": [{"properties": {"method": {"enum": [n]}}} for n in names]}))
    (d / "ThreadStartParams.json").write_text(json.dumps({"properties": {"dynamicTools": {}, "ephemeral": {}, "config": {}, "baseInstructions": {}}} if with_dynamic else {"properties": {"ephemeral": {}, "config": {}, "baseInstructions": {}}}))
    return d


def provider(tmp_path, scenario="two_tools", **kw):
    log = tmp_path / "wire.log"
    p = CA.CodexAppServerProvider(binary=[sys.executable, FAKE], schema_dir=str(schema_dir(tmp_path)), env={"SCENARIO": scenario, "LOG": str(log), "PATH": "/usr/bin:/bin"}, workdir=str(tmp_path / "work"), **kw)
    return p, log


def wire(log):
    return [json.loads(l) for l in Path(log).read_text().splitlines() if l.strip()]


async def collect(p, request, session="s1"):
    return [e async for e in p.stream(request, session_id=session)]


def user(text):
    return Message.user_text(text)


def results(*pairs):
    return Message("user", [{"type": "tool_result", "tool_call_id": cid, "content": text, "is_error": err} for cid, text, err in pairs])


async def test_the_probe_names_what_is_missing_and_a_complete_schema_passes(tmp_path):
    ok = CA.probe_schema(str(schema_dir(tmp_path)))
    assert ok["dynamic_tools"] is True
    bad = tmp_path / "bad"
    bad.mkdir()
    with pytest.raises(CA.CodexAppServerError, match="does not expose dynamic tools in app-server: update Codex, or use LAMPWAY_PROVIDER=codex_cli"):
        CA.probe_schema(str(schema_dir(bad, with_dynamic=False)))
    other = tmp_path / "other"
    other.mkdir()
    (other / "ClientRequest.json").write_text("{}")
    with pytest.raises(CA.CodexAppServerError, match="thread/start"):
        CA.probe_schema(str(other))


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed")
async def test_the_real_codex_schema_has_every_method_and_the_dynamic_tools_field(tmp_path):
    out = CA.probe_binary("codex", str(tmp_path / "real"))
    assert out["dynamic_tools"] is True and out["version"]


async def test_one_turn_two_tool_calls_roundtrip_in_two_stream_calls(tmp_path):
    p, log = provider(tmp_path)
    try:
        first = await collect(p, ModelRequest("be useful", [user("call both tools")], TOOLS))
        calls = [e for e in first if isinstance(e, ToolCall)]
        assert [(c.id, c.name) for c in calls] == [("call-a", "scene_summary"), ("call-b", "lampway_status")]
        second = await collect(p, ModelRequest("be useful", [user("call both tools"), Message("assistant", [{"type": "tool_call", "id": c.id, "name": c.name, "arguments": c.arguments} for c in calls]),
                                                             results(("call-a", "scene ok", False), ("call-b", "status ok", False))], TOOLS))
        assert "".join(e.text for e in second if isinstance(e, Text)) == "OK" and not any(isinstance(e, ToolCall) for e in second)
        w = wire(log)
        start = next(m for m in w if m.get("method") == "thread/start")["params"]
        assert start["approvalPolicy"] == "never" and start["sandbox"] == "read-only" and start["ephemeral"] is True and start["config"]["features.shell_tool"] is False
        assert [t["name"] for t in start["dynamicTools"]] == ["scene_summary", "lampway_status"] and start["dynamicTools"][0]["type"] == "function" and start["baseInstructions"] == "be useful"
        init = next(m for m in w if m.get("method") == "initialize")["params"]
        assert init["capabilities"]["experimentalApi"] is True and init["clientInfo"]["name"] == "lampway"
        answers = [m for m in w if "result" in m and m.get("id", 0) >= 100]
        assert [a["id"] for a in answers] == [100, 101] and answers[0]["result"] == {"success": True, "contentItems": [{"type": "inputText", "text": "scene ok"}]}
    finally:
        await p.close()


async def test_answering_only_one_of_two_pending_calls_leaves_the_turn_open_and_times_out_with_the_documented_message(tmp_path):
    p, log = provider(tmp_path, turn_timeout_s=1.0)
    try:
        first = await collect(p, ModelRequest("s", [user("go")], TOOLS))
        calls = [e for e in first if isinstance(e, ToolCall)]
        second = await collect(p, ModelRequest("s", [user("go"), Message("assistant", []), results((calls[0].id, "only one", False))], TOOLS))
        stops = [e for e in second if isinstance(e, Stop)]
        assert stops and "did not finish" in stops[0].reason
        await asyncio.sleep(0.4)
        assert any(m.get("method") == "turn/interrupt" for m in wire(log))
    finally:
        await p.close()


async def test_a_turn_that_never_completes_sends_turn_interrupt_and_yields_stop(tmp_path):
    p, log = provider(tmp_path, scenario="never", turn_timeout_s=0.8)
    try:
        events = await collect(p, ModelRequest("s", [user("go")], TOOLS))
        assert any(isinstance(e, Stop) and "did not finish" in e.reason for e in events)
        await asyncio.sleep(0.4)
        assert any(m.get("method") == "turn/interrupt" for m in wire(log))
    finally:
        await p.close()


async def test_an_unknown_server_request_gets_method_not_found(tmp_path):
    p, log = provider(tmp_path, scenario="unknown_request")
    try:
        await collect(p, ModelRequest("s", [user("go")], TOOLS))
        reply = next(m for m in wire(log) if m.get("id") == 900)
        assert reply["error"]["code"] == -32601 and "only supports" in reply["error"]["message"]
    finally:
        await p.close()


async def test_a_duplicate_call_id_reuses_the_first_result_and_is_yielded_once(tmp_path):
    p, log = provider(tmp_path, scenario="dup_call")
    try:
        first = await collect(p, ModelRequest("s", [user("go")], TOOLS))
        calls = [e for e in first if isinstance(e, ToolCall)]
        assert [c.id for c in calls] == ["call-a"]
        await collect(p, ModelRequest("s", [user("go"), Message("assistant", []), results(("call-a", "result one", False))], TOOLS))
        answers = [m for m in wire(log) if "result" in m and m.get("id", 0) >= 100]
        assert sorted(a["id"] for a in answers) == [100, 101] and all(a["result"]["contentItems"][0]["text"] == "result one" for a in answers)
    finally:
        await p.close()


async def test_a_tool_call_with_no_active_turn_is_refused(tmp_path):
    p, log = provider(tmp_path, scenario="one_tool")
    try:
        first = await collect(p, ModelRequest("s", [user("go")], TOOLS))
        calls = [e for e in first if isinstance(e, ToolCall)]
        await collect(p, ModelRequest("s", [user("go"), Message("assistant", []), results((calls[0].id, "done", False))], TOOLS))      # the turn completes
        client = p._clients["s1"]
        await client.request_raw({"method": "stray/tool", "id": 77, "params": {}})                  # the fake sends an item/tool/call for a turn nobody has open
        await asyncio.sleep(0.5)
        refusal = next(m for m in wire(log) if m.get("id") == 500)
        assert "No active authorized request or unknown tool" in json.dumps(refusal)
    finally:
        await p.close()


async def test_the_child_environment_has_no_lampway_secret_or_provider_key(tmp_path, monkeypatch):
    for k in ("LAMPWAY_TOKEN", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LAMPWAY_JWT_SECRET", "CLAUDECODE", "CODEX_THREAD_ID"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("LAMPWAY_CLI_FOO", "1")
    log = tmp_path / "wire.log"
    p = CA.CodexAppServerProvider(binary=[sys.executable, FAKE], schema_dir=str(schema_dir(tmp_path)), env=None, extra_env={"SCENARIO": "one_tool", "LOG": str(log)}, workdir=str(tmp_path / "work"))
    try:
        await collect(p, ModelRequest("s", [user("go")], TOOLS))
        keys = set(wire(log)[0]["env_keys"])
        assert not keys & {"LAMPWAY_TOKEN", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LAMPWAY_JWT_SECRET", "CLAUDECODE", "CODEX_THREAD_ID"}
        assert "LAMPWAY_CLI_FOO" in keys and "PATH" in keys
        assert wire(log)[0]["cwd"] == str(tmp_path / "work")                                         # an empty folder of its own: no project instruction file is picked up
    finally:
        await p.close()


async def test_codex_closing_mid_turn_yields_stop_and_the_next_call_replays_the_history_with_a_marker(tmp_path):
    p, log = provider(tmp_path, scenario="exit_mid_turn")
    try:
        events = await collect(p, ModelRequest("s", [user("first question")], TOOLS))
        assert any(isinstance(e, Stop) and "Codex closed; Lampway sessions are unaffected" in e.reason for e in events)
        p._env["SCENARIO"] = "one_tool"
        again = await collect(p, ModelRequest("s", [user("first question"), Message("assistant", [{"type": "text", "text": "partial"}]), user("second question")], TOOLS))
        turn = [m for m in wire(log) if m.get("method") == "turn/start"][-1]["params"]["input"][0]["text"]
        assert "[history replay]" in turn and "first question" in turn and "second question" in turn
        assert any(isinstance(e, ToolCall) for e in again)
    finally:
        await p.close()


async def test_a_non_object_tool_schema_and_an_effort_outside_the_list_are_refused(tmp_path):
    p, _ = provider(tmp_path)
    with pytest.raises(CA.CodexAppServerError, match="not a JSON object schema"):
        await collect(p, ModelRequest("s", [user("go")], [ToolSpec("bad", "d", "string")]))
    with pytest.raises(CA.CodexAppServerError, match="effort"):
        CA.CodexAppServerProvider(binary=[sys.executable, FAKE], effort="turbo")
    await p.close()
