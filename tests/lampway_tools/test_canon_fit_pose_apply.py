# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon 03 B.6 -> B.9: the closest pose is the FIT pose the piece is bound at, so lampway_fit_pose apply=true puts the armature in
it (the entries replayed in the joint grammar through each bone's joint, parents first) - without it the bind would sample the body
at rest. Golden C07 on the REAL binary: the sweep picks the arm lowered 30 deg, and the armature's elbow lands on the sweep's joint."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_fit_support import FIT_PRE  # noqa: E402
from canon_support import LOAD_OBJ, goldens  # noqa: E402,F401


def test_fit_pose_apply_puts_the_armature_in_the_closest_pose(tmp_path, goldens):
    r = run_script(FIT_PRE + LOAD_OBJ + f"GOLD = {str(goldens)!r}\n" + r'''
from mathutils import Matrix
rig = json.load(open(GOLD + "/C07_pose_solve/rig.json"))
sh = Vector(rig["shoulder"]); L = rig["upperarm_length_m"]; ra = rig["arm_radius_m"]
a = math.radians(-40.0); d = Vector((math.cos(a), 0, math.sin(a)))
arm = armature("rig", (("upperarm_l", tuple(sh), tuple(sh + L * d), None), ("lowerarm_l", tuple(sh + L * d), tuple(sh + 1.8 * L * d), "upperarm_l")))
load_obj(GOLD + "/C07_pose_solve/sleeve.obj", "sleeve")
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=ra, radius2=ra, depth=L,
                      matrix=Matrix.Translation(sh + 0.5 * L * d) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4())
bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if (e.verts[0].co - e.verts[1].co).length > 0.2], cuts=11, use_grid_fill=False)
me = bpy.data.meshes.new("armbody"); bm.to_mesh(me); bm.free()
body = bpy.data.objects.new("armbody", me); bpy.context.scene.collection.objects.link(body)
weights(body, arm, lambda co: {"upperarm_l": 1.0})
dof = {"bone": "upperarm_l", "axis": rig["dof"]["axis_world"], "range": rig["dof"]["range"], "step": rig["dof"]["step"],
       "expect": {"joint": "lowerarm_l", "along": "-up", "min_cm": 2.0}}
regions = {"arm_l": {"bones": ["upperarm_l"], "threshold_m": 0.01}}
before = tuple(arm.matrix_world @ arm.pose.bones["lowerarm_l"].head)
dry = api.fit_pose("gauntlets", piece="sleeve", body="armbody", armature="rig", dofs=[dof], regions=regions)
same = tuple(arm.matrix_world @ arm.pose.bones["lowerarm_l"].head)
out = api.fit_pose("gauntlets", piece="sleeve", body="armbody", armature="rig", dofs=[dof], regions=regions, apply=True)
bpy.context.view_layer.update()
after = tuple(arm.matrix_world @ arm.pose.bones["lowerarm_l"].head)
res({"dry": dry.get("entries"), "out": {k: out.get(k) for k in ("ok", "error", "entries", "joints_m", "applied")}, "before": before, "same": same, "after": after})
''', env={"LW_KEEP_ROOT": str(tmp_path)}, timeout=300)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[-1]
    o = d["out"]
    assert o["ok"], o
    assert o["entries"] == [{"bone": "upperarm_l", "axis": [0.0, 1.0, 0.0], "deg": 30.0}], o["entries"]
    assert d["same"] == d["before"], "without apply the armature is not touched"
    want = o["joints_m"]["lowerarm_l"]
    assert max(abs(a - b) for a, b in zip(d["after"], want)) < 1e-5, (d["after"], want)
    assert o["applied"] == o["entries"]
