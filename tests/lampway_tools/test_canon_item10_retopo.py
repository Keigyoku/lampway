# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 10 (canon 12): a QuadriFlow that refuses the mesh is never silently replaced by the voxel remesh - the
fallback is the caller's explicit choice, and the receipt says it was taken. Observed failing on the tool before the change."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

NONMANIFOLD = r'''
bm = bmesh.new()
a = [bm.verts.new(p) for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0.5, 0.5, 1), (0.5, 0.5, -1), (0.5, -0.5, 0.5))]
for f in ((0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 1, 5), (1, 2, 5), (2, 3, 5), (3, 0, 5), (0, 1, 6)):     # edge 0-1 has three faces
    bm.faces.new([a[i] for i in f])
me = bpy.data.meshes.new("nm"); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("nm", me); bpy.context.scene.collection.objects.link(ob)
'''


def test_a_refused_quadriflow_is_refused_unless_the_voxel_fallback_is_asked_for():
    r = run_script(PRE + NONMANIFOLD + '''
a = api.retopo("nm", target_faces=200, method="quadriflow")
left = sorted(o.name for o in bpy.data.objects)
b = api.retopo("nm", target_faces=200, method="quadriflow", fallback=True)
res({"a_ok": a.get("ok"), "a_err": a.get("error"), "a_method": a.get("method"), "left": left, "b_method": b.get("method"), "b_note": b.get("note")})
''', timeout=300)
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["a_ok"] is False and "fallback" in d["a_err"] and d["left"] == ["nm"], d
    assert d["b_method"] == "voxel" and "fallback" in (d["b_note"] or ""), d
