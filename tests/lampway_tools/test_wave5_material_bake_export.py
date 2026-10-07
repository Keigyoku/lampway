# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""material_bake_export (specs/mixar_docs/material_bake_export.md) in the real binary: the layer-stack material baked to engine textures in a niced HEADLESS Cycles worker (never the live scene), with the
colour spaces, the normal convention, ORM packing and a README with every file's sha256. The stack's base colour is known, so the bake can be checked against it."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE_BX = '''
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
import numpy as np
from PIL import Image
COLOR = [0.2, 0.4, 0.6]
def srgb(c):
    return [(12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055) for x in c]
def stack():
    bpy.ops.mesh.primitive_cube_add(); ob = bpy.context.active_object; ob.name = "Plate"
    call("layered_material", action="init", object="Plate")
    call("layered_material", action="add_layer", object="Plate", layer={"type": "fill", "name": "Colour", "color": COLOR})
    return ob
def bumpy(ob):
    """Give the baked material a real normal perturbation (a flat cube's tangent normal is constant, which cannot tell DX from GL)."""
    nt = ob.active_material.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 6.0
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 1.0; bump.inputs["Distance"].default_value = 0.5
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"]); nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
def mode_colour(path):
    a = np.asarray(Image.open(path).convert("RGB"))
    flat = a.reshape(-1, 3)
    covered = flat[flat.max(axis=1) > 0]                                                       # the UV-covered texels: the rest of the atlas is untouched background
    vals, counts = np.unique(covered, axis=0, return_counts=True)
    i = counts.argmax()
    return vals[i].tolist(), float(counts[i]) / max(len(covered), 1), a
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, PRE_BX + body, timeout=600, **kw)


def one(r):
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_a_known_base_colour_bakes_to_that_colour_with_the_right_colour_spaces_and_a_readme_with_hashes(tmp_path):
    d = one(go(tmp_path, '''
stack()
res = call("material_bake_export", object="Plate", channels=["base_color", "roughness", "metallic"], size=1024, out_dir="tex", allow_dirty=True, samples=4)
col, frac, _a = mode_colour(res["files"]["base_color"])
readme = open(res["readme"]).read()
print("RESULT", json.dumps({"res": res, "col": col, "frac": frac, "want": [round(x * 255) for x in srgb(COLOR)], "readme": readme}))
'''))
    res = d["res"]
    assert res["ok"] and set(res["files"]) == {"base_color", "roughness", "metallic"} and res["sizes"] == [1024, 1024]
    assert res["colour_spaces"]["base_color"] == "sRGB" and res["colour_spaces"]["roughness"] == "Non-Color" and res["normal_green"] == "gl"
    assert all(abs(a - b) <= 2 for a, b in zip(d["col"], d["want"])) and d["frac"] > 0.9, (d["col"], d["want"], d["frac"])      # 90 % of the covered texels carry the layer colour
    for name, p in res["files"].items():
        assert Path(p).name in d["readme"] and len(res["sha256"][name]) == 64 and res["sha256"][name] in d["readme"]


def test_normal_dx_and_gl_differ_only_in_green_and_orm_packs_ao_roughness_metallic_in_that_order(tmp_path):
    d = one(go(tmp_path, '''
bumpy(stack())
gl = call("material_bake_export", object="Plate", channels=["normal"], size=1024, out_dir="gl", normal_green="gl", allow_dirty=True, samples=2)
dx = call("material_bake_export", object="Plate", channels=["normal"], size=1024, out_dir="dx", normal_green="dx", allow_dirty=True, samples=2)
orm = call("material_bake_export", object="Plate", channels=["roughness", "metallic", "ao"], size=1024, out_dir="orm", pack="orm", allow_dirty=True, samples=2)
nogl = np.asarray(Image.open(gl["files"]["normal"]).convert("RGB")).astype(int)
nodx = np.asarray(Image.open(dx["files"]["normal"]).convert("RGB")).astype(int)
mask = nogl.sum(axis=2) > 0
o = np.asarray(Image.open(orm["files"]["orm"]).convert("RGB")).astype(float) / 255
rough = np.asarray(Image.open(orm["files"]["roughness"]).convert("L")).astype(float) / 255
met = np.asarray(Image.open(orm["files"]["metallic"]).convert("L")).astype(float) / 255
print("RESULT", json.dumps({"r": int(np.abs(nogl[..., 0] - nodx[..., 0])[mask].max()), "b": int(np.abs(nogl[..., 2] - nodx[..., 2])[mask].max()), "g": float(np.percentile(np.abs((255 - nogl[..., 1]) - nodx[..., 1])[mask], 99)),
                            "g_spread": int(nogl[..., 1][mask].max() - nogl[..., 1][mask].min()), "orm_g_vs_rough": float(np.abs(o[..., 1] - rough).max()), "orm_b_vs_met": float(np.abs(o[..., 2] - met).max()), "orm_r_mean": float(o[..., 0].mean()),
                            "dx_green": dx["normal_green"], "keys": sorted(orm["files"])}))
'''))
    assert d["g_spread"] > 20, d["g_spread"]                                                      # the map really varies, so the check below can fail
    assert d["r"] <= 1 and d["b"] <= 1 and d["g"] <= 1 and d["dx_green"] == "dx"
    assert d["orm_g_vs_rough"] <= 0.02 and d["orm_b_vs_met"] <= 0.02 and d["orm_r_mean"] > 0.3 and "orm" in d["keys"]


def test_refusals_no_stack_lossy_normal_dirty_project_no_uv_and_the_sizes(tmp_path):
    d = one(go(tmp_path, '''
bpy.ops.mesh.primitive_cube_add(); ob = bpy.context.active_object; ob.name = "Plain"
nostack = call("material_bake_export", object="Plain", allow_dirty=True)
ob = stack()
jpeg_normal = call("material_bake_export", object="Plate", channels=["normal"], format="jpeg", allow_dirty=True)
dirty = call("material_bake_export", object="Plate", channels=["base_color"])
small = call("material_bake_export", object="Plate", size=512, allow_dirty=True)
odd = call("material_bake_export", object="Plate", size=1500, allow_dirty=True)
badch = call("material_bake_export", object="Plate", channels=["curvature"], allow_dirty=True)
outside = call("material_bake_export", object="Plate", out_dir="/etc/lw_nope", allow_dirty=True)
while ob.data.uv_layers: ob.data.uv_layers.remove(ob.data.uv_layers[0])
nouv = call("material_bake_export", object="Plate", allow_dirty=True)
print("RESULT", json.dumps({"nostack": nostack, "jn": jpeg_normal, "dirty": dirty, "small": small, "odd": odd, "badch": badch, "outside": outside, "nouv": nouv}))
'''))
    assert "no layer-paint material on Plain: build one first (lampway_layered_material action=init, or action=apply_manifest)" in d["nostack"]["error"]
    assert "lossy normal maps are refused (use png/exr)" in d["jn"]["error"]
    assert "save the project first" in d["dirty"]["error"]
    assert "size is 1024..8192" in d["small"]["error"] and "power of two" in d["odd"]["error"]
    assert "curvature" in d["badch"]["error"] and "outside the project root" in d["outside"]["error"] and "unwrap first" in d["nouv"]["error"]
