# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon 03 G (and 09 G): the source-part check, the detached-glove guard. A piece must be ONE similarity of its source per rigid
group (residual < 0.5 mm) before it is fitted: on 2026-09-29 a glove moved 22 deg off its bracer by an experiment became every later
stage's input (memory gauntlet-glove-detached). lampway_fit_source_check measures it part by part. REAL binary."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_fit_support import FIT_PRE  # noqa: E402

GLOVE = r'''
from mathutils import Matrix
def glove(name):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=16, radius1=0.045, radius2=0.04, depth=0.16, matrix=Matrix.Translation((0, 0, 0.08)))
    nb = len(bm.verts)
    box(bm, (0, 0, 0.22), (0.09, 0.04, 0.12))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    ob.vertex_groups.new(name="bracer").add(list(range(nb)), 1.0, "REPLACE")
    ob.vertex_groups.new(name="glove").add(list(range(nb, len(me.vertices))), 1.0, "REPLACE")
    return ob, nb
src, NB = glove("source")
def variant(name, M_all, M_glove=None):
    ob, _ = glove(name)
    for v in ob.data.vertices:
        co = (M_glove @ v.co) if (M_glove is not None and v.index >= NB) else v.co.copy()
        v.co = M_all @ co
    return ob
wrist = Matrix.Translation((0, 0, 0.16)) @ Matrix.Rotation(math.radians(22), 4, "X") @ Matrix.Translation((0, 0, -0.16))
moved = Matrix.Translation((0.3, -0.1, 1.0)) @ Matrix.Rotation(math.radians(-90), 4, "Z") @ Matrix.Diagonal((1.3, 1.3, 1.3, 1.0))
whole = variant("whole", moved)
detached = variant("detached", moved, wrist)
'''


def test_a_piece_moved_whole_passes_and_a_detached_glove_fails_naming_the_part_and_its_angle(tmp_path):
    r = run_script(FIT_PRE + GLOVE + '''
out = {k: api.fit_source_check(piece=k, source="source") for k in ("whole", "detached")}
out["split"] = api.fit_source_check(piece="detached", source="source", rigid_groups=[["bracer"], ["glove"]])
out["count"] = api.fit_source_check(piece="whole", source=bpy.data.objects.new("pt", bpy.data.meshes.new("pt")).name)
res(out)
''', env={"LW_KEEP_ROOT": str(tmp_path)}, timeout=300)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[-1]
    w, x = d["whole"], d["detached"]
    assert w["ok"] and w["pass"] is True and w["groups"][0]["residual_max_mm"] < 1e-3 and abs(w["groups"][0]["scale"] - 1.3) < 1e-6, w
    assert x["ok"] and x["pass"] is False, x
    g = x["groups"][0]
    assert g["parts"] == ["bracer", "glove"] and g["residual_max_mm"] > 0.5, g
    off = g["relative_deg"]
    assert abs(off["glove"] - 22.0) < 0.01 and off["bracer"] == 0.0, off
    assert "glove" in x["reason"] and "22.0" in x["reason"], x["reason"]
    assert d["split"]["pass"] is True, d["split"]                            # declared as two rigid groups, each its own similarity
    assert d["count"]["ok"] is False and "vertices" in d["count"]["error"], d["count"]
