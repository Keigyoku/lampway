# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE view's consumer side (specs/ue_parity/contracts/ue_look.md §6, T-LOOK-02, T-LOOK-03) in the REAL binary. The cube is
DATA named by the profile (tonemap.lut: cube, cube_sha256, shaper); these tests use a SYNTHETIC cube (the sRGB encoding of the
shaper-decoded value), so they prove the plumbing: the view applies the profile's log2 shaper then its cube, a view is named
by the profile hash, a cube file is never rewritten, and both traps the audit found are refused loudly: a broken config
(Blender silently falls back to its built-in config, AgX) and a cube rewritten on disk mid-session (Blender keeps the old one)."""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

SHAPER = {"base": 2.0, "lin_side_slope": 1.0, "lin_side_offset": 0.0039, "log_side_slope": 1 / 14.0, "log_side_offset": 0.6}


def _lin(enc):
    """The shaper's inverse: the linear value a cube coordinate stands for."""
    return 2.0 ** ((enc - SHAPER["log_side_offset"]) / SHAPER["log_side_slope"]) - SHAPER["lin_side_offset"]


def _srgb(x):
    x = max(0.0, min(1.0, x))
    return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


def write_cube(path, size=32):
    rows = [f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    g = [_srgb(_lin(i / (size - 1))) for i in range(size)]
    for b in range(size):
        for gg in range(size):
            for r in range(size):
                rows.append(f"{g[r]:.7f} {g[gg]:.7f} {g[b]:.7f}")
    path.write_text("\n".join(rows) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profile(tmp_path, name, cube, sha, **edits):
    src = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/ue/profiles/engine_defaults.json"
    p = json.loads(src.read_text())
    p["source"] = "live-dump"
    p["tonemap"]["lut"] = {"cube": str(cube), "cube_sha256": sha, "size": 32, "shaper": SHAPER}
    for k, v in edits.items():
        p["light_units"][k] = v
    q = tmp_path / name
    q.write_text(json.dumps(p))
    return q


GREY = r'''
S = bpy.context.scene
S.render.engine = "BLENDER_EEVEE"; S.render.resolution_x = 4; S.render.resolution_y = 1; S.eevee.taa_render_samples = 1
S.render.dither_intensity = 0.0
w = bpy.data.worlds.new("W"); w.use_nodes = True; S.world = w
cd = bpy.data.cameras.new("C"); cam = link(bpy.data.objects.new("C", cd)); S.camera = cam
def grey(v):
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (v, v, v, 1)
    p = os.path.join(root, f"g{len(os.listdir(root))}.png")
    S.render.image_settings.file_format = "PNG"; S.render.image_settings.color_depth = "16"; S.render.filepath = p
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(p); im.colorspace_settings.name = "Non-Color"
    v = float(np.array(im.pixels[:]).reshape(-1, 4)[:, 0].mean()); bpy.data.images.remove(im); return v
'''


def go(tmp_path, body, env=None):
    r = run(tmp_path, body, env=env or {}, timeout=600)
    assert r.rc == 0, r.out[-3000:]
    return r.results[0], r.out


def test_look03_a_view_per_profile_hash_and_a_cube_is_never_rewritten(tmp_path):
    cube = tmp_path / "ue.cube"
    sha = write_cube(cube)
    p1, p2 = profile(tmp_path, "p1.json", cube, sha), profile(tmp_path, "p2.json", cube, sha, k=1)
    bad = profile(tmp_path, "bad.json", cube, "0" * 64)
    d, _ = go(tmp_path, f'''
a = call("ue_look", action="generate", profile={str(p1)!r})
b = call("ue_look", action="generate", profile={str(p2)!r})
c1 = open(a["cube_path"], "rb").read()
again = call("ue_look", action="generate", profile={str(p1)!r})
bad = call("ue_look", action="generate", profile={str(bad)!r})
print("RESULT", json.dumps({{"a": a, "b": b, "again": again, "same_bytes": c1 == open(a["cube_path"], "rb").read(), "bad": bad}}))
''')
    a, b = d["a"], d["b"]
    assert a["ok"] and b["ok"] and a["view_name"] != b["view_name"] and a["view_name"].startswith("UE 5.8 Filmic ")
    assert Path(a["config_path"]).parent != Path(b["config_path"]).parent
    assert d["again"]["ok"] and d["again"]["config_path"] == a["config_path"] and d["same_bytes"]
    assert d["again"]["config_sha256"] == a["config_sha256"]                         # T-COL-03 for the consumer: same profile, same bytes
    assert not d["bad"]["ok"] and "cube_sha256" in d["bad"]["error"]


def test_view_renders_through_the_shaper_then_the_cube_and_traps_are_refused(tmp_path):
    cube = tmp_path / "ue.cube"
    sha = write_cube(cube)
    p1 = profile(tmp_path, "p1.json", cube, sha)
    gen, _ = go(tmp_path, f'''
print("RESULT", json.dumps(call("ue_look", action="generate", profile={str(p1)!r})))
''')
    cfg, view = gen["config_path"], gen["view_name"]
    # a session started with the config: apply sets the view, and greys come out as the synthetic cube says (sRGB of linear)
    d, _ = go(tmp_path, GREY + f'''
a = call("ue_look", action="apply", profile={str(p1)!r})
st = call("ue_look", action="status")
print("RESULT", json.dumps({{"a": a, "st": st, "view": S.view_settings.view_transform, "g18": grey(0.18), "g05": grey(0.05)}}))
''', env={"OCIO": cfg})
    assert d["a"]["ok"] and d["view"] == view and d["st"]["view_present"] is True and d["a"]["classes"]["COL"] == "unmeasured", d
    ev = 2 ** d["a"]["exposure_stops"]
    assert abs(d["g18"] - _srgb(0.18 * ev)) <= 0.004, (d["g18"], _srgb(0.18 * ev))
    assert abs(d["g05"] - _srgb(0.05 * ev)) <= 0.004, (d["g05"], _srgb(0.05 * ev))
    # trap 1: a broken config makes Blender fall back to its built-in one: apply refuses instead of rendering AgX
    broken = Path(cfg).with_name("broken.ocio")
    broken.write_text(Path(cfg).read_text().replace("ocio_profile_version:", "ocio_profile_version: [", 1))
    d, out = go(tmp_path, f'''
print("RESULT", json.dumps({{"a": call("ue_look", action="apply", profile={str(p1)!r}), "view": bpy.context.scene.view_settings.view_transform}}))
''', env={"OCIO": str(broken)})
    assert not d["a"]["ok"] and "the UE view is missing: Blender fell back to its built-in config" in d["a"]["error"], d
    # trap 2: the cube rewritten on disk after the session loaded it: Blender keeps the old processor, so apply refuses
    d, _ = go(tmp_path, f'''
open({gen["cube_path"]!r}, "a").write("\\n")
print("RESULT", json.dumps({{"a": call("ue_look", action="apply", profile={str(p1)!r})}}))
''', env={"OCIO": cfg})
    assert not d["a"]["ok"] and "the cube changed on disk" in d["a"]["error"], d
