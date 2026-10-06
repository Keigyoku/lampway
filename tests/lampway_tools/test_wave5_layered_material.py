# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""layered_material (specs/mixar_docs/layered_material.md) in the real binary: the Client's layer-paint stack from the agent: init, inspect, add fill / paint / image / group layers (with an edge-detect mask),
procedural layers from the library, parameter edits and manifests. A thin, validated wrapper over the Client's own agent_tools: no new algorithm."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE_LM = '''
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
def lm(**kw):
    return call("layered_material", **kw)
def plate(name="Plate"):
    bpy.ops.mesh.primitive_cube_add(); ob = bpy.context.active_object; ob.name = name
    return ob
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, PRE_LM + body, **kw)


def one(r):
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_init_adds_a_fill_layer_with_an_edge_mask_and_inspect_returns_that_stack(tmp_path):
    d = one(go(tmp_path, '''
plate()
before = lm(action="inspect", object="Plate")
init = lm(action="init", object="Plate")
add = lm(action="add_layer", object="Plate", layer={"type": "fill", "name": "Edge wear", "blend": "MULTIPLY", "opacity": 0.6, "color": [0.8, 0.5, 0.2], "mask": {"type": "edge_detect"}})
stack = lm(action="inspect", object="Plate")
print("RESULT", json.dumps({"before": before, "init": init, "add": add, "stack": stack}))
'''))
    assert d["before"]["ok"] is False and "initialise a layer paint project first (lampway_layered_material action=init)" in d["before"]["error"]
    assert d["init"]["ok"] and d["add"]["ok"]
    layers = d["stack"]["stack"]
    edge = next(l for l in layers if l["name"] == "Edge wear")
    assert edge["type"] == "COLOR" and edge["blend"] == "MULTIPLY" and abs(edge["opacity"] - 0.6) < 1e-6 and edge["mask"]["type"] == "EDGE_DETECT" and len(layers) == 2
    assert {"index", "name", "type", "enabled", "blend", "opacity", "channels", "mask"} <= set(edge)


def test_invalid_blend_unknown_type_object_not_a_mesh_and_unknown_mask_are_refused_with_the_list(tmp_path):
    d = one(go(tmp_path, '''
plate(); lm(action="init", object="Plate")
bad_blend = lm(action="add_layer", object="Plate", layer={"type": "fill", "blend": "DIVIDE"})
bad_type = lm(action="add_layer", object="Plate", layer={"type": "plasma"})
bad_mask = lm(action="add_layer", object="Plate", layer={"type": "fill", "mask": {"type": "psychic"}})
bpy.ops.object.empty_add(); bpy.context.active_object.name = "Empty"
not_mesh = lm(action="init", object="Empty")
bad_action = lm(action="explode", object="Plate")
print("RESULT", json.dumps({"bb": bad_blend, "bt": bad_type, "bm": bad_mask, "nm": not_mesh, "ba": bad_action}))
'''))
    assert "MIX, ADD, MULTIPLY, SUBTRACT, SCREEN, OVERLAY" in d["bb"]["error"]
    assert "fill" in d["bt"]["error"] and "paint" in d["bt"]["error"] and "group" in d["bt"]["error"]
    assert "EDGE_DETECT" in d["bm"]["error"] and "not a mesh" in d["nm"]["error"] and "action is" in d["ba"]["error"]


def test_set_params_edits_the_named_layer_and_procedural_layers_come_from_the_library(tmp_path):
    d = one(go(tmp_path, '''
plate(); lm(action="init", object="Plate")
lm(action="add_layer", object="Plate", layer={"type": "fill", "name": "Tint layer", "color": [0.2, 0.3, 0.9]})
st = lm(action="inspect", object="Plate")["stack"]
idx = next(l["index"] for l in st if l["name"] == "Tint layer")
sp = lm(action="set_params", object="Plate", layer_index=idx, params={"opacity": 0.25, "enabled": False})
proc = lm(action="add_procedural", object="Plate", material="bronze_hammered", layer={"name": "Greaves"})
after = lm(action="inspect", object="Plate")["stack"]
print("RESULT", json.dumps({"sp": sp, "proc": proc, "after": after, "idx": idx}))
'''))
    assert d["sp"]["ok"]
    tint = next(l for l in d["after"] if l["name"] == "Tint layer")
    assert abs(tint["opacity"] - 0.25) < 1e-6 and tint["enabled"] is False
    assert d["proc"]["ok"] and len(d["after"]) == 3


def test_group_and_paint_layers_and_the_uv_projection_refusal(tmp_path):
    d = one(go(tmp_path, '''
ob = plate(); lm(action="init", object="Plate")
grp = lm(action="add_layer", object="Plate", layer={"type": "group", "name": "Trim"})
paint = lm(action="add_layer", object="Plate", layer={"type": "paint", "name": "Hand paint", "size": 256})
names = [l["name"] for l in lm(action="inspect", object="Plate")["stack"]]
while ob.data.uv_layers:
    ob.data.uv_layers.remove(ob.data.uv_layers[0])
nouv = lm(action="add_layer", object="Plate", layer={"type": "fill", "name": "Needs UV", "projection": "uv"})
tri = lm(action="add_layer", object="Plate", layer={"type": "fill", "name": "Tri", "projection": "triplanar"})
print("RESULT", json.dumps({"grp": grp, "paint": paint, "names": names, "nouv": nouv, "tri": tri}))
'''))
    assert d["grp"]["ok"] and d["paint"]["ok"] and "Trim" in d["names"] and "Hand paint" in d["names"]
    assert d["nouv"]["ok"] is False and "use projection triplanar or unwrap first" in d["nouv"]["error"]
    assert d["tri"]["ok"]


def test_apply_manifest_refuses_a_manifest_without_a_pbr_base_layer_naming_the_rule(tmp_path):
    d = one(go(tmp_path, '''
plate()
res = lm(action="apply_manifest", object="Plate", manifest={"layers": []})
res2 = lm(action="apply_manifest", object="Plate", manifest={"layers": [{"index": 0, "type": "FILL"}]})
print("RESULT", json.dumps({"a": res, "b": res2}))
'''))
    assert d["a"]["ok"] is False and "no layers" in d["a"]["error"] and d["b"]["ok"] is False and "index 0 layer must be type PBR" in d["b"]["error"]
