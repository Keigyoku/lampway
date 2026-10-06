# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Asset Vault editor in the real binary (specs/asset_library/asset_ui_editor.md section 10, facelift 09): the probe (the space is in the editor enum, the Vault's classes
replace the stub, a Python draw handler attaches), the panels drawn into a recording layout (facet counts, the empty state, Place disabled with no scene, no network in draw),
and the operators over a fake transport."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from asset_place_support import go, one  # noqa: E402

PRE = '''
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from types import SimpleNamespace
from mixar.modules.asset_library.core import session as SES
from mixar.modules.asset_library.ui.panels import vault_panels as VP
from mixar.modules.lampway_tools import library_client as LC
calls = []
def fake(method, path, body=None, timeout=60):
    calls.append([method, path, body])
    return {"ok": True, "data": {}}
LC._request = fake
SES.PUMP.spawn = lambda job: job()
class Rec:
    def __init__(self, log, enabled=True):
        self.log, self.enabled, self.active, self.alert, self.scale_y, self.scale_x, self.alignment, self.use_property_split = log, enabled, True, False, 1, 1, "EXPAND", False
    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
    def _child(self):
        return Rec(self.log, self.enabled)
    def row(self, align=False, heading=""): return self._child()
    def column(self, align=False, heading=""): return self._child()
    def box(self): return self._child()
    def split(self, factor=0.5, align=False): return self._child()
    def grid_flow(self, **kw): return self._child()
    def panel(self, idname, default_closed=False):
        self.log.append(("panel", idname, default_closed)); return (self._child(), None if default_closed else self._child())
    def separator(self, **kw): pass
    def label(self, text="", icon="NONE", icon_value=0, translate=True): self.log.append(("label", text, icon))
    def prop(self, data, prop, **kw): self.log.append(("prop", prop, kw.get("text")))
    def template_icon(self, icon_value=0, scale=1.0): self.log.append(("icon", icon_value, scale))
    def template_header(self): self.log.append(("header",))
    def operator(self, idname, text="", icon="NONE", icon_value=0, depress=False, emboss=True):
        self.log.append(("op", idname, text, self.enabled)); return SimpleNamespace()
def ctx(scene=True, width=1200):
    return SimpleNamespace(scene=bpy.context.scene if scene else None, window_manager=bpy.context.window_manager, region=SimpleNamespace(width=width))
def page(n=3, facets=None):
    items = [{"id": f"a{i}", "kind": "mesh", "name": f"greave {i}", "version": 1, "score": 0, "rating": None, "thumb": None, "tags": []} for i in range(n)]
    return {"items": items, "total": n, "facets": facets or {}, "cursor": None}
def land(p):
    SES.VM.submit(); r = SES.VM.due(); SES.VM.receive(r["token"], p)
'''


def test_the_probe_space_classes_draw_handler_and_operators(tmp_path):
    r = go(tmp_path, PRE + '''
spaces = [i.identifier for i in bpy.types.Space.bl_rna.properties["type"].enum_items]
h = bpy.types.SpaceMixarAssets.draw_handler_add(lambda: None, (), "WINDOW", "POST_PIXEL")
bpy.types.SpaceMixarAssets.draw_handler_remove(h, "WINDOW")
p = bpy.types.WindowManager.bl_rna.properties["mixar_lib"].fixed_type.properties["tile_size"]
ops = [n for n in ("search", "toggle_facet", "select", "place", "rate", "compare_add", "find_similar", "open_folder", "save_search", "open_window", "page", "copy")
       if not hasattr(bpy.ops.mixar, "asset_library_" + n) or bpy.ops.mixar.__getattr__("asset_library_" + n).idname_py() != "mixar.asset_library_" + n]
print("RESULT", json.dumps({"space": "MIXAR_ASSETS" in spaces, "vault": [hasattr(bpy.types, c) for c in ("MIXAR_ASSETS_HT_vault", "MIXAR_ASSETS_PT_vault")],
                            "stub": hasattr(bpy.types, "MIXAR_ASSETS_PT_main"), "tile": [p.hard_min, p.hard_max, p.default], "missing_ops": ops}))
''')
    d = one(r)
    assert "Error registering class" not in r.out
    assert d["space"] and d["vault"] == [True, True] and d["stub"] is False
    assert d["tile"] == [64, 256, 128] and d["missing_ops"] == []


def test_the_body_draws_facet_counts_and_the_detail_with_no_network_call(tmp_path):
    d = one(go(tmp_path, PRE + '''
land(page(3, facets={"material_role": [{"value": "metal", "count": 3}], "kind": [{"value": "mesh", "count": 3}]}))
SES.VM.select("a1")
SES.VM.receive_detail("a1", {"id": "a1", "kind": "mesh", "name": "greave 1", "created_at": 1759672920.0, "stats": {"tris": 1200}, "generation": [], "relations": [], "terms": [], "tags": [],
                             "files": [{"role": "main", "sha256": "s", "bytes": 1, "locations": [{"path": "/x/g.glb", "storage": "external", "missing": 0}]}], "license_id": None})
calls.clear()
log = []
VP.draw_body(Rec(log), ctx(scene=True))
with_scene = [e for e in log if e[0] == "op" and e[1] == "mixar.asset_library_place"]
log2 = []
VP.draw_body(Rec(log2), ctx(scene=False))
no_scene = [e for e in log2 if e[0] == "op" and e[1] == "mixar.asset_library_place"]
land(page(0))
log3 = []
VP.draw_body(Rec(log3), ctx())
print("RESULT", json.dumps({"labels": [e[1] for e in log if e[0] == "label"], "ops": [e[1] for e in log if e[0] == "op"], "place": [with_scene[0][3], no_scene[0][3]],
                            "panels": [e for e in log if e[0] == "panel"], "empty": [e[1] for e in log3 if e[0] == "label"], "calls": calls}))
'''))
    assert d["calls"] == [], "draw makes no network call"
    assert "metal  3" in d["labels"] and "mesh  3" in d["labels"]
    assert "local embeddings, no egress" in d["labels"] and "Triangles  1 200" in d["labels"]
    assert d["place"] == [True, False], "Place is disabled with no scene"
    assert ["panel", "MIXAR_ASSETS_vault_provenance", True] in d["panels"], "the timeline is one click away"
    assert "The Vault is empty: Initial import adds your folders" in d["empty"]
    assert d["ops"].count("mixar.asset_library_select") == 3


def test_select_rate_and_place_through_the_operators(tmp_path):
    d = one(go(tmp_path, PRE + f'''
glb = {str(tmp_path / "g.glb")!r}
make_glb(glb)
land(page(3))
bpy.ops.mixar.asset_library_select(asset_id="a0")
bpy.ops.mixar.asset_library_select(asset_id="a2", mode="range")
sel = list(SES.VM.selected)
bpy.ops.mixar.asset_library_rate(asset_id="a0", stars=4)
SES.PUMP.tick()
rated = [c for c in calls if c[1].endswith("/rate")]
def fake2(method, path, body=None, timeout=60):
    calls.append([method, path, body])
    if method == "GET":
        return {{"ok": True, "data": rec("mesh", glb, aid="a0")}}
    return {{"ok": True, "data": {{}}}}
LC._request = fake2
res = bpy.ops.mixar.asset_library_place(asset_id="a0")
placed = [o.name for o in bpy.data.objects if o.get("lw_asset_id") == "a0"]
print("RESULT", json.dumps({{"sel": sel, "rated": rated, "place": sorted(res), "placed": placed}}))
'''))
    assert d["sel"] == ["a0", "a1", "a2"]
    assert d["rated"] and d["rated"][0][0] == "POST" and d["rated"][0][2] == {"stars": 4}
    assert d["place"] == ["FINISHED"] and d["placed"]


def test_initial_import_previews_then_imports_on_confirm_and_the_header_says_so(tmp_path):
    d = one(go(tmp_path, PRE + f'''
folder = {str(tmp_path / "Armour")!r}
os.makedirs(folder)
def fake3(method, path, body=None, timeout=60):
    calls.append([method, path, body])
    if path.endswith("/ingest/scan"):
        return {{"ok": True, "data": {{"scan_id": "s1", "report": {{"by_kind": {{"mesh": 2}}, "deduped": 0, "new_assets": 2, "unknown": [], "skipped": [], "failed": []}}}}}}
    if path.endswith("/ingest/import"):
        return {{"ok": True, "data": {{"scan_id": "s1", "report": {{"new_assets": 2, "deduped": 0, "failed": []}}}}}}
    return {{"ok": True, "data": {{"items": [], "total": 0, "facets": {{}}, "cursor": None}}}}
LC._request = fake3
try:
    early = sorted(bpy.ops.mixar.asset_library_import_confirm())
except RuntimeError as e:
    early = ["REFUSED", str(e)[:120]]
SES.PUMP.tick()
early_calls = [c for c in calls if c[1].endswith("/ingest/import")]
bpy.ops.mixar.asset_library_initial_import(directory=folder)
SES.PUMP.tick()
preview = SES.VM.import_summary()
imports_before_confirm = [c for c in calls if c[1].endswith("/ingest/import")]
log = []
VP.MIXAR_ASSETS_HT_vault.draw(SimpleNamespace(layout=Rec(log)), ctx())
bpy.ops.mixar.asset_library_import_confirm()
SES.PUMP.tick()
print("RESULT", json.dumps({{"early": early, "early_calls": early_calls, "scan": [c for c in calls if c[1].endswith("/ingest/scan")], "preview": preview, "before": imports_before_confirm,
    "header": [e for e in log if e[0] in ("label", "op")], "after": SES.VM.import_summary(), "imported": [c[2] for c in calls if c[1].endswith("/ingest/import")]}}))
'''))
    assert d["early"][0] == "REFUSED" and "no preview to import" in d["early"][1] and d["early_calls"] == []
    assert d["scan"] == [["POST", "/api/v1/library/ingest/scan", {"paths": [str(tmp_path / "Armour")]}]]
    assert d["preview"] == "2 files: 2 mesh" and d["before"] == [], "nothing is imported before the user confirms"
    assert ["label", "2 files: 2 mesh", "IMPORT"] in d["header"] and any(e[0] == "op" and e[1] == "mixar.asset_library_import_confirm" for e in d["header"])
    assert d["imported"] == [{"scan_id": "s1"}] and d["after"] == "Imported 2 new assets (0 duplicates, 0 failed)"
