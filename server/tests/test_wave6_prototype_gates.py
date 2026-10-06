"""prototype_gates (specs/wiki/prototype_gates.md): "playable core before asset polish" as recorded gates. Core, Look, Feedback, Export in order, each with a
generation allowance; a generation spend is refused until every earlier pass has passed, each allowed spend uses one generation of its pass, and an agent
cannot pass a captain-owned gate. State lives on the experiment ledger (kind 'gate')."""

import asyncio
import json

import pytest

from lampway_server import prototype_gates as PG
from lampway_server.ledger import Ledger

PASSES = [{"name": "Core", "generation_allowance": 0, "gate": "Win/fail/restart and three edge cases work", "owner": "agent"},
          {"name": "Look", "generation_allowance": 2, "gate": "Scale/collision/readability pass", "owner": "captain"},
          {"name": "Feedback", "generation_allowance": 1, "gate": "State readable at gameplay camera", "owner": "captain"},
          {"name": "Export", "generation_allowance": 0, "gate": "Same mechanic works in target build", "owner": "captain"}]


@pytest.fixture
def root(tmp_path):
    PG.define(str(tmp_path), "arena", PASSES)
    return str(tmp_path)


def test_look_spend_refused_before_core_gate(root):
    with pytest.raises(PG.GateError, match="Core has not passed: Win/fail/restart and three edge cases work"):
        PG.may_spend(root, "arena", {"kind": "asset", "credits": 100, "pass": "Look"})
    PG.record_gate(root, "arena", {"pass": "Core", "result": "pass", "evidence": "builds/core_0412.zip: all three edge cases", "by": "agent"})
    out = PG.may_spend(root, "arena", {"kind": "asset", "credits": 100, "pass": "Look"})
    assert out["allowed"] is True and out["remaining_allowance"] == 1 and out["pass"] == "Look"


def test_allowance_decrements_and_runs_out(root):
    PG.record_gate(root, "arena", {"pass": "Core", "result": "pass", "evidence": "core build", "by": "agent"})
    a = PG.may_spend(root, "arena", {"kind": "asset", "credits": 100})
    b = PG.may_spend(root, "arena", {"kind": "material", "credits": 30})
    assert (a["pass"], a["remaining_allowance"], b["remaining_allowance"]) == ("Look", 1, 0)
    with pytest.raises(PG.GateError, match="the Look allowance of 2 generations is used"):
        PG.may_spend(root, "arena", {"kind": "asset", "credits": 100})
    with pytest.raises(PG.GateError, match="Core allows no generation"):
        PG.may_spend(root, "arena", {"kind": "asset", "credits": 1, "pass": "Core"})


def test_agent_cannot_pass_a_captain_gate(root):
    PG.record_gate(root, "arena", {"pass": "Core", "result": "pass", "evidence": "core build", "by": "agent"})
    with pytest.raises(PG.GateError, match="captain"):
        PG.record_gate(root, "arena", {"pass": "Look", "result": "pass", "by": "agent"})
    proposed = PG.record_gate(root, "arena", {"pass": "Look", "result": "pass", "evidence": "shots/look_review.png", "by": "agent"})
    assert proposed["state"] == "proposed"
    with pytest.raises(PG.GateError, match="Look has not passed"):
        PG.may_spend(root, "arena", {"kind": "vfx", "credits": 10, "pass": "Feedback"})
    PG.record_gate(root, "arena", {"pass": "Look", "result": "pass", "evidence": "reviewed", "by": "captain"})
    assert PG.may_spend(root, "arena", {"kind": "vfx", "credits": 10, "pass": "Feedback"})["allowed"] is True


def test_gates_are_ledger_rows_and_status_reads_them_back(root, tmp_path):
    PG.record_gate(root, "arena", {"pass": "Core", "result": "fail", "evidence": "restart breaks", "by": "agent"})
    st = PG.status(root, "arena")
    assert st["passes"][0]["state"] == "failed" and st["current"] == "Core"
    rows = Ledger(tmp_path / "ledger" / "runs.jsonl").rows("gate")
    assert [r["event"] for r in rows] == ["define", "record_gate"] and rows[1]["result"] == "fail"


def test_passes_out_of_order_or_unknown_are_refused(tmp_path):
    with pytest.raises(PG.GateError, match="Core, Look, Feedback, Export"):
        PG.define(str(tmp_path), "x", [{"name": "Look", "generation_allowance": 1, "gate": "g"}, {"name": "Core", "generation_allowance": 0, "gate": "g"}])
    with pytest.raises(PG.GateError, match="define the passes first"):
        PG.may_spend(str(tmp_path), "nothing", {"kind": "asset", "credits": 1})


def test_the_agent_tool_records_as_the_agent(tmp_path, monkeypatch):
    from lampway_server.agent.providers.base import ToolCall
    from lampway_server.agent.turns import AgentHub
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    hub = AgentHub.__new__(AgentHub)
    run = lambda args: asyncio.run(hub._run_tool(None, None, None, ToolCall("c", "lampway_prototype_gates", args)))  # noqa: E731
    out, err = run({"action": "define", "project": "arena", "passes": PASSES})
    assert not err
    run({"action": "record_gate", "project": "arena", "gate_result": {"pass": "Core", "result": "pass", "evidence": "core", "by": "agent"}})
    out, err = run({"action": "record_gate", "project": "arena", "gate_result": {"pass": "Look", "result": "pass", "evidence": "x", "by": "captain"}})
    assert not err and json.loads(out)["state"] == "proposed"                     # the tool records as the agent whatever `by` claims
