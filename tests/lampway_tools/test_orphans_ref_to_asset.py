# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""workflow_reference_to_asset (specs/mixar_docs/workflow_reference_to_asset.md): one piece through the existing tools in order, stopping at every gate, every
step a row in <piece>/decisions.jsonl and a report; a spend step stays blocked (only the user confirms), resume skips what is done, and each piece keeps its own
log. REAL binary, a cube piece."""

import json
from pathlib import Path

from features_support import run


def _rows(root, piece):
    p = Path(root) / piece / "decisions.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_the_plan_names_each_steps_tool_cost_and_gate_and_auto_is_no_spend_gate(tmp_path):
    r = run(tmp_path, '''
plan = call("workflow_reference_to_asset", piece="Crate", route="existing", existing_object="crate", steps=["prep", "retopo", "uv", "texture", "export"])
auto = call("workflow_reference_to_asset", piece="Crate", route="existing", existing_object="crate", gates={"spend": "auto"})
noobj = call("workflow_reference_to_asset", piece="Crate", route="existing")
print("RESULT", json.dumps({"plan": plan, "auto": auto, "noobj": noobj}))
''')
    assert r.rc == 0, r.out[-2000:]
    o = r.results[0]
    steps = {s["step"]: s for s in o["plan"]["plan"]}
    assert o["plan"]["ok"] is True and o["plan"]["run"] is False and steps["prep"]["tool"] == "lampway_mesh_prep" and steps["prep"]["cost"] == "local", o["plan"]
    assert steps["texture"]["cost"] == "spend" and steps["texture"]["gate"] == "captain" and all(s["status"] == "pending" for s in steps.values()), steps
    assert o["auto"]["ok"] is False and "only the user" in o["auto"]["error"], o["auto"]
    assert o["noobj"]["ok"] is False and "existing_object" in o["noobj"]["error"], o["noobj"]


def test_a_cube_runs_prep_retopo_uv_and_each_step_leaves_a_decision_row_and_a_spend_step_stays_blocked(tmp_path):
    r = run(tmp_path, '''
sphere("crate", 0.5, subdiv=4)                     # 1280 faces: the retopo target (2000) must be within 3x the source (canon INV-12.5)
a = call("workflow_reference_to_asset", piece="Crate", route="existing", existing_object="crate", steps=["prep", "retopo", "uv", "texture"], run=True)
again = call("workflow_reference_to_asset", piece="Crate", route="existing", existing_object="crate", steps=["prep", "retopo", "uv", "texture"], run=True, resume=True)
sphere("barrel", 0.4, subdiv=3, loc=(3, 0, 0))
b = call("workflow_reference_to_asset", piece="Barrel", route="existing", existing_object="barrel", steps=["prep"], run=True)
print("RESULT", json.dumps({"a": a, "again": again, "b": b, "objects": sorted(o.name for o in bpy.data.objects)}))
''', timeout=900)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    st = {s["step"]: s for s in o["a"]["plan"]}
    assert st["prep"]["status"] == "done" and st["retopo"]["status"] == "done" and st["uv"]["status"] == "done", st
    assert st["texture"]["status"] == "blocked" and "user" in st["texture"]["reason"], st["texture"]
    assert st["uv"]["object"] and st["uv"]["object"] in o["objects"] and "crate" in o["objects"], "every step works on a copy; the source stays"
    rows = _rows(tmp_path, "Crate")
    assert [x["step"] for x in rows if x["kind"] == "measurement"] == ["prep", "retopo", "uv"], rows
    assert any(x["step"] == "texture" and x["kind"] == "refusal" for x in rows), rows
    assert all({"id", "at", "step", "kind", "by", "detail"} <= set(x) for x in rows)
    again = {s["step"]: s for s in o["again"]["plan"]}
    assert again["prep"]["status"] == "done" and again["prep"].get("skipped") is True, again
    assert [x["step"] for x in _rows(tmp_path, "Barrel")] == ["prep"], "each piece keeps its own log"
    assert Path(o["a"]["report"]).exists()
