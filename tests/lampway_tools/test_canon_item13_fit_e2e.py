# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon 03 (IMPLEMENTATION_PLAN item 13): lampway_fit END TO END on the REAL binary, every stage through its real tool.

A synthetic body package (a closed figure with its head, at human size: metres, the goldens' scale) carries its native weight
sidecar, written the way the UE editor leg writes it; a metal waist band (one part, so conform is not applicable: the soft-part
deformer waits on decision 03-H2) runs intake (the source-part check, then normalize_mesh) -> proportion (piece_ratios) -> match
-> place (fit_place, applied to the scene piece) -> pose_correct -> pose (fit_pose, applied: the fit pose) -> openings (detect) ->
bind (fit_bind plan) -> weights (fit_bind weights from the package, then return) -> validate (fit_validate measure, written) ->
export (fit_export: the FBX and its joint read-back).

Two inputs are stand-ins for the UE editor leg, which does not run here, and are said to be: the sidecar file (from the scene
body's own weights, in the engine's frame and schema) and the bind check (the piece's bind against the native reference). The
match stage's sign-off is recorded with decider "captain" as the canon requires; in this test it is the test's, not the captain's."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_fit_support import FIT_PRE  # noqa: E402

E2E = r'''
from mathutils import Matrix
body, arm = figure()
if WITH_SIDECAR:
    write_sidecar(body, arm, os.path.join(root, "ue", "sidecar.json"), root_bone="pelvis")
pkg = api.fit_body("build", armature="rig", mesh="body", sidecar="ue/sidecar.json" if WITH_SIDECAR else "", out="fit/body")
assert pkg.get("ok"), pkg
P = os.path.relpath(pkg["package"], root)
body_npz = os.path.join(P, "body.npz")
def band(name):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=32, radius1=0.19, radius2=0.19, depth=0.2, matrix=Matrix.Translation((0, 0, 1.1)))
    bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.1], cuts=3, use_grid_fill=False)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    ob.vertex_groups.new(name="band").add(list(range(len(me.vertices))), 1.0, "REPLACE")
    return ob
src, piece = band("band_src"), band("band")
json.dump({"ok": True, "over_tolerance": [], "source": "test stand-in for the UE editor leg's bind check"}, open(os.path.join(root, "bind_check.json"), "w"))
def fit(stage, **kw):
    return api.fit(stage=stage, piece="Waist1", **kw)
DOF = [{"bone": "spine_01", "axis": "lateral", "range": [-4, 4], "step": 4, "expect": {"joint": "neck_01", "along": "forward", "min_cm": 0.5}}]
steps = [
    ("intake", dict(kind="waist", roles={"band": "metal"}, body=P,
                    args={"parts": ["band"], "input": "band", "source": "band_src", "turn_deg": 0, "generator": "captain_authored", "weld": "never"})),
    ("proportion", dict(args={"args": ["waist", "Waist1/fit/ratios.json", body_npz, "band=Waist1/band.npz:0"]})),
    ("match", dict(decider="captain", args={"captain_seen": True, "render_sha256": "c" * 64})),
    ("place", dict(args={"piece": "Waist1/band.npz", "body": body_npz, "out": "Waist1/fit/placed.npz", "object": "band"})),
    ("pose_correct", dict(args={"segments": []})),
    ("pose", dict(args={"piece": "band", "body": "body", "armature": "rig", "dofs": DOF, "out": "Waist1/fit/pose.json"})),
    ("openings", dict(args={"object": "band", "axis": [0, 0, 1]})),
    ("bind", dict(args={"piece": "band", "armature": "rig", "out_dir": "Waist1/fit/bind"})),
    ("weights", dict(args={"piece": "band", "armature": "rig", "out_dir": "Waist1/fit/bind"})),
    ("validate", dict(args={"piece": "band", "bound": "band_rest", "original": "band_src", "body": "body",
                            "poses": [{"name": "rest"}, {"name": "bend", "bones": [{"bone": "spine_03", "axis": "lateral", "deg": 10}]}]})),
    ("export", dict(args={"object": "band_rest", "armature": "rig", "out_dir": "export/Waist1/t1", "bind_check": "bind_check.json"})),
]
out = {"early_bind": fit("bind"), "escape": api.fit(piece="../outside"), "stages": {}}
for stage, kw in steps:
    if stage == "proportion":
        npz(piece, os.path.join(root, "Waist1", "band.npz"))               # mesh_to_npz's output for the scorer and the placement
    r = fit(stage, **kw)
    out["stages"][stage] = r
    if not r.get("ok"):
        break
out["status"] = fit("status")
rp = os.path.join(root, "Waist1", "fit", "ratios.json")
out["ratios"] = json.load(open(rp))["pieces"].get("band") if os.path.exists(rp) else None
res(out)
'''


def test_lampway_fit_runs_end_to_end_on_a_synthetic_body_package(tmp_path):
    r = run_script(FIT_PRE + "WITH_SIDECAR = True\n" + E2E, env={"LW_KEEP_ROOT": str(tmp_path)}, timeout=900)
    assert r.rc == 0, r.out[-3000:]
    d = r.results[-1]
    st = d["stages"]
    failed = [(k, v.get("error")) for k, v in st.items() if not v.get("ok")]
    assert not failed, failed
    assert list(st) == ["intake", "proportion", "match", "place", "pose_correct", "pose", "openings", "bind", "weights", "validate", "export"]
    assert d["early_bind"]["ok"] is False and "lampway_fit_pose" in d["early_bind"]["error"], d["early_bind"]
    assert d["escape"]["ok"] is False
    s = d["status"]
    assert s["next"] == [] and s["not_applicable"] == ["conform"] and len(s["done"]) == 11, s
    w = st["weights"]["result"]
    assert "rigid" in w["fit_bind"]["weights_source"] and w["fit_bind"]["body_package_sha256"], w
    assert w["fit_bind_return"]["per_metal_part"]["band"]["max_mm"] < 0.5, w["fit_bind_return"]
    v = st["validate"]["result"]
    assert v["summary"]["ok"] and v["summary"]["counts"]["FAIL"] == 0 and v["rest_fidelity"]["judge"]["band"]["verdict"] == "PASS", v["summary"]
    e = st["export"]["result"]
    assert e["readback"]["ok"], e
    placed = st["place"]["result"]["object"]
    rec = json.loads((tmp_path / "Waist1" / "fit" / "fit.json").read_text())
    assert [x["stage"] for x in rec["stages"]] == list(st) and rec["body"]["package_sha256"], rec
    rt = d["ratios"]
    assert rt and "rms_logdev" in rt and rt["rms_logdev"] == rt["rms_logdev"], rt                  # scored, not NaN
    m = {"proportion_rms_logdev": rt["rms_logdev"], "proportion_dev_pct": rt["dev_pct"], "placement_scale": placed["scale"], "pose_entries": st["pose"]["result"]["entries"],
         "openings": len(st["openings"]["result"]["candidates"]), "metal_return_max_mm": w["fit_bind_return"]["per_metal_part"]["band"]["max_mm"],
         "validation_counts": v["summary"]["counts"], "rest_fidelity_mm": v["rest_fidelity"]["per_part"]["band"]["max_mm"],
         "readback": {k: e["readback"].get(k) for k in ("bones_compared", "position_max_m", "axis_max_deg")}}
    print("E2E", json.dumps(m))


def test_the_same_run_on_a_package_without_its_native_sidecar_stops_at_weights(tmp_path):
    r = run_script(FIT_PRE + "WITH_SIDECAR = False\n" + E2E, env={"LW_KEEP_ROOT": str(tmp_path)}, timeout=900)
    assert r.rc == 0, r.out[-3000:]
    st = r.results[-1]["stages"]
    assert list(st)[-1] == "weights" and all(v["ok"] for k, v in st.items() if k != "weights"), {k: v.get("error") for k, v in st.items()}
    assert st["weights"]["ok"] is False and "weights come from the native asset" in st["weights"]["error"], st["weights"]
    assert r.results[-1]["status"]["next"] == ["lampway_fit stage=weights"]


def test_seam_split_body_with_native_head_opening_runs_every_real_fit_stage(tmp_path):
    seam_open = r'''
body.data.calc_loop_triangles()
old = body.data
triangles = [tuple(t.vertices) for t in old.loop_triangles]
remove = next(i for i,t in enumerate(triangles) if min(old.vertices[k].co.z for k in t) > 1.7)
triangles.pop(remove)
points = [old.vertices[k].co[:] for t in triangles for k in t]
weights_by_vertex = [[(g.group,g.weight) for g in old.vertices[k].groups] for t in triangles for k in t]
group_names = [g.name for g in body.vertex_groups]
mesh = bpy.data.meshes.new("seam_split_native_openings")
mesh.from_pydata(points,[],[(i,i+1,i+2) for i in range(0,len(points),3)]); mesh.update()
body.data = mesh
for name in group_names:
    body.vertex_groups.new(name=name)
for i, groups in enumerate(weights_by_vertex):
    for group, weight in groups:
        body.vertex_groups[group].add([i],weight,"REPLACE")
native_vertex_count = len(body.data.vertices)
'''
    script = E2E.replace('body, arm = figure()','body, arm = figure()\n'+seam_open)
    script = script.replace('res(out)', 'out["body_state"] = api.fit_body("verify",out=P)["body"]\nout["native_vertex_count"] = native_vertex_count\nout["packaged_vertices"] = len(np.load(os.path.join(root,body_npz))["V"])\nres(out)')
    r = run_script(FIT_PRE + "WITH_SIDECAR = True\n" + script, env={"LW_KEEP_ROOT": str(tmp_path)},timeout=900)
    assert r.rc == 0, r.out[-3000:]
    d = r.results[-1]
    assert not [(k,v.get("error")) for k,v in d["stages"].items() if not v.get("ok")], d["stages"]
    assert len(d["stages"]) == 11 and d["status"]["next"] == []
    state = d["body_state"]
    assert state["raw_boundary_edges"] > state["boundary_edges"] > 0 and not state["closed"]
    assert state["head_winding"] > 0.5 and state["native_openings_accepted"]
    assert d["native_vertex_count"] == d["packaged_vertices"]
    assert d["stages"]["weights"]["result"]["fit_bind"]["body_package_sha256"]
    assert d["stages"]["validate"]["result"]["summary"]["ok"]
    assert d["stages"]["export"]["result"]["readback"]["ok"]
