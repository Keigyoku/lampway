# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Scene builders for the fit chain's tests (REAL binary, synthetic shapes): a skinned body whose NATIVE weight sidecar is written
the way the UE editor leg writes it (Titan armour-validate.py sidecar: titan.native-weight-sidecar/1, UE asset space - cm, the
body frame's (x, y, z) at UE (100 x, -100 y, 100 z)), and a closed body with a head."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_wave3_weights import PRE as WEIGHTS_PRE  # noqa: E402

FIT_PRE = WEIGHTS_PRE + r'''
def write_sidecar(body, arm, path, root_bone=None, schema="titan.native-weight-sidecar/1"):
    """The engine's weights as the editor leg writes them, from a skinned scene body: every vertex, every influence, UE space."""
    me = body.data
    me.calc_loop_triangles()
    gn = {g.index: g.name for g in body.vertex_groups}
    bones = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
    mw, nm = body.matrix_world, body.matrix_world.to_3x3()
    rows = {}
    for v in me.vertices:
        ws = {gn[g.group]: g.weight for g in v.groups if g.weight > 0 and gn[g.group] in bones}
        s = sum(ws.values())
        if not s:
            continue
        p, n = mw @ v.co, (nm @ v.normal).normalized()
        rows[str(v.index)] = {"position": [p.x * 100, -p.y * 100, p.z * 100], "normal": [n.x, -n.y, n.z], "uv0": [0.0, 0.0],
                              "weights": {k: w / s for k, w in ws.items()}}
    tris = [[k] + list(t.vertices) for k, t in enumerate(me.loop_triangles)]
    doc = {"schema": schema, "tool": "armour-validate sidecar (test stand-in)", "version": "test",
           "conventions": {"units": "cm", "space": "UE asset/component space (Z up, left-handed), the rest the engine skins"},
           "result": {"schema": "titan.native-weight-sidecar-result/1", "errors": {}, "root_bone": root_bone or arm.data.bones[0].name,
                      "bones": bones, "vertices": rows, "triangles": tris}}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(doc, open(path, "w"))
    return path

def box(bm, c, s):
    bmesh.ops.create_cube(bm, size=1.0, matrix=__import__("mathutils").Matrix.Translation(c) @ __import__("mathutils").Matrix.Diagonal((s[0], s[1], s[2], 1.0)))

HUMAN_BONES = (("pelvis", (0, 0, 0.9), (0, 0, 1.0), None), ("spine_01", (0, 0, 1.0), (0, 0, 1.2), "pelvis"),
               ("spine_03", (0, 0, 1.2), (0, 0, 1.45), "spine_01"), ("neck_01", (0, 0, 1.45), (0, 0, 1.55), "spine_03"),
               ("head", (0, 0, 1.55), (0, 0, 1.75), "neck_01"))

def human(name="body", head=True, open_body=False, arm=None):
    """A closed figure (torso box, neck, head) skinned to HUMAN_BONES by height; head=False leaves the head off, open_body
    deletes one torso face (a boundary)."""
    arm = arm or armature("rig", HUMAN_BONES)
    bm = bmesh.new()
    box(bm, (0, 0, 1.2), (0.36, 0.22, 0.6))
    box(bm, (0, 0, 1.5), (0.12, 0.12, 0.1))
    if head:
        box(bm, (0, 0, 1.66), (0.2, 0.22, 0.24))
    if open_body:
        bm.faces.ensure_lookup_table()
        bm.faces.remove(bm.faces[0])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    spans = [(b[0], b[1][2], b[2][2]) for b in HUMAN_BONES]
    def fn(co):
        for n, z0, z1 in spans:
            if z0 - 1e-9 <= co.z < z1 or n == "head" and co.z >= z0:
                return {n: 1.0}
        return {"pelvis": 1.0}
    weights(ob, arm, fn)
    return ob, arm
'''
