# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""print_check and print_prep (specs/wiki/print_check.md, print_prep.md) in the real binary: printability measured (manifold, self-intersections, isolated triangles,
wall thickness by inward rays, overhang area, floating parts, printer volume) and a scale-correct STL derivative made from a copy, refused when the printer's wall
limit is missing or not met, or when the source is still rigged."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

SHAPES = '''
def hollow(name, outer=0.02, wall=0.0005):
    """A closed box with a closed inner cavity (inner faces wound inward): walls `wall` thick."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=outer)
    inner = bmesh.ops.create_cube(bm, size=outer - 2 * wall)
    bmesh.ops.reverse_faces(bm, faces=list({f for v in inner["verts"] for f in v.link_faces}))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location.z = outer / 2
    return link(ob)
'''


def test_cube_passes(tmp_path):
    d = one(go(tmp_path, SHAPES + '''
ob = boxes("cube", [((0, 0, 0.01), (0.02, 0.02, 0.02))])
canon("cube")
res = call("print_check", object="cube", min_wall_mm=1.0, printer_volume_mm=[100, 100, 100])
print("RESULT", json.dumps(res))
'''))
    assert d["ok"] and d["pass"] is True and d["manifold"] is True and d["intersections"] == 0 and d["isolated_triangles"] == 0
    assert d["thin"] == [] and d["floating_parts"] == 0 and d["fits_volume"] is True and d["overhang_area_fraction"] == 0.0
    assert d["size_mm"] == [20.0, 20.0, 20.0]


def test_two_overlapping_cubes_intersect(tmp_path):
    d = one(go(tmp_path, SHAPES + '''
boxes("pair", [((0, 0, 0.01), (0.02, 0.02, 0.02)), ((0.01, 0.005, 0.015), (0.02, 0.02, 0.02))])
canon("pair")
res = call("print_check", object="pair", min_wall_mm=0.5)
print("RESULT", json.dumps(res))
'''))
    assert d["intersections"] > 0 and d["pass"] is False and d["floating_parts"] == 1


def test_wall_below_limit_listed_and_a_thicker_wall_passes(tmp_path):
    d = one(go(tmp_path, SHAPES + '''
hollow("thin", wall=0.0005)
hollow("thick", wall=0.002)
canon("thin")
thin = call("print_check", object="thin", min_wall_mm=1.0)
canon("thick")
thick = call("print_check", object="thick", min_wall_mm=1.0)
print("RESULT", json.dumps({"thin": thin, "thick": thick}))
'''))
    thin, thick = d["thin"], d["thick"]
    assert thin["thin"] and all(abs(t["thickness_mm"] - 0.5) < 0.01 for t in thin["thin"]) and thin["thin_faces"] == 12 and thin["pass"] is False
    assert thick["thin"] == [] and thick["thin_faces"] == 0                       # the falsifier: thicken the wall and it passes the wall check


def test_overhang_counts_downward_faces_off_the_plate_and_the_volume_check(tmp_path):
    d = one(go(tmp_path, SHAPES + '''
boxes("tee", [((0, 0, 0.01), (0.01, 0.01, 0.02)), ((0, 0, 0.025), (0.04, 0.01, 0.01))])   # a stem and an overhanging bar (two shells that touch)
canon("tee")
res = call("print_check", object="tee", min_wall_mm=0.5, overhang_deg=45, printer_volume_mm=[30, 30, 30])
print("RESULT", json.dumps(res))
'''))
    assert 0 < d["overhang_area_fraction"] < 0.3 and d["fits_volume"] is False


def test_missing_min_wall_refused(tmp_path):
    d = one(go(tmp_path, '''
boxes("cube", [((0, 0, 0.01), (0.02, 0.02, 0.02))])
canon("cube")
print("RESULT", json.dumps(call("print_check", object="cube")))
'''))
    assert d["ok"] is False and "min_wall_mm" in d["error"]


def test_stl_dimensions_equal_target_height_from_a_copy(tmp_path):
    d = one(go(tmp_path, SHAPES + '''
ob = boxes("figure", [((0, 0, 0.65), (0.4, 0.3, 1.3))])                                     # a 1.3 m figure, one closed shell
bpy.ops.object.select_all(action="DESELECT")
canon("figure")
res = call("print_prep", object="figure", target_height_mm=15, min_wall_mm=0.4, out_dir="print")
for o in list(bpy.data.objects):
    if o.name != "figure":
        bpy.data.objects.remove(o)
bpy.ops.wm.stl_import(filepath=os.path.join(root, res["files"][0]["path"]))
imp = [o for o in bpy.data.objects if o.name != "figure"][0]
print("RESULT", json.dumps({"res": res, "dims": [round(x, 3) for x in imp.dimensions], "src": [round(x, 3) for x in bpy.data.objects["figure"].dimensions]}))
'''))
    res = d["res"]
    assert res["ok"], res
    assert abs(d["dims"][2] - 15.0) < 0.01 and abs(d["dims"][0] - 15.0 * 0.4 / 1.3) < 0.01
    assert d["src"] == [0.4, 0.3, 1.3] and res["scale"]["to_height_mm"] == 15 and res["report"]["pass"] is True


def test_thin_wall_and_armature_and_missing_wall_limit_are_refused(tmp_path):
    d = one(go(tmp_path, SHAPES + '''
hollow("shell", outer=1.0, wall=0.01)                                      # a 1 m box with 1 cm walls: at 15 mm tall the wall is 0.15 mm
canon("shell")
thin = call("print_prep", object="shell", target_height_mm=15, min_wall_mm=0.4, out_dir="print")
canon("shell")
nowall = call("print_prep", object="shell", target_height_mm=15, out_dir="print")
rig = armature(); bind("shell")
canon("shell")
rigged = call("print_prep", object="shell", target_height_mm=150, min_wall_mm=0.4, out_dir="print")
stl = [f for f in (os.listdir(os.path.join(root, "print")) if os.path.isdir(os.path.join(root, "print")) else []) if f.endswith(".stl")]
print("RESULT", json.dumps({"thin": thin, "nowall": nowall, "rigged": rigged, "stl": stl, "objects": sorted(o.name for o in bpy.data.objects)}))
'''))
    assert d["thin"]["ok"] is False and "thinner than min_wall_mm" in d["thin"]["error"]
    assert d["nowall"]["ok"] is False and "the wall limit is the printer's: give it" in d["nowall"]["error"]
    assert d["rigged"]["ok"] is False and "print derivatives are static: pose it first and apply" in d["rigged"]["error"]
    assert d["stl"] == [] and d["objects"] == ["rig", "shell"]                          # nothing written, no derivative left behind
