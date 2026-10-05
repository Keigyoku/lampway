# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""bake_maps (wiki + mixar_docs contracts): a high-poly donor baked onto a UV-mapped low-poly target by a niced headless Cycles worker, never the live scene.

The planner's refusals are pure; the bake itself runs in the real binary on tiny meshes (64 px maps, 4 samples)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

PRE = r'''
import bpy, json, bmesh, math, os, tempfile
from mixar.modules.lampway_tools import api
root = tempfile.mkdtemp(prefix="lw_bake_")
api.settings_set(project_root=root)
bpy.ops.wm.read_factory_settings(use_empty=True)

def plane(name, n, z_fn=None, size=1.0, color=None, uv=True, loc=(0, 0, 0), scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=n, y_segments=n, size=size / 2)
    if z_fn:
        for v in bm.verts:
            v.co.z = z_fn(v.co.x, v.co.y)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    ob.location = loc; ob.scale = scale
    if color:
        m = bpy.data.materials.new(name + "_m"); m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1)
        me.materials.append(m)
    if uv:
        bpy.context.view_layer.objects.active = ob; ob.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT"); bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.001); bpy.ops.object.mode_set(mode="OBJECT"); ob.select_set(False)
    return ob

def err(out):
    return None if out.get('ok') else out.get('error')

def res(r):
    print("RESULT " + json.dumps(r))
'''


def run(body, **kw):
    return run_script(PRE + body, timeout=600, **kw)


def test_a_dented_plane_baked_onto_a_flat_quad_has_nonflat_normals_and_the_report_says_so():
    r = run('''
plane("high", 32, lambda x, y: 0.05 * math.exp(-((x * x + y * y) / 0.03)), color=(0.8, 0.2, 0.1), uv=False)
plane("low", 1)
out = api.bake_maps("high", "low", maps=["normal", "albedo", "ao"], size=64, samples=4, out_dir="bake", max_ray_m=0.2, cage_extrusion_m=0.1)
import numpy as np
from PIL import Image
assert out.get("ok"), out
n = np.asarray(Image.open(out["maps"]["normal"]).convert("RGB")).astype(float) / 255
res({"ok": out.get("ok"), "std": float(n.std(axis=(0, 1)).max()), "keys": sorted(out["maps"]), "checks": out["checks"], "margin": out["margin_px"], "cs": out["colorspace"], "err": out.get("error")})
''')
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["ok"] is True, d
    assert d["std"] > 0.02 and d["keys"] == ["albedo", "ao", "normal"] and d["margin"] >= 2
    assert d["cs"] == {"normal": "Non-Color", "albedo": "sRGB", "ao": "Non-Color"}


def test_albedo_has_no_lighting_a_flat_colour_donor_gives_a_constant_colour():
    r = run('''
plane("high", 8, lambda x, y: 0.05 * math.sin(6 * x), color=(0.8, 0.2, 0.1), uv=False)
plane("low", 1)
out = api.bake_maps("high", "low", maps=["albedo"], size=32, samples=4, out_dir="bake", max_ray_m=0.2, cage_extrusion_m=0.1)
import numpy as np
from PIL import Image
a = np.asarray(Image.open(out["maps"]["albedo"]).convert("RGB")).astype(float)
c = a[8:24, 8:24].reshape(-1, 3)
res({"std": float(c.std(axis=0).max()), "mean": c.mean(axis=0).tolist(), "diffuse_flags": out["albedo_passes"]})
''')
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["std"] < 3.0, d                       # a Combined bake of the wavy donor would carry the lighting
    assert d["diffuse_flags"] == ["COLOR"]
    assert d["mean"][0] > d["mean"][1] > d["mean"][2]


def test_a_misaligned_pair_is_refused_before_any_bake():
    r = run('''
plane("high", 4, color=(1, 0, 0), uv=False)
plane("low", 1, loc=(0.5, 0, 0))
res({"refused": err(api.bake_maps("high", "low", out_dir="bake"))})
''')
    assert r.rc == 0, r.out[-1500:]
    assert "align them first" in r.results[-1]["refused"], r.results[-1]


def test_no_uv_overlap_unapplied_scale_and_the_same_object_are_refused_with_the_fix():
    r = run('''
plane("high", 4, uv=False); plane("nouv", 1, uv=False)
plane("scaled", 1, scale=(2, 1, 1)); plane("same", 1)
out = {}
for key, args in {"nouv": ("high", "nouv"), "scaled": ("high", "scaled"), "same": ("same", "same")}.items():
    out[key] = err(api.bake_maps(*args, maps=["normal"], out_dir="bake"))
# two quads sharing one UV square overlap
a = plane("a", 1); b = plane("b", 1)
bm = bmesh.new(); bm.from_mesh(a.data); bm.faces.ensure_lookup_table()
bm.free()
join = plane("hi2", 2, uv=False)
low = plane("lowj", 2)
for l in low.data.uv_layers.active.data: l.uv = (0.25 + 0.1 * l.uv[0], 0.25 + 0.1 * l.uv[1])
for f in low.data.polygons[:1]:
    pass
dup = bpy.data.objects.new("lowdup", low.data.copy()); bpy.context.scene.collection.objects.link(dup)
bpy.context.view_layer.objects.active = low; low.select_set(True); dup.select_set(True)
bpy.ops.object.join()
out["overlap"] = err(api.bake_maps("hi2", "lowj", maps=["normal"], out_dir="bake"))
res(out)
''')
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert "unwrap first" in d["nouv"] and "apply scale first" in d["scaled"] and "two objects" in d["same"] and "overlapping UVs" in d["overlap"], d


def test_a_bake_never_overwrites_an_existing_map_and_the_live_scene_is_untouched():
    r = run('''
plane("high", 4, color=(1, 0, 0), uv=False); plane("low", 1)
before = (len(bpy.data.objects), bpy.context.scene.render.engine, len(bpy.data.materials), len(bpy.data.images))
out = api.bake_maps("high", "low", maps=["albedo"], size=32, samples=2, out_dir="bake", cage_extrusion_m=0.1, max_ray_m=0.2)
after = (len(bpy.data.objects), bpy.context.scene.render.engine, len(bpy.data.materials), len(bpy.data.images))
again = err(api.bake_maps("high", "low", maps=["albedo"], size=32, samples=2, out_dir="bake", cage_extrusion_m=0.1, max_ray_m=0.2))
out2 = api.bake_maps("high", "low", maps=["albedo"], size=32, samples=2, out_dir="bake", cage_extrusion_m=0.1, max_ray_m=0.2, overwrite=True)
res({"before": before, "after": after, "again": again, "ok2": out2["ok"], "engine": bpy.context.scene.render.engine})
''')
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["before"][0] == d["after"][0] and d["before"][1] == d["after"][1] and d["engine"] != "CYCLES"
    assert "overwrite" in d["again"] and d["ok2"] is True


def test_an_unsupported_map_names_what_is_supported():
    r = run('''
plane("high", 4, uv=False); plane("low", 1)
res({"e": err(api.bake_maps("high", "low", maps=["curvature"], out_dir="bake"))})
''')
    assert "curvature" in r.results[-1]["e"] and "normal, albedo, ao" in r.results[-1]["e"]
