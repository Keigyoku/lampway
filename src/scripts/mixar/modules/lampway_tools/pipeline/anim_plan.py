# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Planning for the animation-from-video set: the character clip (anim_clip), the tracker (anim_track: undecided providers answer needs_decision) and the orchestrator
(anim_from_video). Nothing here spends: a plan is a dry run, a confirmed run calls injected executors, and every step lands one row in decisions.jsonl.
Prices are LIST prices as recorded in the specs (derived, not measured live)."""

import hashlib
import json
import sys
import time
from pathlib import Path

SCAFFOLD = "locked camera, no cuts, no zoom, the whole body and feet in frame, {motion} in place"   # the exact wording the user used is not recorded: this is the design doc's
HIGGSFIELD_CREDITS = 22.5            # per 720p 9:16 5 s Seedance 2.0 clip (recorded)
OPENROUTER_USD = {"plain": 0.76, "with_reference_video": 0.46}      # derived from the model's SKUs, not measured live
MIN_DURATION = 4
COVERAGE_MIN = 0.90
PIPELINE = ("anim_reference_render", "anim_clip", "anim_track", "anim_check", "anim_loop_export")
FREE_STEPS = ("anim_reference_render",)
PROVIDER_SLOTS = [{"id": "gem_x", "label": "GEM-X body tracking", "state": "needs_approval", "why": "model slot: no provider decided"},
                  {"id": "sam3d_body_hosted", "label": "SAM 3D Body, hosted", "state": "needs_approval", "why": "no hosted provider is known; the local run breaks the no-heavy-local-model rule"},
                  {"id": "uthana", "label": "Uthana", "state": "needs_approval", "why": "a paid service: the user's click"}]


class PlanError(ValueError):
    pass


def clip_plan(reference_image, view, motion, driver_video=None, route="higgsfield", model=None, duration=5, resolution="720p", aspect_ratio="9:16",
              generate_audio=False, has_camera_record=True, **_):
    if view not in ("front", "side"):
        raise PlanError("view is front or side")
    if not has_camera_record:
        raise PlanError("reference image missing the camera record: run anim_reference_render")
    if aspect_ratio != "9:16":
        raise PlanError("16:9 halves the figure's pixel height: a full-body clip is 9:16")
    if duration < MIN_DURATION:
        raise PlanError(f"duration {duration} s gives fewer than the 4 strides the cycle averaging uses: {MIN_DURATION} s or more")
    default = "higgsfield/seedance_2_0" if route == "higgsfield" else "bytedance/seedance-2.0"
    gen = {"prompt": SCAFFOLD.format(motion=motion), "model": model or default, "duration": duration, "resolution": resolution, "aspect_ratio": aspect_ratio,
           "generate_audio": bool(generate_audio), "images": [reference_image], "dry_run": True}
    if driver_video:
        gen["videos"] = [driver_video]
    return {"ok": True, "spend": False, "dry_run": True, "view": view, "video_gen": gen, "route": route,
            "price": {"higgsfield_credits": HIGGSFIELD_CREDITS, "openrouter_usd": OPENROUTER_USD["with_reference_video" if driver_video else "plain"],
                      "basis": "list price, derived from the recorded 22.5-credit clip and the model's SKUs; not measured live"},
            "next": "run lampway_video_gen with this plan's video_gen; the user confirms the cost; then gate the clip with lampway_video_gate kind=clip. A failed gate is not retried."}


def clip_refusal(gates: dict):
    """The first failed clip gate as the refusal text; None when every gate passed."""
    for gid, g in gates.items():
        if g.get("passed") is False:
            return f"gate failed: {g.get('message') or gid}; not accepted, not retried: ask the user (every draw is a new charge)"
    return None


def track_plan(provider=None, shipping=True, clip="", mask_dir="", camera="", skeleton="metahuman_base_skel", host=None):
    host = host or sys.platform
    if not mask_dir:
        raise PlanError("mask_dir is required: per-frame silhouette masks from our own render pipeline (a person detector misses the armoured figure)")
    if provider == "gvhmr" and shipping:
        raise PlanError("GVHMR's licence is research and non-profit only and needs SMPL-X; prototype only: pass shipping=false and the output is tagged prototype and cannot be exported")
    if provider == "mha_markerless" and not str(host).lower().startswith("win"):
        raise PlanError("the MetaHuman Markerless Motion Capture plugin is Windows-only; point provider at a Windows runner or choose another")
    out = {"ok": False, "state": "needs_decision", "primary": "anim_multiview_fit", "slots": PROVIDER_SLOTS, "provider": provider, "skeleton": skeleton,
           "question": "Which body-tracking provider should anim_track use: a Windows runner for MetaHuman Animator Markerless, hosted SAM 3D Body, GEM-X, Uthana, or none (the two-view fit, anim_multiview_fit, needs no provider)?",
           "reason": "the provider is the user's decision (licence, cost, the no-local-heavy-model rule); nothing was run or spent"}
    if provider == "gvhmr":
        out.update(tag="prototype", exportable=False)
    return out


def coverage_gate(frames_with_pose, total) -> dict:
    n = len(frames_with_pose)
    share = n / total if total else 0.0
    return {"passed": share >= COVERAGE_MIN, "value": round(share, 4), "threshold": COVERAGE_MIN,
            "message": "covered" if share >= COVERAGE_MIN else f"tracker coverage {n}/{total} frames ({share * 100:.0f} %) < 90 %: this tracker cannot see the armoured figure; not accepted"}


def stock_check(motion, inventory, stock_first=True):
    if not stock_first:
        return
    hits = [n for n in inventory if motion.lower() in n.lower()]
    if hits:
        raise PlanError(f"stock animation exists for this move ({', '.join(hits)}): retarget it (animation_retarget) or pass stock_first=false")


# ------------------------------------------------------------------------------------------------------------- orchestrator
def _sha(artefact) -> str:
    return hashlib.sha256(json.dumps(artefact, sort_keys=True, default=str).encode()).hexdigest()


def _row(step, tool, params, result, by="agent"):
    return {"step": step, "tool": tool, "params": params, "gate_results": result["gates"], "cost": result.get("cost", 0), "by": by, "ts": time.time(), "artefact_sha256": _sha(result["artefact"])}


def run_pipeline(params, executors, confirm=False, out_dir=".", views=("front", "side")) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "decisions.jsonl"
    log.write_text("")
    prior, total = {}, 0.0
    card = {"credits": HIGGSFIELD_CREDITS * len(views), "usd": round(sum([OPENROUTER_USD["plain"]] + [OPENROUTER_USD["with_reference_video"]] * (len(views) - 1)), 2),
            "text": f"{len(views)} clips, {HIGGSFIELD_CREDITS * len(views):g} credits (list price)"}
    steps = []
    for i, tool in enumerate(PIPELINE):
        if tool not in FREE_STEPS and not confirm:
            return {"state": "awaiting_confirm", "steps": steps, "total_cost": total, "spend_card": card, "decisions": str(log)}
        result = executors[tool](params, prior)
        total += result.get("cost", 0)
        with log.open("a") as f:
            f.write(json.dumps(_row(i, tool, params, result)) + "\n")
        steps.append({"id": tool, "tool": tool, "status": "done", "gates": result["gates"], "cost": result.get("cost", 0)})
        prior[tool] = result["artefact"]
        why = clip_refusal(result["gates"])
        if why:
            steps[-1]["status"] = "failed"
            return {"state": "stopped", "stopped_at": tool, "message": why, "steps": steps, "total_cost": total, "decisions": str(log)}
    return {"state": "done", "steps": steps, "total_cost": total, "decisions": str(log)}


def replay(out_dir, executors) -> dict:
    """Re-run every recorded step with the given executors (cache-backed in real use) and compare the artefact hashes with decisions.jsonl."""
    rows = [json.loads(l) for l in (Path(out_dir) / "decisions.jsonl").read_text().splitlines() if l.strip()]
    prior, mismatches = {}, []
    for r in rows:
        res = executors[r["tool"]](r["params"], prior)
        prior[r["tool"]] = res["artefact"]
        if _sha(res["artefact"]) != r["artefact_sha256"]:
            mismatches.append(r["tool"])
    return {"identical": not mismatches, "mismatches": mismatches, "steps": len(rows)}
