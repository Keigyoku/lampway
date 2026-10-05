# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The headless Cycles worker of bake_maps: opens the pair the tool wrote (a .blend holding the high-poly donors and the UV-mapped low-poly target), bakes each requested map
# selected-to-active on the CPU and writes PNGs. Always niced by the runner; never run in the user's live scene (Cycles locks the machine while a person works live).
# blender -b -P bake_maps.py -- <pair.blend> <args.json> <result.json>
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, 'Bake normal, albedo (colour only) and AO from high-poly donors onto a UV-mapped low-poly target in headless Cycles')
    else: print(f'error: {len(_A)} argument(s); 3 needed')
    _ax.helps(['blender -b -P scripts/bake/bake_maps.py -- <pair.blend> <args.json> <result.json>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
import json, os, bpy, numpy as np
BLEND, ARGS, OUT = _A[:3]
a = json.load(open(ARGS))
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(BLEND) as (src, dst):
    dst.objects = list(src.objects)
for o in dst.objects:
    bpy.context.scene.collection.objects.link(o)
low = bpy.data.objects[a['low']]
highs = [bpy.data.objects[n] for n in a['high']]
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = a['samples']
size = a['size']; margin = a['margin_px']
BAKE = {'normal': 'NORMAL', 'albedo': 'DIFFUSE', 'ao': 'AO'}
mat = bpy.data.materials.new(low.name + '_baked'); mat.use_nodes = True
low.data.materials.clear(); low.data.materials.append(mat)
nt = mat.node_tree
files, colorspace, passes = {}, {}, []
for m in a['maps']:
    img = bpy.data.images.new(f"{low.name}_{m}", size, size, alpha=False, float_buffer=False)
    img.colorspace_settings.name = 'sRGB' if m == 'albedo' else 'Non-Color'
    colorspace[m] = img.colorspace_settings.name
    node = nt.nodes.new('ShaderNodeTexImage'); node.image = img; node.label = f"bake {m}"
    for n in nt.nodes: n.select = False
    node.select = True; nt.nodes.active = node
    bpy.ops.object.select_all(action='DESELECT')
    for h in highs: h.select_set(True)
    low.select_set(True); bpy.context.view_layer.objects.active = low
    kw = dict(type=BAKE[m], use_selected_to_active=True, margin=margin, cage_extrusion=a['cage_extrusion_m'], max_ray_distance=a['max_ray_m'], use_clear=True)
    if m == 'normal':
        kw.update(normal_space='TANGENT')
        sc.render.bake.normal_r = 'POS_X'; sc.render.bake.normal_g = 'POS_Y' if a['normal_green'] == 'gl' else 'NEG_Y'; sc.render.bake.normal_b = 'POS_Z'
    if m == 'albedo':
        sc.render.bake.use_pass_direct = False; sc.render.bake.use_pass_indirect = False; sc.render.bake.use_pass_color = True   # colour only: no lighting, by construction
        passes = ['COLOR']
        kw.update(pass_filter={'COLOR'})
    bpy.ops.object.bake(**kw)
    path = os.path.join(a['out_dir'], f"{low.name}_{m}.png")
    img.filepath_raw = path; img.file_format = 'PNG'; img.save()
    files[m] = path
# coverage and black texels: how much of the UV-covered area stayed black (a cage that is too small, rays that miss)
from mixar.modules.lampway_tools.features import uv_islands as UI
bm_uv = [[l.uv[:] for l in low.data.uv_layers.active.data[p.loop_start:p.loop_start + p.loop_total]] for p in low.data.polygons]
from PIL import Image
mask = Image.new('L', (size, size), 0)
from PIL import ImageDraw
d = ImageDraw.Draw(mask)
for poly in bm_uv:
    d.polygon([(u * (size - 1), (1 - v) * (size - 1)) for u, v in poly], fill=255)
cov = np.asarray(mask) > 0
checks = {}
for m, p in files.items():
    px = np.asarray(Image.open(p).convert('RGB')).astype(int)
    black = (px.max(axis=2) <= 1) & cov
    checks[m] = round(float(black.sum() / max(cov.sum(), 1)), 5)
nan = 0
json.dump({'files': files, 'colorspace': colorspace, 'albedo_passes': passes, 'black_texel_fraction': checks, 'covered_texels': int(cov.sum()), 'material': mat.name}, open(OUT, 'w'))
_ax.kv({'baked': ','.join(files), 'size': size})
