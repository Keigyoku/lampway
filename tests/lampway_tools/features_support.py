# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared scene builders for the feature tests (REAL binary, synthetic shapes): a dense sphere, a T-pose humanoid made of
boxes and a sphere, and the call helper that runs ``api.call`` inside the app and returns its JSON."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

PRE = '''
import bpy, bmesh, json, math, os
import numpy as np
from mathutils import Vector, Matrix
from mixar.modules.lampway_tools import api
root = ROOT
for _o in list(bpy.data.objects):
    bpy.data.objects.remove(_o)

def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    return ob

def sphere(name, radius=0.5, subdiv=5, loc=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location = loc
    return link(ob)

def boxes(name, parts):
    """parts: [(center, size)] -> one joined mesh of axis-aligned boxes (disconnected shells)."""
    bm = bmesh.new()
    for c, s in parts:
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s[0], s[1], s[2], 1.0)))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))

def humanoid(name="body"):
    """A 1.8 m T-pose figure of one connected-ish mesh set: torso, head, two arms, two legs (separate shells)."""
    return boxes(name, [((0, 0, 1.15), (0.40, 0.22, 0.60)),            # torso
                        ((0, 0, 1.62), (0.18, 0.18, 0.22)),            # head
                        ((-0.55, 0, 1.30), (0.60, 0.12, 0.12)), ((0.55, 0, 1.30), (0.60, 0.12, 0.12)),   # arms along X
                        ((-0.12, 0, 0.45), (0.16, 0.16, 0.85)), ((0.12, 0, 0.45), (0.16, 0.16, 0.85))])   # legs

def call(fn, **kw):
    return api.call(fn, json.dumps(kw))

def canon(*names, welded=False, scale="real"):
    """Stamp test fixtures canonical through canon's own normalizer (the door refuses a raw object): metres, +Z up, front -Y, the transform
    applied, the origin kept (pivot source_origin, so world positions do not move), real scale on a declared length (or scale=any), and
    a weld by position when the tool's door asks for welded input. Call it after the fixture is built and before the tool: any later edit
    to the mesh changes its hash and the door refuses it again."""
    from mixar.modules.lampway_tools.features import normalize as _NZ
    for n in names:
        _NZ.normalize_object(bpy.data.objects[n], turn_deg=0.0, generator="trellis" if welded else "lampway_tool",
                             want_scale="real" if scale == "real" else "any",
                             scale_evidence={"method": "captain_length", "value": 1.0} if scale == "real" else None,
                             pivot="source_origin", pivot_offset=(0.0, 0.0, 0.0))
    return names
'''


def run(tmp_path, body, **kw):
    env = {"LAMPWAY_PROJECT_ROOT": str(tmp_path), "LAMPWAY_HOME": str(tmp_path / "home")}
    env.update(kw.pop("env", {}))
    return run_script(PRE.replace("ROOT", repr(str(tmp_path))) + body, env=env, **kw)
