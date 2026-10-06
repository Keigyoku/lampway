# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared builders for the Wave 6 tool tests (REAL binary, synthetic shapes): a one-chain armature, spheres with an optional cap removed, and the
``one`` reader that asserts a clean exit and returns the first RESULT."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402,F401

W6 = '''
def armature(name="rig", bones=(("root", (0, 0, 0), (0, 0, 1)),), loc=(0, 0, 0)):
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    ob.location = loc
    link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    prev = None
    for bname, head, tail in bones:
        eb = arm.edit_bones.new(bname)
        eb.head, eb.tail = head, tail
        if prev is not None:
            eb.parent = prev
        prev = eb
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob

def capped_sphere(name, radius=0.6, subdiv=4, cut_z=None, loc=(0, 0, 0)):
    """An icosphere; cut_z removes every face whose centre is above that height (a gap in a garment)."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    if cut_z is not None:
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z > cut_z], context="FACES")
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location = loc
    return link(ob)

def bind(obj, arm="rig", bone="root"):
    r = call("bind_to_armature", object=obj, armature=arm, mode="rigid", bone=bone)
    assert r["ok"], r
'''


def one(r):
    assert r.rc == 0, r.out[-3000:]
    assert r.results, r.out[-3000:]
    return r.results[0]


def go(tmp_path, body, **kw):
    return run(tmp_path, W6 + body, **kw)
