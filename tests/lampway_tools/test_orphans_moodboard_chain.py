# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The captain's moodboard prompts as the reference-to-asset chain in workflow_graph (O24): P1 anatomy sheet -> P2 armor adaptation -> P3 fit-check ->
P4 breakdown -> P7 cutout, then per piece P5 multiview, P6 single views (the matched four) and P8 the 3x2 turnaround; each step's image feeds the next
step's Image A or Image B. Every generation is a spend node: plan and run never generate, and ONE confirm generates ONE node (the user's word per image);
a confirmed output is keyed by the node's inputs, so a changed upstream needs a new confirm."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import workflow_graph as WG  # noqa: E402
from mixar.modules.lampway_tools.features import moodboard_chain as MC  # noqa: E402

BUILTIN = Path(__file__).resolve().parents[2] / "server/lampway_server/prompts/builtin"


class Exec:
    def __init__(self):
        self.calls = []

    def __call__(self, tool, args):
        self.calls.append((tool, json.loads(json.dumps(args))))
        return {"ok": True, "image": f"img/{args['template']}-{len(self.calls)}.png"}


@pytest.fixture
def g(tmp_path):
    ex = Exec()
    return WG.Graphs(tmp_path, executor=ex, tools=("prompt_image",)), ex


def chain(g, pieces=("helmet", "left greave")):
    graph = MC.graph(pieces)
    g.define("set", graph, {"body_refs": ["body/front.png", "body/left.png"], "armor_design": "concept/armor.png"})
    return graph


def test_the_chain_is_the_captains_order_with_each_image_feeding_the_next(g):
    graph = chain(g[0])
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert [n["id"] for n in graph["nodes"]][:5] == ["anatomy", "adaptation", "fit_check", "breakdown", "cutout"]
    tmpl = {n["id"]: n["args"]["template"] for n in graph["nodes"]}
    assert [tmpl[i] for i in ("anatomy", "adaptation", "fit_check", "breakdown", "cutout")] == [
        "moodboard-anatomy-sheet", "moodboard-armor-adaptation", "moodboard-fit-check", "moodboard-armor-breakdown", "moodboard-cutout-sheet"]
    refs = lambda i: nodes[i]["args"]["references"]
    assert refs("anatomy") == {"image_references": "{{body_refs}}"} and refs("adaptation") == {"character_body": "@anatomy.image", "design_plate": "{{armor_design}}"}
    assert refs("fit_check") == {"character_body": "@anatomy.image", "design_plate": "@adaptation.image"}
    assert refs("breakdown") == {"character_body": "@anatomy.image", "design_plate": "@fit_check.image"}
    assert refs("cutout") == {"character_body": "@anatomy.image", "design_plate": "@fit_check.image"} and nodes["cutout"]["after"] == ["breakdown", "fit_check"]
    h = MC.slug("left greave")
    assert refs(f"multiview_{h}") == {"character_body": "@anatomy.image", "design_plate": "@breakdown.image"} and nodes[f"multiview_{h}"]["after"][0] == "cutout"
    views = [n for n in graph["nodes"] if n["id"].startswith(f"view_{h}_")]
    assert len(views) == 4 and all(refs(v["id"])["design_plate"] == f"@multiview_{h}.image" for v in views)
    assert [v["args"]["variables"]["view"].split()[0] for v in views] == ["FRONT", "LEFT", "BACK", "RIGHT"]
    assert refs(f"turnaround_{h}") == {"reference_image": f"@multiview_{h}.image"} and nodes[f"turnaround_{h}"]["args"]["variables"] == {"asset_name": "left greave"}
    assert all(n["spend"] and n["studio_action"] == "image_gen" and n["tool"] == "prompt_image" for n in graph["nodes"])
    assert len(graph["nodes"]) == 5 + 2 * 6
    for t in set(tmpl.values()):
        assert (BUILTIN / f"{t}@1.0.0.json").exists(), t


def test_plan_and_run_generate_nothing_and_one_confirm_generates_one_node(g):
    graphs, ex = g
    chain(graphs)
    plan = graphs.plan("set")
    assert len(plan["plan"]) == 17 and ex.calls == []
    run = graphs.run("set")
    assert ex.calls == [] and run["states"]["anatomy"] == "planned_only" and run["states"]["adaptation"] == "blocked"
    c = graphs.confirm("set", "anatomy")
    assert c["state"] == "confirmed" and len(ex.calls) == 1 and ex.calls[0][1]["references"] == {"image_references": ["body/front.png", "body/left.png"]}
    run = graphs.run("set")
    assert run["states"]["anatomy"] == "confirmed" and run["states"]["adaptation"] == "planned_only" and len(ex.calls) == 1
    graphs.confirm("set", "adaptation")
    assert ex.calls[-1][1]["references"] == {"character_body": "img/moodboard-anatomy-sheet-1.png", "design_plate": "concept/armor.png"}
    with pytest.raises(WG.GraphError, match="waiting on"):
        graphs.confirm("set", "breakdown")
    with pytest.raises(WG.GraphError, match="not a spend node"):
        graphs.confirm("set", "nope")


def test_a_confirmation_belongs_to_its_inputs(g):
    graphs, ex = g
    chain(graphs)
    graphs.confirm("set", "anatomy")
    graphs.define("set", MC.graph(("helmet", "left greave")), {"body_refs": ["body/front.png"], "armor_design": "concept/armor.png"})
    assert graphs.run("set")["states"]["anatomy"] == "planned_only", "new body references: the old image is not this node's output"


FAKES = '''
from mixar.modules.lampway_tools import orphans_api as OA
import io
from PIL import Image as _I
BUILTIN = BUILTIN_DIR
sent, rows = [], []
def render(template, variables=None, model=""):
    t = json.load(open(os.path.join(BUILTIN, template + "@1.0.0.json")))
    ins = sorted(t["inputs"].items(), key=lambda kv: kv[1].get("order", 99))
    return {"template": template + "@1.0.0", "prompt": "rendered " + template + " " + json.dumps(variables or {}),
            "inputs_required": [{"role": r, "required": bool(s.get("required")), "description": s["description"]} for r, s in ins], "params": {}}
def gen(prompt, reference_png, count=1, extra_references=None, params_extra=None):
    sent.append({"prompt": prompt, "refs": 1 + len(extra_references or []) if reference_png else 0})
    b = io.BytesIO(); _I.new("RGB", (8, 8), (len(sent) * 20, 0, 0)).save(b, "PNG"); return [b.getvalue()]
OA._render_prompt, OA._generate_image, OA._record_ledger = render, gen, lambda row: rows.append(row) or {"recorded": True}
for f in ("body/front.png", "body/left.png", "concept/armor.png"):
    os.makedirs(os.path.join(root, os.path.dirname(f)), exist_ok=True)
    _I.new("RGB", (8, 8)).save(os.path.join(root, f))
'''


def test_the_chain_answers_through_api_and_a_confirm_generates_one_image_with_its_references_in_order(tmp_path):
    from features_support import run
    r = run(tmp_path, FAKES.replace("BUILTIN_DIR", repr(str(BUILTIN))) + '''
plan = call("workflow_reference_to_asset", piece="GreekSet", route="moodboard", reference="concept/armor.png", body_refs=["body/front.png", "body/left.png"],
            pieces=["helmet", "left greave"])
dry = call("prompt_image", template="moodboard-fit-check", references={"character_body": "body/front.png", "design_plate": "concept/armor.png"})
missing = call("prompt_image", template="moodboard-fit-check", references={"character_body": "body/front.png"})
n_dry = len(sent)
c1 = call("workflow_graph", action="confirm", name="GreekSet", from_node="anatomy")
c2 = call("workflow_graph", action="confirm", name="GreekSet", from_node="adaptation")
early = call("workflow_graph", action="confirm", name="GreekSet", from_node="cutout")
state = call("workflow_graph", action="run", name="GreekSet")
print("RESULT", json.dumps({"plan": plan, "dry": dry, "missing": missing, "n_dry": n_dry, "c1": c1, "c2": c2, "early": early, "states": state["states"],
                            "sent": sent, "rows": len(rows)}))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["plan"]["ok"] and o["plan"]["route"] == "moodboard" and len(o["plan"]["plan"]) == 17 and o["n_dry"] == 0, o["plan"]
    assert o["dry"]["ok"] and o["dry"]["live"] is False and [x["role"] for x in o["dry"]["references"]] == ["character_body", "design_plate"], o["dry"]
    assert o["missing"]["ok"] is False and "design_plate" in o["missing"]["error"], o["missing"]
    assert o["c1"]["ok"] and o["c1"]["state"] == "confirmed" and Path(o["c1"]["output"]["image"]).exists(), o["c1"]
    assert o["sent"][0]["refs"] == 2 and o["sent"][1]["refs"] == 2 and len(o["sent"]) == 2 and o["rows"] == 2, o["sent"]
    assert o["early"]["ok"] is False and "waiting on" in o["early"]["error"], o["early"]
    assert o["states"]["anatomy"] == "confirmed" and o["states"]["adaptation"] == "confirmed" and o["states"]["fit_check"] == "planned_only", o["states"]
