# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""segment_mesh island_labels (specs/mixar_docs/segment_mesh.md, BUILD_ORDER Wave 5): part names on UV islands as vertex groups ``<object>_<label>``, with the
SAME island enumeration as the Client's Mesh Segment (mesh_labeler.get_uv_islands), so an island index means one thing on both sides of the wire. REAL binary."""

import json

import numpy as np

from features_support import run

PLANE = '''
def islands3(name):
    """Three quads, three UV islands (each quad its own UV rect), plus a recipe of two parts."""
    me = bpy.data.meshes.new(name)
    verts, faces = [], []
    for i in range(3):
        b = len(verts); x = 2.0 * i
        verts += [(x, 0, 0), (x + 1, 0, 0), (x + 1, 0, 1), (x, 0, 1)]
        faces.append((b, b + 1, b + 2, b + 3))
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    for i in range(3):
        for k, (u, v) in enumerate(((0, 0), (0.2, 0), (0.2, 0.2), (0, 0.2))):
            uv.data[4 * i + k].uv = (u + 0.3 * i, v)
    me.update()
    return link(bpy.data.objects.new(name, me))
json.dump({"parts": {"cuirass_front": {"class": "metal"}, "skirt": {"class": "cloth"}}}, open(os.path.join(root, "recipe.json"), "w"))
'''


def _go(tmp_path, body):
    r = run(tmp_path, PLANE + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_labels_indices_match_client_enumeration(tmp_path):
    res = _go(tmp_path, '''
ob = islands3("chest")
from mixar.modules.mesh_segment.core.mesh_labeler import get_uv_islands
client = {str(k): sorted(v) for k, v in get_uv_islands(ob).items()}
r = call("segment_mesh", object="chest", labels={"mode": "map", "island_labels": {"0": "cuirass_front", "1": "skirt", "2": "skirt"}, "recipe": "recipe.json"})
print("RESULT", json.dumps({"client": client, "r": r}))
''')
    r = res["r"]
    assert r["ok"] is True and sorted(r["islands"]) == sorted(res["client"]), res
    assert all(sorted(r["islands"][k]["verts"]) == res["client"][k] for k in res["client"]), res


def test_map_labels_become_vertex_groups_named_object_label(tmp_path):
    res = _go(tmp_path, '''
ob = islands3("chest")
r = call("segment_mesh", object="chest", labels={"mode": "map", "island_labels": {"0": "cuirass_front", "1": "skirt", "2": "skirt"}})
groups = {g.name: sorted(v.index for v in ob.data.vertices if any(e.group == g.index for e in v.groups)) for g in ob.vertex_groups}
print("RESULT", json.dumps({"r": r, "groups": groups, "objects": sorted(o.name for o in bpy.data.objects)}))
''')
    assert res["groups"] == {"chest_cuirass_front": [0, 1, 2, 3], "chest_skirt": [4, 5, 6, 7, 8, 9, 10, 11]}, res
    assert res["r"]["island_labels"] == {"0": "cuirass_front", "1": "skirt", "2": "skirt"} and res["objects"] == ["chest"], "labelling splits nothing"


def test_recipe_labels_come_from_the_owner_map_by_island_vote(tmp_path):
    np.save(tmp_path / "owner.npy", np.array([0, 1, 1], dtype=np.int32))
    res = _go(tmp_path, '''
islands3("chest")
print("RESULT", json.dumps(call("segment_mesh", object="chest", labels={"mode": "recipe", "recipe": "recipe.json", "owner": "owner.npy"})))
''')
    assert res["ok"] is True and res["island_labels"] == {"0": "cuirass_front", "1": "skirt", "2": "skirt"}, res
    assert res["unlabeled_islands"] == [] and res["evidence"]["0"]["share"] == 1.0, res


def test_labels_need_uv_and_a_known_vocabulary(tmp_path):
    res = _go(tmp_path, '''
me = bpy.data.meshes.new("n"); me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)]); link(bpy.data.objects.new("n", me))
islands3("chest")
out = {"nouv": call("segment_mesh", object="n", labels={"mode": "map", "island_labels": {"0": "x"}}),
       "vocab": call("segment_mesh", object="chest", labels={"mode": "map", "island_labels": {"0": "pauldron"}, "recipe": "recipe.json"}),
       "free": call("segment_mesh", object="chest", labels={"mode": "description", "description": "split the chest"})}
print("RESULT", json.dumps(out))
''')
    assert res["nouv"]["ok"] is False and "no UV map" in res["nouv"]["error"], res
    assert res["vocab"]["ok"] is False and "pauldron" in res["vocab"]["error"] and "recipe" in res["vocab"]["error"], res
    assert res["free"]["ok"] is False and "map | recipe" in res["free"]["error"], res


def test_too_many_unlabeled_faces_refuse_to_apply(tmp_path):
    np.save(tmp_path / "owner.npy", np.array([0, -1, -1], dtype=np.int32))
    res = _go(tmp_path, '''
ob = islands3("chest")
r = call("segment_mesh", object="chest", labels={"mode": "recipe", "recipe": "recipe.json", "owner": "owner.npy"})
print("RESULT", json.dumps({"r": r, "groups": [g.name for g in ob.vertex_groups]}))
''')
    assert res["r"]["ok"] is False and "unlabelled" in res["r"]["error"] and res["groups"] == [], res
