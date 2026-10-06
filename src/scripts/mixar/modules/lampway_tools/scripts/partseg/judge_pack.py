# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/judge_pack.py, sha256 bad384205892) on 2026-10-06. The header below, with the measured rules behind
# the code, is the original's; the first argument is the mesh (mesh_load.py), the two vote attributes are arguments (default the shelf's), the
# context views are framed by the mesh's bounds, and island_vote's one helper used here is inlined.
# SPIKE (2026-10-03): build the review pack for the parts regroup - candidates, decisions and renders - from a
# smart mesh carrying two island-vote groupings (vote_p3sam = A, vote_geosam2 = B).
#   agreed    : an A part and a B part with face IoU >= 0.8 - one candidate.
#   split     : an A part B cuts into >= 2 pieces of >= 10 % each - option A the whole, option B the pieces.
#   merge     : a B part spanning >= 2 A parts at >= 10 % of itself each - option B the whole, option A those A parts.
#   standalone: every other A part - one candidate.
# Renders (Workbench, orthographic, deterministic): per candidate an isolated front/back/side sheet and a context
# sheet (front/back, candidate coloured on the grey chest); per decision one sheet with option A over option B.
# Usage: blender -b --python-use-system-env <votes.blend> -P judge_pack.py -- <object> <out_dir>
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['blender -b --python-use-system-env <votes.blend> -P tools/partseg/judge_pack.py -- <object> <out_dir>']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, 'Build the review pack (candidates, decisions, renders) for a parts regroup')
    else: print(f'error: {len(_A)} argument(s); at least 2 needed')
    _ax.helps(['blender -b --python-use-system-env <votes.blend> -P tools/partseg/judge_pack.py -- <object> <out_dir>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import bpy, bmesh, sys, os, json, numpy as np, colorsys
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
def _face_attr(me, name):
    a = np.empty(len(me.polygons), np.int32)
    me.attributes[name].data.foreach_get('value', a)
    return a
from PIL import Image, ImageDraw, ImageFont

argv = sys.argv[sys.argv.index('--') + 1:]
MESH, OBJ, OUT = argv[0], argv[1], argv[2]
VOTE_A, VOTE_B = (argv[3], argv[4]) if len(argv) >= 5 else ('vote_p3sam', 'vote_geosam2')
import mesh_load; mesh_load.load(MESH)
os.makedirs(OUT + '/cand', exist_ok=True); os.makedirs(OUT + '/ctx', exist_ok=True); os.makedirs(OUT + '/dec', exist_ok=True)
src = bpy.data.objects[OBJ]; me = src.data; nf = len(me.polygons)
A, B = _face_attr(me, VOTE_A), _face_attr(me, VOTE_B)
ua = [int(x) for x in np.unique(A[A >= 0])]; ub = [int(x) for x in np.unique(B[B >= 0])]
na = {a: int((A == a).sum()) for a in ua}; nb = {b: int((B == b).sum()) for b in ub}
inter = {}
for (a, b), c in zip(*np.unique(np.c_[A, B][(A >= 0) & (B >= 0)], axis=0, return_counts=True)):
    inter[(int(a), int(b))] = int(c)

cands, decisions = {}, []
def cand(cid, mask, origin):
    cands[cid] = {'id': cid, 'faces': int(mask.sum()), 'origin': origin, 'mask': mask}
    return cid

agreed_a = set()
for a in ua:
    for b in ub:
        c = inter.get((a, b), 0)
        if c and c / (na[a] + nb[b] - c) >= 0.8:
            agreed_a.add(a); cand(f'P{a:02d}', A == a, f'agreed: P3-SAM {a} = GeoSAM2 {b}')
            decisions.append({'id': f'D_agree_P{a:02d}', 'kind': 'agreed', 'A': [f'P{a:02d}'], 'B': []})
for a in ua:
    if a in agreed_a: continue
    pieces = [b for b in ub if inter.get((a, b), 0) >= 0.1 * na[a]]
    if len(pieces) >= 2:
        cand(f'P{a:02d}', A == a, f'split: P3-SAM {a} whole')
        ids = [cand(f'P{a:02d}g{b:03d}', (A == a) & (B == b), f'split piece: P3-SAM {a} cut by GeoSAM2 {b}') for b in pieces]
        rest = (A == a) & ~np.isin(B, pieces)
        if rest.sum() >= 0.05 * na[a]: ids.append(cand(f'P{a:02d}rest', rest, f'split remainder of P3-SAM {a}'))
        decisions.append({'id': f'D_split_P{a:02d}', 'kind': 'split', 'A': [f'P{a:02d}'], 'B': ids})
for b in ub:
    covers = [a for a in ua if inter.get((a, b), 0) >= 0.1 * nb[b]]
    if len(covers) >= 2:
        cand(f'G{b:03d}', B == b, f'merge: GeoSAM2 {b} whole, spans P3-SAM {covers}')
        for a in covers:
            if f'P{a:02d}' not in cands: cand(f'P{a:02d}', A == a, f'P3-SAM {a}')
        decisions.append({'id': f'D_merge_G{b:03d}', 'kind': 'merge', 'A': [f'P{a:02d}' for a in covers], 'B': [f'G{b:03d}']})
for a in ua:
    if f'P{a:02d}' not in cands:
        cand(f'P{a:02d}', A == a, 'standalone P3-SAM part')
        decisions.append({'id': f'D_solo_P{a:02d}', 'kind': 'standalone', 'A': [f'P{a:02d}'], 'B': []})

# ---- rendering ---------------------------------------------------------------------------------------------------
sc = bpy.context.scene
for o in list(sc.objects):
    if o is not src: o.hide_render = True
src.hide_render = False; src.hide_set(False)
sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading; sh.light = 'STUDIO'; sh.color_type = 'VERTEX'; sh.show_cavity = True
sh.cavity_type = 'WORLD'; sh.show_object_outline = False
sc.render.film_transparent = False
if sc.world: sc.world.color = (0.16, 0.16, 0.16)
sc.render.resolution_x = sc.render.resolution_y = 512; sc.render.image_settings.file_format = 'PNG'
cam = bpy.data.objects.new('judge_cam', bpy.data.cameras.new('judge_cam')); sc.collection.objects.link(cam)
cam.data.type = 'ORTHO'; sc.camera = cam
VIEWS = {'front': ((0, -1, 0), (1.5708, 0, 0)), 'back': ((0, 1, 0), (1.5708, 0, 3.14159)),
         'left': ((1, 0, 0), (1.5708, 0, 1.5708)), 'right': ((-1, 0, 0), (1.5708, 0, -1.5708))}
tot = np.empty(nf, np.int32); me.polygons.foreach_get('loop_total', tot); loop_face = np.repeat(np.arange(nf), tot)
if 'judge_col' in me.color_attributes: me.color_attributes.remove(me.color_attributes['judge_col'])
col = me.color_attributes.new('judge_col', 'BYTE_COLOR', 'CORNER'); me.color_attributes.active_color = col
GREY = np.array([0.42, 0.42, 0.42, 1.0], np.float32)
def pal(k):
    return np.array(colorsys.hsv_to_rgb((k * 0.6180339887 + 0.05) % 1, 0.75, 0.95) + (1.0,), np.float32)
def paint(masks):
    fc = np.tile(GREY, (nf, 1))
    for k, m in enumerate(masks): fc[m] = pal(k)
    col.data.foreach_set('color', fc[loop_face].ravel())
def shoot(path, view, centre, scale):
    d, rot = VIEWS[view]
    cam.location = Vector(centre) + Vector(d) * 5; cam.rotation_euler = rot; cam.data.ortho_scale = scale
    cam.data.clip_end = 20; sc.render.filepath = path; bpy.ops.render.render(write_still=True)
co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
ALO, AHI = co.min(0), co.max(0); ACTR = tuple(float(x) for x in (ALO + AHI) / 2); AEXT = float((AHI - ALO).max()) * 1.15 + 0.01   # the mesh's own bounds frame the context views
fv = [np.array(p.vertices) for p in me.polygons]
FONT = ImageFont.load_default(size=22)
def sheet(paths, caption, out, cols=None):
    ims = [Image.open(p).convert('RGB') for p in paths]; cols = cols or len(ims)
    rows = (len(ims) + cols - 1) // cols; W, H = ims[0].size
    S = Image.new('RGB', (W * cols, H * rows + 36), (25, 25, 25)); d = ImageDraw.Draw(S)
    d.text((10, 6), caption, fill=(235, 235, 235), font=FONT)
    for k, im in enumerate(ims): S.paste(im, ((k % cols) * W, 36 + (k // cols) * H))
    S.save(out)
    for p in paths: os.remove(p)

TMP = OUT + '/_tmp'; os.makedirs(TMP, exist_ok=True)
for cid, c in cands.items():
    m = c['mask']
    # context: whole chest grey, the candidate coloured
    paint([m]); src.hide_render = False
    ps = []
    for v in ('front', 'back'):
        p = f'{TMP}/{cid}_{v}.png'; shoot(p, v, ACTR, AEXT); ps.append(p)
    sheet(ps, f'{cid} in context ({c["faces"]} faces) - {c["origin"]}', f'{OUT}/ctx/{cid}.png')
    # isolated: a temporary object holding only the candidate's faces
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not m[f.index]], context='FACES')
    iso_me = bpy.data.meshes.new('iso'); bm.to_mesh(iso_me); bm.free()
    iso = bpy.data.objects.new('iso', iso_me); sc.collection.objects.link(iso)
    ic = iso_me.color_attributes.get('judge_col'); iso_me.color_attributes.active_color = ic
    vals = np.tile(pal(0), (len(iso_me.loops), 1)); ic.data.foreach_set('color', vals.ravel())
    src.hide_render = True
    vi = np.unique(np.concatenate([fv[i] for i in np.flatnonzero(m)])); lo, hi = co[vi].min(0), co[vi].max(0)
    ctr, ext = (lo + hi) / 2, float(max(hi - lo)) * 1.15 + 0.01
    ps = []
    for v in ('front', 'back', 'left', 'right'):
        p = f'{TMP}/{cid}_iso_{v}.png'; shoot(p, v, ctr, ext); ps.append(p)
    sheet(ps, f'{cid} isolated ({c["faces"]} faces, {ext * 100 / 1.15:.1f} cm across) - front/back/left/right',
          f'{OUT}/cand/{cid}.png')
    bpy.data.objects.remove(iso); bpy.data.meshes.remove(iso_me); src.hide_render = False

for d in decisions:
    if d['kind'] in ('agreed', 'standalone'): continue
    rows = []
    for opt in ('A', 'B'):
        masks = [cands[c]['mask'] for c in d[opt]]; paint(masks)
        for v in ('front', 'back'):
            p = f'{TMP}/{d["id"]}_{opt}_{v}.png'; shoot(p, v, ACTR, AEXT); rows.append(p)
    sheet(rows, f'{d["id"]}: top row option A {d["A"]} | bottom row option B {d["B"]}', f'{OUT}/dec/{d["id"]}.png', cols=2)

json.dump({'object': OBJ, 'votes': [VOTE_A, VOTE_B],
           'candidates': [{k: v for k, v in c.items() if k != 'mask'} | {'face_ids_file': f'masks/{c["id"]}.npy'} for c in cands.values()],
           'decisions': decisions}, open(OUT + '/pack.json', 'w'), indent=1)
os.makedirs(OUT + '/masks', exist_ok=True)
for cid, c in cands.items(): np.save(f'{OUT}/masks/{cid}.npy', np.flatnonzero(c['mask']).astype(np.int32))
print('PACK DONE', len(cands), 'candidates', len(decisions), 'decisions')
