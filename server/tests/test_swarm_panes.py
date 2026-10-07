# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The swarm in Mode 2 (docs/reports/agent-modes-spec.md S3, S4, S5): pane workers.

A bound BYOA pane (B2) starts a swarm over MCP; each worker is a pane on Lampway's herdr server running the parent's harness (Q10),
started under that harness's ``byoa:<harness>`` route (B5), with the task on its command line and its own MCP config bound to
``swarm:<swarm_id>:<worker_id>``. The worker pane's tool calls land on ITS worker's headless Lampway (``WorkerJob.call_tool``);
``lampway_worker_done(summary)`` stages and finishes the task; a pane that exits without it fails the task; the swarm closes only
panes it opened (law 5). External MCP apps never get the swarm tools (server invariant 4).

herdr is faked (no herdr, no harness binary runs: the fake records the commands and plays the panes); the parent desktop and its
workers are the fake fleet of ``test_swarm_v3.py``. Nothing leaves the machine."""
import json
import stat
import threading
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from lampway_server import egress as EG
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L
from lampway_server.herdr import harnesses as HN

from .fake_client import FakeMixarClient
from .fake_harness import FakeFleet
from .herdr_support import PaneHerdr

SCENE = "6f1c2a52-3c1e-4c55-9d7e-2b0f6c1d9a10"
PANE_URL = "http://127.0.0.1:8787/api/v1/mcp/pane"
NEVER_FOR_A_WORKER = {"swarm_start", "swarm_status", "swarm_cancel", "swarm_collect", "ask_user", "lampway_workbench"}


def wait_for(cond, timeout=10.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return cond()


def serve_parent(fake, fleet, ready, stop, held):
    """The user's desktop: answers every request the server sends it (the swarm's harness requests) with the fake fleet."""
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        held["ws"] = ws
        ready.set()
        while not stop.is_set():
            try:
                frame = ws.receive_json()
            except Exception:  # noqa: BLE001 - the socket closed
                return
            fleet.frames.append(frame)
            if frame.get("method") and frame.get("id"):
                ws.send_json({"jsonrpc": "2.0", "id": frame["id"], "result": fleet.handle(frame)})
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            pass


class Rig:
    """The server, the user's desktop (the fake fleet) and a bound Claude Code pane: the BYOA parent."""

    def __init__(self, http, fake, fleet, cockpit, herdr, strict):
        self.http, self.fake, self.fleet, self.cockpit, self.herdr, self.egress = http, fake, fleet, cockpit, herdr, strict
        self.parent = None

    # -- the parent pane, as its harness sees it: the entries of its own MCP config
    def bind_parent(self, scene=SCENE, harness="claude"):
        self.parent = self.cockpit.create_session(harness, "Parent audit pane", str(self.cockpit.project_root), by="user", scene_session_id=scene)
        return self.parent

    def parent_headers(self, rec=None):
        rec = rec or self.parent
        entry = json.loads(Path(rec["mcp_config_path"]).read_text())["mcpServers"]["lampway_swarm"]
        assert entry["type"] == "http" and entry["url"] == PANE_URL
        return dict(entry["headers"])

    def rpc(self, url, headers, method, params=None, rid=1):
        body = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            body["params"] = params
        return self.http.post(url, json=body, headers={**headers, "Accept": "application/json, text/event-stream"})

    def parent_call(self, name, arguments, rec=None):
        r = self.rpc(PANE_URL, self.parent_headers(rec), "tools/call", {"name": name, "arguments": arguments})
        assert r.status_code == 200, r.text
        return r.json()["result"]

    def parent_json(self, name, arguments):
        res = self.parent_call(name, arguments)
        assert res["isError"] is False, res
        return json.loads(res["content"][0]["text"])

    # -- the worker panes
    def worker_panes(self):
        return [s for s in self.cockpit.list_sessions() if s.get("created_by") == "swarm"]

    def worker_entry(self, rec):
        return json.loads(Path(rec["mcp_config_path"]).read_text())["mcpServers"]["lampway"]

    def worker_rpc(self, rec, method, params=None, headers=None):
        entry = self.worker_entry(rec)
        return self.rpc(entry["url"], headers if headers is not None else entry["headers"], method, params)

    def worker_call(self, rec, name, arguments):
        r = self.worker_rpc(rec, "tools/call", {"name": name, "arguments": arguments})
        assert r.status_code == 200, r.text
        return r.json()["result"]

    def status(self, swarm_id):
        return {w["id"]: w for w in self.parent_json("swarm_status", {"swarm_id": swarm_id})["workers"]}


@pytest.fixture
def strict(tmp_path):
    m = EG.Egress(tmp_path / "egress-state")
    EG.install()
    prev = EG.ACTIVE
    EG.set_active(m)
    m.set_route("byoa:claude", True)
    yield m
    EG.set_active(prev)


@pytest.fixture
def rig(settings, tmp_path, monkeypatch, strict):
    from lampway_server import capabilities as CAP
    from lampway_server.agent.providers.base import Text
    from lampway_server.agent.providers.mock import ScriptedProvider
    from lampway_server.app import create_app
    from lampway_server.herdr import swarm_brain as SB
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    monkeypatch.setenv("LAMPWAY_MCP_LAUNCHER", "/opt/lw/connector/lampway-mcp")
    monkeypatch.setattr(SB, "POLL_S", 0.05)
    herdr = PaneHerdr(strict)
    monkeypatch.setattr(L, "run", herdr)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    (tmp_path / "proj").mkdir()
    cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path / "proj"))
    app = create_app(settings, provider=ScriptedProvider([[Text("unused")]]), cockpit=cockpit, egress=strict)
    CAP.ACTIVE.set("swarm", enabled=True, by="user")
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        fleet = FakeFleet(fake, fake.instance_id)
        ready, stop, held = threading.Event(), threading.Event(), {}
        t = threading.Thread(target=serve_parent, args=(fake, fleet, ready, stop, held), daemon=True)
        t.start()
        assert ready.wait(10)
        rig = Rig(http, fake, fleet, cockpit, herdr, strict)
        rig.held, rig.app = held, app                    # the desktop's socket (the island's), and the server
        try:
            yield rig
        finally:
            swarms = app.state.agent.swarm

            async def cancel_all():                       # what a test left running ends while the desktop can still answer
                for swarm in swarms.swarms.values():
                    swarms.cancel_all(swarm)
            http.portal.call(cancel_all)                  # on the server's own loop: a task is not cancelled from another thread
            wait_for(lambda: all(w.task is None or w.task.done() for s in swarms.swarms.values() for w in s.workers), timeout=10)
            stop.set()
            try:                          # wake the desktop thread's blocked receive: the server answers, the loop sees ``stop``
                held["ws"].send_json({"jsonrpc": "2.0", "method": "system.ping", "id": "bye"})
            except Exception:  # noqa: BLE001 - already closed
                pass
            t.join(10)
            fleet.close()


def tasks(*names):
    return [{"name": n, "prompt": f"Model the {n} piece and name it {n}_part"} for n in names]


def marker(rec_name):
    return {"script": f"import bpy\n# by {rec_name}\n# collection QA_candidates {rec_name}_L000\n"}


# ------------------------------------------------------------------------------------------------------------- the whole loop
def test_a_bound_pane_starts_a_swarm_of_panes_each_bound_to_its_worker_and_their_work_lands_in_the_panes_scene(rig):
    rig.bind_parent()
    started = rig.parent_json("swarm_start", {"tasks": tasks("boots", "belt")})
    sid = started["swarm_id"]
    panes = wait_for(lambda: len(rig.worker_panes()) == 2 and rig.worker_panes())
    assert panes, "one pane per task was never opened"
    by_worker = {}
    for rec in panes:
        # the parent's harness (Q10), under its route (B5): the route's row is written before herdr makes the pane
        assert rec["agent"] == "claude" and rec["harness"] == "claude" and rec["created_by"] == "swarm"
        start = rig.herdr.start_of(rec["pane_id"])
        assert start["sends_before"].count("byoa:claude") >= 2, "the parent's row and this worker's row precede its start"
        # its own MCP config, 0600 under the Lampway root, bound to swarm:<swarm_id>:<worker_id>, pointing at the server only
        cfg = Path(rec["mcp_config_path"])
        assert str(cfg).startswith(str(rig.cockpit.root / "panes")) and stat.S_IMODE(cfg.stat().st_mode) == 0o600
        servers = json.loads(cfg.read_text())["mcpServers"]
        assert set(servers) == {"lampway"}, "a worker gets no desktop launcher (its UI and scene-tab tools reach the user's scene)"
        entry = servers["lampway"]
        binding = entry["headers"]["X-Mixar-Session-Id"]
        assert entry["type"] == "http" and entry["url"] == PANE_URL and binding.startswith(f"swarm:{sid}:worker-")
        assert entry["headers"]["Authorization"].startswith("Bearer ") and len(entry["headers"]["Authorization"]) > 40
        assert rec["swarm_binding"] == binding and rec["scene_session_id"] is None
        assert entry["headers"]["Authorization"][7:] not in json.dumps(rig.cockpit.list_sessions()), "the worker's token is not in the registry"
        # the task on its command line: the worker's system prompt, then the task prompt; then the pane's own config
        argv = start["args"][start["args"].index("--") + 1:]
        task = next(a for a in argv if a.startswith("You are worker-"))
        worker_id = binding.rsplit(":", 1)[1]
        assert task.startswith(f"You are {worker_id}, one worker of a swarm") and "Model the " in task and "lampway_worker_done" in task
        assert argv[argv.index("--mcp-config") + 1] == str(cfg) and argv.index(task) < argv.index("--mcp-config")
        by_worker[worker_id] = rec
    assert sorted(by_worker) == ["worker-1", "worker-2"]
    creates = rig.herdr.made()
    assert len(creates) == 3 and all(c["sends_before"].count("byoa:claude") >= i + 1 for i, c in enumerate(creates)), "each pane's route row precedes its creation"
    # spec A4: the workers split into the parent's tab (its unit is the bound scene tab), right of it, then down the column
    assert [c["args"][:2] for c in creates[1:]] == [["pane", "split"]] * 2 and len(rig.herdr.tabs) == 1
    assert {(w["unit"], w["role"], w["tab_id"]) for w in panes} == {(SCENE, "worker", rig.parent["tab_id"])}

    for worker_id, rec in by_worker.items():
        listed = {t["name"] for t in rig.worker_rpc(rec, "tools/list").json()["result"]["tools"]}
        assert "lampway_worker_done" in listed and "run_blender_python" in listed
        assert not listed & NEVER_FOR_A_WORKER and not [n for n in listed if n.startswith("studio_")]
        res = rig.worker_call(rec, "run_blender_python", marker(worker_id))
        assert res["isError"] is False, res
    for worker in rig.fleet.workers.values():                    # each pane's call landed on its own worker connection
        marked = [f["params"] for f in worker.frames if f.get("method") == "blender.execute_script" and "# by worker-" in f["params"]["script"]]
        assert len(marked) == 1 and marked[0]["session_id"] == f"agent:{worker.connection_id}"
        assert marked[0]["envelope"]["execution_target"] == worker.connection_id
    assert not [p for m, p in rig.fleet.requests if m == "blender.execute_script" and "# by worker-" in p.get("script", "")], "nothing reached the user's scene"

    for worker_id, rec in by_worker.items():
        done = rig.worker_call(rec, "lampway_worker_done", {"summary": f"{worker_id} drew its marker"})
        assert done["isError"] is False
    assert wait_for(lambda: {w["status"] for w in rig.status(sid).values()} == {"staged"})
    again = rig.worker_call(by_worker["worker-1"], "run_blender_python", marker("worker-1"))
    assert again["isError"] is True, "a finished worker's binding is revoked"

    out = rig.parent_json("swarm_collect", {"swarm_id": sid})
    assert {w["status"] for w in out["workers"]} == {"done"}
    assert sorted(w["summary"] for w in out["workers"]) == ["worker-1 drew its marker", "worker-2 drew its marker"]
    activate = next(p for m, p in rig.fleet.requests if m == "agent.execution.activate")
    assert activate["session_id"] == SCENE, "the swarm's parent scene is the pane's bound scene tab"
    assert len(rig.fleet.parent.collections["Lampway Agent"]) == 2
    assert rig.parent["pane_id"] not in rig.herdr.closed(), "the swarm never closes a pane it did not start (law 5)"


def test_a_worker_pane_that_exits_without_lampway_worker_done_fails_its_task_and_nothing_is_committed(rig):
    rig.bind_parent()
    sid = rig.parent_json("swarm_start", {"tasks": tasks("boots")})["swarm_id"]
    rec = wait_for(lambda: rig.worker_panes() and rig.worker_panes()[0])
    assert rec
    rig.worker_call(rec, "run_blender_python", marker("worker-1"))
    rig.herdr.exit(rec["pane_id"])                                          # the harness quit (or the user closed the pane)
    w = wait_for(lambda: rig.status(sid)["worker-1"]["status"] == "failed" and rig.status(sid)["worker-1"])
    assert w and "lampway_worker_done" in w["error"]
    out = rig.parent_json("swarm_collect", {"swarm_id": sid})
    assert [x["status"] for x in out["workers"]] == ["failed"]
    assert not [p for m, p in rig.fleet.requests if m == "agent.execution.commit"]
    late = rig.worker_call(rec, "lampway_worker_done", {"summary": "too late"})
    assert late["isError"] is True


def test_a_worker_that_never_finishes_times_out_and_the_swarm_closes_only_its_own_pane(rig, monkeypatch):
    from lampway_server.herdr import swarm_brain as SB
    monkeypatch.setattr(SB, "PANE_WORKER_TIMEOUT_S", 0.6)
    other = rig.cockpit.create_session("claude", "Someone else's pane", str(rig.cockpit.project_root), by="user")
    rig.bind_parent()
    sid = rig.parent_json("swarm_start", {"tasks": tasks("boots")})["swarm_id"]
    rec = wait_for(lambda: rig.worker_panes() and rig.worker_panes()[0])
    w = wait_for(lambda: rig.status(sid)["worker-1"]["status"] == "failed" and rig.status(sid)["worker-1"])
    assert w and "did not finish" in w["error"]
    assert wait_for(lambda: rig.herdr.closed()) == [rec["pane_id"]]
    assert other["pane_id"] in rig.herdr.panes and rig.parent["pane_id"] in rig.herdr.panes


def test_cancelling_a_worker_closes_its_pane_and_nothing_else(rig):
    rig.bind_parent()
    sid = rig.parent_json("swarm_start", {"tasks": tasks("boots", "belt")})["swarm_id"]
    panes = wait_for(lambda: len(rig.worker_panes()) == 2 and rig.worker_panes())
    one = next(p for p in panes if p["swarm_binding"].endswith(":worker-1"))
    two = next(p for p in panes if p["swarm_binding"].endswith(":worker-2"))
    rig.parent_json("swarm_cancel", {"swarm_id": sid, "worker": "worker-1"})
    assert wait_for(lambda: rig.herdr.closed()) == [one["pane_id"]]
    assert two["pane_id"] in rig.herdr.panes and rig.parent["pane_id"] in rig.herdr.panes
    assert rig.worker_call(one, "run_blender_python", marker("worker-1"))["isError"] is True
    rig.worker_call(two, "lampway_worker_done", {"summary": "worker-2 done"})
    out = rig.parent_json("swarm_collect", {"swarm_id": sid})
    assert {w["id"]: w["status"] for w in out["workers"]} == {"worker-1": "cancelled", "worker-2": "done"}


def test_with_the_harness_route_off_no_worker_pane_starts_and_the_task_fails_naming_the_route(rig):
    rig.bind_parent()
    rig.egress.set_route("byoa:claude", False)
    sid = rig.parent_json("swarm_start", {"tasks": tasks("boots")})["swarm_id"]
    w = wait_for(lambda: rig.status(sid)["worker-1"]["status"] == "failed" and rig.status(sid)["worker-1"])
    assert w and "byoa:claude is off" in w["error"]
    assert rig.worker_panes() == []


# ------------------------------------------------------------------------------------------------------------- who gets what
def test_an_external_mcp_app_is_refused_the_swarm_tools_and_never_reaches_a_worker(rig):
    rig.bind_parent()
    sid = rig.parent_json("swarm_start", {"tasks": tasks("boots")})["swarm_id"]
    rec = wait_for(lambda: rig.worker_panes() and rig.worker_panes()[0])
    head = {"X-Mixar-Instance-Id": rig.fake.instance_id, "X-Mixar-Session-Id": SCENE}
    listed = {t["name"] for t in rig.fake.post("/api/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=head).json()["result"]["tools"]}
    assert not listed & {"swarm_start", "swarm_status", "swarm_cancel", "swarm_collect", "lampway_worker_done"}
    for name, args in (("swarm_start", {"tasks": tasks("x")}), ("swarm_collect", {"swarm_id": sid}), ("lampway_worker_done", {"summary": "x"})):
        r = rig.fake.post("/api/v1/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": args}}, headers=head)
        assert r.json()["error"]["code"] == -32602, name
    # the worker's binding in the session header is not a credential: the external route never resolves it
    binding = rec["swarm_binding"]
    r = rig.fake.post("/api/v1/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "run_blender_python", "arguments": marker("intruder")}},
                      headers={"X-Mixar-Instance-Id": rig.fake.instance_id, "X-Mixar-Session-Id": binding})
    assert r.json()["result"]["isError"] is True and "worker" in r.json()["result"]["content"][0]["text"]
    assert not [f for w in rig.fleet.workers.values() for f in w.frames if "intruder" in json.dumps(f)]
    assert not [p for m, p in rig.fleet.requests if "intruder" in json.dumps(p)]
    # the pane endpoint takes only a pane's own key or a worker's own token, and a worker token only with its own binding
    user = rig.fake.rest_headers()
    assert rig.rpc(PANE_URL, user, "tools/list").status_code == 401
    assert rig.rpc(PANE_URL, {"Authorization": "Bearer not-a-key"}, "tools/list").status_code == 401
    entry = rig.worker_entry(rec)
    wrong = {**entry["headers"], "X-Mixar-Session-Id": f"swarm:{sid}:worker-9"}
    assert rig.worker_rpc(rec, "tools/list", headers=wrong).status_code == 401
    forged = {**entry["headers"], "Authorization": "Bearer " + "x" * 43}
    assert rig.worker_rpc(rec, "tools/list", headers=forged).status_code == 401
    assert rig.worker_rpc(rec, "tools/list", headers={**entry["headers"], "Authorization": rig.parent_headers()["Authorization"]}).status_code == 401


def test_only_a_bound_pane_with_the_swarm_capability_gets_the_swarm_tools(rig):
    from lampway_server import capabilities as CAP
    rig.bind_parent()
    listed = {t["name"] for t in rig.rpc(PANE_URL, rig.parent_headers(), "tools/list").json()["result"]["tools"]}
    assert listed == {"swarm_start", "swarm_status", "swarm_cancel", "swarm_collect"}
    CAP.ACTIVE.set("swarm", enabled=False, by="user")
    assert rig.rpc(PANE_URL, rig.parent_headers(), "tools/list").json()["result"]["tools"] == []
    res = rig.parent_call("swarm_start", {"tasks": tasks("boots")})
    assert res["isError"] is True and "swarm" in res["content"][0]["text"] and rig.worker_panes() == []
    CAP.ACTIVE.set("swarm", enabled=True, by="user")
    headers = rig.parent_headers()
    rig.cockpit.unbind(rig.parent["id"])                                 # the scene tab closed: the pane runs on, unbound
    res = rig.rpc(PANE_URL, headers, "tools/call", {"name": "swarm_start", "arguments": {"tasks": tasks("boots")}}).json()["result"]
    assert res["isError"] is True and "not bound to a scene tab" in res["content"][0]["text"] and rig.worker_panes() == []


def test_a_pane_reaches_only_the_swarms_it_started(rig):
    rig.bind_parent()
    sid = rig.parent_json("swarm_start", {"tasks": tasks("boots")})["swarm_id"]
    second = rig.cockpit.create_session("claude", "Second bound pane", str(rig.cockpit.project_root), by="user", scene_session_id=SCENE)
    res = rig.parent_call("swarm_status", {"swarm_id": sid}, rec=second)
    assert res["isError"] is True and "not started by this pane" in res["content"][0]["text"]


def test_a_codex_parent_gets_codex_workers_whose_bearers_live_only_in_their_pane_environment(rig):
    rig.egress.set_route("byoa:codex", True)
    parent = rig.cockpit.create_session("codex", "Codex parent pane", str(rig.cockpit.project_root), by="user", scene_session_id=SCENE)
    key = rig.herdr.env_of(parent["pane_id"])["LAMPWAY_PANE_KEY"]
    pargv = rig.herdr.start_of(parent["pane_id"])["args"]
    assert key not in json.dumps(pargv) and 'mcp_servers.lampway_swarm.bearer_token_env_var="LAMPWAY_PANE_KEY"' in pargv
    assert key not in Path(parent["mcp_config_path"]).read_text()
    res = rig.rpc(PANE_URL, {"Authorization": f"Bearer {key}"}, "tools/call", {"name": "swarm_start", "arguments": {"tasks": tasks("boots")}}).json()["result"]
    assert res["isError"] is False, res
    sid = json.loads(res["content"][0]["text"])["swarm_id"]
    worker = wait_for(lambda: rig.worker_panes() and rig.worker_panes()[0])
    assert worker and worker["agent"] == "codex"                                         # Q10: the parent's harness
    token = rig.herdr.env_of(worker["pane_id"])["LAMPWAY_WORKER_TOKEN"]
    wargv = rig.herdr.start_of(worker["pane_id"])["args"]
    wargv = wargv[wargv.index("--") + 1:]
    assert token not in json.dumps(wargv) and token not in Path(worker["mcp_config_path"]).read_text()
    assert not [a for a in wargv if "mcp_servers.lampway.command" in a or "lampway_swarm" in a], "a worker has only its own entry"
    assert f'mcp_servers.lampway.url="{PANE_URL}"' in wargv
    assert f'mcp_servers.lampway.http_headers={{"X-Mixar-Session-Id" = "{worker["swarm_binding"]}"}}' in wargv
    assert next(a for a in wargv if a.startswith("You are worker-1")) and wargv.index(next(a for a in wargv if a.startswith("You are"))) < wargv.index("-c")
    head = {"Authorization": f"Bearer {token}", "X-Mixar-Session-Id": worker["swarm_binding"]}
    done = rig.rpc(PANE_URL, head, "tools/call", {"name": "lampway_worker_done", "arguments": {"summary": "worker-1 made nothing"}}).json()["result"]
    assert done["isError"] is False
    out = json.loads(rig.rpc(PANE_URL, {"Authorization": f"Bearer {key}"}, "tools/call",
                             {"name": "swarm_collect", "arguments": {"swarm_id": sid}}).json()["result"]["content"][0]["text"])
    assert [w["status"] for w in out["workers"]] == ["done"]


# ------------------------------------------------------------------------------------------------------------- the parts
def test_the_swarm_cannot_end_a_pane_it_did_not_open_and_a_worker_pane_cannot_be_bound_to_a_tab(rig):
    users = rig.cockpit.create_session("claude", "Someone else's pane", str(rig.cockpit.project_root), by="user")
    rig.bind_parent()
    rig.parent_json("swarm_start", {"tasks": tasks("boots")})
    worker = wait_for(lambda: rig.worker_panes() and rig.worker_panes()[0])
    for sid, binding in ((users["id"], worker["swarm_binding"]), (rig.parent["id"], worker["swarm_binding"]), (worker["id"], "swarm:sw1:worker-2")):
        with pytest.raises(H.CockpitError, match="did not start"):
            rig.cockpit.end_swarm_pane(sid, binding, "planted", True)
    with pytest.raises(H.CockpitError, match="bound to its worker"):
        rig.cockpit.bind(worker["id"], SCENE)
    assert rig.herdr.closed() == [] and {s["state"] for s in rig.cockpit.list_sessions()} == {"live"}


def test_a_bound_pane_gets_a_swarm_entry_whose_key_only_its_own_config_holds(rig):
    rec = rig.bind_parent()
    headers = rig.parent_headers()
    key = headers["Authorization"][7:]
    assert len(key) >= 32 and headers.get("X-Mixar-Session-Id") is None
    assert key not in json.dumps(rig.cockpit.list_sessions()) and rec["pane_key_sha256"]
    assert json.loads(Path(rec["mcp_config_path"]).read_text())["mcpServers"]["lampway"]["env"] == {"LAMPWAY_BOUND_SESSION": SCENE}
    rig.cockpit.bind(rec["id"], "scene-2")                               # a re-bind keeps the pane's key: the running harness still holds it
    assert rig.parent_headers()["Authorization"] == headers["Authorization"]
    unbound = rig.cockpit.create_session("claude", "Unbound pane", str(rig.cockpit.project_root), by="user")
    assert unbound["mcp_config_path"] is None and not unbound.get("pane_key_sha256")


def test_the_adapters_put_the_task_on_the_command_line_only_where_herdr_starts_the_harness(tmp_path):
    claude, codex, opencode = HN.get("claude"), HN.get("codex"), HN.get("opencode")
    pane = HN.PaneSpec(cwd=str(tmp_path), session_id="s-1")
    assert claude.launch(pane, task="Do the thing") == ["claude", "--session-id", "s-1", "Do the thing"]
    assert codex.launch(HN.PaneSpec(cwd=str(tmp_path)), task="Do the thing") == ["codex", "--no-alt-screen", "Do the thing"]
    assert opencode.launch(HN.PaneSpec(cwd=str(tmp_path)), task="Do the thing") == ["opencode", "--prompt", "Do the thing"]
    # herdr 0.9.3 starts Pi, Grok and Cursor's agent itself too (agent start --kind, its arguments quoted for the shell by herdr), and
    # each takes its first prompt as a positional argument (their installed --help): the task goes on their command line.
    assert HN.get("pi").launch(HN.PaneSpec(cwd=str(tmp_path), session_id="s-1"), task="Do the thing") == ["pi", "--session-id", "s-1", "Do the thing"]
    assert HN.get("grok").launch(HN.PaneSpec(cwd=str(tmp_path)), task="Do the thing") == ["grok", "Do the thing"]
    assert HN.get("cursor").launch(HN.PaneSpec(cwd=str(tmp_path)), task="Do the thing") == ["cursor-agent", "Do the thing"]
    with pytest.raises(ValueError, match="task"):                      # your Hermes: no top-level prompt argument (v0.21.5 --help)
        HN.get("hermes").launch(HN.PaneSpec(cwd=str(tmp_path)), task="Do the thing")

    class Shell(HN.Adapter):                                           # a harness herdr has no kind for is typed into a shell by
        id, label, binary, task_flag = "typed", "Typed", "typed-agent", ()   # pane run: never a model-written task
    with pytest.raises(ValueError, match="task"):
        Shell().launch(HN.PaneSpec(cwd=str(tmp_path)), task="Do the thing")
    assert claude.launch(pane) == ["claude", "--session-id", "s-1"]


def test_a_codex_worker_reads_its_token_from_its_pane_environment_never_its_command_line(tmp_path):
    codex = HN.get("codex")
    direct = HN.DirectServer("lampway", PANE_URL, {"X-Mixar-Session-Id": "swarm:sw1:worker-1"}, "LAMPWAY_WORKER_TOKEN", "tok-secret-value")
    pane = HN.PaneSpec(cwd=str(tmp_path), mcp_config_path=str(tmp_path / "p" / "mcp.toml"), desktop=False, direct=(direct,))
    w = codex.lampway_tools(pane)
    argv = codex.launch(pane, task="Do it")
    assert "tok-secret-value" not in json.dumps(argv) and w.env == {"LAMPWAY_WORKER_TOKEN": "tok-secret-value"}
    assert f'mcp_servers.lampway.url="{PANE_URL}"' in argv and 'mcp_servers.lampway.bearer_token_env_var="LAMPWAY_WORKER_TOKEN"' in argv
    assert not [a for a in argv if "mcp_servers.lampway.command" in a], "no desktop launcher for a worker"


def test_the_units_next_swarm_closes_the_previous_runs_ended_worker_panes_before_it_splits_new_ones(rig):
    """Spec A4, Q13 (built 2026-10-07; the captain: nothing hidden, finish it). A finished worker's pane stays readable until its
    unit's next swarm starts; then the swarm closes the previous run's ended worker panes of that unit, and only those, before it
    splits new ones, so the new run's first worker stands right of the main pane again. It says which panes it closed."""
    scratch = rig.cockpit.create_session("claude", "Someone else's pane", str(rig.cockpit.project_root), by="user")
    rig.bind_parent()
    first = rig.parent_json("swarm_start", {"tasks": tasks("boots", "belt")})
    old = wait_for(lambda: len(rig.worker_panes()) == 2 and rig.worker_panes())
    assert old and first.get("closed_panes") == []
    for rec in old:
        rig.worker_call(rec, "lampway_worker_done", {"summary": "made nothing"})
    rig.parent_json("swarm_collect", {"swarm_id": first["swarm_id"]})
    assert rig.herdr.closed() == [], "a finished worker's pane stays readable until the unit's next swarm"
    second = rig.parent_json("swarm_start", {"tasks": tasks("gloves")})
    assert sorted(rig.herdr.closed()) == sorted(r["pane_id"] for r in old)
    assert sorted(c["id"] for c in second["closed_panes"]) == sorted(r["id"] for r in old)
    new = wait_for(lambda: [r for r in rig.worker_panes() if r["swarm_binding"].startswith(f"swarm:{second['swarm_id']}:")])
    assert new, "the next swarm's worker pane never opened"
    assert rig.herdr.splits[new[0]["pane_id"]] == {"of": rig.parent["pane_id"], "direction": "right", "ratio": 0.6}, \
        "the next run starts a fresh column from the main pane"
    assert rig.parent["pane_id"] in rig.herdr.panes and scratch["pane_id"] in rig.herdr.panes, "never the main pane or a pane it did not start"
    ended = {r["id"]: r for r in rig.cockpit.list_sessions()}
    assert all(ended[r["id"]]["state"] == "ended" for r in old)


def test_a_worker_still_working_is_not_closed_by_its_units_next_swarm(rig):
    rig.bind_parent()
    first = rig.parent_json("swarm_start", {"tasks": tasks("boots", "belt")})
    old = wait_for(lambda: len(rig.worker_panes()) == 2 and rig.worker_panes())
    done = next(p for p in old if p["swarm_binding"].endswith(":worker-1"))
    busy = next(p for p in old if p["swarm_binding"].endswith(":worker-2"))
    rig.worker_call(done, "lampway_worker_done", {"summary": "made nothing"})
    assert wait_for(lambda: rig.status(first["swarm_id"])["worker-1"]["status"] == "staged")
    second = rig.parent_json("swarm_start", {"tasks": tasks("gloves")})
    assert rig.herdr.closed() == [done["pane_id"]] and [c["id"] for c in second["closed_panes"]] == [done["id"]]
    assert busy["pane_id"] in rig.herdr.panes, "a live worker's pane is never closed"
    new = wait_for(lambda: [r for r in rig.worker_panes() if r["swarm_binding"].startswith(f"swarm:{second['swarm_id']}:")])
    assert new and rig.herdr.splits[new[0]["pane_id"]]["of"] == busy["pane_id"], "the column goes on below the worker still working"


def test_a_swarm_tells_herdr_its_size_so_its_workers_share_the_column_evenly(rig):
    """Spec A4: the swarm's worker count reaches the layout; three workers keep 1/3, then 1/2, of what they split: a third each."""
    rig.bind_parent()
    sid = rig.parent_json("swarm_start", {"tasks": tasks("boots", "belt", "gloves")})["swarm_id"]
    panes = wait_for(lambda: len(rig.worker_panes()) == 3 and rig.worker_panes())
    assert panes, "one pane per task was never opened"
    splits = [rig.herdr.splits[p["pane_id"]] for p in sorted(panes, key=lambda p: int(p["pane_id"][1:]))]
    assert [s["direction"] for s in splits] == ["right", "down", "down"]
    assert [round(s["ratio"], 3) for s in splits] == [0.6, 0.333, 0.5], "the main agent keeps 60 %, the workers a third each"
    assert all(p["swarm_binding"].startswith(f"swarm:{sid}:") for p in panes)
