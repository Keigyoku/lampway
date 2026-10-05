# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""pbr_pack (wiki/pbr_pack.md): pack engine-ready maps, audit a material's colour spaces and connected channels, swap only the base colour.

pack is numpy/PIL and runs here; audit and swap read and edit a node tree, so they run in the real binary."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from blender_run import run_script  # noqa: E402
from mixar.modules.lampway_tools.pipeline import pbr_pack as PP  # noqa: E402


def _png(path, arr):
    Image.fromarray(np.asarray(arr, dtype=np.uint8)).save(path)
    return str(path)


@pytest.fixture
def maps(tmp_path):
    n = 64
    rng = np.random.default_rng(1)
    base = rng.integers(0, 255, (n, n, 3))
    normal = np.zeros((n, n, 3)); normal[..., 0] = 140; normal[..., 1] = 100; normal[..., 2] = 240
    rough = np.full((n, n), 200); metal = np.full((n, n), 255); ao = np.full((n, n), 90)
    return {"base": _png(tmp_path / "b.png", base), "normal": _png(tmp_path / "n.png", normal), "rough": _png(tmp_path / "r.png", rough), "metal": _png(tmp_path / "m.png", metal),
            "ao": _png(tmp_path / "ao.png", ao), "root": str(tmp_path)}


def test_pack_writes_orm_in_unreal_order_and_both_normal_conventions(maps):
    out = PP.pack(maps, "both", "pk", maps["root"])
    orm = np.asarray(Image.open(out["files"]["ORM"]).convert("RGB"))
    assert (orm[..., 0] == 90).all() and (orm[..., 1] == 200).all() and (orm[..., 2] == 255).all()          # R occlusion, G roughness, B metallic
    gl = np.asarray(Image.open(out["files"]["Normal_GL"]).convert("RGB")).astype(int)
    dx = np.asarray(Image.open(out["files"]["Normal_DX"]).convert("RGB")).astype(int)
    assert (dx[..., 1] == 255 - gl[..., 1]).all() and (dx[..., 0] == gl[..., 0]).all() and (dx[..., 2] == gl[..., 2]).all()
    assert out["merge"]["colorspace"] == {"BaseColor": "sRGB", "ORM": "Non-Color", "Normal_GL": "Non-Color", "Normal_DX": "Non-Color"}
    assert {"BaseColor", "ORM", "Normal_DX", "Normal_GL", "Roughness", "Metallic"} <= set(out["files"])


def test_no_ao_gives_r_equal_one_and_the_result_says_so(maps):
    m = dict(maps, ao=None)
    out = PP.pack(m, "gl", "pk2", maps["root"])
    assert (np.asarray(Image.open(out["files"]["ORM"]).convert("RGB"))[..., 0] == 255).all() and "no AO map: ORM red is 1" in " ".join(out["notes"])
    assert "Normal_DX" not in out["files"]


def test_a_flat_normal_is_flagged_and_a_non_power_of_two_is_refused(maps, tmp_path):
    flat = _png(tmp_path / "flat.png", np.dstack([np.full((64, 64), 128), np.full((64, 64), 128), np.full((64, 64), 255)]))
    out = PP.pack(dict(maps, normal=flat), "gl", "pk3", maps["root"])
    assert any("flat normal: no height information" in n for n in out["notes"])
    odd = _png(tmp_path / "odd.png", np.zeros((60, 60, 3)))
    with pytest.raises(PP.PackError, match="power-of-two"):
        PP.pack(dict(maps, base=odd, normal=odd, rough=odd, metal=odd, ao=None), "gl", "pk4", maps["root"])


def test_metallic_is_forced_to_zero_on_the_listed_cloth_classes_and_not_otherwise(maps, tmp_path):
    mask = np.zeros((64, 64), np.uint8); mask[:, :32] = 255
    mpath = _png(tmp_path / "mask_red.png", mask)
    out = PP.pack(dict(maps), "gl", "pk5", maps["root"], metal_zero_masks=[mpath])
    metal = np.asarray(Image.open(out["files"]["Metallic"]).convert("L"))
    assert (metal[:, :32] == 0).all() and (metal[:, 32:] == 255).all()
    out2 = PP.pack(dict(maps), "gl", "pk6", maps["root"])                         # falsifier: no mask, metal untouched
    assert (np.asarray(Image.open(out2["files"]["Metallic"]).convert("L")) == 255).all()


def test_pack_never_overwrites_a_set(maps):
    PP.pack(maps, "gl", "pk7", maps["root"])
    with pytest.raises(PP.PackError, match="exists"):
        PP.pack(maps, "gl", "pk7", maps["root"])


PRE = r'''
import bpy, json, os, tempfile, numpy as np
from PIL import Image
from mixar.modules.lampway_tools import api
root = tempfile.mkdtemp(prefix="lw_pbr_"); api.settings_set(project_root=root)
bpy.ops.wm.read_factory_settings(use_empty=True)
def img(name, v, cs):
    p = os.path.join(root, name + ".png"); Image.fromarray(np.full((16, 16, 3), v, np.uint8)).save(p)
    i = bpy.data.images.load(p); i.colorspace_settings.name = cs; return i
def build(normal_cs="Non-Color"):
    me = bpy.data.meshes.new("m"); me.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0)], [], [(0,1,2,3)]); me.uv_layers.new(name="UVMap")
    ob = bpy.data.objects.new("piece", me); bpy.context.scene.collection.objects.link(ob)
    m = bpy.data.materials.new("mat"); m.use_nodes = True; ob.data.materials.append(m)
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    def tex(img_, label):
        n = nt.nodes.new("ShaderNodeTexImage"); n.image = img_; n.label = label; return n
    nt.links.new(tex(img("base", 200, "sRGB"), "base").outputs["Color"], b.inputs["Base Color"])
    nt.links.new(tex(img("rough", 100, "Non-Color"), "rough").outputs["Color"], b.inputs["Roughness"])
    nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(tex(img("normal", 128, normal_cs), "normal").outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return ob
def res(r): print("RESULT " + json.dumps(r))
'''


def test_audit_fails_a_normal_map_in_srgb_and_lists_the_connected_channels_and_the_missing_ones():
    r = run_script(PRE + '''
build("sRGB")
a = api.pbr_pack("audit", object="piece")
res({"issues": a["issues"], "connected": a["connected"], "checks": a["checks"]})
''', timeout=240)
    assert r.rc == 0, r.out[-1200:]
    d = r.results[-1]
    assert any("normal" in i and "Non-Color" in i for i in d["issues"]), d
    linked = {c["channel"]: c["linked"] for c in d["connected"]}
    assert linked["Base Color"] and linked["Normal"] and linked["Roughness"] and not linked["Metallic"]
    assert any("Metallic" in i and "not connected" in i for i in d["issues"])


def test_audit_passes_a_correct_material_for_the_connected_channels():
    r = run_script(PRE + '''
build("Non-Color")
a = api.pbr_pack("audit", object="piece")
res({"bad": [c for c in a["checks"] if not c["pass"]], "n": len(a["checks"])})
''', timeout=240)
    d = r.results[-1]
    assert d["bad"] == [] and d["n"] == 3


def test_swap_replaces_only_the_base_keeps_roughness_and_normal_and_edits_a_copy():
    r = run_script(PRE + '''
ob = build("Non-Color")
newp = os.path.join(root, "newbase.png"); Image.fromarray(np.full((16, 16, 3), 10, np.uint8)).save(newp)
out = api.pbr_pack("swap_base_color", object="piece", new_base=newp)
nt = bpy.data.materials[out["material"]].node_tree
labels = {n.label: os.path.basename(n.image.filepath) for n in nt.nodes if n.type == "TEX_IMAGE"}
orig = {n.label: os.path.basename(n.image.filepath) for n in bpy.data.materials["mat"].node_tree.nodes if n.type == "TEX_IMAGE"}
res({"out": out.get("replaced"), "labels": labels, "orig": orig, "name": out["material"], "slot": ob.material_slots[0].material.name})
''', timeout=240)
    assert r.rc == 0, r.out[-1200:]
    d = r.results[-1]
    assert d["out"] == "base" and d["labels"]["base"] == "newbase.png" and d["labels"]["rough"] == "rough.png" and d["labels"]["normal"] == "normal.png"
    assert d["orig"]["base"] == "base.png" and d["name"] != "mat" and d["slot"] == d["name"]


def test_swap_is_refused_when_the_colour_map_does_not_share_the_meshs_uv_layout():
    r = run_script(PRE + '''
build()
newp = os.path.join(root, "newbase.png"); Image.fromarray(np.full((16, 16, 3), 10, np.uint8)).save(newp)
a = api.pbr_pack("swap_base_color", object="piece", new_base=newp, uv_hash="deadbeef")
res({"e": a.get("error"), "ok": a.get("ok")})
''', timeout=240)
    d = r.results[-1]
    assert d["ok"] is False and "the colour map must share this mesh's UV layout" in d["e"]
