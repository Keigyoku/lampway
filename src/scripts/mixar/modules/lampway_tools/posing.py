# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_pose: the closest pose for a piece. Only the CHEST is built (pose_clearance); every other kind answers ``needs_decision`` because the degrees of freedom and their ranges are the user's to
rule (the shelf has the chest's alone). The proposals are the contract's, marked unverified."""

KINDS = ("chest", "helmet", "waist", "boots", "gauntlets")

PROPOSALS = {
    "helmet": "neck_01, neck_02 and head: pitch and roll -8..8 step 4",
    "waist": "spine_01 and pelvis pitch -8..8; thigh flexion/abduction as the piece's lower edge needs",
    "boots": "calf and foot: ankle pitch and roll, knee flexion a small range; the shaft rides the calf",
    "gauntlets": "forearm twist, wrist flexion; finger curl fractions 80/95/60 degrees for fingers 01/02/03 (armour-poses recipe)",
}


def fit_pose(kind, **_):
    if kind not in KINDS:
        raise ValueError("kind is " + " | ".join(KINDS))
    if kind == "chest":
        return {"ok": True, "route": "pose_clearance",
                "how": "run_tool('pose_clearance', [...]): both upper arms lowered/swung, then the spine_01, spine_03, neck_01 pitch chain, as the shelf's chest pose sweep"}
    return {"ok": False, "needs_decision": {
        "what": f"fit_pose degrees of freedom for {kind}",
        "question": f"which bones, axes and ranges may the body move through to find the closest pose for a {kind}, and which poses count as natural?",
        "why": "pose the body to the piece before clearance, fit or weights: a sweep rewards whatever the ranges allow, so the ranges are a ruling, not a default",
        "proposal": PROPOSALS[kind], "proposal_status": "[UNVERIFIED] a proposal from the contract; nothing has been run on a real piece",
        "needs_from_user": "the DOF list (bone, axis, range, step) or 'accept the proposal'"}}
