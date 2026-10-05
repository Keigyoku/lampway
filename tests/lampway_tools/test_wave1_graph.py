# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""workflow_graph (specs/wiki/workflow_graph.md): a typed DAG of Lampway tool calls with content-addressed cached outputs, partial reruns, named versions and
saved templates; a spend node is planned and priced, never run. Pure python: the executor is injected, the real one is api.call."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import workflow_graph as WG  # noqa: E402

TOOLS = ("mesh_prep", "uv_unwrap", "texture_gen", "export_piece")


class Exec:
    """A deterministic fake of api.call: the output depends on the tool and its arguments; records every execution."""

    def __init__(self):
        self.calls = []

    def __call__(self, tool, args):
        self.calls.append((tool, json.loads(json.dumps(args))))
        return {"ok": True, "object": f"{tool}({args.get('object', '')}|{args.get('quality', '')})"}


GRAPH = {"nodes": [{"id": "prep", "tool": "mesh_prep", "args": {"object": "{{piece}}"}},
                   {"id": "uv", "tool": "uv_unwrap", "args": {"object": "@prep.object", "quality": 1}, "after": ["prep"]},
                   {"id": "tex", "tool": "texture_gen", "args": {"object": "@uv.object"}, "after": ["uv"], "spend": True, "studio_action": "tripo.texture", "credits": 30},
                   {"id": "out", "tool": "export_piece", "args": {"object": "@uv.object"}, "after": ["uv"]}],
         "outputs": ["out"]}


@pytest.fixture
def g(tmp_path):
    ex = Exec()
    return WG.Graphs(tmp_path, ex, tools=TOOLS), ex


def test_a_plan_prices_the_spend_node_and_runs_nothing(g):
    graphs, ex = g
    graphs.define("boots", GRAPH, inputs={"piece": "Boots1"})
    plan = graphs.plan("boots")
    assert [n["node"] for n in plan["plan"]] == ["prep", "uv", "tex", "out"]
    assert plan["credits_planned"] == 30 and next(n for n in plan["plan"] if n["node"] == "tex")["credits_planned"] == 30 and ex.calls == []
    assert all(n["cached"] is False for n in plan["plan"])


def test_a_spend_node_is_never_run_and_what_depends_on_it_waits(g):
    graphs, ex = g
    graphs.define("boots", dict(GRAPH, nodes=GRAPH["nodes"] + [{"id": "after_tex", "tool": "export_piece", "args": {"object": "@tex.object"}, "after": ["tex"]}]),
                  inputs={"piece": "Boots1"})
    res = graphs.run("boots")
    assert res["states"]["tex"] == "planned_only" and "user confirms" in res["messages"]["tex"] and res["states"]["after_tex"] == "blocked"
    assert res["states"]["prep"] == res["states"]["uv"] == res["states"]["out"] == "done"
    assert "texture_gen" not in [t for t, _ in ex.calls]


def test_rerun_from_a_node_reuses_the_upstream_cache_and_a_changed_arg_invalidates_downstream_only(g):
    graphs, ex = g
    graphs.define("boots", GRAPH, inputs={"piece": "Boots1"})
    graphs.run("boots")
    assert [t for t, _ in ex.calls] == ["mesh_prep", "uv_unwrap", "export_piece"]
    ex.calls.clear()
    again = graphs.run("boots")
    assert ex.calls == [] and again["states"]["uv"] == "cached", "an identical run executes nothing"
    graphs.rerun("boots", from_node="uv")
    assert [t for t, _ in ex.calls] == ["uv_unwrap", "export_piece"], "upstream (mesh_prep) is reused; the node and what follows it re-execute"
    ex.calls.clear()
    changed = json.loads(json.dumps(GRAPH))
    changed["nodes"][1]["args"]["quality"] = 2
    graphs.define("boots", changed, inputs={"piece": "Boots1"})
    graphs.run("boots")
    assert [t for t, _ in ex.calls] == ["uv_unwrap", "export_piece"], "mesh_prep upstream of the change stays cached"


def test_a_cycle_an_unknown_tool_and_a_spend_node_without_its_action_are_refused(g):
    graphs, _ = g
    cyc = {"nodes": [{"id": "a", "tool": "mesh_prep", "args": {}, "after": ["b"]}, {"id": "b", "tool": "uv_unwrap", "args": {}, "after": ["a"]}]}
    with pytest.raises(WG.GraphError, match="the graph has a cycle through"):
        graphs.define("c", cyc)
    with pytest.raises(WG.GraphError, match="mesh_prep"):
        graphs.define("u", {"nodes": [{"id": "a", "tool": "no_such_tool", "args": {}}]})
    with pytest.raises(WG.GraphError, match="studio_action"):
        graphs.define("s", {"nodes": [{"id": "a", "tool": "texture_gen", "args": {}, "spend": True}]})
    with pytest.raises(WG.GraphError, match="unknown node"):
        graphs.define("d", {"nodes": [{"id": "a", "tool": "mesh_prep", "args": {}, "after": ["ghost"]}]})


def test_a_failing_node_stops_what_follows_it(g):
    graphs, ex = g
    bad = lambda tool, args: {"ok": False, "error": "no mesh"} if tool == "uv_unwrap" else Exec.__call__(ex, tool, args)  # noqa: E731
    graphs.executor = bad
    graphs.define("boots", GRAPH, inputs={"piece": "Boots1"})
    res = graphs.run("boots")
    assert res["states"]["uv"] == "failed" and "no mesh" in res["messages"]["uv"] and res["states"]["out"] == "blocked"


def test_versions_and_templates_roll_back_and_reuse(g):
    graphs, ex = g
    graphs.define("boots", GRAPH, inputs={"piece": "Boots1"})
    graphs.version("boots", "v1")
    changed = json.loads(json.dumps(GRAPH))
    changed["nodes"][1]["args"]["quality"] = 9
    graphs.define("boots", changed, inputs={"piece": "Boots1"})
    assert graphs.show("boots")["graph"]["nodes"][1]["args"]["quality"] == 9
    graphs.rollback("boots", "v1")
    assert graphs.show("boots")["graph"]["nodes"][1]["args"]["quality"] == 1 and graphs.show("boots")["versions"] == ["v1"]
    with pytest.raises(WG.GraphError, match="description"):
        graphs.template_save("boots", "uv-tex-export", description="")
    graphs.template_save("boots", "uv-tex-export", description="Smart UV, texture (planned), export")
    graphs.template_use("uv-tex-export", "helm", inputs={"piece": "Helm1"})
    assert graphs.show("helm")["graph"]["nodes"][0]["args"]["object"] == "Helm1"
    graphs.run("helm")
    assert ex.calls[0] == ("mesh_prep", {"object": "Helm1"})


def test_a_node_that_only_follows_another_re_executes_when_the_upstream_output_changes(g):
    """Its own arguments did not change: only the hash of what it follows can invalidate it (the falsifier: change an upstream arg and the cache must miss)."""
    graphs, ex = g
    two = {"nodes": [{"id": "a", "tool": "mesh_prep", "args": {"object": "P", "quality": 1}}, {"id": "b", "tool": "export_piece", "args": {"object": "FIXED"}, "after": ["a"]}]}
    graphs.define("g", two)
    graphs.run("g")
    ex.calls.clear()
    two["nodes"][0]["args"]["quality"] = 2
    graphs.define("g", two)
    graphs.run("g")
    assert [t for t, _ in ex.calls] == ["mesh_prep", "export_piece"]
