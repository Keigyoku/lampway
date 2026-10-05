# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""qa_propose: proven rules first, the model second. The rules (meshqa/rules.py) decide what the descriptors make unambiguous and name
the rule in every reason; what they cannot decide is returned as ``ambiguous`` for the model slot, which sees COMPACT descriptors in
small batches (never ``segments_m``). Tripo smart meshes are genuinely many open shells (the Boots original: 8,203 boundary edges),
so most rims are KEEP and a flood guard stops the see-through rule from marking everything HOLE. REAL binary."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_agent_execution import dirs  # noqa: E402,F401
from test_qa_dogfood import run as run_scene  # noqa: E402

RULES = '''
import json
from mixar.modules.lampway_tools.meshqa import rules as R
def loop(i, per=0.3, hit="surface", backfacing=False, depth=12.0):
    return {"id": f"L{i:03d}", "kind": "open_loop", "perimeter_m": per, "edges": 40, "extent_m": [0.1, 0.1, 0.02], "side": "front",
            "bordering_parts_pct": {"plate": 100.0}, "bordering_classes": ["rigid-metal"], "seen_from_pct": {"front": 90.0},
            "behind": {"hit": hit, "backfacing": backfacing, "depth_mm": depth} if hit != "nothing" else {"hit": "nothing"},
            "segments_m": [[[0, 0, 0], [0.01, 0, 0]]] * 5000, "facing": [0, -1, 0], "centroid_m": [0, 0, 0]}
def shell(i, gap, tris=40):
    return {"id": f"S{i:03d}", "kind": "loose_shell", "tris": tris, "gap_to_nearest_mm": gap, "extent_m": [0.02, 0.02, 0.02], "side": "back",
            "parts_pct": {"plate": 100.0}, "seen_from_pct": {"back": 50.0}, "facing": [0, 1, 0], "centroid_m": [0, 0, 0]}
P = R.Params(float_mm=3.0)
'''


def test_each_rule_decides_what_the_descriptor_makes_clear_and_names_itself():
    r = run_script(RULES + '''
rows = {
 "floating": R.classify(shell(0, 12.0), P), "no_surface_near": R.classify(shell(1, None), P), "near_threshold": R.classify(shell(2, 4.0), P),
 "see_through": R.classify(loop(0, hit="nothing"), P), "rim": R.classify(loop(1), P), "backfacing": R.classify(loop(2, backfacing=True), P),
 "large_rim": R.classify(loop(3, per=1.4), P)}
print("RESULT", json.dumps({k: list(v) for k, v in rows.items()}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["floating"][:2] == ["delete", "float"] and "12.0 mm" in o["floating"][2] and o["floating"][2].startswith("rule float:")
    assert o["no_surface_near"][:2] == ["delete", "float"]
    assert o["near_threshold"][0] is None and o["near_threshold"][1] == "float_threshold"
    assert o["see_through"][:2] == ["hole", "see_through"] and o["see_through"][2].startswith("rule see_through:")
    assert o["rim"][:2] == ["keep", "rim"] and "12.0 mm" in o["rim"][2]
    assert o["backfacing"][0] is None and o["backfacing"][1] == "backfacing_hit"
    assert o["large_rim"][0] is None and o["large_rim"][1] == "large_rim"


def test_a_flood_of_see_through_loops_is_capped_to_the_largest_and_the_rest_are_left_to_the_model():
    r = run_script(RULES + '''
cands = [loop(i, per=0.2 + i * 0.01, hit="nothing") for i in range(30)] + [loop(100 + i) for i in range(70)]
out = R.propose(cands, P)
holes = sorted(v["id"] for v in out["verdicts"] if v["verdict"] == "hole")
print("RESULT", json.dumps({"holes": holes, "keep": sum(v["verdict"] == "keep" for v in out["verdicts"]), "ambiguous": out["ambiguous"],
                            "flood": [v["reason"] for v in out["verdicts"] if v["id"] == "L029"][:1], "ambiguous_why": out["ambiguous_why"]}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert len(o["holes"]) == 15 and "L029" in o["holes"] and "L000" not in o["holes"], "the largest 15% of 100 loops stay HOLE"
    assert o["keep"] == 70 and len(o["ambiguous"]) == 15 and set(o["ambiguous_why"].values()) == {"flood_guard"}


def test_a_compact_descriptor_never_carries_the_segments():
    r = run_script(RULES + '''
c = R.compact(loop(0))
print("RESULT", json.dumps({"keys": sorted(c), "size": len(json.dumps(c))}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert "segments_m" not in o["keys"] and o["size"] < 900


def test_qa_propose_applies_the_rules_returns_the_ambiguous_and_the_models_judgement_never_loses_to_a_rerun(tmp_path):
    r = run_scene(tmp_path, '''
call("qa_setup", object="piece", piece="a", offset=[0, 0, 0.5], **common)
call("qa_candidates", piece="a", draw=True)
rules = call("qa_propose", piece="a")
rd = work + "/a/rulings"
rows = {x["id"]: x for x in json.load(open(rd + "/a_proposals.json"))}
batch = call("qa_descriptors", piece="a", ambiguous_only=True, limit=5)
model = call("qa_propose", piece="a", proposals={"L000": {"verdict": "keep", "reason": "inside of the open sphere"}}, by="agent", rules=False)
again = call("qa_propose", piece="a")
rows2 = {x["id"]: x for x in json.load(open(rd + "/a_proposals.json"))}
hidden = {n: bpy.data.objects[n].hide_viewport for n in ("a_L000", "a_S000")}
print("RESULT", json.dumps({"rules": rules, "rows": rows, "batch": batch, "model": model, "rows2": rows2, "hidden": hidden,
    "decisions": os.path.exists(rd + "/decisions.jsonl")}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["rules"]["ok"] and o["rules"]["applied"] == {"delete": 1, "hole": 0, "mislabel": 0, "keep": 0} and o["rules"]["ambiguous"] == ["L000"]
    s = o["rows"]["S000"]
    assert s["verdict"] == "delete" and s["by"] == "rule:float" and s["reason"].startswith("rule float:") and s["kind"] == "loose_shell"
    assert "L000" not in o["rows"], "an ambiguous candidate gets no rule verdict"
    assert o["batch"]["ok"] and [d["id"] for d in o["batch"]["descriptors"]] == ["L000"] and all("segments_m" not in d for d in o["batch"]["descriptors"])
    assert o["rows2"]["L000"]["by"] == "agent" and o["rows2"]["L000"]["verdict"] == "keep", "a rules re-run keeps the model's row"
    assert o["rows2"]["S000"]["by"] == "rule:float"
    assert o["hidden"] == {"a_L000": True, "a_S000": False}, "KEEP markers are hidden, the others shown"
    assert o["decisions"] is False
