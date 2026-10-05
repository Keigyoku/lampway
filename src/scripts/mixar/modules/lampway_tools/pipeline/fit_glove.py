# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_glove: the typed plate-label decision of a glove, and the honest stubs.

Every automatic hand sizing and finger identification failed on the user's gauntlets, so the plate labels are a TYPED DECISION: the algorithm may propose, the user (or an agent's proposal, recorded as such)
labels each plate with a hand or arm bone. ``labels`` validates (every plate labelled - never guessed -, the right hand's bones, finger caps and the bracer metal on ONE bone each, a cloth plate never rigid),
writes ``glove_labels.json`` and one decision row per plate to ``<piece>/fit/decisions.jsonl``, and returns the bind plan fragment that fit_bind takes as overrides.
pose, bind and report need the hand-pose engine of the user's project (not available here) and answer needs_decision; fit_state is the user's to rule (the Laya route against the measured validators)."""

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


def not_built(stage):
    return {"ok": False, "stage": stage, "needs_decision": {
        "what": f"fit_glove {stage}",
        "questions": ["hand keypoints: the body's joints (exact, the default) or a hand model run on renders for the piece's own implied hand?",
                      "left glove: mirrored labels from the right (a mirror relabel) or an independent pass?"],
        "why": f"the {stage} stage needs the hand-pose engine (pose_transforms, similarity, lbs, segment_weights) of the user's project, which is not available here; the label decision (stage labels) is built",
        "proposal": "labels now; pose and bind when the hand-pose engine is wired in"}}


def fit_state(stage):
    return {"ok": False, "stage": stage, "needs_decision": {
        "what": "fit_state: the descriptor / question / answer loop",
        "question": "is the Laya / fit-model route still the direction after the three-input fit law and the native-body validation route, or do the measured validators (fit_validate) make it unnecessary?",
        "why": "fit_state builds on the project's fit_measure Blender recipe, which was being edited and could not be read as committed; the user's word decides whether it is built at all",
        "proposal": "do not build it until fit_validate has been run on real pieces; revisit with its numbers",
        "also": "whether a descriptor's `hideable` idea (hide the body under solid armour instead of fixing poke-through) becomes a first-class export flag"}}
