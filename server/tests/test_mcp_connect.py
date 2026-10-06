"""mcp_connect additions (specs/mixar_docs/mcp_connect.md): tools/list says which tools spend (none offered here do) and never offers a confirm; lampway_credit_balance reads the local ledger and nothing
secret; every call has an id whose recorded outcome can be read back with lampway_call_status after the external app's request timed out."""
import asyncio
import json

import pytest

from lampway_server import mcp as M
from lampway_server.ledger import Ledger

from .test_mcp import _rpc, signed  # noqa: F401


def test_tools_list_marks_spend_and_never_offers_a_confirm(signed):
    tools = _rpc(signed, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"lampway_credit_balance", "lampway_call_status"} <= names
    assert all(t["_meta"]["spend"] is False for t in tools) and not [n for n in names if "confirm" in n or n.startswith("studio_")]
    assert all("confirm" in t["_meta"]["spend_policy"] for t in tools)


class FakeHub:
    def __init__(self):
        self.sockets = {"i1": object()}


class FakeAgent:
    def __init__(self):
        self.release = asyncio.Event()
        self.started = asyncio.Event()

    async def _blender_script(self, socket, **kw):
        self.started.set()
        await self.release.wait()
        return {"success": True, "output": "the report", "created_objects": []}


def run(coro):
    return asyncio.run(coro)


def test_call_status_returns_the_recorded_outcome_after_the_external_apps_request_died(tmp_path):
    async def go():
        agent = FakeAgent()
        server = M.McpServer(FakeHub(), agent)
        msg = {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "run_blender_python", "arguments": {"script": "print(1)"}}}
        task = asyncio.create_task(server.handle(msg, "i1", "s1"))
        await asyncio.wait_for(agent.started.wait(), 5)
        call_id = next(iter(server.journal))
        running = await server.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "lampway_call_status", "arguments": {"call_id": call_id}}}, "i1", "s1")
        task.cancel()                                                         # the external app timed out and went away
        with pytest.raises(asyncio.CancelledError):
            await task
        agent.release.set()
        for _ in range(50):
            await asyncio.sleep(0.01)
            if server.journal[call_id]["state"] == "complete":
                break
        done = await server.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "lampway_call_status", "arguments": {"call_id": call_id}}}, "i1", "s1")
        unknown = await server.handle({"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "lampway_call_status", "arguments": {"call_id": "nope"}}}, "i1", "s1")
        return running, done, unknown, call_id
    running, done, unknown, call_id = run(go())
    assert json.loads(running["result"]["content"][0]["text"])["state"] == "running"
    d = json.loads(done["result"]["content"][0]["text"])
    assert d["state"] == "complete" and "the report" in d["text"] and d["is_error"] is False and d["call_id"] == call_id
    assert unknown["result"]["isError"] is True and "no call" in unknown["result"]["content"][0]["text"]


def test_every_call_result_names_its_call_id(tmp_path):
    async def go():
        agent = FakeAgent()
        agent.release.set()
        server = M.McpServer(FakeHub(), agent)
        r = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "run_blender_python", "arguments": {"script": "print(1)"}}}, "i1", "s1")
        return r, list(server.journal)
    r, ids = run(go())
    assert r["result"]["_meta"]["call_id"] == ids[0] and ids[0] in r["result"]["content"][0]["text"]


def test_credit_balance_reads_the_ledger_and_nothing_secret(tmp_path):
    ledger = Ledger(tmp_path / "runs.jsonl")
    ledger.record_job({"job_key": "a" * 16, "provider": "openrouter", "model": "m", "state": "downloaded", "price": {"amount": 0.12, "unit": "USD"}, "output_hashes": [], "origin": "user"})
    ledger.record_job({"job_key": "b" * 16, "provider": "openrouter", "model": "m", "state": "provider_error", "price": {"amount": 0.05, "unit": "USD"}, "output_hashes": [], "origin": "user"})
    ledger.record_job({"job_key": "c" * 16, "provider": "higgsfield", "model": "m", "state": "downloaded", "price": {"amount": 13.5, "unit": "credits"}, "output_hashes": [], "origin": "user"})

    async def go():
        server = M.McpServer(FakeHub(), FakeAgent(), ledger=ledger, caps=lambda: {"video_job_cap_usd": 5.0})
        return await server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "lampway_credit_balance", "arguments": {}}}, "i1", "s1")
    r = run(go())
    out = json.loads(r["result"]["content"][0]["text"])
    by = {(x["provider"], x["unit"]): x for x in out["spend_by_provider"]}
    assert by[("openrouter", "USD")]["amount"] == pytest.approx(0.17) and by[("openrouter", "USD")]["jobs"] == 2 and by[("higgsfield", "credits")]["amount"] == 13.5
    assert out["caps"] == {"video_job_cap_usd": 5.0} and "studio" in out["note"]
    blob = json.dumps(out).lower()
    assert not any(w in blob for w in ("token", "secret", "authorization", "password", "api_key"))
