# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""zone_sheet (specs/wiki/zone_sheet.md): one image where every material slot, part, segment or vertex group of an object is a flat colour with a number, and
a legend, so a region is named by number. REAL binary, Workbench."""

import json

import numpy as np
from PIL import Image

from features_support import run

PIECE = '''
ob = boxes("piece", [((0, 0, 1.0), (0.6, 0.3, 0.6)), ((-0.6, 0, 1.0), (0.3, 0.3, 0.3)), ((0.6, 0, 1.0), (0.3, 0.3, 0.3))])
for n in ("plate", "gold", "leather"):
    ob.data.materials.append(bpy.data.materials.new(n))
idx = np.array([0] * 6 + [1] * 6 + [2] * 6, dtype=np.int32)
ob.data.polygons.foreach_set("material_index", idx)
a = ob.data.attributes.new("part", "INT", "FACE"); a.data.foreach_set("value", np.array([0] * 6 + [1] * 12, dtype=np.int64))
canon("piece")                                       # the door: the tool reads a canonical mesh
'''


def _go(tmp_path, body):
    r = run(tmp_path, PIECE + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_each_zone_gets_a_distinct_colour_and_number(tmp_path):
    res = _go(tmp_path, '''
print("RESULT", json.dumps(call("zone_sheet", object="piece", by="material_slot", views=["Front"], size=256, out="zones/piece.png")))
''')
    assert res["ok"] is True, res
    leg = res["legend"]
    assert [z["number"] for z in leg] == [1, 2, 3] and [z["name"] for z in leg] == ["plate", "gold", "leather"], leg
    assert len({tuple(z["rgb"]) for z in leg}) == 3, "two zones never share a colour"
    a = np.asarray(Image.open(res["sheet_png"]).convert("RGB")).astype(int)
    for z in leg:
        assert (np.abs(a - np.array(z["rgb"])).sum(axis=2) == 0).sum() > 100, z
    assert json.loads(open(res["legend_json"]).read())["legend"] == leg


def test_legend_counts_match_slots_and_parts(tmp_path):
    res = _go(tmp_path, '''
out = {"slots": call("zone_sheet", object="piece", by="material_slot", views=["Front", "Back"], size=256, out="z/a.png"),
       "parts": call("zone_sheet", object="piece", by="part", views=["Front"], size=256, out="z/b.png")}
print("RESULT", json.dumps(out))
''')
    assert [z["faces"] for z in res["slots"]["legend"]] == [6, 6, 6] and res["slots"]["views"] == ["Front", "Back"], res["slots"]
    assert [z["faces"] for z in res["parts"]["legend"]] == [6, 12], res["parts"]
    w = Image.open(res["slots"]["sheet_png"]).size[0]
    assert w >= 2 * 100, "the views sit side by side on one sheet"


def test_refusals(tmp_path):
    res = _go(tmp_path, '''
one = boxes("one", [((3, 0, 1), (0.3, 0.3, 0.3))]); canon("one")
print("RESULT", json.dumps({"seg": call("zone_sheet", object="piece", by="segment"), "one": call("zone_sheet", object="one", by="material_slot"),
                            "big": call("zone_sheet", object="piece", size=4096)}))
''')
    assert res["seg"]["ok"] is False and "run segment_mesh first" in res["seg"]["error"], res
    assert res["one"]["ok"] is False and "two zones" in res["one"]["error"], res
    assert res["big"]["ok"] is False and "256..2048" in res["big"]["error"], res
