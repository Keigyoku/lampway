# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generator for the rig goldens R01-R08 (canon 16-21). numpy only; deterministic (two runs are byte-identical).

    python3 gen_rig_goldens.py [out_dir]

Each case is one directory holding case.json: {"input": ..., "expected": ..., "falsifier": ...}. The skeletons are SYNTHETIC
(made-up proportions in the body frame); the naming tables carry public naming conventions only (bone NAMES, no geometry).
No vendor skeleton geometry (Epic's, MetaHuman's, the captain's) is written here."""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rig_reference as R  # noqa: E402


def r9(x):
    if isinstance(x, dict):
        return {k: r9(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [r9(v) for v in x]
    if isinstance(x, np.ndarray):
        return r9(x.tolist())
    if isinstance(x, (float, np.floating)):
        v = round(float(x), 9)
        return 0.0 if v == 0 else v
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def write(out, name, doc):
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "case.json").write_text(json.dumps(r9(doc), indent=1, sort_keys=True) + "\n")


# ----------------------------------------------------------------------------- R01 mapping + synthesis
TABLES = {
    # naming conventions only (public); the UE slot names are the UE5 mannequin's bone names
    "mixamo": {"pelvis": "mixamorig:Hips", "spine_01": "mixamorig:Spine", "spine_02": "mixamorig:Spine1", "spine_05": "mixamorig:Spine2",
               "neck_01": "mixamorig:Neck", "head": "mixamorig:Head", "clavicle_l": "mixamorig:LeftShoulder", "upperarm_l": "mixamorig:LeftArm",
               "lowerarm_l": "mixamorig:LeftForeArm", "hand_l": "mixamorig:LeftHand", "index_01_l": "mixamorig:LeftHandIndex1",
               "thigh_l": "mixamorig:LeftUpLeg", "calf_l": "mixamorig:LeftLeg", "foot_l": "mixamorig:LeftFoot"},
    "rigify": {"pelvis": "DEF-spine", "spine_01": "DEF-spine.001", "spine_02": "DEF-spine.002", "spine_05": "DEF-spine.003",
               "neck_01": "DEF-spine.004", "neck_02": "DEF-spine.005", "head": "DEF-spine.006", "clavicle_l": "DEF-shoulder.L",
               "upperarm_l": "DEF-upper_arm.L", "lowerarm_l": "DEF-forearm.L", "hand_l": "DEF-hand.L", "index_01_l": "DEF-f_index.01.L",
               "thigh_l": "DEF-thigh.L", "calf_l": "DEF-shin.L", "foot_l": "DEF-foot.L"},
}
REQUIRED = ["pelvis", "spine_01", "head", "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l", "thigh_l", "calf_l", "foot_l"]
MIXAMO_NAMES = ["mixamorig:Hips", "mixamorig:Spine", "mixamorig:Spine1", "mixamorig:Spine2", "mixamorig:Neck", "mixamorig:Head",
                "mixamorig:HeadTop_End", "mixamorig:LeftShoulder", "mixamorig:LeftArm", "mixamorig:LeftForeArm",
                "mixamorig:LeftHandIndex1", "mixamorig:LeftHandIndex2", "mixamorig:LeftHand", "mixamorig:LeftHandThumb1",
                "mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:LeftFoot", "mixamorig:LeftToeBase"]
SUBSTRING_WORDS = {"hand_l": ["left", "hand"], "upperarm_l": ["left", "arm"]}
# a synthetic reference torso chain (made-up heights), the fractions every synthesis uses
REF_TORSO = [("pelvis", (0, 0, 0.96)), ("spine_01", (0, 0.005, 1.00)), ("spine_02", (0, 0.01, 1.07)), ("spine_03", (0, 0.012, 1.14)),
             ("spine_04", (0, 0.010, 1.22)), ("spine_05", (0, 0.004, 1.32))]
# a rigify-like source torso: pelvis, spine_01, spine_02 and spine_05 present; spine_03 and spine_04 missing
SRC_TORSO = [("pelvis", (0, -0.02, 0.93)), ("spine_01", (0, -0.015, 0.99)), ("spine_02", (0, -0.005, 1.06)), ("spine_05", (0, 0.0, 1.35))]


def ref_fractions(chain):
    pts = np.array([p for _n, p in chain], float)
    cum = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    return {n: c / cum[-1] for (n, _p), c in zip(chain, cum)}


def r01():
    fam, hits = R.detect_family(MIXAMO_NAMES, TABLES)
    m, missing = R.map_slots(MIXAMO_NAMES, TABLES[fam], REQUIRED)
    bad = R.substring_map(MIXAMO_NAMES, SUBSTRING_WORDS)
    fr = ref_fractions(REF_TORSO)
    syn = R.synthesize_chain(SRC_TORSO, fr)
    mid3 = R.midpoint_synthesis(dict(SRC_TORSO)["spine_02"], dict(SRC_TORSO)["spine_05"])
    mixed = MIXAMO_NAMES[:6] + ["DEF-spine", "DEF-spine.001", "DEF-spine.002", "DEF-spine.003", "DEF-spine.004", "DEF-spine.006"]
    try:
        R.detect_family(mixed, TABLES)
        tie = "accepted"
    except ValueError:
        tie = "refused"
    return {"input": {"tables": TABLES, "required": REQUIRED, "names": MIXAMO_NAMES, "substring_words": SUBSTRING_WORDS,
                      "ref_torso": REF_TORSO, "src_torso": SRC_TORSO, "tie_names": mixed},
            "expected": {"family": fam, "hits": hits, "map": m, "missing_required": missing,
                         "synthesized": {k: syn[k] for k in ("spine_03", "spine_04")}, "fractions": fr, "tie": tie},
            "falsifier": {"substring_map": bad, "substring_wrong_slots": sorted(k for k in bad if bad[k] != m.get(k)),
                          "midpoint_spine_03": mid3, "midpoint_error_m": float(np.linalg.norm(mid3 - syn["spine_03"]))}}


# ----------------------------------------------------------------------------- R02 rest frames
ARM = {"upperarm_l": (0.20, 0.0, 1.40), "lowerarm_l": (0.45, -0.02, 1.20), "hand_l": (0.68, -0.05, 1.02), "middle_01_l": (0.76, -0.06, 0.96)}
UP = (0.0, 0.0, 1.0)


def r02():
    names = list(ARM)
    frames_y, frames_x, ang_y, ang_x = {}, {}, {}, {}
    for a, b in zip(names[:-1], names[1:]):
        Fy = R.frame_from(ARM[a], ARM[b], UP, along="y")
        Fx = R.frame_from(ARM[a], ARM[b], UP, along="x")
        frames_y[a], frames_x[a] = Fy, Fx
        ang_y[a] = R.along_axis_angle(Fy, ARM[a], ARM[b], "y")
        ang_x[a] = R.along_axis_angle(Fx, ARM[a], ARM[b], "y")
    mixed = [ang_y["upperarm_l"], ang_x["lowerarm_l"], ang_y["hand_l"]]
    helper_frame = R.rot("y", 120.0)
    helper = {"name": "upperarm_correctiveRoot_l", "parent": "upperarm_l",
              "children": ["upperarm_corrective_front_l", "upperarm_corrective_back_l"],
              "authored_frame": helper_frame, "frame": R.corrective_root_frame(helper_frame),
              "along_source": "authored_helper_frame"}
    # falsifier: the same joints, two input rolls, Damped Track on Y: the output keeps the input roll
    a, b = names[0], names[1]
    base = R.frame_from(ARM[a], ARM[b], UP, along="y")
    rolled = base @ R.rot("y", 40.0)
    start = R.rot("z", 30.0) @ base
    start_rolled = R.rot("z", 30.0) @ rolled
    dt0 = R.damped_track(start, "y", np.array(ARM[b]) - np.array(ARM[a]))
    dt1 = R.damped_track(start_rolled, "y", np.array(ARM[b]) - np.array(ARM[a]))
    return {"input": {"joints": ARM, "chain": names, "up_hint": UP},
            "expected": {"corrective_root": helper, "frames_blender": frames_y, "frames_ue_axes": frames_x, "angle_blender_deg": ang_y, "angle_ue_axes_deg": ang_x,
                         "class_blender": R.classify_convention(list(ang_y.values())), "class_ue_axes": R.classify_convention(list(ang_x.values())),
                         "class_mixed": R.classify_convention(mixed)},
            "falsifier": {"damped_track_roll_difference_deg": R.angle_deg(dt0, dt1), "frame_from_roll_difference_deg": 0.0,
                          "corrective_parent_frame_error_deg": R.angle_deg(helper_frame, np.eye(3))}}


# ----------------------------------------------------------------------------- R03 apply object scale
R_REST = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])   # local X -> world -Y, local Y -> world X (a bone along +X, roll 0)


def r03():
    S, loc = (2.0, 1.0, 3.0), (0.1, 0.2, 0.3)
    world = np.diag(S) @ R_REST @ np.array(loc)
    exact, Rn = R.apply_scale_loc_exact(R_REST, S, loc)
    comp = R.apply_scale_loc_componentwise(S, loc)
    world_comp = Rn @ comp
    U = (2.0, 2.0, 2.0)
    exact_u, Rn_u = R.apply_scale_loc_exact(R_REST, U, loc)
    comp_u = R.apply_scale_loc_componentwise(U, loc)
    return {"input": {"R_rest": R_REST, "scale": S, "loc": loc, "uniform_scale": U},
            "expected": {"world_offset": world, "new_loc": exact, "new_rest": Rn, "world_after": Rn @ exact,
                         "uniform_new_loc": exact_u, "uniform_error_m": float(np.linalg.norm(Rn_u @ comp_u - np.diag(U) @ R_REST @ np.array(loc)))},
            "falsifier": {"componentwise_loc": comp, "componentwise_world": world_comp, "error_m": float(np.linalg.norm(world_comp - world)),
                          "blender_5_2_measured": {"before": [0.4, -0.1, 0.9], "after": [0.2, -0.2, 0.9], "error_m": 0.223607,
                                                   "source": "GRT 4.3.0 gamerigtool.apply_scale_op, headless Blender 5.2.1, 2026-10-05"}}}


# ----------------------------------------------------------------------------- R04 retarget
def direction_angle_deg(a, b):
    """Angle without arccos's amplification of backend roundoff near dot=1.

    atan2 retains actual small misalignment instead of converting a one-ULP dot
    error into a microradian angle. Cross and dot scale equally for nonunit axes.
    """
    return float(np.degrees(np.arctan2(np.linalg.norm(np.cross(a, b)), a @ b)))


def r04():
    Rs = {"A": R.rot("x", 90.0), "B": R.rot("x", 90.0) @ R.rot("y", 10.0)}
    Rt = {"A": Rs["A"] @ R.rot("y", 90.0), "B": Rs["B"] @ R.rot("y", -30.0)}        # same along axes, different rolls
    frames = []
    for t in range(5):
        LA = R.rot("x", 15.0 * t) @ R.rot("z", 5.0 * t)
        LB = R.rot("x", 20.0 * t)
        WsA = Rs["A"] @ LA
        WsB = WsA @ (Rs["A"].T @ Rs["B"]) @ LB
        WtA, WtB = R.retarget_world(WsA, Rs["A"], Rt["A"]), R.retarget_world(WsB, Rs["B"], Rt["B"])
        keyA = Rt["A"].T @ WtA
        keyB = R.local_from_world(WtB, WtA, Rt["B"], Rt["A"])
        naive = R.retarget_local_copy(WsB, Rs["B"], Rt["B"])
        frames.append({"Ws": {"A": WsA, "B": WsB}, "Wt": {"A": WtA, "B": WtB}, "key": {"A": keyA, "B": keyB},
                       "along_error_deg": max(direction_angle_deg(W[:, 1], Ws[:, 1])
                                              for W, Ws in ((WtA, WsA), (WtB, WsB))),
                       "naive_error_deg": R.angle_deg(naive, WtB)})
    Ls, Lt = 0.27, 0.30
    return {"input": {"Rs_rest": Rs, "Rt_rest": Rt, "source_local": "A: rot_x(15t) rot_z(5t); B: rot_x(20t); t = 0..4", "lengths": {"source_A": Ls, "target_A": Lt}},
            "expected": {"frames": frames, "max_along_error_deg": max(f["along_error_deg"] for f in frames)},
            "falsifier": {"local_copy_max_error_deg": max(f["naive_error_deg"] for f in frames),
                          "copy_transforms_pose_space_length_drift_m": abs(Lt - Ls)}}


# ----------------------------------------------------------------------------- R05 root motion
def pelvis(t):
    P = np.eye(4)
    P[:3, :3] = R.rot("z", 10.0 * t) @ R.rot("x", 6.0 * np.sin(t)) @ R.rot("y", 4.0 * np.cos(t))
    P[:3, 3] = (0.05 * t, 0.02 * np.sin(t), 0.95 + 0.02 * np.sin(2 * t))
    return P


def r05():
    rows = []
    for t in range(9):
        P = pelvis(t)
        out = {}
        for mode in ("none", "heading"):
            root, local = R.root_from_pelvis(P, yaw=mode)
            out[mode] = {"root": root, "pelvis_local": local, "recompose_error": float(np.abs(root @ local - P).max()),
                         "root_z": float(root[2, 3]), "root_tilt_deg": R.tilt_deg(root)}
        full = R.root_copy_full_rotation(P)
        rows.append({"t": t, "pelvis": P, "modes": out, "falsifier_tilt_deg": R.tilt_deg(full)})
    return {"input": {"pelvis": "rot_z(10t) rot_x(6 sin t) rot_y(4 cos t); translation (0.05t, 0.02 sin t, 0.95 + 0.02 sin 2t); t = 0..8"},
            "expected": {"frames": rows, "max_recompose_error": max(r["modes"][m]["recompose_error"] for r in rows for m in ("none", "heading")),
                         "max_root_tilt_deg": max(r["modes"][m]["root_tilt_deg"] for r in rows for m in ("none", "heading"))},
            "falsifier": {"max_tilt_deg": max(r["falsifier_tilt_deg"] for r in rows)}}


# ----------------------------------------------------------------------------- R06 template fit
TEMPLATE = {"pelvis": (0, 0, 0.95), "spine_01": (0, 0.0, 1.02), "spine_05": (0, 0.0, 1.30), "neck_01": (0, 0.0, 1.45), "head": (0, 0.0, 1.55),
            "thigh_l": (0.09, 0, 0.92), "calf_l": (0.10, 0.0, 0.50), "foot_l": (0.11, 0.02, 0.08),
            "upperarm_l": (0.18, 0.0, 1.40), "lowerarm_l": (0.43, 0.0, 1.38), "hand_l": (0.68, 0.0, 1.36)}
PARENTS = {"pelvis": None, "spine_01": "pelvis", "spine_05": "spine_01", "neck_01": "spine_05", "head": "neck_01", "thigh_l": "pelvis",
           "calf_l": "thigh_l", "foot_l": "calf_l", "upperarm_l": "spine_05", "lowerarm_l": "upperarm_l", "hand_l": "lowerarm_l"}


def example_joints():
    T = {k: np.array(v, float) for k, v in TEMPLATE.items()}
    E = {}
    shift = np.array([0.0, 0.01, 0.03])
    for k in ("pelvis", "spine_01", "spine_05", "neck_01", "head"):
        E[k] = T[k] + shift
    hip = T["thigh_l"] + shift
    for k in ("thigh_l", "calf_l", "foot_l"):
        E[k] = hip + 1.08 * (T[k] - T["thigh_l"])
    sh = T["upperarm_l"] + shift
    for k in ("upperarm_l", "lowerarm_l", "hand_l"):
        E[k] = sh + 0.95 * (T[k] - T["upperarm_l"])
    return E


def r06():
    E = example_joints()
    heads, ratios = R.fit_template(TEMPLATE, PARENTS, E)
    _h2, ratios_copied = R.fit_template(TEMPLATE, PARENTS, TEMPLATE)
    return {"input": {"template": TEMPLATE, "parents": PARENTS, "example_joints": E},
            "expected": {"heads": heads, "residual_m": max(float(np.linalg.norm(heads[k] - E[k])) for k in E), "length_ratios": ratios,
                         "copied_flag_fitted": R.copied_not_fitted(ratios), "copied_flag_copied": R.copied_not_fitted(ratios_copied)},
            "falsifier": {"joints_from_template_body": "target joints taken from the template's own skeleton: every ratio 1.000, flagged"}}


# ----------------------------------------------------------------------------- R07 rest change (uses C02)
def r07():
    import meshgen as M
    w = json.loads((HERE / "C02_inverse_lbs" / "weights.json").read_text())
    V, _F, *_ = M.read_obj(HERE / "C02_inverse_lbs" / "piece_fit_pose.obj")
    W = np.array(w["W"])
    mats = [np.eye(4), np.array(w["fit_pose"]["B"])]
    import reference as REF
    v0 = np.array([REF.lbs_inverse(p, ww, mats) for p, ww in zip(V, W)])
    back = np.array([REF.blend_of_inverses(p, ww, mats) for p, ww in zip(V, W)])
    err = np.linalg.norm(back - v0, axis=1)
    return {"input": {"from": "C02_inverse_lbs (weights.json, piece_fit_pose.obj): the posed mesh baked as a new rest, bind = the pose"},
            "expected": {"exact_return_max_m": 0.0, "rigid_vertices_error_m": float(err[W.max(1) > 1 - 1e-12].max())},
            "falsifier": {"apply_pose_as_rest_then_return_max_m": float(err.max()), "vertices_over_1mm": int((err > 0.001).sum()),
                          "why": "a baked rest returned through the new bind is the blend of inverses (canon 04)"}}


# ----------------------------------------------------------------------------- R08 FBX bone axes (canon 21 / 17)
def r08():
    pairs = [("Z", "X"), ("X", "-Y"), ("Y", "X")]
    ang = {c: {f"{p}/{s}": R.frame_angle_deg(R.fbx_node_map(p, s), R.ENGINE[c]) for p, s in pairs} for c in ("blender", "ue_axes")}
    return {"input": {"pairs": [f"{p}/{s}" for p, s in pairs], "engine_frames": {c: R.ENGINE[c] for c in R.ENGINE},
                      "rule": "an exporter pair writes node frames R_bone @ M(primary, secondary) (the node's primary axis = the bone's +Y, its "
                              "secondary = the bone's +X); it carries a convention when M equals the convention's engine frame"},
            "expected": {"recipe": {c: list(R.recipe_for(c)) for c in ("blender", "ue_axes")}, "angle_deg": ang,
                         "titan_cm_native": "Z/X carries neither canon-17 convention: it is the pair a rig imported FROM an engine with "
                                            "primary Z / secondary X needs to go back (a round trip), which is how Titan measured it"},
            "falsifier": {"inverse_map_angle_deg_blender_X/-Y": R.frame_angle_deg(R.fbx_node_map("X", "-Y").T, R.ENGINE["blender"]),
                          "why": "reading the pair as the bone's axis in the node frame (M transposed) would make the right pair 180 deg off"}}


def main(out):
    out = Path(out)
    for name, fn in (("R01_mapping", r01), ("R02_rest_frames", r02), ("R03_apply_scale", r03), ("R04_retarget", r04),
                     ("R05_root_motion", r05), ("R06_template_fit", r06), ("R07_rest_change", r07),
                     ("R08_export_axes", r08)):
        write(out, name, fn())
        print("wrote", name)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else HERE)
