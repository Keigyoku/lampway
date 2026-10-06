# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""lampway_normalize_texture (specs/canon/normalization contracts/normalize_texture.md; the coordinator's door ruling B): an image
into a canonical `texture` - its role (declared, or from the DECLARED source's naming), the colour space bound to that role, the
normal convention (from the naming or declared, never assumed), the raw sha256, the size, bit depth and channels - so image-only
tools can declare a real Need. Runs in the real Blender (tests/lampway_tools/blender_run)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

SCRIPT = r"""
import bpy, json, hashlib, os
from pathlib import Path
from mixar.modules.lampway_tools import api, canon_asset as CA
root = Path(ROOT); root.mkdir(parents=True, exist_ok=True)
api.settings_set(project_root=str(root))

def png(name, w, h, rgb=(0.5, 0.5, 1.0), alpha=False):
    img = bpy.data.images.new("tmp_" + name, w, h, alpha=alpha)
    img.pixels.foreach_set([c for _ in range(w * h) for c in (*rgb, 1.0)])
    img.filepath_raw = str(root / name); img.file_format = "PNG"; img.save()
    bpy.data.images.remove(img)
    return name

out = {}
for n in ("Metal009_2K-PNG_Color.png", "Metal009_2K-PNG_NormalGL.png", "Metal009_2K-PNG_Roughness.png"):
    png(n, 64, 64)
out["acg"] = {n: api.normalize_texture(input=n, source_naming="ambientcg") for n in ("Metal009_2K-PNG_Color.png", "Metal009_2K-PNG_NormalGL.png", "Metal009_2K-PNG_Roughness.png")}
out["acg_cs"] = {i.name: i.colorspace_settings.name for i in bpy.data.images if i.name.startswith("Metal009")}
out["acg_docs"] = {i.name: json.loads(i["lw_canon"]) for i in bpy.data.images if "lw_canon" in i}
out["sha"] = hashlib.sha256((root / "Metal009_2K-PNG_NormalGL.png").read_bytes()).hexdigest()
png("rock_nor_dx_1k.png", 32, 48); png("rock_arm_1k.png", 32, 32)
out["ph_n"] = api.normalize_texture(input="rock_nor_dx_1k.png", source_naming="polyhaven")
out["ph_arm"] = api.normalize_texture(input="rock_arm_1k.png", source_naming="polyhaven")
png("mystery.png", 16, 16)
out["auto_none"] = api.normalize_texture(input="mystery.png")
out["normal_undeclared"] = api.normalize_texture(input="mystery.png", role="normal")
out["normal_declared"] = api.normalize_texture(input="mystery.png", role="normal", normal_convention="dx", tiling_real_world_m=[2.0, 2.0])
out["normal_declared_doc"] = (out["normal_declared"].get("document") or {"body": {"normal": {}}})
out["role_bad"] = api.normalize_texture(input="Metal009_2K-PNG_Roughness.png", role="shiny")

# the door: an image-only tool can now declare a real Need
probe = api.tool(consumes={"image": api.Need(kind=("texture",), roles=("normal",))})(lambda image: {"ran": image})
png("raw_one.png", 8, 8)
from mixar.modules.lampway_tools import canon_io
canon_io.load_image(str(root / "raw_one.png"))
again_img = canon_io.load_image(str(root / "Metal009_2K-PNG_NormalGL.png"), check_existing=True)       # a placement re-reading a canonical image
out["reload"] = {"same": again_img.name, "raw": "lw_raw" in again_img.keys(), "canon": "lw_canon" in again_img.keys()}
out["door_raw"] = probe(image="raw_one.png")
out["door_ok"] = probe(image="Metal009_2K-PNG_NormalGL.png")
out["door_role"] = probe(image="Metal009_2K-PNG_Roughness.png")
bpy.data.images["Metal009_2K-PNG_NormalGL.png"].colorspace_settings.name = "sRGB"
out["door_changed"] = probe(image="Metal009_2K-PNG_NormalGL.png")
out["again"] = api.normalize_texture(input="Metal009_2K-PNG_NormalGL.png", source_naming="ambientcg")
png("Metal009_2K-PNG_NormalGL.png", 64, 64, rgb=(0.4, 0.6, 1.0))                     # the file is rewritten under the stamped image
out["door_file"] = probe(image="Metal009_2K-PNG_NormalGL.png")
print("RESULT", json.dumps(out))
"""


def test_normalize_texture_binds_role_colour_space_and_convention_and_opens_the_door(tmp_path):
    r = run_script(SCRIPT.replace("ROOT", repr(str(tmp_path / "proj"))), timeout=180)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    for n, res in d["acg"].items():
        assert res["ok"], (n, res)
    assert d["acg_cs"] == {"Metal009_2K-PNG_Color.png": "sRGB", "Metal009_2K-PNG_NormalGL.png": "Non-Color", "Metal009_2K-PNG_Roughness.png": "Non-Color"}
    nd = d["acg_docs"]["Metal009_2K-PNG_NormalGL.png"]
    assert nd["kind"] == "texture" and nd["body"]["role"] == "normal" and nd["body"]["colour_space"] == "Non-Color"
    assert nd["body"]["normal"] == {"convention": "gl", "space": "tangent", "tangent_basis": "mikktspace", "convention_evidence": "source_naming"}
    assert nd["body"]["width"] == 64 and nd["body"]["height"] == 64 and nd["body"]["power_of_two"] is True and nd["body"]["bit_depth"] == 8
    assert nd["body"]["image_sha256"] == d["sha"] == nd["raw"]["sha256"] and nd["raw"]["container"] == "png"
    assert d["acg_docs"]["Metal009_2K-PNG_Color.png"]["body"]["role"] == "basecolor"
    assert d["ph_n"]["ok"] and d["ph_n"]["document"]["body"]["normal"]["convention"] == "dx" and d["ph_n"]["document"]["body"]["power_of_two"] is False
    assert d["ph_arm"]["document"]["body"]["role"] == "orm" and d["ph_arm"]["document"]["body"]["packing"] == {"r": "ao", "g": "roughness", "b": "metallic"}
    assert d["auto_none"]["ok"] is False and "role unknown for mystery.png: declare role=" in d["auto_none"]["error"]
    assert d["normal_undeclared"]["ok"] is False and "normal convention unknown: declare normal_convention=gl|dx" in d["normal_undeclared"]["error"]
    assert d["normal_declared"]["ok"], d["normal_declared"]
    assert d["normal_declared_doc"]["body"]["normal"]["convention_evidence"] == "declared" and d["normal_declared_doc"]["body"]["tiling"] == {"real_world_m": [2.0, 2.0]}
    assert d["role_bad"]["ok"] is False and "shiny" in d["role_bad"]["error"]
    assert d["reload"] == {"same": "Metal009_2K-PNG_NormalGL.png", "raw": False, "canon": True}, d["reload"]
    assert d["door_ok"] == {"ok": True, "ran": "Metal009_2K-PNG_NormalGL.png"}, d["door_ok"]
    assert d["door_raw"]["ok"] is False and d["door_raw"]["error"].startswith("normalize first") and d["door_raw"]["help"][0] == "lampway_normalize_texture input=raw_one.png"
    assert d["door_role"]["ok"] is False and "texture role 'roughness'" in d["door_role"]["error"]
    assert d["door_changed"]["ok"] is False and "colour space 'sRGB'" in d["door_changed"]["error"], d["door_changed"]
    assert d["door_file"]["ok"] is False and "image file changed since it was normalized" in d["door_file"]["error"], d["door_file"]
    assert d["again"]["ok"] and d["again"]["document"]["body"]["colour_space"] == "Non-Color"         # normalizing again restores it
