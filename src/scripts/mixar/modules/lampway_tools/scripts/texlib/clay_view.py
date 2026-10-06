# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/texlib/clay_view.py, sha256 99c30baaf39f) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-05): orthographic clay render of a mesh from a cardinal view - the "FIRST image" of a mesh-paint request (an image
# model paints V3's design over OUR mesh's own render, so the painted plate lands on the geometry: 0.98-0.99 silhouette IoU,
# projection IoU 0.987 in all four views on chest seed 9c052d49, against 0.75-0.89 for the V3 plates themselves). Workbench
# studio light + cavity, grey; the camera (ortho scale, centre) is written beside the image.
# blender -b -P clay_view.py -- <mesh.fbx> <out.png> <Front|Back|Left|Right> <res> [--turn -90]
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
import lw_canon
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
if __name__ == '__main__' and len(_A) < 4:
    if not _A: _ax.home(__file__, 'Orthographic clay render of a mesh from a cardinal view (mesh-paint input), camera recorded')
    else: print(f'error: {len(_A)} argument(s); at least 4 needed')
    _ax.helps(['blender -b -P scripts/texlib/clay_view.py -- <mesh.fbx> <out.png> <Front|Back|Left|Right> <res> [--turn -90]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import argparse, bpy, json, math, numpy as np
from mathutils import Matrix
ap = argparse.ArgumentParser(prog='clay_view.py'); [ap.add_argument(k) for k in ('mesh', 'out', 'view')]; ap.add_argument('res', type=int); ap.add_argument('--turn', type=float, default=-90.0)
a = ap.parse_args(_A)
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
lw_canon.io.import_raw(a.mesh); ob = next(o for o in bpy.data.objects if o.type == 'MESH')
bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob; bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
ob.data.transform(Matrix.Rotation(math.radians(a.turn), 4, 'Z'))
co = np.array([v.co[:] for v in ob.data.vertices]); lo, hi = co.min(0), co.max(0); c = (lo + hi) / 2; ext = float(max(hi - lo)) * 1.08
cam = bpy.data.cameras.new('c'); cam.type = 'ORTHO'; cam.ortho_scale = ext; co_ = bpy.data.objects.new('c', cam); sc.collection.objects.link(co_); sc.camera = co_
dirs = {'Front': ((c[0], c[1] - 3, c[2]), (90, 0, 0)), 'Back': ((c[0], c[1] + 3, c[2]), (90, 0, 180)), 'Left': ((c[0] + 3, c[1], c[2]), (90, 0, 90)), 'Right': ((c[0] - 3, c[1], c[2]), (90, 0, -90))}
if a.view not in dirs: _ax.refuse(f'view {a.view!r}: one of {list(dirs)}', [])
co_.location, r = dirs[a.view]; co_.rotation_euler = [math.radians(x) for x in r]
sc.render.engine = 'BLENDER_WORKBENCH'; sh = sc.display.shading; sh.light = 'STUDIO'; sh.color_type = 'SINGLE'; sh.single_color = (0.75, 0.75, 0.75); sh.show_cavity = True; sh.cavity_type = 'BOTH'
sc.render.resolution_x = sc.render.resolution_y = a.res; sc.render.filepath = a.out; bpy.ops.render.render(write_still=True)
json.dump({'view': a.view, 'ortho_scale': ext, 'centre': c.tolist(), 'res': a.res, 'turn': a.turn}, open(a.out + '.json', 'w'))
_ax.kv({'out': a.out, 'view': a.view, 'ortho_scale': round(ext, 4)})
