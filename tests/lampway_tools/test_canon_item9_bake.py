# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 9 (canon 14 B.3): the bake's `auto` cage and ray come from the MEASURED LP<->HP distances - the cage
encloses the HP's greatest height above the LP, the ray reaches the cage plus the HP's greatest depth below it - and an explicit cage
under the median distance is refused. Golden C10 (the bump, and the bump sunk 1 cm). Plan only: no Cycles runs here."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from canon_support import goldens  # noqa: E402,F401
from test_canon_item6_tools import run  # noqa: E402

BODY = '''
from mixar.modules.lampway_tools.features import bake as BK
low = load_obj(GOLD + "/C10_bake/lp_plane.obj", "low")
high = load_obj(GOLD + "/C10_bake/hp_bump.obj", "high")
a = BK.plan("high", "low", ["normal"], 256, None, None, None, 4, "gl", False, "bake", False, root)
high.location.z = -0.01; bpy.context.view_layer.update()
b = BK.plan("high", "low", ["normal"], 256, None, None, None, 4, "gl", False, "bake", False, root)
try:
    BK.plan("high", "low", ["normal"], 256, None, 0.004, None, 4, "gl", False, "bake", False, root); small = None
except Exception as e:
    small = str(e)
try:
    BK.plan("high", "low", ["normal"], 256, None, None, None, 4, "+Y", False, "bake", False, root); green = None
except Exception as e:
    green = str(e)
res({"green": green, "a": {k: a[k] for k in ("cage_extrusion_m", "max_ray_m", "measured")}, "b": {k: b[k] for k in ("cage_extrusion_m", "max_ray_m", "measured")},
     "pad": BK.AUTO_PAD, "small": small})
'''


def test_g14_auto_cage_and_ray_come_from_the_measured_distances(goldens):
    d = run(BODY, goldens)
    pad = d["pad"]
    a, b = d["a"], d["b"]
    assert a["measured"]["height_max_m"] == pytest.approx(0.05, abs=1e-6) and a["measured"]["depth_max_m"] == pytest.approx(0.0, abs=1e-6), a
    assert a["cage_extrusion_m"] == pytest.approx(0.05 * pad, abs=1e-6) and a["max_ray_m"] == pytest.approx(0.05 * pad, abs=1e-6), a
    assert b["measured"]["height_max_m"] == pytest.approx(0.04, abs=1e-6) and b["measured"]["depth_max_m"] == pytest.approx(0.01, abs=1e-6), b
    assert b["cage_extrusion_m"] == pytest.approx(0.04 * pad, abs=1e-6) and b["max_ray_m"] == pytest.approx((0.04 + 0.01) * pad, abs=1e-6), b
    assert b["measured"]["median_m"] == pytest.approx(0.01, abs=1e-6)
    assert d["small"] and "median" in d["small"] and "0.01" in d["small"], d["small"]
    assert d["green"] and d["green"].startswith("normal_green is gl") and "'+Y'" in d["green"], d["green"]          # "+Y" used to bake DX silently (anything but "gl" took NEG_Y)


def _png16(path):
    """(bit depth, (h, w, c) float array in 0..1) of a PNG, decoded here (Pillow narrows 16-bit RGB)."""
    import struct
    import zlib

    import numpy as np
    data = Path(path).read_bytes()
    w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
    pos, idat = 8, b""
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IDAT":
            idat += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    ch = {2: 3, 6: 4, 0: 1, 4: 2}[ctype]
    bpp = ch * depth // 8
    raw = zlib.decompress(idat)
    rows, prev, i = [], bytearray(w * bpp), 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + w * bpp])
        i += 1 + w * bpp
        for x in range(len(line)):
            a = line[x - bpp] if x >= bpp else 0
            b, c = prev[x], (prev[x - bpp] if x >= bpp else 0)
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(bytes(line))
        prev = line
    arr = np.frombuffer(b"".join(rows), dtype=">u2" if depth == 16 else np.uint8).reshape(h, w, ch).astype(float)
    return depth, arr / (65535.0 if depth == 16 else 255.0)


def test_g14_1_one_gl_bake_16_bit_and_dx_is_its_green_flipped(goldens, tmp_path):
    """canon 14 B.4 / F.2: normals are 16-bit, baked ONCE in GL; DX is the same pixels with green flipped, never a second bake. The
    cap's tangent normals match the analytic surface (golden C10 G14.1, within 0.02)."""
    from canon_support import J
    d = run('''
low = load_obj(GOLD + "/C10_bake/lp_plane.obj", "low")
high = load_obj(GOLD + "/C10_bake/hp_bump.obj", "high")
g = api.bake_maps("high", "low", maps=["normal"], size=256, samples=1, out_dir="gl", normal_green="gl", cage_extrusion_m=0.06, max_ray_m=0.12, attach=False)
x = api.bake_maps("high", "low", maps=["normal"], size=256, samples=1, out_dir="dx", normal_green="dx", cage_extrusion_m=0.06, max_ray_m=0.12, attach=False)
import shutil
for tag, o in (("gl", g), ("dx", x)):
    if o.get("ok"):
        shutil.copy(o["maps"]["normal"], DEST + "/" + tag + ".png")                      # the run's temp dir is removed with it
res({"g": {k: g.get(k) for k in ("ok", "error", "normal")}, "x": {k: x.get(k) for k in ("ok", "error", "normal")}})
'''.replace("DEST", repr(str(tmp_path))), goldens)
    assert d["g"]["ok"] and d["x"]["ok"], d
    dg, G = _png16(tmp_path / "gl.png")
    dx, X = _png16(tmp_path / "dx.png")
    assert dg == 16 and dx == 16
    import numpy as np
    assert len(np.unique(np.round(G[..., 0] * 65535))) > 256, "16-bit in name only: the data has at most 8-bit levels"   # the cap's flank is continuous
    exp = J(goldens, "C10_bake/expected.json")
    for s in exp["samples"]:
        u, v = s["uv"]
        px = G[min(int((1 - v) * 256), 255), min(int(u * 256), 255), :3]
        assert max(abs(px - s["rgb_gl"])) < 0.02, (s, px.tolist())
    assert abs(X[..., 1] - (1 - G[..., 1])).max() < 1e-4 and abs(X[..., [0, 2]] - G[..., [0, 2]]).max() < 1e-4
    assert d["g"]["normal"] == {"convention": "gl", "bit_depth": 16, "baked": "gl"} and d["x"]["normal"] == {"convention": "dx", "bit_depth": 16, "baked": "gl", "green_flipped": True}


def test_attach_shades_a_dx_bake_like_the_gl_bake(goldens, tmp_path):
    """contract normalize_texture test 2 / canon 14: Blender's Normal Map node reads GL; a DX map attached straight into it shades
    the bump inverted. Attached through the green flip, the DX bake renders as the GL one (EEVEE, 32 px, a grazing sun)."""
    d = run('''
import numpy as np
low = load_obj(GOLD + "/C10_bake/lp_plane.obj", "low")
high = load_obj(GOLD + "/C10_bake/hp_bump.obj", "high")
outs = {}
for tag in ("gl", "dx"):
    r = api.bake_maps("high", "low", maps=["normal"], size=64, samples=1, out_dir=tag, normal_green=tag, cage_extrusion_m=0.06, max_ray_m=0.12,
                      attach=True, overwrite=True)
    assert r.get("ok"), r
    outs[tag] = low.data.materials[-1].name
high.hide_render = True
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); bpy.context.scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(80), 0, math.radians(30))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); bpy.context.scene.collection.objects.link(cam)
cam.data.type = "ORTHO"; cam.data.ortho_scale = 1.0; cam.location = (0, 0, 2); bpy.context.scene.camera = cam
sc = bpy.context.scene; sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = 32; sc.render.image_settings.file_format = "PNG"
px = {}
for tag in ("gl", "dx"):
    low.data.materials.clear(); low.data.materials.append(bpy.data.materials[outs[tag]])
    sc.render.filepath = os.path.join(root, tag + ".png"); bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath); px[tag] = np.array(img.pixels[:]).reshape(32, 32, 4)[..., :3]
res({"diff": float(np.abs(px["gl"] - px["dx"]).max()), "spread": float(px["gl"].max() - px["gl"].min())})
''', goldens)
    assert d["spread"] > 0.05, d                     # the bump is visible in the GL render
    assert d["diff"] < 0.01, d                       # and the DX bake attached through the flip renders the same
