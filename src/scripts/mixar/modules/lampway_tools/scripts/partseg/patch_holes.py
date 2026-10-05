# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/patch_holes.py, sha256 32b43f60701b) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): apply the captain's mesh QA rulings to a mesh - delete the faces he ruled deleted, and patch every open
# loop he ruled a hole - writing a NEW mesh plus maps, so the parts/texture pipeline re-runs on it.
# Holes come from meshqa decisions (scripts/meshqa/qa_read_marks.py rows, answer 'hole') matched to the mesh's boundary edges by
# the candidate's segments (edge midpoints within --match-mm). Fill: bmesh beauty triangle fill, then the patch's interior
# edges are split until none is longer than --edge-cm, then its interior vertices are relaxed (umbrella Laplacian, the loop's
# rim pinned) so a patch across a curved plate bows with it instead of lying flat. Each patch is wound like the faces it
# borders; its owner is the part bordering most of the loop (--owner-override HOLE=part for a ruled exception); its UVs are
# the nearest rim vertex's (a placeholder - the texture pass re-projects).
# Measured 2026-10-04 on chest seed 9c052d49: the back plate's holes are in Tripo's generation itself (the original and the
# Smart UV clone carry the same 312 loops); the captain ruled 11 holes (8 named, 3 by "whatever else in that region").
# blender -b -P patch_holes.py -- <mesh.fbx> <owner_poly.npy> <recipe.json> <candidates.json> <decisions.jsonl> <out_prefix>
#        [--deletions deletions.json] [--session S] [--turn -90] [--edge-cm 1.5] [--relax 150] [--match-mm 2]
#   candidates were measured with --turn; their coordinates are turned back into the mesh's own frame here.
# Writes <out_prefix>.fbx (the mesh's own frame), <out_prefix>_owner_poly.npy, <out_prefix>_orig_poly.npy (source polygon id per
# face, -1 for a patch face) and <out_prefix>_patch.json (per hole: faces, area, owner, rim edges matched / expected).
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
if __name__ == '__main__' and len(_A) < 6:
    if not _A: _ax.home(__file__, "Apply the captain's mesh QA rulings: delete ruled faces, patch ruled holes with curved fills")
    else: print(f'error: {len(_A)} argument(s); at least 6 needed')
    _ax.helps(['blender -b -P scripts/partseg/patch_holes.py -- <mesh.fbx> <owner_poly.npy> <recipe.json> <candidates.json> <decisions.jsonl> <out_prefix>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import argparse, bpy, bmesh, json, math, numpy as np
from mathutils import Vector, Matrix, kdtree
ap = argparse.ArgumentParser(prog='patch_holes.py'); [ap.add_argument(k) for k in ('mesh', 'owner', 'recipe', 'cands', 'decisions', 'out')]
ap.add_argument('--deletions'); ap.add_argument('--session'); ap.add_argument('--turn', type=float, default=-90.0)
ap.add_argument('--edge-cm', type=float, default=1.5); ap.add_argument('--relax', type=int, default=150); ap.add_argument('--match-mm', type=float, default=2.0)
ap.add_argument('--owner-override', action='append', default=[]); ap.add_argument('--bridge-cm', type=float, default=6.0)
ap.add_argument('--relabel-orig', help='json {"relabels": [{"faces_orig": [...], "to": part, "why": ...}]} - ruled labels by SOURCE face id (stable across rebuilds)')
ap.add_argument('--relabel', action='append', default=[], help='FROM:TO:WITH - faces labelled FROM on small shells (< 2000 faces) that also carry WITH faces become TO')
a = ap.parse_args(_A)
names = list(json.load(open(a.recipe))['parts']); own = np.load(a.owner)
cands = {c['id']: c for c in json.load(open(a.cands))['candidates']}
latest = {}                                                                  # the LATEST answer per candidate wins (a correction row
for ln in open(a.decisions):                                                 # overrides an earlier ruling - L027, 2026-10-04)
    r = json.loads(ln)
    if r['descriptor'].get('kind') == 'open_loop' and (not a.session or r.get('session') == a.session): latest[r['descriptor']['id']] = r.get('answer')
holes = sorted(k for k, v in latest.items() if v == 'hole'); ovr = dict(x.split('=') for x in a.owner_override)
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=a.mesh)
ob = next(o for o in bpy.data.objects if o.type == 'MESH'); me = ob.data
if len(own) != len(me.polygons): _ax.refuse(f'owner has {len(own)} labels for {len(me.polygons)} polygons', [])
me.attributes.new('orig', 'INT', 'FACE').data.foreach_set('value', np.arange(len(me.polygons)))
# the candidates' frame -> the mesh's object frame: undo the turn, then the object's own world matrix
Mw = ob.matrix_world.copy(); R = Matrix.Rotation(math.radians(-a.turn), 4, 'Z'); toObj = Mw.inverted() @ R
bm = bmesh.new(); bm.from_mesh(me); lay = bm.faces.layers.int['orig']; uvl = bm.loops.layers.uv.active
if a.deletions:
    dl = set(json.load(open(a.deletions))['polys']); bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[lay] in dl], context='FACES_ONLY')
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5 / max(ob.scale)); bm.edges.ensure_lookup_table()
refill_rep = []
pl = bm.faces.layers.int.new('patch')
if a.deletions:                                                              # refill: faces ruled bad but whose AREA must stay covered
    for rf in json.load(open(a.deletions)).get('refill', []):              # (a fold: two triangles over one spot, a gap beside it)
        dead = [f for f in bm.faces if f[lay] in set(rf['polys'])]
        if not dead: refill_rep.append({'polys': rf['polys'], 'error': 'faces not found'}); continue
        ring_e = {e for f in dead for e in f.edges}
        nbp = {}
        for e in ring_e:
            for g in e.link_faces:
                if g not in dead and g[lay] >= 0: nbp[names[int(own[g[lay]])]] = nbp.get(names[int(own[g[lay]])], 0) + 1
        bmesh.ops.delete(bm, geom=dead, context='FACES_ONLY')
        es = [e for e in ring_e if e.is_valid and e.is_boundary]
        r_ = bmesh.ops.holes_fill(bm, edges=es, sides=0); nf = list(r_['faces']); how_ = 'holes_fill'
        if not nf:
            r_ = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=es); nf = [f for f in r_['geom'] if isinstance(f, bmesh.types.BMFace)]; how_ = 'triangle_fill'
        if not nf and es:                                                    # a self-touching opening: fan from its centre, each
            cv = bm.verts.new(sum((v.co for e in es for v in e.verts), Vector()) / (2 * len(es))); how_ = 'fan'   # wound against its neighbour
            for e in es:
                v0, v1 = e.verts
                for lo in e.link_faces[0].loops:
                    if lo.edge == e: v0, v1 = lo.link_loop_next.vert, lo.vert
                try: nf.append(bm.faces.new((v0, v1, cv)))
                except ValueError: pass
        if nf: nf = list(bmesh.ops.triangulate(bm, faces=nf, quad_method='BEAUTY', ngon_method='BEAUTY')['faces'])
        for f in nf: f[lay] = -1; f[pl] = -2                                 # -2: a refill, owner set below
        refill_rep.append({'polys': rf['polys'], 'faces': len(nf), 'fill': how_, 'owner': rf.get('owner') or (max(nbp, key=nbp.get) if nbp else None)})
    bm.edges.ensure_lookup_table()
scale = max(ob.scale) * max(Mw.to_scale())                                   # object units -> metres (FBX imports at 0.01 x 100)
bnd = [e for e in bm.edges if e.is_boundary]
kd = kdtree.KDTree(len(bnd))
for i, e in enumerate(bnd): kd.insert((e.verts[0].co + e.verts[1].co) / 2, i)
kd.balance()
rl_ = bm.verts.layers.int.new('rim'); rep = []
# measured 2026-10-04: bmesh.ops.subdivide_edges invalidates every Python vertex handle, so rim membership lives in a vertex
# layer and rim UVs in plain lists, never in BMVert-keyed dicts
for k, hid in enumerate(holes):
    c = cands[hid]; want = set()
    for p0, p1 in c['segments_m']:
        m = toObj @ ((Vector(p0) + Vector(p1)) / 2); co, i, d = kd.find(m)
        if d * scale * 1000 <= a.match_mm: want.add(i)
    bm.edges.ensure_lookup_table()
    edges = [bnd[i] for i in sorted(want) if bnd[i].is_valid and bnd[i].is_boundary]
    # complete the rim along the boundary when the matched set falls a few edges short of closed (measured: L018 85 of 88), as
    # long as the boundary component it lies on is not much longer than the candidate (a giant multi-part loop is not walked)
    if edges:
        comp, stack, seen_e = [], [edges[0]], set()
        while stack and len(comp) < 20000:
            e = stack.pop()
            if e in seen_e: continue
            seen_e.add(e); comp.append(e)
            for v in e.verts:
                for f in v.link_edges:
                    if f.is_boundary and f not in seen_e: stack.append(f)
        clen = sum(e.calc_length() for e in comp) * scale
        lp = c.get('loop_perimeter_m', c['perimeter_m'])                     # a split piece fills its whole loop only when that loop
        cap = 1.05 * lp if (lp > c['perimeter_m'] + 1e-6 and lp <= 3.0) else 1.25 * c['perimeter_m']   # is hole-sized (L027 2.25 m), never the 16 m hem loop (L018)
        if len(comp) > len(edges) and clen <= cap: edges = comp            # a ruled piece of a split loop fills its whole loop (L027)
    if len(edges) < 3: rep.append({'hole': hid, 'error': f'matched {len(edges)} rim edges of {len(c["segments_m"])}'}); continue
    rim_pos, rim_uv, nb = [], [], {}
    for e in edges:
        f0 = e.link_faces[0]; pn = names[int(own[f0[lay]])] if f0[lay] >= 0 else None
        if pn: nb[pn] = nb.get(pn, 0) + e.calc_length()                       # owner by bordering length per PART (it voted per face: a bug)
        for l in f0.loops:
            if l.vert in e.verts:
                l.vert[rl_] = k + 1; rim_pos.append(l.vert.co.copy()); rim_uv.append(l[uvl].uv.copy() if uvl is not None else None)
    owner = ovr.get(hid) or max(nb, key=nb.get)
    res = bmesh.ops.holes_fill(bm, edges=edges, sides=0); new = res['faces']; how = 'holes_fill'
    if not new:                                                              # an open chain: bridge its ends (gaps <= --bridge-cm), fill again
        deg = {}
        for e in edges:
            for v in e.verts: deg[v] = deg.get(v, 0) + 1
        ends = [v for v, n in deg.items() if n == 1]; added = 0
        while len(ends) >= 2 and added < 20:
            v0 = ends.pop(); j = min(range(len(ends)), key=lambda i: (ends[i].co - v0.co).length); v1 = ends.pop(j)
            if (v1.co - v0.co).length * scale * 100 > a.bridge_cm: break
            if bm.edges.get((v0, v1)) is None: edges.append(bm.edges.new((v0, v1))); added += 1
        if added:
            res = bmesh.ops.holes_fill(bm, edges=edges, sides=0); new = res['faces']; how = f'holes_fill+bridge{added}'
    if not new:
        res = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges); new = [f for f in res['geom'] if isinstance(f, bmesh.types.BMFace)]; how = 'triangle_fill'
    if not new:                                                              # last resort: a fan from the rim's centroid (a loop touching
        cv = bm.verts.new(sum((v.co for e in edges for v in e.verts), Vector()) / (2 * len(edges)))   # itself at a vertex: L042)
        new = []
        for e in edges:
            v0, v1 = e.verts; nbf = e.link_faces[0]
            for lo in nbf.loops:
                if lo.edge == e: v0, v1 = lo.link_loop_next.vert, lo.vert         # run the edge opposite to its neighbour
            try: new.append(bm.faces.new((v0, v1, cv)))
            except ValueError: pass
        how = 'fan'
    if not new: rep.append({'hole': hid, 'error': 'no fill made faces', 'rim_edges_matched': len(edges)}); continue
    for f in new: f[pl] = k + 1; f[lay] = -1
    bmesh.ops.triangulate(bm, faces=new, quad_method='BEAUTY', ngon_method='BEAUTY')
    lim = a.edge_cm / 100 / scale
    for _ in range(10):                                                      # bounded refinement of the patch interior
        pf = [f for f in bm.faces if f[pl] == k + 1]
        inner = list({e for f in pf for e in f.edges if len(e.link_faces) == 2 and all(g[pl] == k + 1 for g in e.link_faces) and e.calc_length() > lim})
        if not inner: break
        bmesh.ops.subdivide_edges(bm, edges=inner, cuts=1, use_grid_fill=False)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if f[pl] == k + 1])
    pf = [f for f in bm.faces if f[pl] == k + 1]; pv = {v for f in pf for v in f.verts}
    inner_v = [v for v in pv if v[rl_] != k + 1 and all(g[pl] == k + 1 for g in v.link_faces)]
    for _ in range(a.relax):                                                 # umbrella relax, rim pinned: the patch bows with the plate
        newco = [sum((e.other_vert(v).co for e in v.link_edges), Vector()) / max(len(v.link_edges), 1) for v in inner_v]
        for v, cc in zip(inner_v, newco): v.co = cc
    flips = 0                                                                # winding: across a rim edge, opposite to the original neighbour
    for f in pf:
        for l in f.loops:
            e = l.edge; other = [g for g in e.link_faces if g[pl] != k + 1]
            if not other: continue
            mine = (l.vert, l.link_loop_next.vert)
            for lo in other[0].loops:
                if lo.edge == e: flips += 1 if (lo.vert, lo.link_loop_next.vert) == mine else -1
    if flips > 0: bmesh.ops.reverse_faces(bm, faces=pf)
    if uvl is not None and rim_pos:
        kdv = kdtree.KDTree(len(rim_pos))
        for i, pp in enumerate(rim_pos): kdv.insert(pp, i)
        kdv.balance()
        for f in pf:
            for l in f.loops: _, j, _ = kdv.find(l.vert.co); l[uvl].uv = rim_uv[j]
    area = sum(f.calc_area() for f in pf) * scale * scale
    rep.append({'hole': hid, 'owner': owner, 'fill': how, 'faces': len(pf), 'area_cm2': round(area * 1e4, 1), 'rim_edges_matched': len(edges),
                'rim_edges_expected': len(c['segments_m']), 'interior_vertices_relaxed': len(inner_v), 'flipped': flips > 0})
# measured 2026-10-04: the FBX importer drops zero-area and vertex-duplicate faces (chest_p6: 44,263 written, 44,166 read back),
# which silently shifts every per-face map - drop them here, before any map is written, and prove the round trip below
bm.faces.ensure_lookup_table()
seen_sets, bad = set(), []
for f in bm.faces:
    ks = frozenset(v.index for v in f.verts)
    if f.calc_area() * scale * scale < 1e-10 or len(ks) < len(f.verts) or ks in seen_sets: bad.append(f)
    else: seen_sets.add(ks)
dropped = {'zero_area_or_duplicate': len(bad), 'patch': sum(1 for f in bad if f[pl] > 0)}
bmesh.ops.delete(bm, geom=bad, context='FACES_ONLY'); bm.faces.ensure_lookup_table()
orig = np.array([f[lay] for f in bm.faces]); pid = np.array([f[pl] for f in bm.faces])
own_new = np.where(orig >= 0, own[np.maximum(orig, 0)], -1)
relabelled = {}
for r in refill_rep:
    if r.get('owner'): own_new[pid == -2] = names.index(r['owner'])          # (one owner for every refill: they are rare; refine if mixed)
if a.relabel_orig:
    for r in json.load(open(a.relabel_orig))['relabels']:
        m = np.isin(orig, r['faces_orig']); own_new[m] = names.index(r['to']); relabelled[r['why'][:60]] = int(m.sum())
if a.relabel:
    vsh = {}; par = list(range(len(bm.verts)))
    def fnd(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    bm.verts.ensure_lookup_table()
    for e in bm.edges: par[fnd(e.verts[0].index)] = fnd(e.verts[1].index)
    fsh = np.array([fnd(f.verts[0].index) for f in bm.faces]); cnt = {}
    for x in fsh: cnt[x] = cnt.get(x, 0) + 1
    for spec in a.relabel:
        fr, to, wi = spec.split(':'); fi, ti, wi_ = names.index(fr), names.index(to), names.index(wi)
        small = np.array([cnt[x] < 2000 for x in fsh]); carry = set(fsh[(own_new == wi_) & small].tolist())
        m = (own_new == fi) & small & np.isin(fsh, list(carry)); own_new[m] = ti; relabelled[spec] = int(m.sum())
for r in rep:
    if 'owner' in r: own_new[pid == holes.index(r['hole']) + 1] = names.index(r['owner'])
bm.to_mesh(me); bm.free(); me.update()
me.attributes.new('part', 'INT', 'FACE').data.foreach_set('value', own_new.astype(np.int32))   # the label rides the mesh too
bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
bpy.ops.export_scene.fbx(filepath=a.out + '.fbx', use_selection=True, mesh_smooth_type='FACE', add_leaf_bones=False, bake_anim=False)
np.save(a.out + '_owner_poly.npy', own_new.astype(np.int32)); np.save(a.out + '_orig_poly.npy', orig.astype(np.int32))
bpy.ops.wm.save_as_mainfile(filepath=a.out + '.blend', copy=True)
before = set(bpy.data.objects.keys()); bpy.ops.import_scene.fbx(filepath=a.out + '.fbx')         # the round trip, proved
back = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before and bpy.data.objects[n].type == 'MESH']
if not back or len(back[0].data.polygons) != len(own_new): _ax.refuse(f'FBX round trip changed the face count: wrote {len(own_new)}, read {len(back[0].data.polygons) if back else 0}', [])
json.dump({'mesh': a.mesh, 'deletions': a.deletions, 'relabelled': relabelled, 'dropped_before_export': dropped, 'refills': refill_rep, 'fbx_round_trip_faces': len(own_new), 'holes': rep, 'faces_out': int(len(orig)), 'patch_faces': int((orig < 0).sum())}, open(a.out + '_patch.json', 'w'), indent=1)
_ax.table('holes', [{k: r.get(k) for k in ('hole', 'owner', 'fill', 'faces', 'area_cm2', 'rim_edges_matched', 'rim_edges_expected', 'flipped', 'error')} for r in rep],
          ['hole', 'owner', 'fill', 'faces', 'area_cm2', 'rim_edges_matched', 'rim_edges_expected', 'flipped', 'error'])
_ax.helps([f'blender -b -P scripts/meshqa/mesh_qa.py -- {a.out}.fbx {a.out}_owner_poly.npy {a.recipe} <qa_out> --turn {a.turn}  (re-check: the patched loops should be gone)'])
