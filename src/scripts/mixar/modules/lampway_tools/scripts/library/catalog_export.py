# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The headless worker of asset_catalog_export: reads each asset's datablock from its own file (append from a .blend, or import a GLB/FBX/OBJ/USD mesh), marks it as an asset
# with the catalogue id the tool computed and the lw_asset_* provenance properties, and writes the library .blend (to a temporary name, then renamed). Never run in the user's
# live scene: the runner starts it niced in a fresh -b process.
# blender -b -P catalog_export.py -- <job.json> <result.json>
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
if __name__ == '__main__' and len(_A) < 2:
    if not _A: _ax.home(__file__, "Write Asset Vault assets into a Blender asset library .blend, marked with their catalogues")
    else: print(f'error: {len(_A)} argument(s); 2 needed')
    _ax.helps(['blender -b -P scripts/library/catalog_export.py -- <job.json> <result.json>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
import json, bpy
import lw_canon                                              # canon_io, the one importer: each import is stamped lw_raw
JOB, OUT = _A[:2]
job = json.load(open(JOB))
bpy.ops.wm.read_factory_settings(use_empty=True)


def read(it):
    if it['import']:
        before = set(bpy.data.objects)
        lw_canon.io.import_raw(it['path'])
        new = [o for o in bpy.data.objects if o not in before]
        roots = [o for o in new if o.parent is None]
        if len(roots) != 1:
            raise SystemExit(f"{it['name']}: the import gave {len(roots)} root objects; one is publishable")
        roots[0].name = it['name']
        return roots[0]
    slot = it['slot']
    with lw_canon.io.load_library(it['path']) as (src, dst):
        names = list(getattr(src, slot))
        if it['name'] not in names and slot == 'materials' and it['name'] in src.node_groups:
            slot, names = 'node_groups', list(src.node_groups)
        name = it['name'] if it['name'] in names else (names[0] if len(names) == 1 else None)
        if name is None:
            raise SystemExit(f"{it['name']}: not in {_os.path.basename(it['path'])} (it holds {sorted(names)[:20]})")
        setattr(dst, slot, [name])
    return getattr(dst, slot)[0]


published, ids = [], set()
for it in job['items']:
    idb = read(it)
    idb.asset_mark()
    idb.asset_data.catalog_id = it['catalog_id']
    for k, v in it['lw'].items():
        idb[k] = v
    ids.add(idb)
    published.append({'name': idb.name, 'type': type(idb).__name__, 'catalog': it['catalog_path']})
tmp = job['dest_blend'] + '.writing'
bpy.data.libraries.write(tmp, ids, fake_user=True, compress=True)
_os.replace(tmp, job['dest_blend'])
json.dump({'published': published, 'previews': 'none'}, open(OUT, 'w'))
print(f"published {len(published)} asset(s) to {job['dest_blend']}")
