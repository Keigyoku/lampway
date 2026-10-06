# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Texture Gen, AI Render and local texture repair (Mixar docs "Generate textures for a mesh", "AI Render: explore a look"; Stefan's
local-texture-repair and multi-piece workflows). Proven code first: projection texturing of cardinal views into the UV atlas with
normal-facing weights (and an optional occlusion ray test), a clay render of the actual mesh as the conditioning image, and a
masked projective blend for repairs. The IMAGE MODEL is the slot (our job queue's image_gen, OpenRouter): the tests replace it
with a deterministic generator, the live run uses the real one. Studio slot: Tripo Texture + PBR (30 + 5 credits, approval first)."""

import json

from features_support import run

SETUP = '''
from PIL import Image
os.makedirs(root + "/views", exist_ok=True)
def solid(path, rgb, size=(120, 120)):
    Image.new("RGB", size, rgb).save(path)
    return path
ball = sphere("ball", 0.5, subdiv=4, loc=(0, 0, 0.5))
uv = call("uv_unwrap", object="ball", method="smart")
obj = uv["object"]
'''


def test_front_and_back_images_are_projected_into_the_atlas_by_which_way_each_texel_faces(tmp_path):
    r = run(tmp_path, SETUP + '''
solid(root + "/views/Front.png", (255, 0, 0)); solid(root + "/views/Back.png", (0, 0, 255))
res = call("project_views", object=obj, views={"Front": "views/Front.png", "Back": "views/Back.png"}, size=128, out="tex/atlas.png")
atlas = np.asarray(Image.open(root + "/tex/atlas.png").convert("RGB")).astype(int)
ob = bpy.data.objects[obj]
print("RESULT", json.dumps({"res": res, "mat": [m.name for m in ob.data.materials],
                            "red": int(((atlas[..., 0] > 200) & (atlas[..., 2] < 60)).sum()), "blue": int(((atlas[..., 2] > 200) & (atlas[..., 0] < 60)).sum()),
                            "px": atlas.shape[0] * atlas.shape[1]}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and out["mat"] == ["ball_uv_proj"]
    assert res["report"]["coverage"] > 0.9 and res["report"]["view_share"]["Front"] > 0.3 and res["report"]["view_share"]["Back"] > 0.3
    assert out["red"] > 500 and out["blue"] > 500, (out["red"], out["blue"])


def test_occlusion_removes_the_front_view_from_texels_a_nearer_surface_hides(tmp_path):
    r = run(tmp_path, '''
from PIL import Image
os.makedirs(root + "/views", exist_ok=True)
Image.new("RGB", (120, 120), (255, 0, 0)).save(root + "/views/Front.png")
big = boxes("two", [((0, 0.3, 0.5), (1.0, 0.2, 1.0)), ((0, -0.3, 0.5), (0.4, 0.2, 0.4))])    # a small cube in front of a wall
uv = call("uv_unwrap", object="two", method="angle", angle_limit=60)
a = call("project_views", object=uv["object"], views={"Front": "views/Front.png"}, size=128, out="tex/a.png", occlusion=False)
b = call("project_views", object=uv["object"], views={"Front": "views/Front.png"}, size=128, out="tex/b.png", occlusion=True)
print("RESULT", json.dumps({"a": a["report"]["view_texels"]["Front"], "b": b["report"]["view_texels"]["Front"]}))
''')
    out = r.results[0]
    assert out["b"] < out["a"], out


def test_texture_gen_chains_clay_render_image_slot_and_projection_and_applies_the_material(tmp_path):
    r = run(tmp_path, '''
from mixar.modules.lampway_tools.features import texture as T
calls = []
def fake_image(prompt, reference_png, count=1):
    calls.append({"prompt": prompt, "ref_bytes": len(reference_png)})
    from PIL import Image
    import io
    im = Image.new("RGB", (64, 64), (20, 200, 60)); b = io.BytesIO(); im.save(b, "PNG")
    return [b.getvalue()]
T.generate_image = fake_image
ball = sphere("ball", 0.5, subdiv=4, loc=(0, 0, 0.5))
uv = call("uv_unwrap", object="ball", method="smart")
res = call("texture_gen", object=uv["object"], prompt="mossy stone", views=["Front", "Back"], size=128, out_dir="tex/gen")
print("RESULT", json.dumps({"res": res, "calls": calls, "files": sorted(os.listdir(root + "/tex/gen")),
                            "mat": [m.name for m in bpy.data.objects[res["object"]].data.materials],
                            "src_mat": [m.name for m in bpy.data.objects[uv["object"]].data.materials]}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    assert out["res"]["ok"] is True and len(out["calls"]) == 2 and all(c["ref_bytes"] > 100 for c in out["calls"])
    assert all("mossy stone" in c["prompt"] for c in out["calls"])
    assert {"clay_Front.png", "clay_Back.png", "gen_Front.png", "gen_Back.png", "atlas.png"} <= set(out["files"])
    assert out["res"]["report"]["coverage"] > 0.8 and out["mat"] == ["ball_uv_tex_proj"] and out["src_mat"] == [], "the result is a copy; the source keeps its materials"


def test_ai_render_renders_the_clay_view_and_hands_it_to_the_image_slot(tmp_path):
    r = run(tmp_path, '''
from mixar.modules.lampway_tools.features import texture as T
seen = {}
def fake_image(prompt, reference_png, count=1):
    seen["prompt"] = prompt; seen["ref"] = reference_png[:8]
    from PIL import Image
    import io
    b = io.BytesIO(); Image.new("RGB", (80, 60), (90, 90, 200)).save(b, "PNG"); return [b.getvalue()]
T.generate_image = fake_image
sphere("ball", 0.5, subdiv=3, loc=(0, 0, 0.5))
res = call("ai_render", object="ball", prompt="a warm evening interior", view="Front", out="ai/look.png")
print("RESULT", json.dumps({"res": res, "seen": {"prompt": seen["prompt"], "png": seen["ref"] == b"\\x89PNG\\r\\n\\x1a\\n"}, "exists": os.path.exists(root + "/ai/look.png"),
                            "img": "look.png" in [i.name for i in bpy.data.images]}))
''')
    out = r.results[0]
    assert out["res"]["ok"] is True and out["seen"]["png"] is True and "warm evening interior" in out["seen"]["prompt"] and out["exists"] and out["img"]
    assert "does not change" in out["res"]["note"], "the docs: AI Render is an image for look development, it does not change scene materials or lights"


def test_repair_blends_a_patch_through_a_mask_into_the_existing_texture_only_where_masked(tmp_path):
    r = run(tmp_path, SETUP + '''
Image.new("RGB", (128, 128), (128, 128, 128)).save(root + "/tex_base.png")
solid(root + "/views/patch.png", (255, 0, 0), (120, 120))
m = Image.new("L", (120, 120), 0)
from PIL import ImageDraw
ImageDraw.Draw(m).ellipse([40, 40, 80, 80], fill=255); m.save(root + "/views/mask.png")
res = call("repair_texture", object=obj, texture="tex_base.png", view="Front", patch="views/patch.png", mask="views/mask.png", out="tex_fixed.png", feather=2)
base = np.asarray(Image.open(root + "/tex_base.png").convert("RGB")).astype(int); fixed = np.asarray(Image.open(root + "/tex_fixed.png").convert("RGB")).astype(int)
changed = (np.abs(fixed - base).sum(axis=2) > 30)
print("RESULT", json.dumps({"res": res, "changed": int(changed.sum()), "px": base.shape[0] * base.shape[1], "base_same": bool((base == 128).all()),
                            "red_where_changed": float(((fixed[changed][:, 0] > 160) & (fixed[changed][:, 1] < 110)).mean()) if changed.any() else 0.0}))
''')
    out = r.results[0]
    assert out["res"]["ok"] is True and out["base_same"] is True, "the original texture is never overwritten"
    assert 20 < out["changed"] < out["px"] * 0.3 and out["red_where_changed"] > 0.8, "the feathered rim is a partial blend, the core is the patch"
    assert out["res"]["report"]["changed_fraction"] == round(out["changed"] / out["px"], 4) or abs(out["res"]["report"]["changed_fraction"] - out["changed"] / out["px"]) < 0.02


def test_studio_slot_and_refusals(tmp_path):
    r = run(tmp_path, SETUP + '''
print("RESULT", json.dumps({"studio": call("texture_gen", object=obj, prompt="x", engine="studio:tripo"),
    "no_uv": call("project_views", object="ball", views={"Front": "views/none.png"}, size=64, out="t.png"),
    "bad_view": call("project_views", object=obj, views={"Up": "x.png"}, size=64, out="t.png"),
    "outside": call("project_views", object=obj, views={"Front": "/etc/hostname"}, size=64, out="t.png")}))
''')
    out = r.results[0]
    assert out["studio"]["needs_approval"] is True and "30 credits" in out["studio"]["price"]
    assert out["no_uv"]["ok"] is False and "UV" in out["no_uv"]["error"]
    assert out["bad_view"]["ok"] is False and "Up" in out["bad_view"]["error"]
    assert out["outside"]["ok"] is False and "outside the project root" in out["outside"]["error"]
