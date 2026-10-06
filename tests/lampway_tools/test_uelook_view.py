# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE view (specs/ue_parity/contracts/ue_look.md §6, T-LOOK-02, T-LOOK-03) in the REAL binary, from a cube that is DATA (the
captain's ruling: the generator lives on the UE side). The tests use a SYNTHETIC cube and sidecar (uelook_support): the view
applies the sidecar's log2 shaper then the cube; the config points at the cube where it lies (no copy); the view is named by the
profile and the cube's hash; both traps the audit found are refused: a broken config (Blender silently falls back to AgX) and a
cube changed on disk mid-session (Blender keeps the cube it loaded). enable / disable write the launcher's state."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uelook_support as U  # noqa: E402
from features_support import run  # noqa: E402

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
    return r.results[0]


def generate(tmp_path, profile):
    return go(tmp_path, f'''
print("RESULT", json.dumps(call("ue_look", action="generate", profile={str(profile)!r})))
''')


def test_look03_a_view_per_cube_hash_pointing_at_the_cube_where_it_lies(tmp_path):
    p1, p2 = U.profile_with_cube(tmp_path, "p1.json"), U.profile_with_cube(tmp_path, "p2.json", curve="identity")
    p3 = U.profile_with_cube(tmp_path, "p3.json", edits={"light_units__k": 1})
    bad = U.profile_with_cube(tmp_path, "bad.json")
    Path(json.loads(bad.read_text())["tonemap_cube"]).write_text("LUT_3D_SIZE 32\n")
    d = go(tmp_path, f'''
a = call("ue_look", action="generate", profile={str(p1)!r})
again = call("ue_look", action="generate", profile={str(p1)!r})
b = call("ue_look", action="generate", profile={str(p2)!r})
c = call("ue_look", action="generate", profile={str(p3)!r})
bad = call("ue_look", action="generate", profile={str(bad)!r})
files = sorted(str(p.relative_to(os.path.dirname(a["config_path"]))) for p in __import__("pathlib").Path(os.path.dirname(a["config_path"])).rglob("*") if p.is_file())
print("RESULT", json.dumps({{"a": a, "again": again, "b": b, "c": c, "bad": bad, "files": files, "cfg": open(a["config_path"]).read()}}))
''')
    a = d["a"]
    assert a["ok"] and a["view_name"].startswith("UE 5.8 Filmic ") and a["cube_sha256"] == json.loads(Path(json.loads(p1.read_text())["tonemap_cube_meta"]).read_text())["cube"]["sha256"]
    assert d["b"]["view_name"] != a["view_name"]                                                   # another cube: another view
    assert d["c"]["view_name"] == a["view_name"]                                                   # the same cube under another k: the same view
    assert d["again"]["config_path"] == a["config_path"] and d["again"]["config_sha256"] == a["config_sha256"]
    assert not any(f.endswith(".cube") for f in d["files"]), d["files"]                            # the cube is never copied
    assert json.loads(p1.read_text())["tonemap_cube"] in d["cfg"]                                   # it is read where it lies
    assert not d["bad"]["ok"] and "generate the cube on the UE side, then point UE Look at it" in d["bad"]["error"]


def test_the_view_renders_through_the_shaper_then_the_cube_and_both_traps_are_refused(tmp_path):
    p1, pid = U.profile_with_cube(tmp_path, "p1.json"), U.profile_with_cube(tmp_path, "pid.json", curve="identity")
    gen, gid = generate(tmp_path, p1), generate(tmp_path, pid)
    d = go(tmp_path, GREY + f'''
a = call("ue_look", action="apply", profile={str(p1)!r})
st = call("ue_look", action="status")
S.view_settings.exposure = 0.0
print("RESULT", json.dumps({{"a": a, "st": st, "view": S.view_settings.view_transform, "g18": grey(0.18), "g05": grey(0.05), "g1": grey(1.0)}}))
''', env={"OCIO": gen["config_path"]})
    assert d["a"]["ok"] and d["view"] == gen["view_name"] and d["st"]["view_present"] is True and d["a"]["classes"]["COL"] == "unmeasured", d
    assert d["a"]["cube"]["sha256"] == gen["cube_sha256"] and d["a"]["cube"]["engine_version"] == "5.8.2"
    for k, v in (("g18", 0.18), ("g05", 0.05), ("g1", 1.0)):
        assert abs(d[k] - U.through_cube(v)) <= 0.002, (k, d[k], U.through_cube(v))
    assert abs(d["g18"] - U.srgb(0.18)) <= 0.004                                                 # and the known curve itself at mid grey
    d = go(tmp_path, GREY + f'''
a = call("ue_look", action="apply", profile={str(pid)!r})
S.view_settings.exposure = 0.0
print("RESULT", json.dumps({{"a": a, "g18": grey(0.18)}}))
''', env={"OCIO": gid["config_path"]})
    assert d["a"]["ok"] and abs(d["g18"] - U.through_cube(0.18, "identity")) <= 0.002, (d["g18"], U.enc(0.18))         # the identity cube shows the shaper itself
    # trap 1: a broken config makes Blender fall back to its built-in one (AgX): apply refuses instead of rendering AgX
    broken = Path(gen["config_path"]).with_name("broken.ocio")
    broken.write_text(Path(gen["config_path"]).read_text().replace("ocio_profile_version:", "ocio_profile_version: [", 1))
    d = go(tmp_path, f'''
print("RESULT", json.dumps({{"a": call("ue_look", action="apply", profile={str(p1)!r}), "view": bpy.context.scene.view_settings.view_transform}}))
''', env={"OCIO": str(broken)})
    assert not d["a"]["ok"] and "the UE view is missing: Blender fell back to its built-in config" in d["a"]["error"] and d["view"] == "AgX", d
    # trap 2: the cube changed after the session loaded it. Edited alone it no longer matches its sidecar; re-described by a
    # new sidecar it is a new cube with a new view name this session does not have. Both refused.
    cube, meta = json.loads(p1.read_text())["tonemap_cube"], json.loads(p1.read_text())["tonemap_cube_meta"]
    d = go(tmp_path, f'''
open({cube!r}, "a").write("\\n")
alone = call("ue_look", action="apply", profile={str(p1)!r})
import sys; sys.path.insert(0, {str(Path(__file__).parent)!r}); import uelook_support as U
U.write_meta({meta!r}, {cube!r})
redescribed = call("ue_look", action="apply", profile={str(p1)!r})
print("RESULT", json.dumps({{"alone": alone, "redescribed": redescribed}}))
''', env={"OCIO": gen["config_path"]})
    assert not d["alone"]["ok"] and "sha256" in d["alone"]["error"] and "generate the cube on the UE side" in d["alone"]["error"], d
    assert not d["redescribed"]["ok"] and "the UE view is missing" in d["redescribed"]["error"], d


def test_enable_writes_the_launchers_state_only_for_a_valid_cube_and_disable_removes_it(tmp_path):
    p1 = U.profile_with_cube(tmp_path, "p1.json")
    bad = U.profile_with_cube(tmp_path, "bad.json")
    Path(json.loads(bad.read_text())["tonemap_cube"]).unlink()
    d = go(tmp_path, f'''
from mixar.modules.lampway_tools.ue import launch as L
off = call("ue_look", action="disable")
bad = call("ue_look", action="enable", profile={str(bad)!r})
after_bad = os.path.exists(L.state_path())
on = call("ue_look", action="enable", profile={str(p1)!r})
state = open(L.state_path()).read()
off2 = call("ue_look", action="disable")
print("RESULT", json.dumps({{"bad": bad, "after_bad": after_bad, "on": on, "state": state, "gone": not os.path.exists(L.state_path()), "off2": off2}}))
''')
    assert not d["bad"]["ok"] and "generate the cube on the UE side" in d["bad"]["error"] and d["after_bad"] is False
    on = d["on"]
    assert on["ok"] and on["restart"] is True and "restart Lampway" in on["message"]
    lines = dict(l.split("=", 1) for l in d["state"].splitlines() if "=" in l)
    assert lines["config"] == on["config_path"] and lines["cube"] == json.loads(p1.read_text())["tonemap_cube"] and lines["cube_sha256"] == on["cube_sha256"]
    assert d["gone"] and d["off2"]["ok"]
