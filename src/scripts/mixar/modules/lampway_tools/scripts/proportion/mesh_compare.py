# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/proportion/mesh_compare.py, sha256 6d4f3d82723e) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): compare candidate meshes (Smart Mesh variants) with a reference mesh, headless:
# per mesh - faces (polygons and triangles), open boundary edges and loops (positions welded at 1e-5 of the bbox), edges
# shared by 3+ faces, separate shells; each mesh scaled to the reference's height and its bbox centre aligned; 4 orthographic
# matcap renders (front -Y, back +Y, left +X, right -X) side by side; triangles saved as npz for registration tests.
# MC_VIEWS=oblique: only studio-lit raking views from 45 deg above and below each shoulder (dents show).
# blender -b -P mesh_compare.py -- <out_dir> <reference.glb|fbx> <candidate> [<candidate> ...]
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
import lw_canon
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['blender -b -P scripts/proportion/mesh_compare.py -- <out_dir> <reference> <candidate> [...]   (MC_VIEWS=oblique for raking shoulder views)']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, 'Compare candidate meshes with a reference: topology stats, auto-orient, matcap/studio renders')
    else: print(f'error: {len(_A)} argument(s); at least 3 needed')
    _ax.helps(['blender -b -P scripts/proportion/mesh_compare.py -- <out_dir> <reference> <candidate> [...]   (MC_VIEWS=oblique for raking shoulder views)']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import bpy, bmesh, sys, os, json, math, numpy as np
from mathutils import Vector
a = sys.argv[sys.argv.index('--') + 1:]; OUT = a[0]; files = a[1:]; os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
def load(f):
    before = set(bpy.data.objects)
    lw_canon.io.import_raw(f)
    obs = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for o in obs: o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    if len(obs) > 1: bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active; bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for x in [x for x in bpy.data.objects if x not in before and x != o]: bpy.data.objects.remove(x)
    return o
def front_sil(V, F, W=256, ext=None):
    """front (-Y) orthographic silhouette of a mesh, W px, framed by ext (half-width, height); numpy fan rasterizer"""
    hw, hh = ext; V = np.asarray(V); X = (V[:, 0] / (2 * hw) + 0.5) * W; Y = (1 - V[:, 2] / hh) * W; out = np.zeros((W, W), bool)
    for f_ in F:
        for k in range(1, len(f_) - 1):
            ix = [f_[0], f_[k], f_[k + 1]]; xs, ys = X[ix], Y[ix]
            x0, x1 = max(int(xs.min()), 0), min(int(xs.max()) + 1, W - 1); y0, y1 = max(int(ys.min()), 0), min(int(ys.max()) + 1, W - 1)
            if x1 < x0 or y1 < y0: continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(d) < 1e-12: continue
            l0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d; l1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
            out[y0:y1 + 1, x0:x1 + 1] |= (l0 >= 0) & (l1 >= 0) & (1 - l0 - l1 >= 0)
    return out
rows = []; ref_h = None; ref_sil = None
for i, f in enumerate(files):
    o = load(f); me = o.data
    co = np.array([v.co[:] for v in me.vertices]); lo, hi = co.min(0), co.max(0)
    h = hi[2] - lo[2]
    if ref_h is None: ref_h = h
    s = ref_h / h; c = (lo + hi) / 2
    for v in me.vertices: v.co = (Vector(v.co) - Vector(c)) * s + Vector((0, 0, ref_h / 2))
    Fl = [tuple(p.vertices) for p in me.polygons]; ext = (0.6 * ref_h, 1.05 * ref_h); rot = 0
    if ref_sil is None: ref_sil = front_sil([v.co[:] for v in me.vertices], Fl, ext=ext)
    else:                                                               # orient: the FBX forward axis differs; keep the turn whose front silhouette matches the reference
        best = None
        for deg in (0, 90, -90, 180):
            R = np.array([[math.cos(math.radians(deg)), -math.sin(math.radians(deg)), 0], [math.sin(math.radians(deg)), math.cos(math.radians(deg)), 0], [0, 0, 1]])
            V2 = np.array([v.co[:] for v in me.vertices]) @ R.T; sil = front_sil(V2, Fl, ext=ext); iou = (sil & ref_sil).sum() / max((sil | ref_sil).sum(), 1)
            if best is None or iou > best[0]: best = (iou, deg, V2)
        rot = best[1]
        for k, v in enumerate(me.vertices): v.co = Vector(best[2][k])
        me.update()
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.triangulate(bm, faces=bm.faces[:])
    P = np.array([[v.co[:] for v in f_.verts] for f_ in bm.faces]); ntri = len(P); bm.free()
    co = np.array([v.co[:] for v in me.vertices]); lo, hi = co.min(0), co.max(0); s = 1.0
    W = np.round(P.reshape(-1, 3) / (1e-5 * ref_h)).astype(np.int64); _, wid = np.unique(W, axis=0, return_inverse=True); wid = wid.reshape(-1, 3)
    E = {}
    for t in wid:
        for k in range(3):
            e = tuple(sorted((int(t[k]), int(t[(k + 1) % 3])))); E[e] = E.get(e, 0) + 1
    bnd = [e for e, n in E.items() if n == 1]; nm = sum(1 for n in E.values() if n >= 3)
    par = {}
    def find(x):
        while par.get(x, x) != x: x = par[x]
        return x
    for e in bnd: par[find(e[0])] = find(e[1])
    loops = len({find(e[0]) for e in bnd})
    par2 = list(range(wid.max() + 1))
    def f2(x):
        while par2[x] != x: par2[x] = par2[par2[x]]; x = par2[x]
        return x
    for t in wid: par2[f2(t[0])] = f2(t[1]); par2[f2(t[1])] = f2(t[2])
    shells = len({f2(t[0]) for t in wid})
    np.savez(os.path.join(OUT, f'mesh{i}.npz'), P=P.astype(np.float32))
    rows.append({'file': os.path.basename(f), 'polygons': len(me.polygons), 'triangles': ntri, 'open_edges': len(bnd), 'open_loops': loops, 'edges_3plus_faces': nm,
                 'shells': shells, 'height_scale_to_ref': round(float(s), 4), 'turned_deg_z': rot, 'bbox_m': [round(float(x), 3) for x in (hi - lo) * s]})
    print(rows[-1])
    o.name = f'mesh{i}'; o.hide_render = True
# renders
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.light = 'MATCAP'; sc.display.shading.color_type = 'SINGLE'
sc.display.shading.single_color = (0.8, 0.75, 0.65); sc.render.resolution_x = sc.render.resolution_y = 700; sc.render.film_transparent = True
cam = bpy.data.cameras.new('c'); co_ = bpy.data.objects.new('c', cam); sc.collection.objects.link(co_); sc.camera = co_; cam.type = 'ORTHO'; cam.ortho_scale = ref_h * 1.15
views = {'front': ((0, -5, ref_h / 2), (90, 0, 0)), 'back': ((0, 5, ref_h / 2), (90, 0, 180)), 'left': ((5, 0, ref_h / 2), (90, 0, 90)), 'right': ((-5, 0, ref_h / 2), (90, 0, -90)),
         'top': ((0, 0, ref_h + 5), (0, 0, 0)), 'bottom': ((0, 0, -5), (180, 0, 0)),
         'pauldronR_top': ((-0.32 * ref_h, 0, ref_h + 5), (0, 0, 0)), 'pauldronL_top': ((0.32 * ref_h, 0, ref_h + 5), (0, 0, 0)),
         'pauldronR_bottom': ((-0.32 * ref_h, 0, -5), (180, 0, 0)), 'pauldronL_bottom': ((0.32 * ref_h, 0, -5), (180, 0, 0))}
ZOOM = {k: 0.42 for k in views if k.startswith('pauldron')}
if os.environ.get('MC_VIEWS') == 'oblique':                              # raking, studio-lit views from 45 deg above / below each shoulder, outside
    sc.display.shading.light = 'STUDIO'; sc.display.shading.show_cavity = True; sc.display.shading.cavity_type = 'BOTH'; sc.display.shading.show_shadows = True
    views = {}
    for sd, sg in (('R', -1), ('L', 1)):
        for nm, el in (('above', 45), ('below', -45)):
            d = Vector((sg * math.cos(math.radians(el)), 0, math.sin(math.radians(el))))
            tgt = Vector((sg * 0.38 * ref_h, 0, 0.78 * ref_h)); pos = tgt + 5 * d
            views[f'sh{sd}_{nm}'] = (tuple(pos), tuple(math.degrees(x) for x in (-d).to_track_quat('-Z', 'Y').to_euler()))
    ZOOM = {k: 0.5 for k in views}
for i in range(len(files)):
    ob = bpy.data.objects[f'mesh{i}']; ob.hide_render = False
    for vn, (pos, rot) in views.items():
        co_.location = pos; co_.rotation_euler = [math.radians(x) for x in rot]; cam.ortho_scale = ref_h * ZOOM.get(vn, 1.15)
        sc.render.filepath = os.path.join(OUT, f'mesh{i}_{vn}.png'); bpy.ops.render.render(write_still=True)
    ob.hide_render = True
json.dump(rows, open(os.path.join(OUT, 'compare.json'), 'w'), indent=1); print('COMPARE DONE')
