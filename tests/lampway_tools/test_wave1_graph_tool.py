# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""workflow_graph as an api tool inside the app: nodes are real Lampway tools run through api.call, with an upstream output feeding a downstream argument."""

from features_support import run


def test_a_graph_of_real_tools_runs_feeds_outputs_forward_and_caches(tmp_path):
    r = run(tmp_path, '''
boxes("helm", [((0, 0, 0), (1, 1, 1))])
g = {"nodes": [{"id": "prep", "tool": "mesh_prep", "args": {"object": "{{piece}}"}},
               {"id": "acc", "tool": "asset_acceptance", "args": {"object": "@prep.object", "reference": "{{piece}}"}, "after": ["prep"]},
               {"id": "tex", "tool": "texture_gen", "args": {"object": "@prep.object"}, "after": ["prep"], "spend": True, "studio_action": "tripo.texture", "credits": 30}],
     "outputs": ["acc"]}
d = call("workflow_graph", action="define", name="helm", graph=g, inputs={"piece": "helm"})
plan = call("workflow_graph", action="plan", name="helm")
first = call("workflow_graph", action="run", name="helm")
second = call("workflow_graph", action="run", name="helm")
bad = call("workflow_graph", action="define", name="bad", graph={"nodes": [{"id": "a", "tool": "nope", "args": {}}]})
print("RESULT", json.dumps({"d": d, "plan": plan, "first": first, "second": second, "bad": bad, "objs": sorted(o.name for o in bpy.data.objects)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["d"]["ok"] is True and o["plan"]["credits_planned"] == 30
    assert o["first"]["states"] == {"prep": "done", "acc": "done", "tex": "planned_only"} and o["first"]["outputs"]["acc"]["accepted"] is not None
    assert o["second"]["states"]["prep"] == "cached" and o["second"]["states"]["acc"] == "cached" and o["objs"].count("helm_prep") == 1, "the cached run did not branch again"
    assert o["bad"]["ok"] is False and "nope" in o["bad"]["error"]
