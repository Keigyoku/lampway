# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/render_final.py, sha256 1a1446aa9b68) on 2026-10-06. The header below, with the measured rules behind
# the code, is the original's; the first argument is the mesh (mesh_load.py), and the assembly is framed by its own bounds, not a fixed 1 m box.
# SPIKE (2026-10-03): render a finished part set for review - per part an isolated front/back/left/right sheet and
# a context sheet (part coloured on the grey assembly), plus assembled front/back/left/right with every part in its
# own colour and an UNASSIGNED sheet. Workbench, orthographic, deterministic.
# Usage: blender -b --python-use-system-env <votes.blend> -P render_final.py -- <object> <owner.npy> <recipe.json> <out_dir>
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['blender -b --python-use-system-env <votes.blend> -P tools/partseg/render_final.py -- <object> <owner.npy> <recipe.json> <out_dir>']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 5:
    if not _A: _ax.home(__file__, 'Render a finished part set for review: per-part isolated sheets and the assembled set')
    else: print(f'error: {len(_A)} argument(s); at least 4 needed')
    _ax.helps(['blender -b --python-use-system-env <votes.blend> -P tools/partseg/render_final.py -- <object> <owner.npy> <recipe.json> <out_dir>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import bpy, bmesh, sys, os, json, numpy as np, colorsys
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

argv = sys.argv[sys.argv.index('--') + 1:]
MESH, OBJ, OWNER, RECIPE, OUT = argv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import mesh_load; mesh_load.load(MESH)
for d in ('part', 'ctx', 'assembly'): os.makedirs(f'{OUT}/{d}', exist_ok=True)
src = bpy.data.objects[OBJ]; me = src.data; nf = len(me.polygons)
owner = np.load(OWNER); names = list(json.load(open(RECIPE))['parts'])
sc = bpy.context.scene
for o in list(sc.objects):
    if o is not src: o.hide_render = True
src.hide_render = False
sc.render.engine = 'BLENDER_WORKBENCH'; sh = sc.display.shading
sh.light = 'STUDIO'; sh.color_type = 'VERTEX'; sh.show_cavity = True; sh.cavity_type = 'WORLD'
sc.render.resolution_x = sc.render.resolution_y = 512; sc.render.image_settings.file_format = 'PNG'
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); cam.data.type = 'ORTHO'; sc.camera = cam
VIEWS = {'front': ((0, -1, 0), (1.5708, 0, 0)), 'back': ((0, 1, 0), (1.5708, 0, 3.14159)),
         'left': ((1, 0, 0), (1.5708, 0, 1.5708)), 'right': ((-1, 0, 0), (1.5708, 0, -1.5708))}
tot = np.empty(nf, np.int32); me.polygons.foreach_get('loop_total', tot); lf = np.repeat(np.arange(nf), tot)
if 'rv_col' in me.color_attributes: me.color_attributes.remove(me.color_attributes['rv_col'])
col = me.color_attributes.new('rv_col', 'BYTE_COLOR', 'CORNER'); me.color_attributes.active_color = col
GREY = np.array([0.42, 0.42, 0.42, 1], np.float32)
pal = lambda k: np.array(colorsys.hsv_to_rgb((k * 0.6180339887 + 0.05) % 1, 0.72, 0.95) + (1.0,), np.float32)
def paint(fc): col.data.foreach_set('color', fc[lf].ravel())
def shoot(path, view, centre, scale):
    d, rot = VIEWS[view]; cam.location = Vector(centre) + Vector(d) * 5; cam.rotation_euler = rot
    cam.data.ortho_scale = scale; cam.data.clip_end = 20; sc.render.filepath = path; bpy.ops.render.render(write_still=True)
FONT = ImageFont.load_default(size=22)
def sheet(paths, caption, out, cols=None):
    ims = [Image.open(p).convert('RGB') for p in paths]; cols = cols or len(ims); rows = (len(ims) + cols - 1) // cols
    W, H = ims[0].size; S = Image.new('RGB', (W * cols, H * rows + 36), (25, 25, 25))
    ImageDraw.Draw(S).text((10, 6), caption, fill=(235, 235, 235), font=FONT)
    for k, im in enumerate(ims): S.paste(im, ((k % cols) * W, 36 + (k // cols) * H))
    S.save(out); [os.remove(p) for p in paths]
co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
ALO, AHI = co.min(0), co.max(0); ACTR = tuple(float(x) for x in (ALO + AHI) / 2); AEXT = float((AHI - ALO).max()) * 1.15 + 0.01   # the assembly's own bounds frame it
fv = np.split(np.array([v for p in me.polygons for v in p.vertices]), np.cumsum(tot)[:-1])
T = OUT + '/_tmp'; os.makedirs(T, exist_ok=True)

# assembly: every part its own colour, unassigned dark
fc = np.tile(np.array([0.12, 0.12, 0.12, 1], np.float32), (nf, 1))
for k in range(len(names)): fc[owner == k] = pal(k)
paint(fc); ps = []
for v in VIEWS: p = f'{T}/asm_{v}.png'; shoot(p, v, ACTR, AEXT); ps.append(p)
sheet(ps, f'assembled: {len(names)} parts, each its own colour; near-black = unassigned ({int((owner < 0).sum())} faces)', f'{OUT}/assembly/assembled.png', cols=4)
fc = np.tile(GREY, (nf, 1)); fc[owner < 0] = np.array([1, 0.15, 0.6, 1], np.float32); paint(fc); ps = []
for v in VIEWS: p = f'{T}/un_{v}.png'; shoot(p, v, ACTR, AEXT); ps.append(p)
sheet(ps, f'UNASSIGNED faces in magenta ({int((owner < 0).sum())})', f'{OUT}/assembly/unassigned.png', cols=4)

for k, name in enumerate(names):
    m = owner == k
    if not m.any(): continue
    fc = np.tile(GREY, (nf, 1)); fc[m] = pal(0); paint(fc); src.hide_render = False; ps = []
    for v in ('front', 'back'): p = f'{T}/{name}_{v}.png'; shoot(p, v, ACTR, AEXT); ps.append(p)
    sheet(ps, f'{name} in context ({int(m.sum())} faces)', f'{OUT}/ctx/{name}.png')
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not m[f.index]], context='FACES')
    im_ = bpy.data.meshes.new('iso'); bm.to_mesh(im_); bm.free()
    iso = bpy.data.objects.new('iso', im_); sc.collection.objects.link(iso)
    ic = im_.color_attributes.get('rv_col'); im_.color_attributes.active_color = ic
    ic.data.foreach_set('color', np.tile(pal(0), (len(im_.loops), 1)).ravel()); src.hide_render = True
    vi = np.unique(np.concatenate([fv[i] for i in np.flatnonzero(m)])); lo, hi = co[vi].min(0), co[vi].max(0)
    ctr, ext = (lo + hi) / 2, float(max(hi - lo)) * 1.15 + 0.01; ps = []
    for v in VIEWS: p = f'{T}/{name}_iso_{v}.png'; shoot(p, v, ctr, ext); ps.append(p)
    sheet(ps, f'{name} isolated ({int(m.sum())} faces, {ext * 100 / 1.15:.1f} cm across) - front/back/left/right', f'{OUT}/part/{name}.png')
    bpy.data.objects.remove(iso); bpy.data.meshes.remove(im_); src.hide_render = False
print('RENDER FINAL DONE', len(names))
