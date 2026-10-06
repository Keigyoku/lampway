# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 21 / 17, golden R08 (lane orphans' finding, 2026-10-06: the default UE recipe titan_cm_native reads back 120 deg off on a
canon-17 'blender' rig and 90 deg off on a 'ue_axes' rig). The exporter's axis pair maps each bone to an FBX node frame
N = R_bone @ M(primary, secondary); the engine frame canon 17 defines is R_bone @ T ('blender') or R_bone ('ue_axes'). This test
drives Blender's REAL FBX exporter and a raw read-back (no automatic orientation, primary Y / secondary X) and requires the written
frames to be exactly R_bone @ M from the golden's reference - so R08's angles (0 for the convention's own pair, 120 / 90 for Z/X)
are a property of the exporter, measured here, not an assumption. No UE run: the engine side is MEASUREMENT_PLAN M-RIG-01."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "docs/canon/goldens"
sys.path.insert(0, str(GOLD))
sys.path.insert(0, str(Path(__file__).parent))
import rig_reference as RR  # noqa: E402
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

PAIRS = (("Z", "X"), ("X", "-Y"), ("Y", "X"))
# Blender's own edit-bone storage does not hold an arbitrary frame to 0.01 deg: setting EditBone.matrix and reading it back measured
# max 0.112 deg over 400 random frames (67 over 0.01 deg), 2026-10-06; the FBX round trip shows the same size (max 0.092 deg over 60).
# The mapping under test is 0 vs >= 90 deg, so the bar sits above that noise. (The read-back gate's 0.01 deg is a separate finding.)
STORAGE_NOISE_DEG = 0.2


def test_r08_the_case_matches_its_reference():
    c = json.loads((GOLD / "R08_export_axes/case.json").read_text())
    for conv in ("blender", "ue_axes"):
        assert RR.recipe_for(conv) == tuple(c["expected"]["recipe"][conv])
        for p, s in PAIRS:
            got = RR.frame_angle_deg(RR.fbx_node_map(p, s), RR.ENGINE[conv])
            assert abs(got - c["expected"]["angle_deg"][conv][f"{p}/{s}"]) < 1e-9
    assert c["expected"]["angle_deg"]["blender"]["Z/X"] == 120.0 and c["expected"]["angle_deg"]["ue_axes"]["Z/X"] == 90.0


def test_blenders_fbx_exporter_writes_r_bone_times_m_for_every_pair(tmp_path):
    rots = {"a": (0.0, 0.0, 0.0), "b": (0.4, -0.7, 1.1), "c": (2.0, 0.3, -0.9)}            # three arbitrary bone frames (Euler, rad)
    r = run_script(PRE + '''
from mathutils import Euler, Matrix
from mixar.modules.lampway_tools import canon_io
ROTS = ''' + repr(rots) + '''; PAIRS = ''' + repr(PAIRS) + '''; OUT = ''' + repr(str(tmp_path)) + '''
arm = bpy.data.armatures.new("rig"); ob = bpy.data.objects.new("rig", arm); bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.objects.active = ob; ob.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for i, (n, e) in enumerate(sorted(ROTS.items())):
    eb = arm.edit_bones.new(n); eb.head = (i * 0.5, 0, 0); eb.tail = (i * 0.5, 0.2, 0)
    eb.matrix = Matrix.Translation((i * 0.5, 0, 0)) @ Euler(e).to_matrix().to_4x4()
bpy.ops.object.mode_set(mode="OBJECT")
rest = {b.name: [list(r) for r in b.matrix_local.to_3x3()] for b in arm.bones}
out = {"rest": rest, "read": {}}
for p, s in PAIRS:
    path = OUT + "/" + f"{p}_{s}".replace("-", "m") + ".fbx"
    bpy.context.view_layer.update()
    for o in list(bpy.context.scene.objects): o.select_set(o is ob)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE"}, add_leaf_bones=False, primary_bone_axis=p,
                             secondary_bone_axis=s, axis_forward="-Z", axis_up="Y", apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE")
    rec = canon_io.import_raw(path, automatic_bone_orientation=False, primary_bone_axis="Y", secondary_bone_axis="X", global_scale=1.0)
    a = next(bpy.data.objects[n] for n in rec["objects"] if bpy.data.objects[n].type == "ARMATURE")
    out["read"][p + "/" + s] = {b.name: [list(r) for r in (a.matrix_world.to_3x3() @ b.matrix_local.to_3x3())] for b in a.data.bones}
    for n in rec["objects"]: bpy.data.objects.remove(bpy.data.objects[n])
res(out)
''', timeout=300)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    for pair, read in d["read"].items():
        p, s = pair.split("/")
        M = RR.fbx_node_map(p, s)
        for name, R in d["rest"].items():
            got = RR.frame_angle_deg(np.array(read[name]), np.array(R) @ M)
            assert got < STORAGE_NOISE_DEG, (pair, name, got)            # the written frame IS R_bone @ M(pair); a wrong map is >= 90 deg off
