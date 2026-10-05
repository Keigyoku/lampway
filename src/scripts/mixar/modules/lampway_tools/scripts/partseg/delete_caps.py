# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/delete_caps.py, sha256 cfd8f74293a0) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): delete a CAP that closes an opening which must stay open (neck bowls, waist fans, arm domes - the recurring
# Smart Mesh defect, audits 2026-10-04). Rays are cast along an axis through a rectangular footprint; the first polygon each ray
# meets beyond a threshold coordinate is cap. Those polygons are deleted (UVs and everything else kept) and the mesh is written to a
# NEW file. Method from the 9c052d49 auditor's neck_nocap.py (removing its hits cleared the neck: 0 body vertices through).
# Frame: Blender import (X front, Y wearer's left, Z up), metres - the frame audits report bboxes in.
# blender -b -P delete_caps.py -- <in.fbx|glb> <out.fbx> --axis z+ --footprint x0,x1,y0,y1 --beyond 0.33 [--step 0.004] [--grow 0]
#   axis z+: rays travel +Z from below, footprint in X/Y, cap = first hit with z > beyond.  (z-, x+, x-, y+, y- likewise)
#   --grow N: also delete polygons sharing an edge with the cap and lying beyond the threshold, N rings (bounded).
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
if __name__ == '__main__' and len(_A) < 2:
    if not _A: _ax.home(__file__, 'Delete a cap that closes an opening (neck bowl, waist fan, arm dome) by ray-casting through its footprint; UVs kept; writes a new file')
    else: print(f'error: {len(_A)} argument(s); at least 2 needed')
    _ax.helps(['blender -b -P scripts/partseg/delete_caps.py -- <in> <out.fbx> --axis z+ --footprint x0,x1,y0,y1 --beyond 0.33']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import argparse, bpy, bmesh, json, os, sys, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ap = argparse.ArgumentParser(prog='delete_caps.py'); ap.add_argument('src'); ap.add_argument('out')
ap.add_argument('--axis', default='z+', choices=['x+', 'x-', 'y+', 'y-', 'z+', 'z-']); ap.add_argument('--footprint', required=True)
ap.add_argument('--beyond', type=float, required=True); ap.add_argument('--step', type=float, default=0.004); ap.add_argument('--grow', type=int, default=0)
a = ap.parse_args(_A)
if os.path.exists(a.out): _ax.refuse(f'{a.out} exists; never overwritten', ['delete_caps.py <in> <new_out.fbx> ...'])
bpy.ops.wm.read_factory_settings(use_empty=True)
(bpy.ops.import_scene.fbx if a.src.lower().endswith('.fbx') else bpy.ops.import_scene.gltf)(filepath=a.src)
obs = [o for o in bpy.data.objects if o.type == 'MESH']
if len(obs) != 1: _ax.refuse(f'{len(obs)} mesh objects; expected one', [])
o = obs[0]; me = o.data; M = o.matrix_world
V = [M @ v.co for v in me.vertices]; tree = BVHTree.FromPolygons(V, [tuple(p.vertices) for p in me.polygons])
ax_i = 'xyz'.index(a.axis[0]); sgn = 1 if a.axis[1] == '+' else -1; others = [i for i in range(3) if i != ax_i]
f0, f1, g0, g1 = [float(v) for v in a.footprint.split(',')]; d = [0, 0, 0]; d[ax_i] = sgn
cap = set(); n_rays = 0
for u in np.arange(f0, f1 + 1e-9, a.step):                              # bounded grid
    for w in np.arange(g0, g1 + 1e-9, a.step):
        p = [0, 0, 0]; p[others[0]] = u; p[others[1]] = w; p[ax_i] = -sgn * 2.0; n_rays += 1
        h = tree.ray_cast(Vector(p), Vector(d), 5.0)
        if h[0] is not None and sgn * h[0][ax_i] > sgn * a.beyond: cap.add(h[2])
bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
for _ in range(max(a.grow, 0)):                                          # optional rings, bounded
    ring = set()
    for fi in cap:
        for e in bm.faces[fi].edges:
            for f in e.link_faces:
                if f.index not in cap and sgn * (M @ f.calc_center_median())[ax_i] > sgn * a.beyond: ring.add(f.index)
    cap |= ring
bmesh.ops.delete(bm, geom=[bm.faces[i] for i in sorted(cap)], context='FACES_ONLY')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
n0 = len(me.polygons); bm.to_mesh(me); bm.free(); me.update()
bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
bpy.ops.export_scene.fbx(filepath=a.out, use_selection=True, path_mode='COPY', embed_textures=False, axis_forward='-Z', axis_up='Y')
rec = {'src': a.src, 'out': a.out, 'axis': a.axis, 'footprint': [f0, f1, g0, g1], 'beyond': a.beyond, 'rays': n_rays, 'polygons_before': n0,
       'polygons_deleted': len(cap), 'polygons_after': len(me.polygons), 'uv_layers': [l.name for l in me.uv_layers]}
json.dump(rec, open(a.out + '.json', 'w'), indent=1)
_ax.kv({k: rec[k] for k in ('rays', 'polygons_before', 'polygons_deleted', 'polygons_after')}); print(f'record: {a.out}.json')
_ax.helps(['blender -b -P scripts/proportion/mesh_to_npz.py -- <out.npz> piece_uv <out.fbx>', 'python3 scripts/proportion/place_piece.py ... then pose_clearance.py (neck)'])
