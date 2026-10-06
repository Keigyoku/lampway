# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Self-test of the rig goldens R01-R08: recompute every expected value from the case inputs with rig_reference.py, and show
each falsifier failing. Exit 1 on any failure.

    python3 rig_selftest.py [dir]"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rig_reference as R  # noqa: E402

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
ROWS = []


def check(case, what, ok, detail=""):
    ROWS.append((case, what, bool(ok), detail))


def case(name):
    return json.loads((ROOT / name / "case.json").read_text())


def close(a, b, tol=1e-7):
    return np.allclose(np.asarray(a, float), np.asarray(b, float), atol=tol)


def r01():
    c = case("R01_mapping")
    i, e, f = c["input"], c["expected"], c["falsifier"]
    fam, hits = R.detect_family(i["names"], i["tables"])
    m, missing = R.map_slots(i["names"], i["tables"][fam], i["required"])
    check("R01", "family detected by table hits", fam == e["family"] and hits == e["hits"], f"{fam} {hits}")
    check("R01", "slot map exact, no required slot missing", m == e["map"] and missing == e["missing_required"] == [], f"{len(m)} slots")
    try:
        R.detect_family(i["tie_names"], i["tables"])
        check("R01", "a tie between families refuses", False)
    except ValueError:
        check("R01", "a tie between families refuses", e["tie"] == "refused")
    syn = R.synthesize_chain([(n, p) for n, p in i["src_torso"]], e["fractions"])
    check("R01", "missing spine joints at the reference fractions", all(close(syn[k], e["synthesized"][k]) for k in ("spine_03", "spine_04")),
          "spine_03 %s" % np.round(syn["spine_03"], 4).tolist())
    bad = R.substring_map(i["names"], i["substring_words"])
    check("R01", "falsifier: substring mapping takes LeftHandIndex1 for the hand", bad == f["substring_map"] and f["substring_wrong_slots"] == ["hand_l"],
          bad["hand_l"])
    mid = R.midpoint_synthesis(dict(i["src_torso"])["spine_02"], dict(i["src_torso"])["spine_05"])
    err = float(np.linalg.norm(mid - syn["spine_03"]))
    check("R01", "falsifier: midpoint synthesis is off the reference", abs(err - f["midpoint_error_m"]) < 1e-7 and err > 0.01, f"{err * 1000:.1f} mm")


def r02():
    c = case("R02_rest_frames")
    i, e, f = c["input"], c["expected"], c["falsifier"]
    J = i["joints"]
    names = i["chain"]                    # JSON sorts keys: the chain order is carried explicitly
    ok_y = ok_x = True
    for a, b in zip(names[:-1], names[1:]):
        ok_y &= close(R.frame_from(J[a], J[b], i["up_hint"], "y"), e["frames_blender"][a])
        ok_x &= close(R.frame_from(J[a], J[b], i["up_hint"], "x"), e["frames_ue_axes"][a])
    check("R02", "frames from joints + up hint (Y along / X along)", ok_y and ok_x)
    check("R02", "convention classifier", (e["class_blender"], e["class_ue_axes"], e["class_mixed"]) == ("blender", "ue_axes", "mixed"),
          "%s/%s/%s" % (e["class_blender"], e["class_ue_axes"], e["class_mixed"]))
    base = R.frame_from(J[names[0]], J[names[1]], i["up_hint"], "y")
    d = np.array(J[names[1]]) - np.array(J[names[0]])
    dt0 = R.damped_track(R.rot("z", 30.0) @ base, "y", d)
    dt1 = R.damped_track(R.rot("z", 30.0) @ base @ R.rot("y", 40.0), "y", d)
    diff = R.angle_deg(dt0, dt1)
    check("R02", "falsifier: track-then-apply keeps the incoming roll", abs(diff - f["damped_track_roll_difference_deg"]) < 1e-6 and diff > 1.0, f"{diff:.1f} deg")


def r03():
    c = case("R03_apply_scale")
    i, e, f = c["input"], c["expected"], c["falsifier"]
    Rr = np.array(i["R_rest"])
    new, Rn = R.apply_scale_loc_exact(Rr, i["scale"], i["loc"])
    check("R03", "exact apply keeps the world offset", close(new, e["new_loc"]) and close(Rn @ new, e["world_offset"]), np.round(Rn @ new, 6).tolist())
    comp = R.apply_scale_loc_componentwise(i["scale"], i["loc"])
    err = float(np.linalg.norm(Rn @ comp - np.array(e["world_offset"])))
    check("R03", "falsifier: per-channel object scale moves the bone (matches Blender)", abs(err - f["error_m"]) < 1e-7
          and abs(err - f["blender_5_2_measured"]["error_m"]) < 1e-6 and close(Rn @ comp, f["blender_5_2_measured"]["after"]), f"{err:.6f} m")
    check("R03", "uniform scale: both methods agree", e["uniform_error_m"] < 1e-12)


def r04():
    c = case("R04_retarget")
    i, e, f = c["input"], c["expected"], c["falsifier"]
    Rs = {k: np.array(v) for k, v in i["Rs_rest"].items()}
    Rt = {k: np.array(v) for k, v in i["Rt_rest"].items()}
    worst_key = worst_naive = 0.0
    for fr in e["frames"]:
        WsA, WsB = np.array(fr["Ws"]["A"]), np.array(fr["Ws"]["B"])
        WtA, WtB = R.retarget_world(WsA, Rs["A"], Rt["A"]), R.retarget_world(WsB, Rs["B"], Rt["B"])
        assert close(WtA, fr["Wt"]["A"]) and close(WtB, fr["Wt"]["B"])
        keyB = R.local_from_world(WtB, WtA, Rt["B"], Rt["A"])
        back = WtA @ (Rt["A"].T @ Rt["B"]) @ keyB
        worst_key = max(worst_key, R.angle_deg(back, WtB))
        worst_naive = max(worst_naive, R.angle_deg(R.retarget_local_copy(WsB, Rs["B"], Rt["B"]), WtB))
    check("R04", "W = Ws Rs^-1 Rt keeps the world change; parent-first keys reproduce it", e["max_along_error_deg"] < 1e-4 and worst_key < 0.01,   # arccos near 1 amplifies the 9-decimal storage
          f"along {e['max_along_error_deg']:.1e} deg, keys {worst_key:.1e} deg")
    check("R04", "falsifier: copying the local rotation across different rests", abs(worst_naive - f["local_copy_max_error_deg"]) < 1e-6 and worst_naive > 5,
          f"{worst_naive:.1f} deg")
    check("R04", "falsifier: copy-transforms in pose space changes bone length", f["copy_transforms_pose_space_length_drift_m"] > 0.01,
          f"{f['copy_transforms_pose_space_length_drift_m'] * 1000:.0f} mm")


def r05():
    c = case("R05_root_motion")
    e, f = c["expected"], c["falsifier"]
    worst = tilt = 0.0
    for fr in e["frames"]:
        P = np.array(fr["pelvis"])
        for mode in ("none", "heading"):
            root, local = R.root_from_pelvis(P, yaw=mode)
            worst = max(worst, float(np.abs(root @ local - P).max()))
            tilt = max(tilt, R.tilt_deg(root), abs(root[2, 3]))
            assert close(root, fr["modes"][mode]["root"])
    check("R05", "root on the ground, never tilted; root @ local == pelvis", worst < 1e-12 and tilt < 1e-9 and e["max_root_tilt_deg"] < 1e-9,
          f"recompose {worst:.1e}")
    ft = max(R.tilt_deg(R.root_copy_full_rotation(np.array(fr["pelvis"]))) for fr in e["frames"])
    check("R05", "falsifier: copying the pelvis rotation tilts the root", abs(ft - f["max_tilt_deg"]) < 1e-7 and ft > 1, f"{ft:.2f} deg")


def r06():
    c = case("R06_template_fit")
    i, e = c["input"], c["expected"]
    heads, ratios = R.fit_template(i["template"], i["parents"], i["example_joints"])
    res = max(float(np.linalg.norm(heads[k] - np.array(i["example_joints"][k]))) for k in heads)
    check("R06", "joints land on the example's measured joints", res < 1e-12 and all(abs(ratios[k] - e["length_ratios"][k]) < 1e-9 for k in ratios),
          "thigh %.3f arm %.3f" % (ratios["calf_l"], ratios["lowerarm_l"]))
    _h, rc = R.fit_template(i["template"], i["parents"], i["template"])
    check("R06", "falsifier: joints copied from the template body are flagged", R.copied_not_fitted(rc) and not R.copied_not_fitted(ratios))
    try:
        R.fit_template(i["template"], i["parents"], {k: v for k, v in i["example_joints"].items() if k != "head"})
        check("R06", "a missing example joint refuses", False)
    except ValueError:
        check("R06", "a missing example joint refuses", True)


def r07():
    c = case("R07_rest_change")
    e, f = c["expected"], c["falsifier"]
    import meshgen as M
    import reference as REF
    w = json.loads((HERE / "C02_inverse_lbs" / "weights.json").read_text())
    V, _F, *_ = M.read_obj(HERE / "C02_inverse_lbs" / "piece_fit_pose.obj")
    W = np.array(w["W"])
    mats = [np.eye(4), np.array(w["fit_pose"]["B"])]
    v0 = np.array([REF.lbs_inverse(p, ww, mats) for p, ww in zip(V, W)])
    exact = max(float(np.linalg.norm(REF.lbs(q, ww, mats) - p)) for q, p, ww in zip(v0, V, W))
    back = np.array([REF.blend_of_inverses(p, ww, mats) for p, ww in zip(V, W)])
    err = np.linalg.norm(back - v0, axis=1)
    check("R07", "the exact inverse returns a baked rest", exact < 1e-12 and e["exact_return_max_m"] == 0.0)
    check("R07", "falsifier: apply-pose-as-rest then return = blend of inverses", abs(err.max() - f["apply_pose_as_rest_then_return_max_m"]) < 1e-9
          and int((err > 0.001).sum()) == f["vertices_over_1mm"], f"{err.max() * 1000:.2f} mm over {int((err > 0.001).sum())} vertices")


def r08():
    c = case("R08_export_axes")
    e, f = c["expected"], c["falsifier"]
    for conv in ("blender", "ue_axes"):
        check("R08", f"the {conv} recipe carries its engine frames", tuple(e["recipe"][conv]) == R.recipe_for(conv)
              and np.allclose(R.fbx_node_map(*e["recipe"][conv]), c["input"]["engine_frames"][conv], atol=1e-12))
        for pair, a in e["angle_deg"][conv].items():
            check("R08", f"{pair} on {conv}", abs(R.frame_angle_deg(R.fbx_node_map(*pair.split("/")), R.ENGINE[conv]) - a) < 1e-9, f"{a:.1f} deg")
    check("R08", "Z/X: 120 deg off blender, 90 off ue_axes (lane orphans' measured read-back)",
          e["angle_deg"]["blender"]["Z/X"] == 120.0 and e["angle_deg"]["ue_axes"]["Z/X"] == 90.0)
    check("R08", "falsifier: the transposed map puts the right pair 180 deg off", abs(f["inverse_map_angle_deg_blender_X/-Y"] - 180.0) < 1e-9)


if __name__ == "__main__":
    for fn in (r01, r02, r03, r04, r05, r06, r07, r08):
        try:
            fn()
        except Exception as ex:  # a crash is a failure, named
            check(fn.__name__.upper(), "crashed", False, repr(ex))
    print(f"rows[{len(ROWS)}]{{case,check,ok,detail}}:")
    for r in ROWS:
        print("  %s,%s,%s,%s" % (r[0], r[1], "ok" if r[2] else "FAIL", r[3]))
    bad = sum(1 for r in ROWS if not r[2])
    print(f"summary: {len(ROWS) - bad} ok, {bad} failed")
    sys.exit(1 if bad else 0)
