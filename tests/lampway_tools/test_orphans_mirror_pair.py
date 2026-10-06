# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mirror_pair (specs/wiki/mirror_pair.md): the opposite piece by a mirror across a stated plane, on a COPY, only after the typed decision that the design is
symmetric; normals outward, side names and vertex groups swapped, a decision row written. An asymmetric piece is refused without force. REAL binary."""

import json
from pathlib import Path

from features_support import run

SHAPES = '''
def crest(name, cx=0.4):
    """A symmetric box (about its own x) standing at x=cx, with vertex groups by side name."""
    ob = boxes(name, [((cx, 0.0, 1.0), (0.10, 0.20, 0.30))])
    g1 = ob.vertex_groups.new(name="hand_l"); g1.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
    ob.vertex_groups.new(name="spine_01")
    return ob

def lion(name, cx=0.4):
    """An asymmetric piece: a plate with a head block on its outer side only."""
    return boxes(name, [((cx, 0.0, 1.0), (0.20, 0.20, 0.05)), ((cx + 0.08, 0.0, 1.06), (0.05, 0.08, 0.08))])

def outward(ob):
    """Every face normal points away from the shape's centre (a closed convex box)."""
    mw = ob.matrix_world
    c = sum((mw @ v.co for v in ob.data.vertices), Vector()) / len(ob.data.vertices)
    return all((mw.to_3x3() @ p.normal).dot((mw @ p.center) - c) > 0 for p in ob.data.polygons)
'''


def _go(tmp_path, body):
    r = run(tmp_path, SHAPES + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_mirror_requires_the_symmetry_decision(tmp_path):
    res = _go(tmp_path, '''
crest("crest_l")
out = {"none": call("mirror_pair", object="crest_l"), "no": call("mirror_pair", object="crest_l", design_symmetric=False),
       "objects": sorted(o.name for o in bpy.data.objects)}
print("RESULT", json.dumps(out))
''')
    assert res["none"]["ok"] is False and "record the symmetry decision" in res["none"]["error"], res
    assert res["no"]["ok"] is False and "never mirror" in res["no"]["error"], res
    assert res["objects"] == ["crest_l"], "a refusal makes nothing"


def test_normals_point_outward_after_mirror_and_the_copy_sits_on_the_other_side(tmp_path):
    res = _go(tmp_path, '''
src = crest("crest_l")
r = call("mirror_pair", object="crest_l", design_symmetric=True, origin="body_midline", body_midline_x=0.0)
new = bpy.data.objects[r["object"]]
xs = [(new.matrix_world @ v.co).x for v in new.data.vertices]
print("RESULT", json.dumps({"r": r, "outward": outward(new), "src_outward": outward(src), "min_x": min(xs), "max_x": max(xs),
                            "src_x": [round((src.matrix_world @ v.co).x, 4) for v in src.data.vertices][:1]}))
''')
    r = res["r"]
    assert r["ok"] is True and r["object"] == "crest_r" and r["normals_recalculated"] is True and r["mirrored_vertices"] == 8, r
    assert res["outward"] is True and res["src_outward"] is True, res
    assert abs(res["min_x"] + 0.45) < 1e-5 and abs(res["max_x"] + 0.35) < 1e-5, res


def test_group_names_swapped_or_dropped(tmp_path):
    res = _go(tmp_path, '''
crest("crest_l")
a = call("mirror_pair", object="crest_l", design_symmetric=True)
groups_a = sorted(g.name for g in bpy.data.objects[a["object"]].vertex_groups)
crest("visor_l", cx=0.9)
b = call("mirror_pair", object="visor_l", design_symmetric=True, weights="drop")
print("RESULT", json.dumps({"a": a, "ga": groups_a, "gb": [g.name for g in bpy.data.objects[b["object"]].vertex_groups],
                            "src": sorted(g.name for g in bpy.data.objects["crest_l"].vertex_groups)}))
''')
    assert res["ga"] == ["hand_r", "spine_01"] and res["a"]["renamed_groups"] == [["hand_l", "hand_r"]], res
    assert res["gb"] == [] and res["src"] == ["hand_l", "spine_01"], "the source keeps its groups"


def test_an_asymmetric_piece_is_refused_without_force_and_mirrored_with_it(tmp_path):
    res = _go(tmp_path, '''
lion("lion_l")
refused = call("mirror_pair", object="lion_l", design_symmetric=True)
forced = call("mirror_pair", object="lion_l", design_symmetric=True, force=True, by="captain", captain_words="mirror it anyway")
print("RESULT", json.dumps({"refused": refused, "forced": forced}))
''')
    assert res["refused"]["ok"] is False and "measured asymmetry" in res["refused"]["error"] and "force=true" in res["refused"]["error"], res
    assert res["forced"]["ok"] is True and res["forced"]["forced"] is True, res


def test_a_decision_row_is_appended_for_every_mirror(tmp_path):
    res = _go(tmp_path, '''
crest("crest_l")
r = call("mirror_pair", object="crest_l", design_symmetric=True, piece="Helmet1", by="captain", captain_words="the crest is symmetric")
print("RESULT", json.dumps(r))
''')
    rows = [json.loads(line) for line in (Path(tmp_path) / "Helmet1" / "decisions.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["question"] == "design_symmetric" and rows[0]["answer"] == "true" and rows[0]["decider"] == "captain", rows
    assert rows[0]["captain_words"] == "the crest is symmetric" and rows[0]["descriptor"]["object"] == "crest_l"


def test_uv_mirror_is_opt_in(tmp_path):
    res = _go(tmp_path, '''
ob = crest("crest_l")
ob.data.uv_layers.new(name="UVMap")
uv = ob.data.uv_layers[0]
for i, d in enumerate(uv.data): d.uv = (0.1, 0.2)
a = call("mirror_pair", object="crest_l", design_symmetric=True)
b = call("mirror_pair", object="crest_l", design_symmetric=True, mirror_uv=True)
print("RESULT", json.dumps({"a": [list(bpy.data.objects[a["object"]].data.uv_layers[0].data[0].uv)], "b": [list(bpy.data.objects[b["object"]].data.uv_layers[0].data[0].uv)],
                            "ua": a["uv_mirrored"], "ub": b["uv_mirrored"]}))
''')
    assert res["ua"] is False and abs(res["a"][0][0] - 0.1) < 1e-6, res
    assert res["ub"] is True and abs(res["b"][0][0] - 0.9) < 1e-6, res
