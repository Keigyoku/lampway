# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""cloth_garment_sim (specs/wiki/cloth_garment_sim.md) in the real binary: a bounded Blender cloth drape of a COPY of the garment on a body (pinned zone, body
collision, thickness), baked to a static shape, with a Max-Distance-style map (zero at the pins); the body keeps no modifier and metal is refused."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

DRAPE = '''
body = sphere("body", 0.5, subdiv=4)
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=20, y_segments=20, size=0.8)
me = bpy.data.meshes.new("cloak"); bm.to_mesh(me); bm.free()
cloak = link(bpy.data.objects.new("cloak", me)); cloak.location = (0, 0, 0.62)
pin = cloak.vertex_groups.new(name="pin")
pin.add([v.index for v in cloak.data.vertices if abs(v.co.y) < 0.1 and abs(v.co.x) < 0.3], 1.0, "REPLACE")   # a strip over the top of the sphere
bpy.context.view_layer.update()
before = [tuple(cloak.matrix_world @ v.co) for v in cloak.data.vertices]
pinned = [v.index for v in cloak.data.vertices if any(g.group == pin.index for g in v.groups)]
'''


def test_pinned_vertices_do_not_move_the_free_ones_drape_and_the_source_is_kept(tmp_path):
    d = one(go(tmp_path, DRAPE + '''
res = call("cloth_garment_sim", garment="cloak", body="body", pin_group="pin", frames=40, thickness_m=0.005)
dr = bpy.data.objects[res["draped_object"]]
after = [tuple(dr.matrix_world @ v.co) for v in dr.data.vertices]
move = [(Vector(a) - Vector(b)).length for a, b in zip(after, before)]
print("RESULT", json.dumps({"res": res, "pin_move": max(move[i] for i in pinned), "free_move": max(move), "n": len(pinned),
                            "src_same": [tuple(cloak.matrix_world @ v.co) for v in cloak.data.vertices] == before,
                            "body_mods": [m.type for m in body.modifiers], "dr_mods": [m.type for m in dr.modifiers], "frame": bpy.context.scene.frame_current}))
'''))
    res = d["res"]
    assert res["ok"], res
    assert res["draped_object"] == "cloak_draped" and d["src_same"] and d["n"] > 5
    assert d["pin_move"] < 1e-4 and d["free_move"] > 0.1 and res["stats"]["max_displacement_m"] > 0.1
    assert d["body_mods"] == [] and d["dr_mods"] == [] and d["frame"] == 1                  # the collision modifier is gone, the drape is a static mesh, the frame restored


def test_no_penetration_after_bake_on_a_sphere_body(tmp_path):
    d = one(go(tmp_path, DRAPE + '''
res = call("cloth_garment_sim", garment="cloak", body="body", pin_group="pin", frames=40, thickness_m=0.005)
print("RESULT", json.dumps(res))
'''))
    assert d["ok"] and d["stats"]["penetrations"] == 0 and d["stats"]["frames_simulated"] == 40


def test_max_distance_is_zero_at_the_pins_and_grows_away_from_them(tmp_path):
    d = one(go(tmp_path, DRAPE + '''
res = call("cloth_garment_sim", garment="cloak", body="body", pin_group="pin", frames=10, max_distance_m=0.3)
dr = bpy.data.objects[res["draped_object"]]
g = dr.vertex_groups["max_distance"]
w = {v.index: next((e.weight for e in v.groups if e.group == g.index), None) for v in dr.data.vertices}
far = max(range(len(before)), key=lambda i: Vector(before[i]).xy.length)
print("RESULT", json.dumps({"res": res, "pins": [w[i] for i in pinned], "far": w[far], "all_set": all(x is not None for x in w.values())}))
'''))
    assert d["res"]["vertex_group"] == "max_distance" and d["all_set"]
    assert max(d["pins"]) == 0.0 and d["far"] == 1.0
    assert d["res"]["max_distance_m"] == 0.3


def test_metal_an_armature_bound_garment_and_unbounded_frames_are_refused(tmp_path):
    d = one(go(tmp_path, DRAPE + '''
metal = call("cloth_garment_sim", garment="cloak", body="body", pin_group="pin", material_class="metal")
cloak["lw_material_class"] = "metal"
tagged = call("cloth_garment_sim", garment="cloak", body="body", pin_group="pin")
del cloak["lw_material_class"]
frames = call("cloth_garment_sim", garment="cloak", body="body", pin_group="pin", frames=400)
thick = call("cloth_garment_sim", garment="cloak", body="body", pin_group="pin", thickness_m=0.5)
nopin = call("cloth_garment_sim", garment="cloak", body="body", pin_group="nope")
rig = armature(); m = cloak.modifiers.new("Armature", "ARMATURE"); m.object = rig
bound = call("cloth_garment_sim", garment="cloak", body="body", pin_group="pin")
print("RESULT", json.dumps({"metal": metal, "tagged": tagged, "frames": frames, "thick": thick, "nopin": nopin, "bound": bound,
                            "objects": sorted(o.name for o in bpy.data.objects)}))
'''))
    for k in ("metal", "tagged"):
        assert d[k]["ok"] is False and "metal parts are not cloth: rigid or segmented binding" in d[k]["error"]
    assert d["frames"]["ok"] is False and "10..250" in d["frames"]["error"]
    assert d["thick"]["ok"] is False and "0.0005..0.02" in d["thick"]["error"]
    assert d["nopin"]["ok"] is False and "nope" in d["nopin"]["error"]
    assert d["bound"]["ok"] is False and "bind after" in d["bound"]["error"]
    assert "cloak_draped" not in d["objects"]
