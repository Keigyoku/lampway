# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""multi_piece_material (specs/wiki/multi_piece_material.md): one material across separate pieces: merge copies into a proxy with one shared atlas, texture the
proxy once, transfer the texture back to each piece's ORIGINAL UV layout, with the texel density compared per piece. REAL binary."""

import json

import numpy as np
from PIL import Image

from features_support import run

PIECES = '''
import bmesh
from mathutils import Matrix
def cube(name, x, size=0.5):
    bm = bmesh.new(); uv = bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_cube(bm, size=size, matrix=Matrix.Translation((x, 0, 0.5)), calc_uvs=True)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))
cube("helm", 0.0); cube("boot", 2.0); cube("glove", 4.0, size=0.3)
COLORS = {"helm": (220, 30, 30), "boot": (30, 200, 40), "glove": (40, 60, 230)}
def paint_proxy(proxy_name, path, res=256):
    """The atlas a texturing pass would make: each piece's faces in the SHARED UVs filled with that piece's flat colour."""
    from PIL import Image, ImageDraw
    p = bpy.data.objects[proxy_name]; me = p.data
    piece = np.empty(len(me.polygons), dtype=np.int64); me.attributes["lw_piece"].data.foreach_get("value", piece)
    names = json.loads(p["lw_proxy"])["pieces"]
    im = Image.new("RGB", (res, res), (0, 0, 0)); d = ImageDraw.Draw(im)
    uv = me.uv_layers["lw_shared"].data
    for f in me.polygons:
        pts = [(uv[l].uv[0] * res, (1 - uv[l].uv[1]) * res) for l in f.loop_indices]
        d.polygon(pts, fill=COLORS[names[piece[f.index]]])
    im.save(path)
'''


def _go(tmp_path, body):
    r = run(tmp_path, PIECES + body, timeout=600)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_transfer_returns_the_proxy_colour_to_each_original_uv(tmp_path):
    res = _go(tmp_path, '''
canon(*["helm", "boot", "glove"])
m = call("multi_piece_material", action="merge", pieces=["helm", "boot", "glove"], atlas_res=256)
paint_proxy(m["proxy"], os.path.join(root, "atlas.png"))
t = call("multi_piece_material", action="transfer", proxy=m["proxy"], atlas="atlas.png", out_dir="mpm")
from PIL import Image, ImageDraw
layout = {}
for n in ("helm", "boot", "glove"):                                        # each piece's OWN uv layout, rasterised: where its texture must land
    me = bpy.data.objects[n].data; uv = me.uv_layers.active.data
    im = Image.new("L", (256, 256), 0); d = ImageDraw.Draw(im)
    for f in me.polygons:
        d.polygon([(uv[l].uv[0] * 256, (1 - uv[l].uv[1]) * 256) for l in f.loop_indices], fill=255)
    layout[n] = os.path.join(root, n + "_layout.png"); im.save(layout[n])
print("RESULT", json.dumps({"m": m, "t": t, "layout": layout, "src_mats": {n: [x.name for x in bpy.data.objects[n].data.materials] for n in ("helm", "boot", "glove")}}))
''')
    t = res["t"]
    assert res["m"]["ok"] is True and t["ok"] is True, res
    for row in t["per_piece"]:
        a = np.asarray(Image.open(row["texture"]).convert("RGBA")).astype(int)
        cov = a[..., 3] > 0
        want = {"helm": (220, 30, 30), "boot": (30, 200, 40), "glove": (40, 60, 230)}[row["source"]]
        assert cov.sum() > 1000 and (np.abs(a[cov][:, :3] - np.array(want)).sum(axis=1) <= 3).mean() > 0.99, (row, a[cov][:5])
        assert row["object"] == row["source"] + "_mpm"
        lay = np.asarray(Image.open(res["layout"][row["source"]])) > 127
        assert (cov & lay).sum() / (cov | lay).sum() > 0.97, "the texture lands on the piece's ORIGINAL uv layout"
    assert res["src_mats"] == {"helm": [], "boot": [], "glove": []}, "the originals are untouched"


def test_proxy_edit_blocks_transfer(tmp_path):
    res = _go(tmp_path, '''
canon(*["helm", "boot"])
m = call("multi_piece_material", action="merge", pieces=["helm", "boot"], atlas_res=128)
paint_proxy(m["proxy"], os.path.join(root, "atlas.png"), 128)
bpy.data.objects[m["proxy"]].data.vertices[0].co.z += 0.1
print("RESULT", json.dumps(call("multi_piece_material", action="transfer", proxy=m["proxy"], atlas="atlas.png", out_dir="mpm")))
''')
    assert res["ok"] is False and "the proxy changed after merge; re-merge" in res["error"], res


def test_density_ratio_reported_per_piece(tmp_path):
    res = _go(tmp_path, '''
canon(*["helm", "boot", "glove"])
m = call("multi_piece_material", action="merge", pieces=["helm", "boot", "glove"], atlas_res=256, individual_res=256)
print("RESULT", json.dumps(m))
''')
    rows = {r["object"]: r for r in res["density"]}
    assert set(rows) == {"helm", "boot", "glove"}, res
    for r in rows.values():
        assert 0 < r["ratio"] < 1 and abs(r["ratio"] - r["texel_density_shared"] / r["texel_density_individual"]) < 1e-3, r
        assert r["pass"] == (r["ratio"] >= res["density_floor_ratio"])


def test_overlapping_pieces_refused(tmp_path):
    res = _go(tmp_path, '''
cube("over", 0.2)
canon(*["helm", "over"])
print("RESULT", json.dumps(call("multi_piece_material", action="merge", pieces=["helm", "over"])))
''')
    assert res["ok"] is False and "pieces overlap; move them apart for the proxy only" in res["error"], res
