# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""asset_catalog_export (specs/asset_library/asset_place.md section 6, "Catalogue integration") in the real binary: library assets published as a Blender asset library (a .blend
written by a headless worker, never the live file, plus blender_assets.cats.txt from the taxonomy with UUID5 catalogue ids, stable across exports)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from asset_place_support import go, one  # noqa: E402

EXPORT = '''
src = {src!r}
dest = {dest!r}
write_blend(src, [material("Bronze"), material("Iron", (0.3, 0.3, 0.3)), material("Leather", (0.4, 0.2, 0.1))])
def mat_rec(name, facet, label, aid):
    r = rec("material", src, role="blend", subtype="procedural", name=name, aid=aid)
    r["terms"] = [{{"facet": facet, "label": label, "by": "rule", "confidence": 1.0}}]
    return r
assets = [mat_rec("Bronze", "material_role", "metal", "m-1"), mat_rec("Iron", "material_role", "metal", "m-2"), mat_rec("Leather", "material_role", "leather", "m-3")]
r1 = call("asset_catalog_export", assets=assets, dest_library=dest)
cats1 = open(os.path.join(dest, "blender_assets.cats.txt")).read() if r1.get("ok") else ""
r2 = call("asset_catalog_export", assets=assets, dest_library=dest)
cats2 = open(os.path.join(dest, "blender_assets.cats.txt")).read() if r2.get("ok") else ""
blend = r1.get("blend") or ""
live = sorted(m.name for m in bpy.data.materials if m.asset_data)     # before this test reads the library back into its own file
got = {{}}
if blend:
    with bpy.data.libraries.load(blend, assets_only=True) as (s, d):
        names = sorted(s.materials)
        d.materials = list(s.materials)
    for m in d.materials:
        got[m.name] = [str(m.asset_data.catalog_id) if m.asset_data else None, str(m.get("lw_asset_id"))]
else:
    names = []
print("RESULT", json.dumps({{"r1": r1, "r2": r2, "cats1": cats1, "cats2": cats2, "names": names, "got": got,
                            "live_materials": live}}))
'''


def test_catalog_export_roundtrip(tmp_path):
    d = one(go(tmp_path, EXPORT.format(src=str(tmp_path / "src.blend"), dest=str(tmp_path / "published")), timeout=400))
    assert d["r1"]["ok"] and d["r2"]["ok"], d["r1"]
    assert d["names"] == ["Bronze", "Iron", "Leather"], d
    lines = [ln for ln in d["cats1"].splitlines() if ln and not ln.startswith("#")]
    assert lines[0] == "VERSION 1"
    cat = {ln.split(":")[1]: ln.split(":")[0] for ln in lines[1:]}
    assert set(cat) >= {"material_role/metal", "material_role/leather"}, cat
    assert d["got"]["Bronze"] == [cat["material_role/metal"], "m-1"] and d["got"]["Iron"][0] == cat["material_role/metal"]
    assert d["got"]["Leather"][0] == cat["material_role/leather"]
    assert d["cats1"] == d["cats2"], "the catalogue ids are UUID5 of the path: stable across exports"
    assert d["live_materials"] == [], "the live file is never marked: a worker builds the library"


def test_catalog_export_refuses_a_blend_it_did_not_create_and_registers_the_library(tmp_path):
    d = one(go(tmp_path, f'''
dest = {str(tmp_path / "pub")!r}
os.makedirs(dest)
foreign = os.path.join(dest, "lampway_library.blend")
bpy.data.libraries.write(foreign, set(), fake_user=False)
src = {str(tmp_path / "src.blend")!r}
write_blend(src, [material("Bronze")])
a = [rec("material", src, role="blend", subtype="procedural", name="Bronze", aid="m-1")]
refused = call("asset_catalog_export", assets=a, dest_library=dest)
dest2 = {str(tmp_path / "pub2")!r}
ok = call("asset_catalog_export", assets=a, dest_library=dest2, register=True, library_name="Lampway Vault")
libs = [(l.name, l.path) for l in bpy.context.preferences.filepaths.asset_libraries]
print("RESULT", json.dumps({{"refused": refused, "ok": ok, "libs": libs}}))
''', timeout=400))
    assert d["refused"]["ok"] is False and "was not written by Lampway" in d["refused"]["error"], d["refused"]
    assert d["ok"]["ok"] and d["ok"]["registered"] == "Lampway Vault", d["ok"]
    assert any(n == "Lampway Vault" and p.rstrip("/").endswith("pub2") for n, p in d["libs"]), d["libs"]


def test_catalog_export_imports_a_mesh_through_canon_io(tmp_path):
    """A GLB mesh asset is read by the worker through lw_canon (canon_io, the one importer) and published as one object asset."""
    d = one(go(tmp_path, f'''
glb = {str(tmp_path / "greaves.glb")!r}
dest = {str(tmp_path / "published")!r}
make_glb(glb)
r = call("asset_catalog_export", assets=[rec("mesh", glb)], dest_library=dest)
got = {{}}
if r.get("ok"):
    with bpy.data.libraries.load(r["blend"], assets_only=True) as (s, dd):
        dd.objects = list(s.objects)
    got = {{o.name: [o.type, str(o.get("lw_raw", ""))] for o in dd.objects if o is not None}}
print("RESULT", json.dumps({{"r": r, "got": got}}))
''', timeout=400))
    assert d["r"]["ok"], d["r"]
    assert list(d["got"]) == ["Greaves"] and d["got"]["Greaves"][0] == "MESH", d
    assert '"importer": "import_scene.gltf"' in d["got"]["Greaves"][1], "the worker's import is stamped by canon_io"
