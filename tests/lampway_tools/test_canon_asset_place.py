# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""N3/N4, the Vault placement landing (specs/canon/normalization DOOR.md section 8: "asset_place places the canonical version"): a
placement says what it landed - canonical (its document checked against the placed datablock now) or raw (normalize first) - and a
canonical version imported from a GLB takes its document from the library record. Runs in the real Blender."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from asset_place_support import go, one  # noqa: E402

BODY = '''
from mixar.modules.lampway_tools import api as _api
glb = {glb!r}; blend = {blend!r}
make_glb(glb)
n = _api.normalize_mesh(input=glb, turn_deg=0, generator="lampway_tool")
ob = [o for o in bpy.data.objects if "lw_canon" in o.keys()][0]
doc = json.loads(ob["lw_canon"]); ob.name = "Greaves"
write_blend(blend, [ob])
probe = _api.tool(consumes={{"object": _api.Need(kind=("mesh",), scale=("real", "generator_normalised", "unknown"))}})(lambda object: {{"ran": object}})
out = {{"norm": n.get("ok")}}
r = place(asset=rec("mesh", blend, name="Greaves"), mode="append", target={{"where": "origin"}})
out["origin"] = {{"canon": r.get("canon"), "door": probe(object=r["placed"][0]["object"])}}
bpy.context.scene.cursor.location = (1.0, 2.0, 3.0)
r = place(asset=rec("mesh", blend, name="Greaves"), mode="append", target={{"where": "cursor"}})
out["cursor"] = {{"canon": r.get("canon"), "door": probe(object=r["placed"][0]["object"])}}
r = place(asset=rec("mesh", glb, name="Raw"), mode="import", target={{"where": "origin"}})
out["raw"] = {{"canon": r.get("canon"), "door": probe(object=r["placed"][0]["object"])}}
rr = rec("mesh", glb, name="Twin"); rr["canon_state"] = "canonical"; rr["canonical"] = doc
r = place(asset=rr, mode="import", target={{"where": "origin"}})
out["twin"] = {{"canon": r.get("canon"), "stamped": "lw_canon" in bpy.data.objects[r["placed"][0]["object"]].keys()}}
print("RESULT", json.dumps(out))
'''


def test_asset_place_says_canonical_or_raw_and_checks_the_document_where_it_landed(tmp_path):
    d = one(go(tmp_path, BODY.format(glb=str(tmp_path / "greaves.glb"), blend=str(tmp_path / "greaves.canon.blend"))))
    assert d["norm"]
    o = d["origin"]
    assert o["canon"] == [{"object": "Greaves", "state": "canonical", "unmet": []}] and o["door"]["ok"] is True, o
    c = d["cursor"]["canon"][0]
    assert c["state"] == "canonical" and any("object matrix is not the identity" in u for u in c["unmet"]) and d["cursor"]["door"]["ok"] is False
    r = d["raw"]["canon"][0]
    assert r["state"] == "raw" and r["help"] == f"lampway_normalize_mesh input={r['object']}" and d["raw"]["door"]["error"].startswith("normalize first")
    t = d["twin"]["canon"][0]
    assert t["state"] == "canonical" and d["twin"]["stamped"] is True and t["from"] == "record"
