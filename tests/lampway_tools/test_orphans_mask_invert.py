# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""layered_material mask invert (specs/mixar_docs/layered_material.md: "Mask modifiers Invert, Ramp, Curve"): the paint package's own INVERT mask modifier
(the helper its wm.m_new_mask_modifier operator calls), added on a new layer's mask or toggled on an existing one. REAL binary."""

import json

from features_support import run

PRE = '''
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
def lm(**kw):
    return call("layered_material", **kw)
bpy.ops.mesh.primitive_cube_add(); ob = bpy.context.active_object; ob.name = "Plate"
lm(action="init", object="Plate")
from mixar.modules.paint.core.agent_tools._common import _find_mpaint_node
from mixar.modules.paint.core.subtree.get_subtree import get_mask_tree
def invert_node(index):
    mp = _find_mpaint_node(ob).node_tree.mp
    mask = mp.layers[index].masks[0]
    mods = [m for m in mask.modifiers if m.type == "INVERT"]
    if not mods:
        return None
    n = get_mask_tree(mask).nodes.get(mods[0].invert)
    return {"enable": bool(mods[0].enable), "factor": n.inputs[0].default_value, "mute": n.mute, "linked": any(s.is_linked for s in n.outputs)}
'''


def _go(tmp_path, body):
    r = run(tmp_path, PRE + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_a_new_layer_mask_can_be_inverted(tmp_path):
    res = _go(tmp_path, '''
add = lm(action="add_layer", object="Plate", layer={"type": "fill", "name": "Wear", "mask": {"type": "edge_detect", "invert": True}})
print("RESULT", json.dumps({"add": add, "node": invert_node(add["added_index"]) if add.get("ok") else None}))
''')
    add = res["add"]
    assert add["ok"] is True, add
    row = next(l for l in add["stack"] if l["name"] == "Wear")
    assert row["mask"]["invert"] is True, row
    assert res["node"] == {"enable": True, "factor": 1.0, "mute": False, "linked": True}, res["node"]


def test_mask_invert_toggles_an_existing_mask_and_refuses_a_layer_without_one(tmp_path):
    res = _go(tmp_path, '''
add = lm(action="add_layer", object="Plate", layer={"type": "fill", "name": "Wear", "mask": {"type": "edge_detect"}})
i = add["added_index"]
before = invert_node(i)
on = lm(action="mask_invert", object="Plate", layer_index=i, params={"invert": True})
n_on = invert_node(i)
off = lm(action="mask_invert", object="Plate", layer_index=i, params={"invert": False})
n_off = invert_node(i)
again = lm(action="mask_invert", object="Plate", layer_index=i, params={"invert": True})
mp = _find_mpaint_node(ob).node_tree.mp
count = len([m for m in mp.layers[i].masks[0].modifiers if m.type == "INVERT"])
base = next(l["index"] for l in on["stack"] if l["name"] != "Wear")            # the init layer: no mask
bare = lm(action="mask_invert", object="Plate", layer_index=base, params={"invert": True})
print("RESULT", json.dumps({"before": before, "on": on, "n_on": n_on, "off": off, "n_off": n_off, "count": count, "bare": bare}))
''')
    assert res["before"] is None and res["on"]["ok"] is True and res["n_on"]["enable"] is True, res
    assert res["n_off"]["enable"] is False and res["n_off"]["mute"] is True, res["n_off"]
    assert res["count"] == 1, "toggling reuses the one INVERT modifier"
    assert res["bare"]["ok"] is False and "no mask" in res["bare"]["error"], res["bare"]
