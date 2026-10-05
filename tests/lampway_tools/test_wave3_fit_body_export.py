# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_body (shelf/fit_body_package.md) and fit_export (shelf/fit_export.md): the hashed body package and the gated rigged export, in the real binary."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

SETUP = r'''
import hashlib, shutil
from PIL import Image
BONES = (("pelvis", (0, 0, 1), (0, 0, 1.2), None), ("spine_01", (0, 0, 1.2), (0, 0, 1.5), "pelvis"), ("head", (0, 0, 1.5), (0, 0, 1.8), "spine_01"))
def body_package():
    arm = armature("body_rig", BONES)
    body = tube("body_mesh", r=0.2, z0=1, z1=1.8); weights(body, arm, lambda c: {"spine_01": 1.0})
    return arm, body
def piece_fit(arm, name="piece_fit"):
    p = tube(name, r=0.25, z0=1.2, z1=1.6, loc=(0, 0, 0)); weights(p, arm, lambda c: {"spine_01": 1.0})
    return p
def write_json(path, data):
    open(path, "w").write(json.dumps(data))
def textures_for(ob, root, tag, mesh_sha=None):
    d = os.path.join(root, tag); os.makedirs(d, exist_ok=True)
    for n in ("BaseColor", "ORM", "Normal_DX", "Normal_GL"): Image.new("RGB", (4, 4)).save(os.path.join(d, n + ".png"))
    from mixar.modules.lampway_tools.features import workflows as W
    write_json(os.path.join(d, "merge.json"), {"mesh_sha256": mesh_sha or W.mesh_hash(ob)})
    return [os.path.join(d, n + ".png") for n in ("BaseColor", "ORM", "Normal_DX", "Normal_GL")]
GOOD_VALIDATION = {"summary": {"ok": True, "counts": {"PASS": 2, "FAIL": 0, "UNVERIFIED": 0, "REFUSED": 0, "UNPROVEN": 0}, "limits_status": "proposed"},
                   "poses": [{"name": "rest", "pieces": {"p": {"role": "metal", "judge": {"verdict": "PASS"}}}}]}
'''


def run(body, **kw):
    return run_script(PRE + SETUP + body, timeout=300, **kw)


def test_a_body_package_is_hashed_listed_parents_first_and_verifies_until_a_byte_changes():
    r = run('''
arm, body = body_package()
out = api.fit_body("build", armature="body_rig", mesh="body_mesh", out="fit/body")
pkg = out["package"]
ok = api.fit_body("verify", out=pkg)
j = json.load(open(os.path.join(pkg, "joints.json")))
names = [x["name"] for x in j["joints"]]
order_ok = all(names.index(x["parent"]) < names.index(x["name"]) for x in j["joints"] if x["parent"])
write_json(os.path.join(pkg, "joints.json"), {"tampered": True})
bad = api.fit_body("verify", out=pkg)
res({"out": {k: out.get(k) for k in ("ok", "joints", "vertices", "sidecar_vertices")}, "ok": ok["ok"], "order": order_ok, "names": names, "bad": bad.get("error"), "dirname": os.path.basename(pkg)})
''')
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["out"]["joints"] == 3 and d["out"]["vertices"] > 0 and d["out"]["sidecar_vertices"] == 0 and d["ok"] is True and d["order"] is True
    assert d["names"] == ["pelvis", "spine_01", "head"] and "the body asset changed: rebuild the package" in d["bad"] and len(d["dirname"]) == 8


def test_only_the_project_native_body_and_a_sidecar_for_weights_are_accepted():
    r = run('''
arm, body = body_package()
a = api.fit_body("build", armature="body_rig", native_asset="/Game/Characters/Other")
b = api.fit_body("build", armature="body_rig", native_asset="/Game/MetaHumans/NewMetaHumanCharacter_FullBody", uproject="/x.uproject")
c = api.fit_body("build", armature="body_rig", mesh="body_mesh", out="fit/body")
d = api.fit_body("weights", out=c["package"])
res({"a": a.get("error"), "b": b.get("error"), "d": d.get("error")})
''')
    d = r.results[-1]
    assert "project-native body" in d["a"] and "editor leg" in d["b"] and "weights come from the native asset" in d["d"]


def test_export_with_the_contract_settings_reads_back_every_joint_position_and_axis():
    r = run('''
arm, body = body_package()
pkg = api.fit_body("build", armature="body_rig", mesh="body_mesh", out="fit/body")["package"]
p = piece_fit(arm)
tex = textures_for(p, root, "tex1")
write_json(os.path.join(root, "validation.json"), GOOD_VALIDATION); write_json(os.path.join(root, "bind_check.json"), {"ok": True})
out = api.fit_export("piece_fit", "body_rig", "export/p1", body=pkg, textures=tex, validation="validation.json", bind_check="bind_check.json", note="n")
res({"ok": out.get("ok"), "err": out.get("error"), "files": sorted(os.listdir(os.path.join(root, "export/p1"))), "rb": out.get("readback"), "readme": open(os.path.join(root, "export/p1/README.md")).read() if out.get("ok") else ""})
''')
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["ok"] is True, d
    assert {"piece_fit.fbx", "Textures", "README.md", "export.json"} <= set(d["files"])
    assert d["rb"]["ok"] is True and d["rb"]["position_max_m"] < 1e-4 and d["rb"]["axis_max_deg"] < 0.5 and d["rb"]["bones_compared"] == 3
    assert "UnitScaleFactor" in d["readme"] and "limits: proposed" in d["readme"] and "sha256" in d["readme"]


def test_blender_default_axes_fail_the_readback_which_a_position_only_check_would_miss():
    r = run('''
arm, body = body_package()
pkg = api.fit_body("build", armature="body_rig", mesh="body_mesh", out="fit/body")["package"]
p = piece_fit(arm)
tex = textures_for(p, root, "tex2")
write_json(os.path.join(root, "validation.json"), GOOD_VALIDATION); write_json(os.path.join(root, "bind_check.json"), {"ok": True})
out = api.fit_export("piece_fit", "body_rig", "export/p2", body=pkg, textures=tex, validation="validation.json", bind_check="bind_check.json", _bone_axis="Y")
res({"ok": out.get("ok"), "err": out.get("error"), "rb": out.get("readback")})
''')
    d = r.results[-1]
    assert d["ok"] is False and "axes" in d["err"] and d["rb"]["position_max_m"] < 1e-3 and d["rb"]["axis_max_deg"] > 45, d


def test_the_gates_refuse_a_missing_or_failing_validation_unverified_roles_a_stale_texture_and_an_existing_tag():
    r = run('''
arm, body = body_package()
pkg = api.fit_body("build", armature="body_rig", mesh="body_mesh", out="fit/body")["package"]
p = piece_fit(arm); tex = textures_for(p, root, "tex3")
write_json(os.path.join(root, "bind_check.json"), {"ok": True})
common = dict(body=pkg, textures=tex, bind_check="bind_check.json")
none = api.fit_export("piece_fit", "body_rig", "export/g1", validation="nope.json", **common).get("error")
bad_v = json.loads(json.dumps(GOOD_VALIDATION)); bad_v["summary"]["counts"]["FAIL"] = 2; bad_v["summary"]["ok"] = False
write_json(os.path.join(root, "v_fail.json"), bad_v)
fail = api.fit_export("piece_fit", "body_rig", "export/g2", validation="v_fail.json", **common).get("error")
un_v = json.loads(json.dumps(GOOD_VALIDATION)); un_v["summary"]["counts"]["UNVERIFIED"] = 1; un_v["poses"][0]["pieces"]["c"] = {"role": "cloth", "judge": {"verdict": "UNVERIFIED"}}
write_json(os.path.join(root, "v_un.json"), un_v)
un = api.fit_export("piece_fit", "body_rig", "export/g3", validation="v_un.json", **common).get("error")
unok = api.fit_export("piece_fit", "body_rig", "export/g4", validation="v_un.json", allow_unverified=True, **common)
write_json(os.path.join(root, "validation.json"), GOOD_VALIDATION)
stale_tex = textures_for(p, root, "tex_old", mesh_sha="0" * 64)
stale = api.fit_export("piece_fit", "body_rig", "export/g5", validation="validation.json", body=pkg, textures=stale_tex, bind_check="bind_check.json").get("error")
again = api.fit_export("piece_fit", "body_rig", "export/g4", validation="v_un.json", allow_unverified=True, **common).get("error")
res({"none": none, "fail": fail, "un": un, "unok": unok.get("ok"), "readme": open(os.path.join(root, "export/g4/README.md")).read(), "stale": stale, "again": again})
''')
    d = r.results[-1]
    assert "validation" in d["none"] and "validation has 2 FAIL" in d["fail"] and "roles without declared limits: ['cloth']" in d["un"] and d["unok"] is True
    assert "limits: proposed; roles without limits: cloth" in d["readme"]
    assert "textures predate" in d["stale"] and "exists" in d["again"]


def test_a_vertex_group_that_names_a_bone_the_body_does_not_have_is_refused_with_the_names():
    r = run('''
arm, body = body_package()
pkg = api.fit_body("build", armature="body_rig", mesh="body_mesh", out="fit/body")["package"]
p = piece_fit(arm); p.vertex_groups.new(name="not_a_native_bone")
tex = textures_for(p, root, "tex4")
write_json(os.path.join(root, "validation.json"), GOOD_VALIDATION); write_json(os.path.join(root, "bind_check.json"), {"ok": True})
res({"e": api.fit_export("piece_fit", "body_rig", "export/g6", body=pkg, textures=tex, validation="validation.json", bind_check="bind_check.json").get("error")})
''')
    assert "not_a_native_bone" in r.results[-1]["e"]
