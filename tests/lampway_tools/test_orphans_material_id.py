# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""image_material_id (specs/generation/image_material_id.md): a flat material-ID map. source=parts renders each part in its material's palette colour from the
clay camera (a fact, free, exact); source=model is a DRAFT from the image slot, quantised to the palette with the line art removed and gated on conformance.
REAL binary; the image slot is a recording fake."""

import json

import numpy as np
from PIL import Image

from features_support import run

CHEST = '''
from mixar.modules.lampway_tools.features import material_id as MID
ob = boxes("chest", [((0, 0, 1.0), (0.5, 0.3, 0.6)), ((-0.4, 0, 1.25), (0.25, 0.25, 0.15)), ((0.4, 0, 1.25), (0.25, 0.25, 0.15))])
own = np.array([0] * 6 + [1] * 6 + [2] * 6, dtype=np.int64)            # six faces per box: the plate, then two pauldrons
a = ob.data.attributes.new("part", "INT", "FACE"); a.data.foreach_set("value", own)
json.dump({"parts": {"cuirass": {"class": "metal"}, "pauldron_l": {"class": "leather"}, "pauldron_r": {"class": "leather"}}}, open(os.path.join(root, "recipe.json"), "w"))
PAL = {"metal": "#c0c0c0", "leather": "#5a1e0a"}
'''


def _go(tmp_path, body):
    r = run(tmp_path, CHEST + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_parts_map_is_exactly_the_palette_and_its_regions_sum_to_the_silhouette(tmp_path):
    res = _go(tmp_path, '''
r = call("image_material_id", piece="Chest1", object="chest", view="Front", palette=PAL, recipe="recipe.json", source="parts")
print("RESULT", json.dumps(r))
''')
    assert res["ok"] is True and res["source"] == "parts" and res["conformance"] == 1.0, res
    m = res["maps"]["Front"]
    assert m.endswith("Chest1/Front_matid.png")
    a = np.asarray(Image.open(m).convert("RGBA"))
    op = a[..., 3] > 0
    cols = {tuple(int(c) for c in px) for px in a[op][:, :3]}
    assert cols == {(192, 192, 192), (90, 30, 10)}, cols
    regions = {r["material"]: r for r in res["regions"]["Front"]}
    assert abs(sum(r["fraction"] for r in regions.values()) - float(op.mean())) < 1e-6
    assert regions["metal"]["pixels"] > regions["leather"]["pixels"] > 0


def test_a_palette_with_two_close_colours_is_refused(tmp_path):
    res = _go(tmp_path, '''
print("RESULT", json.dumps(call("image_material_id", piece="P", object="chest", palette={"metal": "#c0c0c0", "steel": "#c4c4c4"}, recipe="recipe.json")))
''')
    assert res["ok"] is False and "indistinguishable materials" in res["error"] and "metal" in res["error"] and "steel" in res["error"], res


def test_parts_need_a_segmented_piece(tmp_path):
    res = _go(tmp_path, '''
one = boxes("one", [((3, 0, 1), (0.3, 0.3, 0.3))])
print("RESULT", json.dumps(call("image_material_id", piece="P", object="one", palette=PAL, recipe="recipe.json")))
''')
    assert res["ok"] is False and "segmented piece" in res["error"], res


def _draft_fakes(extra_blob=False):
    return f'''
import io
calls = []
def fake(prompt, reference_png, count=1, params_extra=None):
    calls.append({{"prompt": prompt, "params": params_extra}})
    im = np.full((200, 200, 3), 255, np.uint8)
    im[40:160, 40:100] = (192, 192, 192); im[40:160, 100:160] = (90, 30, 10)
    im[40:160, 99:101] = 0; im[40:42, 40:160] = 0; im[158:160, 40:160] = 0          # black line art along the borders
    if {extra_blob}: im[60:120, 60:90] = (30, 200, 40)                                # a colour outside the palette
    b = io.BytesIO(); Image.fromarray(im).save(b, "PNG"); return [b.getvalue()]
MID.generate_image = fake
Image.new("RGB", (64, 64), (100, 100, 100)).save(os.path.join(root, "plate.png"))
'''


def test_a_model_draft_is_quantised_with_its_line_art_removed_and_named_draft(tmp_path):
    res = _go(tmp_path, '''
from PIL import Image
''' + _draft_fakes() + '''
dry = call("image_material_id", piece="Chest1", palette=PAL, source="model", design_plate="plate.png", view="Front")
n = len(calls)
live = call("image_material_id", piece="Chest1", palette=PAL, source="model", design_plate="plate.png", view="Front", live=True)
print("RESULT", json.dumps({"dry": dry, "n_after_dry": n, "live": live, "calls": calls}))
''')
    assert res["dry"]["ok"] is True and res["dry"]["dry_run"] is True and res["n_after_dry"] == 0, res["dry"]
    live = res["live"]
    assert live["ok"] is True and live["draft"] is True and live["maps"]["Front"].endswith("Front_matid_draft.png"), live
    assert live["raw_conformance"]["Front"] < 0.99 <= live["conformance"], live
    assert res["calls"][0]["params"] == {"purpose": "mask"} and "#c0c0c0" in res["calls"][0]["prompt"]
    a = np.asarray(Image.open(live["maps"]["Front"]).convert("RGBA"))
    cols = {tuple(int(c) for c in px) for px in a[a[..., 3] > 0][:, :3]}
    assert cols == {(192, 192, 192), (90, 30, 10)}, cols


def test_a_draft_with_colours_outside_the_palette_is_rejected(tmp_path):
    res = _go(tmp_path, '''
from PIL import Image
''' + _draft_fakes(extra_blob=True) + '''
print("RESULT", json.dumps(call("image_material_id", piece="Chest1", palette=PAL, source="model", design_plate="plate.png", live=True)))
''')
    assert res["ok"] is False and "Draft rejected" in res["error"] and "outside the palette" in res["error"], res


def test_model_source_needs_a_design_plate(tmp_path):
    res = _go(tmp_path, '''
print("RESULT", json.dumps(call("image_material_id", piece="P", palette=PAL, source="model")))
''')
    assert res["ok"] is False and "design_plate" in res["error"], res
