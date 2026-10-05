# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/proportion/mesh_to_npz.py, sha256 e297609ebb0d) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): export a mesh (fbx/glb, meshopt glb included) or the MetaHuman body (with its joints) to npz for the numpy
# proportion tools. Copied from the proportion auditor's export.py (scratch/scratch-tmp/proportion/audit/).
# blender -b -P mesh_to_npz.py -- <out.npz> <piece|piece_uv|body> <file>   (piece_uv adds P/UV per triangle, aligned to T)
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['blender -b -P scripts/proportion/mesh_to_npz.py -- <out.npz> piece|piece_uv|body <file>']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, 'Export a mesh (fbx/glb, meshopt included) or the MetaHuman body with joints to npz')
    else: print(f'error: {len(_A)} argument(s); at least 3 needed')
    _ax.helps(['blender -b -P scripts/proportion/mesh_to_npz.py -- <out.npz> piece|piece_uv|body <file>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import bpy, sys, numpy as np
a = sys.argv[sys.argv.index('--') + 1:]; OUT, mode, f = a[0], a[1], a[2]
bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.data.objects)
(bpy.ops.import_scene.fbx if f.lower().endswith('.fbx') else bpy.ops.import_scene.gltf)(filepath=f)
new = [o for o in bpy.data.objects if o not in before]
if mode == 'body':
    arm = next(o for o in new if o.type == 'ARMATURE'); body = max((o for o in new if o.type == 'MESH'), key=lambda o: len(o.data.vertices))
    J = {b.name: np.array((arm.matrix_world @ b.head_local)[:]) for b in arm.data.bones}
    me = body.data; me.calc_loop_triangles()
    np.savez(OUT, V=np.array([(body.matrix_world @ v.co)[:] for v in me.vertices]), T=np.array([t.vertices[:] for t in me.loop_triangles]), names=list(J), J=np.array(list(J.values())))
elif mode == 'piece_uv':                                                # + per-triangle P (positions) and UV, aligned to T (texlib/relief_project.py input)
    V, T, UV, POLY, off, poff = [], [], [], [], 0, 0
    for o in new:
        if o.type != 'MESH': continue
        M = o.matrix_world; me = o.data; me.calc_loop_triangles(); uvl = me.uv_layers.active
        if uvl is None: raise SystemExit(f'error: {o.name} has no UV layer')
        V += [(M @ v.co)[:] for v in me.vertices]
        for t in me.loop_triangles: T.append(tuple(i + off for i in t.vertices)); UV.append([uvl.data[li].uv[:] for li in t.loops]); POLY.append(t.polygon_index + poff)
        off += len(me.vertices); poff += len(me.polygons)
    V = np.array(V); T = np.array(T); np.savez(OUT, V=V, T=T, P=V[T], UV=np.array(UV), POLY=np.array(POLY))   # POLY: source polygon per triangle
else:
    V, T, off = [], [], 0
    for o in new:
        if o.type != 'MESH': continue
        M = o.matrix_world; me = o.data; me.calc_loop_triangles()
        V += [(M @ v.co)[:] for v in me.vertices]; T += [tuple(i + off for i in t.vertices) for t in me.loop_triangles]; off += len(me.vertices)
    np.savez(OUT, V=np.array(V), T=np.array(T))
print('NPZ', OUT)
