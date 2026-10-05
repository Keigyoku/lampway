# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""armor_piece_pipeline: one armour piece from V3 plates to an engine-ready export as an ordered list of gated steps, each one existing tool or Studio action.

A SEQUENCER and a RECORD, not a doer: it holds the step table in the user's order, checks the order laws (texturing last; Studio actions on a saved copy; pose before rig; a geometry
step after the texture makes the texture stale), keeps an append-only run record with artefact hashes, and returns, for every step, its tool, its arguments and its state. A step that
spends is always ``needs_approval``: this module never confirms one and never arms the Studio (only the user's click in the Client does). The steps are the runbook's (15) mapped to the
tools Lampway has; the sub-tools keep their own jails and work on copies."""

import hashlib
import json
import time
from pathlib import Path

PIECES = ("Helmet1", "Chest1", "Waist1", "Gauntlets1", "Boots1")
PAIRED = ("Gauntlets1", "Boots1")                  # [UNVERIFIED] actions.py says gauntlets and boots; the user confirms

#: n, name, tool, credits, geometry step?, kind (free | spend | decision)
STEPS = (
    (1, "plates", "tripo.image", 0, False, "spend"),                       # the free quota; the price is read back and still confirmed
    (2, "seed meshes", "tripo.mesh", 100, False, "spend"),
    (3, "fetch and catalog the seeds", "tripo.fetch + seed_catalog", 0, False, "free"),
    (4, "seed audit (proportions first)", "seed_audit", 0, False, "decision"),
    (5, "proportion score", "piece_ratios", 0, False, "free"),
    (6, "provisional fit and closest pose", "fit_place + pose_clearance", 0, False, "free"),
    (7, "region fixes and matched-view audit", "mesh_defect_scan + silhouette_compare + qa_*", 0, True, "decision"),
    (8, "clone, then Smart UV", "tripo.uv.unwrap", 20, True, "spend"),
    (9, "UV score and mesh QA patches", "uv_score + patch_holes", 0, True, "decision"),
    (10, "parts", "parts_critique + apply_part_fixes", 0, False, "decision"),
    (11, "openings (a geometry step)", "fit_openings", 0, True, "decision"),
    (12, "mesh-paint", "meshpaint", 0, False, "free"),
    (13, "studio texture", "tripo.texture", 30, False, "spend"),
    (14, "PBR, then palette_fit and pbr_pack", "tripo.pbr", 5, False, "spend"),
    (15, "export", "export_piece + asset_acceptance", 0, False, "free"),
)
SMART_UV, TEXTURE = 8, 13
POSE_STEPS = (6,)
RIG_TOOLS = ("rig_armor", "bind_to_armature")


class PipelineError(ValueError):
    pass


def _dir(root, piece):
    return Path(root) / piece / "pipeline"


def run_record(root, piece):
    p = _dir(root, piece) / "run.json"
    if not p.exists():
        return {"piece": piece, "events": [], "texture": "none", "mesh_hash": None}
    return json.loads(p.read_text())


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def record(root, piece, step, artefacts=(), mesh_hash=None, note=""):
    """Append one event. The texture is stale when a later event carries a different mesh hash than the texture step did."""
    _piece(piece)
    rec = run_record(root, piece)
    arts = [{"path": str(a), "sha256": _sha(a) if Path(a).is_file() else None} for a in artefacts]
    rec["events"].append({"step": int(step), "when": time.strftime("%Y-%m-%dT%H:%M:%S"), "artefacts": arts, "mesh_hash": mesh_hash, "note": note})
    tex = [e for e in rec["events"] if e["step"] == TEXTURE]
    if tex:
        later = [e for e in rec["events"][rec["events"].index(tex[-1]) + 1:] if e["mesh_hash"] and e["mesh_hash"] != tex[-1]["mesh_hash"]]
        rec["texture"] = "stale" if later else "fresh"
    rec["mesh_hash"] = mesh_hash or rec.get("mesh_hash")
    d = _dir(root, piece)
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.json").write_text(json.dumps(rec, indent=1))
    return rec


def _piece(piece):
    if piece not in PIECES:
        raise PipelineError(f"unknown piece {piece!r}; the pieces are: {', '.join(PIECES)}")


def _args(piece, n, paired, topology, v3_dir):
    views = ["Front", "Back"] if paired else ["Front", "Left", "Right", "Back"]
    if n == 1:
        return {"piece": piece, "v3_dir": v3_dir, "views": views}
    if n == 2:
        return {"views": views, "paired": paired, "topology": topology, "polycount": "max", "variants": 4}
    if n == SMART_UV:
        return {"on": "the saved COPY (tripo.uv.clone first)"}
    return {}


def plan(root, piece, from_step=1, to_step=15, paired=None, topology="Quad", v3_dir=""):
    _piece(piece)
    from_step, to_step = int(from_step), int(to_step)
    if not 1 <= from_step <= 15 or not 1 <= to_step <= 15:
        raise PipelineError("steps are 1..15")
    if to_step < from_step:
        raise PipelineError(f"to_step {to_step} is below from_step {from_step}")
    paired = (piece in PAIRED) if paired is None else bool(paired)
    rec = run_record(root, piece)
    done = {e["step"] for e in rec["events"]}
    steps = []
    for n, name, tool, credits, geometry, kind in STEPS:
        if not from_step <= n <= to_step:
            continue
        if n in done and not (n == TEXTURE and rec["texture"] == "stale"):
            state = "done" if kind != "spend" or n in done else "needs_approval"
        elif kind == "spend":
            state = "needs_approval"
        elif kind == "decision":
            state = "waiting"
        else:
            state = "ready"
        steps.append({"n": n, "name": name, "tool": tool, "state": state, "credits_planned": credits if tool.startswith("tripo.") and credits else 0, "geometry": geometry,
                      "args": _args(piece, n, paired, topology, v3_dir), "artefacts": [a["path"] for e in rec["events"] if e["step"] == n for a in e["artefacts"]]})
    total = sum(s["credits_planned"] for s in steps)
    nxt = next((s for s in steps if s["state"] != "done"), None)
    return {"ok": True, "piece": piece, "steps": steps, "total_credits_planned": total, "texture": rec["texture"],
            "next": nxt and {"n": nxt["n"], "tool": nxt["tool"], "state": nxt["state"]},
            "note": "spends are needs_approval rows: the user's click in the Client confirms them; this tool never does"}


def start(root, piece, from_step=1, to_step=15, **kw):
    _piece(piece)
    if int(from_step) > 1 and not run_record(root, piece)["events"]:
        raise PipelineError(f"no run record for {piece}: start at step 1, or record the earlier steps first")
    out = plan(root, piece, from_step, to_step, **kw)
    notes = []
    if out["texture"] == "stale" and int(from_step) <= TEXTURE <= int(to_step):
        notes.append("the texture is stale: a geometry or UV step changed the mesh after it; re-run step 13 (and 14)")
    out["notes"] = notes
    return out


def check_step(root, piece, n, studio_is_original=False):
    """The laws for running step n now. Raises PipelineError with the fix; returns {ok: True} otherwise."""
    _piece(piece)
    done = {e["step"] for e in run_record(root, piece)["events"]}
    if n in (13, 14) and SMART_UV not in done:
        raise PipelineError("texturing-last guard: no Smart UV step in this model's History; run step 8 (tripo.uv.unwrap) first (a texture fills the Smart UV islands)")
    if n in (SMART_UV, 13, 14) and studio_is_original:
        raise PipelineError("a Studio action lands on a saved COPY only; the selected model is an original: run tripo.uv.clone on its current version first")
    return {"ok": True}


def check_tool(root, piece, tool):
    _piece(piece)
    done = {e["step"] for e in run_record(root, piece)["events"]}
    if tool in RIG_TOOLS and not any(s in done for s in POSE_STEPS):
        raise PipelineError("pose the body to the piece before rig or weights: record fit_place and pose_clearance (step 6) first")
    return {"ok": True}
