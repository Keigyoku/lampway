# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Chat LIBRARY mode on the Asset Vault (specs/asset_library/asset_ui_editor.md surface D, test 10.5): browsing and a typed search ask the Vault's query off the main thread
(a token drops a stale answer) and never open a .blend on the main thread; a picture shows its own file as the thumbnail; a click places the asset through asset_place.

The mode itself is retired upstream (tests/test_library_mode_retired.py: "re-listing the enum item is the whole of bringing the feature back"). This test re-lists the item
for its own run, which is exactly that step; whether to re-list it in the product is the captain's call."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from asset_place_support import go, one  # noqa: E402

PRE = '''
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.space_mixie_chat.core import library_browse as LB
from mixar.modules.space_mixie_chat.core import library_vault_chat as LVC
from mixar.modules.lampway_tools import library_client as LC
loads = []
_real_load = bpy.data.libraries.load
class Spy:
    def __call__(self, *a, **k):
        loads.append(a[0] if a else k.get("filepath")); return _real_load(*a, **k)
bpy.types.BlendDataLibraries.load = Spy()
calls = []
LVC.SPAWN = lambda fn: fn()
'''


def test_browse_and_search_ask_the_vault_and_never_open_a_blend(tmp_path):
    d = one(go(tmp_path, PRE + f'''
pic = {str(tmp_path / "front.png")!r}
png(pic)
glb = {str(tmp_path / "g.glb")!r}
make_glb(glb)
def fake(method, path, body=None, timeout=60):
    calls.append([method, path, body])
    if method == "GET":
        return {{"data": rec("mesh", glb, aid="m1", name="Greaves")}}
    if path.endswith("/events"):
        return {{"data": {{"recorded": True}}}}
    return {{"data": {{"items": [{{"id": "i1", "kind": "image", "name": "front plate", "path": pic, "thumb": pic}},
                              {{"id": "m1", "kind": "mesh", "name": "Greaves", "path": glb, "thumb": None}}], "total": 2, "facets": {{}}, "cursor": None}}}}
LC._request = fake
# an ENROLLED library holding a .blend asset: the old scan would open it (proved below), so "no .blend opened" is a claim about something that was there to open
libdir = {str(tmp_path / "enrolled")!r}
os.makedirs(libdir)
m = material("EnrolledMat"); m.asset_mark()
bpy.data.libraries.write(os.path.join(libdir, "lib.blend"), {{m}}, fake_user=True)
bpy.ops.preferences.asset_library_add(directory=libdir)
from mixar.modules.asset_search.core import library_enrollment as ENR
ENR.set_enrolled(bpy.context.preferences.filepaths.asset_libraries[-1].name, True)
LB._enumerate_assets(bpy.context, force=True)
old_scan_loads = list(loads)
loads.clear()
from bpy.props import EnumProperty
_items = [(i.identifier, i.name, i.description, i.icon, i.value) for i in bpy.types.Scene.bl_rna.properties["mixie_chat_mode"].enum_items] + [("LIBRARY", "Library", "", "ASSET_MANAGER", 4)]
bpy.types.Scene.mixie_chat_mode = EnumProperty(items=_items)
sc = bpy.context.scene
sc.mixie_chat_mode = "LIBRARY"
sc.mixie_chat_input = ""
LB.execute_library_mode(None, bpy.context)
LVC._poll()
browse = [c[2] for c in calls]
sc.mixie_chat_input = "greaves"
LB.execute_library_mode(None, bpy.context)
stale = LVC._token
LVC._publish(stale - 1, "old", True, {{"items": [{{"id": "zz", "kind": "image", "name": "stale", "path": pic, "thumb": pic}}]}})
LVC._poll()
msg = LB._grid_bubble(sc)
items = [[a.asset_name, a.library, a.blend_file, a.asset_type, bool(a.image)] for a in msg.action_items]
img = bpy.data.images.get(msg.action_items[0].image) if msg.action_items[0].image else None
mesh_action = msg.action_items[1].value
bpy.ops.mixie_chat.select_slot_action(bubble_id=msg.bubble_id, action_value=mesh_action)
placed = [o.name for o in bpy.data.objects if o.get("lw_asset_id") == "m1"]
print("RESULT", json.dumps({{"browse": browse, "search": calls[1][2] if len(calls) > 1 else None, "items": items, "img": img.filepath if img else None,
    "loads_before_click": [p for p in loads if p != glb], "old_scan_loads": old_scan_loads, "placed": placed, "content": msg.content}}))
'''))
    assert d["browse"] == [{"limit": 9, "include": ["thumb", "tags", "path"]}], d["browse"]
    assert d["search"] == {"text": "greaves", "limit": 9, "include": ["thumb", "tags", "path"]}
    assert d["items"] == [["front plate", "Asset Vault", "vault:i1", "image", True], ["Greaves", "Asset Vault", "vault:m1", "mesh", False]], d["items"]
    assert d["img"].endswith("front.png") and "stale" not in d["content"]
    assert d["old_scan_loads"] and d["old_scan_loads"][0].endswith("lib.blend"), "the spy sees a .blend open (the old local scan does open one)"
    assert d["loads_before_click"] == [], "no .blend is opened to browse or search"
    assert d["placed"], "the click placed the asset through asset_place"
