# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon 03 G / F.6: the body package CARRIES its native weight sidecar, read and checked at build (a file that is not the engine's
weights, or one weighted to a bone the package's skeleton lacks, is refused and no package is written), and it records what the fit
order refuses on: whether the body is CLOSED and whether the HEAD is included (the head joint inside the closed body).
REAL binary."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_fit_support import FIT_PRE  # noqa: E402


def run(tmp_path, body):
    r = run_script(FIT_PRE + body, env={"LW_KEEP_ROOT": str(tmp_path)}, timeout=300)
    assert r.rc == 0, r.out[-2500:]
    return r.results[-1]


def test_the_package_carries_the_sidecar_and_records_closed_and_head_included(tmp_path):
    d = run(tmp_path, '''
body, arm = human()
sc = write_sidecar(body, arm, os.path.join(root, "ue", "sidecar.json"), root_bone="pelvis")
b = api.fit_body("build", armature="rig", mesh="body", sidecar="ue/sidecar.json", out="fit/body")
v = api.fit_body("verify", out=os.path.relpath(b["package"], root)) if b.get("ok") else None
res({"build": b, "verify": v, "receipt": json.load(open(os.path.join(b["package"], "receipt.json"))) if b.get("ok") else None})
''')
    assert d["build"]["ok"], d["build"]
    rc = d["receipt"]
    assert rc["sidecar"]["schema"] == "titan.native-weight-sidecar/1" and rc["sidecar"]["vertices"] == 24 and rc["sidecar"]["bones"] == 5, rc["sidecar"]
    assert {k: rc["body"][k] for k in ("closed", "boundary_edges", "head_included", "head_joint")} == {"closed": True, "boundary_edges": 0, "head_included": True, "head_joint": "head"}, rc["body"]
    assert d["verify"]["ok"] and d["verify"]["body"]["closed"] and d["verify"]["body"]["head_included"] and d["verify"]["sidecar"], d["verify"]


def test_a_headless_or_open_body_is_recorded_as_such(tmp_path):
    d = run(tmp_path, '''
out = {}
for tag, kw in (("headless", {"head": False}), ("open", {"open_body": True})):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    body, arm = human(**kw)
    b = api.fit_body("build", armature="rig", mesh="body", out="fit/" + tag)
    out[tag] = json.load(open(os.path.join(b["package"], "receipt.json")))["body"] if b.get("ok") else b
res(out)
''')
    assert d["headless"]["closed"] is True and d["headless"]["head_included"] is False, d["headless"]
    assert d["open"]["closed"] is False and d["open"]["boundary_edges"] > 0 and d["open"]["head_included"] is True and d["open"]["native_openings_accepted"], d["open"]


def test_a_sidecar_that_is_not_the_engines_weights_or_names_a_foreign_bone_is_refused_and_nothing_is_written(tmp_path):
    d = run(tmp_path, '''
body, arm = human()
write_sidecar(body, arm, os.path.join(root, "ue", "wrong.json"), schema="titan.armour-helpers/1")
bad = api.fit_body("build", armature="rig", mesh="body", sidecar="ue/wrong.json", out="fit/wrong")
write_sidecar(body, arm, os.path.join(root, "ue", "foreign.json"))
doc = json.load(open(os.path.join(root, "ue", "foreign.json")))
doc["result"]["bones"]["clavicle_r"] = "spine_03"
row = doc["result"]["vertices"]["0"]; row["weights"] = {"spine_03": 0.5, "clavicle_r": 0.5}
json.dump(doc, open(os.path.join(root, "ue", "foreign.json"), "w"))
foreign = api.fit_body("build", armature="rig", mesh="body", sidecar="ue/foreign.json", out="fit/foreign")
res({"bad": bad, "foreign": foreign, "dirs": sorted(os.listdir(os.path.join(root, "fit"))) if os.path.isdir(os.path.join(root, "fit")) else []})
''')
    assert d["bad"]["ok"] is False and "titan.native-weight-sidecar/1" in d["bad"]["error"], d["bad"]
    assert d["foreign"]["ok"] is False and "clavicle_r" in d["foreign"]["error"], d["foreign"]
    for tag in ("wrong", "foreign"):
        assert not (Path(str(tmp_path)) / "fit" / tag).exists() or not any(
            (q / "receipt.json").exists() for q in (Path(str(tmp_path)) / "fit" / tag).iterdir()), f"a refused build wrote a package under fit/{tag}"


def test_seam_split_topology_and_native_openings_use_winding_without_welding_authored_vertices(tmp_path):
    d = run(tmp_path, '''
body, arm = human()
me = body.data; me.calc_loop_triangles()
verts, faces = [], []
for tri in me.loop_triangles:
    i = len(verts)
    verts.extend([tuple(me.vertices[k].co) for k in tri.vertices])
    faces.append((i, i + 1, i + 2))
split = bpy.data.meshes.new("seam_split"); split.from_pydata(verts, [], faces); body.data = split
n_before = len(split.vertices)
b = api.fit_body("build", armature="rig", mesh="body", out="fit/split")
st = json.load(open(os.path.join(b["package"], "receipt.json")))["body"]
# One head triangle removed represents an authored facial opening. It does not
# remove the head or convert the authored source to welded publication geometry.
faces.pop(-1)
opened = bpy.data.meshes.new("native_opening"); opened.from_pydata(verts, [], faces); body.data = opened
c = api.fit_body("build", armature="rig", mesh="body", out="fit/opening")
cs = json.load(open(os.path.join(c["package"], "receipt.json")))["body"]
res({"split": st, "open": cs, "source_vertices": n_before, "split_package_vertices": b["vertices"], "unchanged": len(opened.vertices) == n_before})
''')
    assert d["split"]["raw_boundary_edges"] > 0
    assert d["split"]["boundary_edges"] == 0 and d["split"]["non_manifold_edges"] == 0
    assert d["split"]["closed"] and d["split"]["head_included"]
    assert d["open"]["boundary_edges"] == 3 and not d["open"]["closed"]
    assert d["open"]["head_included"] and d["open"]["native_openings_accepted"]
    assert d["open"]["head_winding"] > 0.5
    assert d["source_vertices"] == d["split_package_vertices"] and d["unchanged"]


def test_preview_glb_and_native_sidecar_keep_their_distinct_bytes(tmp_path):
    d = run(tmp_path, '''
import hashlib
body, arm = human()
write_sidecar(body,arm,os.path.join(root,"sidecar.json"))
bpy.ops.export_scene.gltf(filepath=os.path.join(root,"preview.glb"),export_format="GLB")
b = api.fit_body("build",armature="rig",mesh="body",sidecar="sidecar.json",glb="preview.glb",out="fit/body")
assert b.get("ok"), b
package = b["package"]
res({"sidecar_equal":open(os.path.join(package,"sidecar.json"),"rb").read() == open(os.path.join(root,"sidecar.json"),"rb").read(),
     "preview_equal":open(os.path.join(package,"body.glb"),"rb").read() == open(os.path.join(root,"preview.glb"),"rb").read(),
     "weights":api.fit_body("weights",out=package)})
''')
    assert d["sidecar_equal"] and d["preview_equal"] and d["weights"]["ok"], d
