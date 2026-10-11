# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_glove: the typed plate-label decision of a glove, and the honest stubs.

Every automatic hand sizing and finger identification failed on the user's gauntlets, so the plate labels are a TYPED DECISION: the algorithm may propose, the user (or an agent's proposal, recorded as such)
labels each plate with a hand or arm bone. ``labels`` validates (every plate labelled - never guessed -, the right hand's bones, finger caps and the bracer metal on ONE bone each, a cloth plate never rigid),
writes ``glove_labels.json`` and one decision row per plate to ``<piece>/fit/decisions.jsonl``, and returns the bind plan fragment that fit_bind takes as overrides.
Pose and bind call the shared canon engines with the body's own joints and each glove's recorded independent labels. Automatic mirror relabelling remains a separate explicit decision; it never blocks an independently labelled glove. Omitted pose DOFs execute the physically untested gauntlet default table for the independently recorded side."""

import json
import re
import time
from pathlib import Path

FINGERS = ("index", "middle", "ring", "pinky", "thumb")
ARM = ("hand", "lowerarm", "upperarm", "clavicle")


class GloveError(ValueError):
    pass


def _hand_bones(side):
    out = [f"{f}_{n:02d}_{side}" for f in FINGERS for n in (1, 2, 3)]
    return set(out + [f"{b}_{side}" for b in ARM])


def labels(root, piece, side, plates, labels, roles, overrides=None, by="agent"):
    if side not in ("l", "r"):
        raise GloveError("side is l or r")
    allowed, other = _hand_bones(side), _hand_bones("l" if side == "r" else "r")
    missing = sorted(set(plates) - set(labels))
    if missing:
        raise GloveError(f"labels cover fewer than every plate (never guess: ask): the unlabelled plates are {missing}")
    rows, fragment = {}, {}
    for plate in plates:
        role = roles.get(plate)
        if role not in ("metal", "leather", "cloth", "embroidery"):
            raise GloveError(f"plate {plate} has no material role: the user or the recipe says metal | leather | cloth | embroidery, never the render's colour")
        lab = labels[plate]
        if isinstance(lab, (list, tuple)):
            if role == "metal":
                raise GloveError(f"{plate}: finger caps and the bracer are metal: one bone each")
            lab = lab[0]
        if lab in other:
            side_name = "left" if side == "r" else "right"
            mine = "right" if side == "r" else "left"
            raise GloveError(f"{lab} is a {side_name}-hand bone but this is the {mine} glove")
        if lab not in allowed:
            raise GloveError(f"{lab} is not a hand or arm bone of the {side} side; the finger bones are <finger>_01..03_{side} and the arm bones hand|lowerarm|upperarm|clavicle_{side}")
        mode = (overrides or {}).get(plate, {}).get("mode") or ("rigid" if role == "metal" else "restrict")
        if role == "cloth" and mode == "rigid":
            raise GloveError(f"{plate}: the upper arm is cloth (above the bracer): a cloth plate is never bound rigid")
        if role == "metal" and mode != "rigid":
            raise GloveError(f"{plate}: finger caps and the bracer are metal: one bone each, rigid")
        rows[plate] = {"bone": lab, "role": role, "mode": mode, "decider": by}
        fragment[plate] = {"mode": mode, "bones": [lab]}
    d = Path(root) / piece / "fit"
    d.mkdir(parents=True, exist_ok=True)
    (d / "glove_labels.json").write_text(json.dumps({"piece": piece, "side": side, "labels": rows}, indent=1))
    with open(d / "decisions.jsonl", "a") as fh:
        for plate, r in rows.items():
            fh.write(json.dumps({"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "question": "glove_plate_label", "what": plate, "answer": r["bone"], "decider": by}) + "\n")
    return {"ok": True, "labels": rows, "bind_fragment": fragment, "files": ["glove_labels.json", "decisions.jsonl"],
            "note": "merge bind_fragment into fit_bind's bind_overrides; finger caps and the bracer are one rigid bone each"}


def _record(root, piece, side):
    path = Path(root) / piece / "fit" / "glove_labels.json"
    if not path.is_file():
        raise GloveError("run fit_glove stage labels for this glove before pose or bind")
    rec = json.loads(path.read_text())
    if rec["side"] != side:
        raise GloveError(f"the recorded labels belong to side {rec['side']}, not {side}; label this glove independently")
    return rec


def pose(root, piece, side, armature, body_object, dofs, chain, regions, out_dir, apply=False, curl_fractions=None):
    _record(root, piece, side)
    from .. import posing
    defaults = None
    if not dofs:
        defaults = posing.fit_pose("gauntlets", side=side)["table"]
        dofs, chain, regions = defaults["dofs"], defaults["chain"], defaults["regions"]
        if curl_fractions is None:
            curl_fractions = defaults["curl_fractions"]
    result = posing.solve_scene("gauntlets", piece, body_object, armature, dofs, chain, regions, root=root,
                                curl_side=side if curl_fractions is not None else "", curl_fractions=curl_fractions)
    if defaults is not None:
        result["defaults"] = defaults
    result["keypoints"] = {"source": "body_joints", "side": side, "labels": "independent"}
    if apply:
        import bpy
        from ..features import validate_pose
        arm = bpy.data.objects[armature]
        joints = validate_pose._joints(arm)
        validate_pose._pose(arm, result["entries"], joints, validate_pose._frame(joints))
        result["applied"] = result["entries"]
    path = Path(root) / out_dir / "glove_pose.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, sort_keys=True))
    return result


def bind(root, piece, side, armature, body_object, body, out_dir, apply=False, accept_seam_gap_mm=None):
    rec = _record(root, piece, side)
    from ..features import fit_bind
    roles = {p: row["role"] for p, row in rec["labels"].items()}
    overrides = {p: {"mode": row["mode"], "bones": [row["bone"]], "reason": "recorded glove plate label"}
                 for p, row in rec["labels"].items()}
    plan = fit_bind.plan(piece, armature, roles, overrides, out_dir, root)
    weighted = fit_bind.weights(piece, armature, out_dir, body_object, root, body=body)
    returned = fit_bind.return_report(piece, armature, out_dir, root)
    result = {"ok": True, "object": weighted["object"], "rest_object": returned["object"],
              "plan": plan, "weights": weighted, "return": returned,
              "keypoints": {"source": "body_joints", "side": side, "labels": "independent"}}
    if apply:
        result["apply"] = fit_bind.apply(piece, armature, out_dir, accept_seam_gap_mm, root)
    return result


def report(root, piece, side, out_dir):
    rec = _record(root, piece, side)
    from ..features import fit_bind
    path = Path(root) / out_dir / "glove_pose.json"
    return {"ok": True, "labels": rec, "pose": json.loads(path.read_text()) if path.is_file() else None,
            "bind": fit_bind.report(out_dir, root)}


def fit_state(stage):
    return {"ok": False, "stage": stage, "needs_decision": {
        "what": "fit_state: the descriptor / question / answer loop",
        "question": "is the Laya / fit-model route still the direction after the three-input fit law and the native-body validation route, or do the measured validators (fit_validate) make it unnecessary?",
        "why": "fit_state builds on the project's fit_measure Blender recipe, which was being edited and could not be read as committed; the user's word decides whether it is built at all",
        "proposal": "do not build it until fit_validate has been run on real pieces; revisit with its numbers",
        "also": "whether a descriptor's `hideable` idea (hide the body under solid armour instead of fixing poke-through) becomes a first-class export flag"}}
