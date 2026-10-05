# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/uv_patches.py, sha256 42dbf2c8cbda) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): give patch faces (patch_holes.py: orig_poly == -1) their own UV islands inside the existing atlas without
# moving a single original island: the original UVs are pinned, the patches Smart-UV-projected, then every island packed with
# pinned islands LOCKED, so patches land in the atlas's free space. patch_holes.py leaves patches with their nearest rim
# vertex's UVs - a smear across every patch in the texture pass (seen 2026-10-04).
# FIRST, the island puzzle (the captain, 2026-10-04: "make islands whole that are missing their owed pieces"): a patch whose rim
# is shared among the islands around its rim: each patch face joins the island of its nearest rim face, each island's own 3D->UV
# map (an affine fit on its faces within 8 cm) is extended over its share, and the rim residual is relaxed inward with the rim
# pinned, so every island gets its owed piece and the texture runs across the repair. Measured: a single-island-only rule filled
# 2 of 23 patches (rims cross seams). A patch whose filled UVs fold (more than --max-flip of its faces flipped against the faces
# around it) falls back to its own island: Smart UV project + pack with the originals locked.
# blender -b -P uv_patches.py -- <mesh.fbx> <orig_poly.npy> <out.fbx> [--margin 0.002] [--angle 66]
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, 'UV islands for patch faces, packed into the atlas free space with the original islands locked')
    else: print(f'error: {len(_A)} argument(s); at least 3 needed')
    _ax.helps(['blender -b -P scripts/partseg/uv_patches.py -- <mesh.fbx> <orig_poly.npy> <out.fbx>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import argparse, bpy, bmesh, math, numpy as np
ap = argparse.ArgumentParser(prog='uv_patches.py'); [ap.add_argument(k) for k in ('mesh', 'orig', 'out')]
ap.add_argument('--margin', type=float, default=0.002); ap.add_argument('--angle', type=float, default=66.0); ap.add_argument('--max-flip', type=float, default=0.01)
a = ap.parse_args(_A); orig = np.load(a.orig)
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=a.mesh)
ob = next(o for o in bpy.data.objects if o.type == 'MESH'); me = ob.data
if len(orig) != len(me.polygons): _ax.refuse(f'orig_poly has {len(orig)} rows for {len(me.polygons)} polygons', [])
bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
uv0 = np.empty(len(me.loops) * 2, np.float32); me.uv_layers.active.data.foreach_get('uv', uv0)
patch = orig < 0
bpy.ops.object.mode_set(mode='EDIT'); bm = bmesh.from_edit_mesh(me); bm.faces.ensure_lookup_table(); bm.verts.ensure_lookup_table(); ul = bm.loops.layers.uv.active
# ---- the island puzzle
comp_of = {}; comps = []
for f in bm.faces:
    if not patch[f.index] or f.index in comp_of: continue
    stack = [f]; cid = len(comps); comps.append([])
    while stack:
        g = stack.pop()
        if g.index in comp_of: continue
        comp_of[g.index] = cid; comps[cid].append(g)
        for e in g.edges:
            for h in e.link_faces:
                if patch[h.index] and h.index not in comp_of: stack.append(h)
filled = 0; fallback = np.zeros(len(me.polygons), bool); why = {}
def sarea(f, uvs):
    pts = [uvs[l] for l in f.loops]; s_ = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % len(pts)]; s_ += x1 * y2 - x2 * y1
    return s_ / 2
# islands of the ORIGINAL faces (corners welded by vertex + UV), so a patch can be shared among the islands around its rim
par = list(range(len(bm.faces)))
def find(x):
    while par[x] != x: par[x] = par[par[x]]; x = par[x]
    return x
key = {}
for f in bm.faces:
    if patch[f.index]: continue
    for l in f.loops:
        k = (l.vert.index, round(l[ul].uv.x, 6), round(l[ul].uv.y, 6))
        if k in key: par[find(f.index)] = find(key[k])
        else: key[k] = f.index
isl = np.array([find(f.index) for f in bm.faces])
for cid, fs in enumerate(comps):
    verts = {v for f in fs for v in f.verts}
    ring = {g for v in verts for g in v.link_faces if not patch[g.index]}          # the original faces around the hole
    if len(ring) < 3: fallback[[f.index for f in fs]] = True; why[cid] = 'no rim'; continue
    rc = np.array([g.calc_center_median()[:] for g in ring]); ri = np.array([isl[g.index] for g in ring])
    # each patch face joins the island of its nearest ring face
    fc = np.array([f.calc_center_median()[:] for f in fs]); own_i = ri[np.argmin(((fc[:, None, :] - rc[None, :, :]) ** 2).sum(2), 1)]
    uvs = {}; bad = False; parts_ = {}
    for k in np.unique(own_i):
        sub = [f for f, o in zip(fs, own_i) if o == k]
        # affine 3D -> UV of island k, fitted on its faces near the hole (its own parametrization, extended)
        cen = fc[own_i == k].mean(0); src = [g for g in bm.faces if isl[g.index] == k and not patch[g.index] and (g.calc_center_median() - __import__('mathutils').Vector(cen)).length < 0.08 / max(ob.scale)]
        if len(src) < 3: src = [g for g in ring if isl[g.index] == k]
        X = np.array([[*l.vert.co, 1.0] for g in src for l in g.loops]); Y = np.array([[l[ul].uv.x, l[ul].uv.y] for g in src for l in g.loops])
        if len(X) < 4: bad = True; break
        sv = {v for f in sub for v in f.verts}
        pred = {v: np.zeros(2) for v in sv}                                  # harmonic: no 3D fit (an affine 3D->UV fit mirrored
                                                                             # patches whose surface faces away from the island plane)
        # exact UVs on the rim (this island's corner UV at that vertex), residual relaxed inward, rim pinned
        pin = {}
        for v in sv:
            u = [np.array(l[ul].uv) for l in v.link_loops if not patch[l.face.index] and isl[l.face.index] == k]
            if u: pin[v] = u[0] - pred[v]
        free = [v for v in sv if v not in pin]; ix = {v: i for i, v in enumerate(free)}
        R = np.tile(np.mean(list(pin.values()), 0) if pin else np.zeros(2), (len(free), 1)); nbr = [[e.other_vert(v) for e in v.link_edges if e.other_vert(v) in sv] for v in free]
        if not pin: bad = True; break
        for _ in range(600):
            R = np.array([np.mean([R[ix[w]] if w in ix else pin[w] for w in n], 0) if n else R[i] for i, n in enumerate(nbr)]) if free else R
        for f in sub:
            for l in f.loops: uvs[l] = pred[l.vert] + (pin[l.vert] if l.vert in pin else R[ix[l.vert]])
        refk = [sarea(g, {l: np.array(l[ul].uv) for l in g.loops}) for g in ring if isl[g.index] == k]
        sk = np.sign(np.sum(np.sign(refk))) or 1.0
        fl = sum(1 for f in sub if np.sign(sarea(f, uvs)) != sk)
        parts_[int(k)] = (len(sub), fl)
    if bad: fallback[[f.index for f in fs]] = True; why[cid] = 'fit'; continue
    flips = sum(fl for _, fl in parts_.values())                           # each share judged against its own island
    if flips > a.max_flip * len(fs): fallback[[f.index for f in fs]] = True; why[cid] = f'folds {flips}/{len(fs)} over {len(parts_)} islands'; continue
    for f in fs:
        for l in f.loops: l[ul].uv = tuple(uvs[l])
    filled += 1; why[cid] = f'filled across {len(parts_)} island(s)'
bmesh.update_edit_mesh(me)
patch_fill = patch & ~fallback; patch = fallback.copy()                  # only the fallbacks go on to their own islands
for f in bm.faces:
    f.select_set(bool(patch[f.index]))
    for l in f.loops: l[ul].pin_uv = not patch[f.index]
bmesh.update_edit_mesh(me)
bpy.context.scene.tool_settings.use_uv_select_sync = True
if patch.any(): bpy.ops.uv.smart_project(angle_limit=math.radians(a.angle), island_margin=a.margin, scale_to_bounds=False)
bm = bmesh.from_edit_mesh(me)
for f in bm.faces: f.select_set(True)
bmesh.update_edit_mesh(me)
if patch.any(): bpy.ops.uv.pack_islands(rotate=True, margin=a.margin, pin=True, pin_method='LOCKED', udim_source='CLOSEST_UDIM')
bm = bmesh.from_edit_mesh(me)
for f in bm.faces:
    for l in f.loops: l[ul].pin_uv = False
bmesh.update_edit_mesh(me); bpy.ops.object.mode_set(mode='OBJECT')
uv1 = np.empty(len(me.loops) * 2, np.float32); me.uv_layers.active.data.foreach_get('uv', uv1)
li = np.repeat(np.arange(len(me.polygons)), [p.loop_total for p in me.polygons])
keep = ~(patch | patch_fill)
moved_orig = float(np.abs(uv1 - uv0).reshape(-1, 2)[keep[li]].max()) if keep.any() else 0.0
pu = uv1.reshape(-1, 2)[patch[li]]
bpy.ops.export_scene.fbx(filepath=a.out, use_selection=True, mesh_smooth_type='FACE', add_leaf_bones=False, bake_anim=False)
_ax.kv({'patches': len(comps), 'filled_into_their_island': filled, 'own_island': len(comps) - filled, 'fallback_why': why, 'patch_faces': int((patch | patch_fill).sum()), 'original_uv_max_move': round(moved_orig, 6), 'patch_uv_in_0_1': bool(((pu >= 0) & (pu <= 1)).all()) if len(pu) else None, 'out': a.out})
if moved_orig > 1e-5: _ax.refuse(f'original UVs moved by {moved_orig:.6f} - the lock did not hold', [])
