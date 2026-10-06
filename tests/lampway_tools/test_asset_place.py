# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""asset_place (specs/asset_library/asset_place.md) in the real binary: put a library asset into the open scene, a material slot, a node tree or the world in the way its kind needs,
reversibly, stamping where it came from; publish library assets to Blender's own catalogue system. The asset record is what the server's ``AssetLibrary.get`` returns; the tests hand
it in (``asset=``), the tool fetches it from the server when it is not given."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from asset_place_support import go, one  # noqa: E402


def test_place_glb_creates_object_at_cursor_with_lw_props(tmp_path):
    d = one(go(tmp_path, f'''
glb = {str(tmp_path / "greaves.glb")!r}
make_glb(glb)
bpy.context.scene.cursor.location = (1.0, 2.0, 3.0)
r = place(asset=rec("mesh", glb), mode="auto", target={{"where": "cursor"}})
ob = bpy.data.objects.get(r["placed"][0]["object"]) if r.get("ok") else None
lo, hi = world_box(ob) if ob else ([0] * 3, [0] * 3)
print("RESULT", json.dumps({{"r": r, "props": {{k: str(ob[k]) for k in ob.keys() if k.startswith("lw_")}} if ob else None, "lo": lo, "hi": hi,
                           "in_scene": bool(ob and ob.name in bpy.context.scene.objects), "meshes": sorted(o.name for o in bpy.data.objects if o.type == "MESH")}}))
'''))
    r = d["r"]
    assert r["ok"], r
    assert r["mode_used"] == "import" and r["undo"] is True
    p = r["placed"][0]
    assert p["kind"] == "object" and p["bytes_loaded"] > 0 and p["collection"]
    assert d["in_scene"] and len(d["meshes"]) == 1
    assert d["props"] == {"lw_asset_id": "asset-1", "lw_asset_version": "1", "lw_asset_sha256": "ab" * 32}
    assert abs((d["lo"][0] + d["hi"][0]) / 2 - 1.0) < 1e-3 and abs((d["lo"][1] + d["hi"][1]) / 2 - 2.0) < 1e-3 and abs(d["lo"][2] - 3.0) < 1e-3


def test_scale_to_unit_uses_unit_scale_stat(tmp_path):
    d = one(go(tmp_path, f'''
glb = {str(tmp_path / "big.glb")!r}
make_glb(glb, size=(30.0, 30.0, 100.0))            # authored in centimetres: 100 units tall
r = place(asset=rec("mesh", glb, stats={{"unit_scale": 0.01}}), mode="import", target={{"where": "origin"}})
ob = bpy.data.objects[r["placed"][0]["object"]]
lo, hi = world_box(ob)
r2 = place(asset=rec("mesh", glb, stats={{"unit_scale": 0.01}}, aid="asset-2"), mode="import", target={{"where": "origin"}}, options={{"scale_to_unit": False}})
ob2 = bpy.data.objects[r2["placed"][0]["object"]]
lo2, hi2 = world_box(ob2)
print("RESULT", json.dumps({{"h": hi[2] - lo[2], "h_raw": hi2[2] - lo2[2]}}))
'''))
    assert abs(d["h"] - 1.0) < 1e-3, d
    assert abs(d["h_raw"] - 100.0) < 1e-2, d


def test_place_is_one_undo_step(tmp_path):
    d = one(go(tmp_path, f'''
glb = {str(tmp_path / "g.glb")!r}
make_glb(glb)
bpy.ops.ed.undo_push(message="before")
before = sorted(o.name for o in bpy.data.objects)
r = place(asset=rec("mesh", glb), mode="import", target={{"where": "origin"}})
after = sorted(o.name for o in bpy.data.objects)
bpy.ops.ed.undo()
undone = sorted(o.name for o in bpy.data.objects)
print("RESULT", json.dumps({{"before": before, "after": after, "undone": undone, "r": r}}))
'''))
    assert d["r"]["ok"] and len(d["after"]) == len(d["before"]) + 1
    assert d["undone"] == d["before"], d


def test_failed_import_leaves_no_orphan_datablocks(tmp_path):
    d = one(go(tmp_path, f'''
bad = {str(tmp_path / "broken.glb")!r}
open(bad, "wb").write(b"glTF" + b"\\x00" * 40)                  # a header and nothing else
snap = lambda: {{k: sorted(getattr(bpy.data, k).keys()) for k in ("objects", "meshes", "materials", "images", "collections", "cameras", "lights", "armatures", "actions")}}
before = snap()
r = place(asset=rec("mesh", bad), mode="import", target={{"where": "origin"}})
print("RESULT", json.dumps({{"r": r, "before": before, "after": snap()}}))
'''))
    assert d["r"]["ok"] is False and "import failed" in d["r"]["error"] and "the file is kept as is" in d["r"]["error"]
    assert d["after"] == d["before"], d


def test_place_refuses_uv_layout_with_the_next_step(tmp_path):
    d = one(go(tmp_path, f'''
p = {str(tmp_path / "layout.png")!r}
open(p, "wb").write(b"x")
r = place(asset=rec("uv_layout", p, subtype="smart_uv"), mode="auto")
print("RESULT", json.dumps(r))
'''))
    assert d["ok"] is False
    assert "not placeable" in d["error"] and "lampway_vault_render" in d["error"] and "uv_unwrap" in d["error"]


def test_place_refuses_a_moved_file_a_huge_mesh_and_a_missing_scene_target(tmp_path):
    d = one(go(tmp_path, f'''
gone = {str(tmp_path / "gone.glb")!r}
r_moved = place(asset=rec("mesh", gone), mode="import")
glb = {str(tmp_path / "g.glb")!r}
make_glb(glb)
r_huge = place(asset=rec("mesh", glb, stats={{"tris": 6_000_000}}), mode="import")
r_force = place(asset=rec("mesh", glb, stats={{"tris": 6_000_000}}), mode="import", options={{"force": True}})
r_slot = place(asset=rec("material", glb, role="blend", subtype="procedural"), mode="assign_material", target={{"where": "slot:Nope:0"}})
print("RESULT", json.dumps({{"moved": r_moved, "huge": r_huge, "force": r_force, "slot": r_slot}}))
'''))
    assert d["moved"]["ok"] is False and "the file moved: re-run lampway_vault {action: verify}" in d["moved"]["error"]
    assert d["huge"]["ok"] is False and "6000000 triangles: place a LOD (lod:2) or confirm force:true" in d["huge"]["error"]
    assert d["force"]["ok"] is True
    assert d["slot"]["ok"] is False and "pick a mesh object with a material slot" in d["slot"]["error"]


def test_place_by_asset_id_fetches_the_record_and_records_the_placed_event(tmp_path):
    """The agent passes only asset_id: the tool asks the server for the record (GET /api/v1/library/assets/{id}, members included) and, once placed, records a ``placed`` event
    (POST /api/v1/library/events) so the library can answer "where did I use this". A fake transport stands in for the server."""
    d = one(go(tmp_path, f'''
from mixar.modules.lampway_tools import library_client as LC
glb = {str(tmp_path / "g.glb")!r}
make_glb(glb)
calls = []
def fake(method, path, body=None, timeout=60):
    calls.append([method, path, body])
    if method == "GET":
        return {{"ok": True, "data": rec("mesh", glb, aid="a-77", version=3)}}
    return {{"ok": True, "data": {{"recorded": True}}}}
LC._request = fake
r = place(asset_id="a-77", version=3, target={{"where": "origin"}})
def down(method, path, body=None, timeout=60):
    raise LC.LibraryClientError("the server could not be reached: refused")
LC._request = down
r_down = place(asset_id="a-78")
print("RESULT", json.dumps({{"r": r, "calls": calls, "down": r_down}}))
'''))
    assert d["r"]["ok"] and d["r"]["placed"][0]["object"], d["r"]
    get, post = d["calls"]
    assert get[0] == "GET" and get[1] == "/api/v1/library/assets/a-77?version=3&include=members"
    assert post[0] == "POST" and post[1] == "/api/v1/library/events"
    assert post[2]["verb"] == "placed" and post[2]["asset_id"] == "a-77" and post[2]["version"] == 3 and post[2]["mode"] == "import"
    assert d["r"]["event_recorded"] is True
    assert d["down"]["ok"] is False and "the server could not be reached" in d["down"]["error"]
