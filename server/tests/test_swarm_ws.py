"""The swarm through the real turn loop and the fake client: lane scripts on the chat's session, worker scripts on their lanes."""

import json
import uuid

import pytest
from starlette.testclient import TestClient

from lampway_server.agent.providers.base import Text, ToolCall
from lampway_server.agent.providers.mock import ScriptedProvider
from lampway_server.app import create_app

from .fake_client import FakeMixarClient


def worker_provider(label):
    n = label.split("-")[1]
    return ScriptedProvider([
        [ToolCall(id=f"w{n}", name="run_blender_python", arguments={"script": f"import bpy\n# w{n}\n"})],
        [Text(f"w{n} made w{n}_obj")]])


def test_a_swarm_turn_routes_lanes_workers_and_merge_to_the_right_sessions(settings):
    main = ScriptedProvider([
        [ToolCall(id="s1", name="swarm_start", arguments={"tasks": [{"name": "a", "prompt": "make a"},
                                                                    {"name": "b", "prompt": "make b"}]})],
        [ToolCall(id="s2", name="swarm_collect", arguments={"swarm_id": "sw1"})],
        [Text("Both workers finished.")]])
    app = create_app(settings, provider=main, swarm_provider_factory=worker_provider)
    scripts = []
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()

        def on_script(params):
            scripts.append(params)
            tool = params["tool_name"]
            if tool == "run_blender_python":
                return fake.execute_script_result(params["script"], created=[params["script"].splitlines()[1][2:] + "_obj"])
            return {"success": True, "lanes": [], "merged": {}, "discarded": {}}

        with fake.connect_ws() as ws:
            fake.handshake(ws)
            session_id = str(uuid.uuid4())
            command_id = fake.command(ws, "chat", fake.chat_payload("make a and b in parallel", session_id))
            frames = fake.run_turn(ws, command_id, on_script=on_script)

    kinds = [(p["tool_name"], p["session_id"], p["agent_ctx"]["chat_session_id"]) for p in scripts]
    assert kinds[0] == ("swarm_lanes", session_id, session_id)
    lanes = sorted((k for k in kinds if k[0] == "run_blender_python"))
    assert lanes == [("run_blender_python", f"agentlane:{session_id}:1", f"agentlane:{session_id}:1"),
                     ("run_blender_python", f"agentlane:{session_id}:2", f"agentlane:{session_id}:2")]
    assert kinds[-1] == ("swarm_merge", session_id, session_id)
    ended = next(f for f in frames if f.get("method") == "agent.turn.ended")
    assert ended["params"]["turn_id"] == command_id
    events = [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event"]
    details = [row["detail"] for e in events for row in (e.get("steps") or {}).get("items", []) if row["label"] == "swarm_start"]
    assert any("workers started" in d for d in details)
    final = [e for e in events if (e.get("content") or {}).get("set")]
    assert final[-1]["content"]["set"] == "Both workers finished."
    assert "swarm_merge" == scripts[-1]["tool_name"] and "lw_worker" in scripts[-1]["script"]


def test_the_owner_can_list_swarms_and_cancel_a_worker_only_with_a_token(http, fake):
    assert http.get("/app/swarm").status_code == 401
    assert http.post("/app/swarm/sw1/cancel/worker-1").status_code == 401
    fake.login()
    assert fake.get("/app/swarm").json() == {"swarms": {}}
    assert fake.post("/app/swarm/sw1/cancel/worker-1").status_code == 404


def test_the_system_prompt_tells_the_main_agent_when_to_use_the_swarm():
    from lampway_server.agent.prompt import SYSTEM_PROMPT
    for token in ("swarm_start", "swarm_collect", "swarm_cancel", "lane"):
        assert token in SYSTEM_PROMPT
