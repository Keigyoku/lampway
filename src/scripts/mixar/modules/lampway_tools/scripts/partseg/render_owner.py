# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/render_owner.py, sha256 e9a26b25765e) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): render a mesh coloured by its part owner map (one stable colour per part, a legend with the part list), four
# orthographic views, so a transfer or segmentation can be judged by eye; optionally the flagged islands (transfer_parts.py) drawn in
# magenta. Frame: the mesh's own import frame; --turn rotates about Z so the front faces -Y (Tripo FBX: -90).
# blender -b -P render_owner.py -- <mesh.fbx|glb> <owner_poly.npy> <recipe.json> <out_prefix> [--turn -90] [--flag-tri owner_tri_flag.npy --tri-npz piece_uv.npz]
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
import lw_canon
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
if __name__ == '__main__' and len(_A) < 4:
    if not _A: _ax.home(__file__, 'Render a mesh coloured by its part owner map, four views plus legend; flagged islands in magenta')
    else: print(f'error: {len(_A)} argument(s); at least 4 needed')
    _ax.helps(['blender -b -P scripts/partseg/render_owner.py -- <mesh> <owner_poly.npy> <recipe.json> <out_prefix> [--turn -90] [--flag-poly flags.npy]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import argparse, bpy, json, math, colorsys, numpy as np
ap = argparse.ArgumentParser(prog='render_owner.py'); [ap.add_argument(k) for k in ('mesh', 'owner', 'recipe', 'out')]
ap.add_argument('--turn', type=float, default=0.0); ap.add_argument('--flag-poly', default=None)
a = ap.parse_args(_A)
bpy.ops.wm.read_factory_settings(use_empty=True)
lw_canon.io.import_raw(a.mesh)
o = next(x for x in bpy.data.objects if x.type == 'MESH'); me = o.data
own = np.load(a.owner); names = list(json.load(open(a.recipe))['parts'])
if len(own) != len(me.polygons): _ax.refuse(f'owner has {len(own)} labels for {len(me.polygons)} polygons', [])
flag = np.load(a.flag_poly).astype(bool) if a.flag_poly else np.zeros(len(own), bool)
o.rotation_euler[2] += math.radians(a.turn)
gold = 0.61803398875
for k, n in enumerate(names):                                           # stable, well-spread hues (golden-ratio walk)
    m = bpy.data.materials.new(n); h = (k * gold) % 1.0; m.diffuse_color = (*colorsys.hsv_to_rgb(h, 0.65 if k % 2 else 0.9, 0.95 if k % 3 else 0.75), 1); me.materials.append(m)
fm = bpy.data.materials.new('FLAGGED'); fm.diffuse_color = (1, 0, 1, 1); me.materials.append(fm)
for i, p in enumerate(me.polygons): p.material_index = len(names) if flag[i] else int(own[i])
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'MATERIAL'
sc.render.resolution_x = sc.render.resolution_y = 800; sc.render.film_transparent = True
cam = bpy.data.cameras.new('c'); co = bpy.data.objects.new('c', cam); sc.collection.objects.link(co); sc.camera = co; cam.type = 'ORTHO'; cam.ortho_scale = 1.15
for vn, (pos, r) in {'front': ((0, -5, 0), (90, 0, 0)), 'back': ((0, 5, 0), (90, 0, 180)), 'left': ((5, 0, 0), (90, 0, 90)), 'right': ((-5, 0, 0), (90, 0, -90))}.items():
    co.location = pos; co.rotation_euler = [math.radians(v) for v in r]; sc.render.filepath = f'{a.out}_{vn}.png'; bpy.ops.render.render(write_still=True)
leg = [{'k': k, 'part': n, 'rgb': [round(c, 3) for c in me.materials[k].diffuse_color[:3]], 'polys': int((own == k).sum())} for k, n in enumerate(names)]
json.dump({'legend': leg, 'flagged_polys': int(flag.sum())}, open(f'{a.out}_legend.json', 'w'), indent=1)
_ax.kv({'views': 4, 'parts': len(names), 'flagged_polys': int(flag.sum()), 'out': a.out}); _ax.helps([f'look at {a.out}_front.png ... and {a.out}_legend.json'])
