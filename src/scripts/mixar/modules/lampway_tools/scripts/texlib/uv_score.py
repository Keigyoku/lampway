# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Derived from the owner's tool shelf (tools/texlib/uv_score.py, sha256 3a2e5b0c1d94, SPIKE 2026-10-04): the measurement now lives in
# mixar.modules.lampway_tools.features.uv_islands (one definition, shared with the in-app tool); this script only imports each file into a factory-empty scene and writes the rows.
# blender -b -P uv_score.py -- <out.json> <res> <mesh> [<mesh> ...]
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, 'Score UV unwraps on measurements: utilization, overlap, islands, stretch, mirrored faces, seams')
    else: print(f'error: {len(_A)} argument(s); at least 3 needed')
    _ax.helps(['blender -b -P scripts/texlib/uv_score.py -- <out.json> <res> <mesh> [<mesh> ...]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
import bpy, json, os
from mixar.modules.lampway_tools.features import uv_islands as UI
OUT, RES, FILES = _A[0], int(_A[1]), _A[2:]
rows = []
for f in FILES:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    (bpy.ops.import_scene.fbx if f.lower().endswith('.fbx') else bpy.ops.import_scene.gltf)(filepath=f)
    obs = [o for o in bpy.data.objects if o.type == 'MESH']
    if not obs:
        rows.append({'name': os.path.basename(f), 'error': 'no mesh in file'}); continue
    bpy.ops.object.select_all(action='DESELECT')
    for o in obs: o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    if len(obs) > 1: bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    row = UI.measure_object(o, RES); row['name'] = row['file'] = os.path.basename(f)
    rows.append(row); print(json.dumps(row), flush=True)
json.dump(rows, open(OUT, 'w'))
