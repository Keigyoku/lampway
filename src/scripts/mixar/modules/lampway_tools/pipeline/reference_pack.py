# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""reference_pack (specs/wiki/reference_pack.md): the four-stage reference method as a GATED sequence; a composite over view_verify (admit, verify), a
silhouette identity measure against the approved source, and the experiment ledger.

sheet   ONE technical sheet on white, neutral light, the whole asset in frame, in the pose downstream tools need; the anatomical LEFT and RIGHT are named
        (camera-left is not anatomical left): refused without them
audit   an image (a sheet candidate, a part, a view) against the approved source: view_verify's admit (empty, fragmented, tiny) and verify (framing, axis,
        rotation: a hard failure fails) and the silhouette IoU of the two figures framed alike (>= IOU_MIN [UNVERIFIED]); a sheet that passes unlocks the next
        stages; a failure STOPS: 'identity failed at <stage>: fix the reference or prompt, not the batch size'
extract one prompt per component, reusing the passing sheet (needs it)
views   only the MISSING views (a view already in the approved sheet is refused); never chain a drifting view as a new authority: each is audited against
        the same sheet
Stages are dry runs (prompt files written, nothing sent) unless live; a live stage records a run (host, model purpose, date, prompts, seed not_exposed, output
files, selected=None: the user selects) and one ledger row per image call. State: <root>/<asset>/reference/state.json."""

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import view_verify as VV

STAGES = ("sheet", "audit", "extract", "views", "run")
VIEWS = ("Front", "Back", "Left", "Right", "Underside")
IOU_MIN = 0.85
SHEET = ("One technical reference sheet of {asset} on a plain white background with neutral, even light; the entire asset in frame with a margin; "
         "{pose}-pose; orthographic, no perspective; {components}the anatomical LEFT: {left}; the anatomical RIGHT: {right} (the wearer's own sides: camera-left "
         "is not anatomical left). Keep every design detail of the reference image; add nothing.")
EXTRACT = ("From this approved technical sheet of {asset}, extract ONLY the {component} as its own reference: plain white background, the same scale, style, "
           "materials and colours as in the sheet; nothing else in frame.")
VIEW = ("From this approved technical sheet of {asset}, draw ONLY the {view} view of the same asset: the same proportions, materials and details; plain white "
        "background, orthographic, the whole asset in frame. Do not mirror the design.")


class ReferenceRefused(ValueError):
    pass


def _dir(root, asset):
    d = Path(root) / asset / "reference"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state(d):
    p = d / "state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save(d, st):
    (d / "state.json").write_text(json.dumps(st, indent=1))


def _framed(mask, n=256):
    """The figure scaled so its HEIGHT fills n (its aspect kept, so a narrower or wider figure stays narrower or wider) and centred on its bbox."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return np.zeros((n, n), bool)
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    nw = max(1, min(4 * n, round(w * n / h)))
    small = np.asarray(Image.fromarray(crop.astype(np.uint8) * 255).resize((nw, n), Image.NEAREST)) > 127
    out = np.zeros((n, 4 * n), bool)
    x0 = 2 * n - nw // 2
    out[:, x0:x0 + nw] = small
    return out


def silhouette_iou(a_path, b_path) -> float:
    a = _framed(VV.to_mask(Image.open(a_path).convert("RGBA")))
    b = _framed(VV.to_mask(Image.open(b_path).convert("RGBA")))
    return float((a & b).sum() / max((a | b).sum(), 1))


def _generate(d, stage, prompts, reference, live, count, purpose, generate, record, asset):
    files_p = []
    for k, text in enumerate(prompts, 1):
        pf = d / f"{stage}_{k}.prompt.txt"
        pf.write_text(text, encoding="utf-8")
        files_p.append(str(pf))
    if not live:
        return {"dry_run": True, "stage": stage, "prompt_files": files_p, "requests": len(prompts), "images_per_request": count,
                "how": "live=true sends each prompt with the approved reference to the image slot (purpose " + purpose + "), only when the user asked"}
    ref = Path(reference).read_bytes()
    outs = []
    for k, text in enumerate(prompts, 1):
        imgs = generate(text, ref, count, params_extra={"purpose": purpose})
        for j, data in enumerate(imgs, 1):
            f = d / f"{stage}_{k}_{j}.png"
            f.write_bytes(data)
            outs.append(str(f))
        if record:
            record({"piece": asset, "stage": "image", "studio": "local", "seed": "not_exposed", "by": "agent", "model_version": None,
                    "settings": {"reference_pack_stage": stage, "purpose": purpose, "count": count, "image_slot": "server image_gen"},
                    "prompt_hash": hashlib.sha256(text.encode()).hexdigest(), "reference_hashes": [hashlib.sha256(ref).hexdigest()],
                    "output_hashes": [hashlib.sha256(Path(o).read_bytes()).hexdigest() for o in outs[-len(imgs):]], "cost": {},
                    "reason": f"reference_pack {stage}: the image job carries its own price row"})
    run_record = {"host": "server image slot", "model_purpose": purpose, "date": time.strftime("%Y-%m-%d"), "prompts": files_p, "controls": {"count": count},
                  "seed": "not_exposed", "output_ids": [os.path.basename(o) for o in outs], "selected": None}
    (d / f"{stage}.run.json").write_text(json.dumps(run_record, indent=1))
    return {"dry_run": False, "stage": stage, "files": outs, "prompt_files": files_p, "run_record": run_record,
            "next": "audit each candidate against the approved source (stage audit); the user selects"}


def run_stage(stage, root, asset, approved_reference, components=None, pose="T", views=None, left_description="", right_description="", model_purpose="plates",
              count=4, live=False, image="", sheet_views=None, generate=None, record=None):
    if stage not in STAGES:
        raise ReferenceRefused("stage is " + " | ".join(STAGES))
    if not asset:
        raise ReferenceRefused("asset names the asset (the reference folder)")
    if not approved_reference or not os.path.exists(approved_reference):
        raise ReferenceRefused("approved_reference is the approved source image every stage is checked against")
    if pose not in ("T", "A"):
        raise ReferenceRefused("pose is T | A")
    if model_purpose not in ("plates", "concept"):
        raise ReferenceRefused("model_purpose is plates | concept (the image purposes)")
    count = int(count)
    if not 1 <= count <= 4:
        raise ReferenceRefused("count is 1..4")
    d = _dir(root, asset)
    st = _state(d)
    if stage == "sheet":
        if not left_description or not right_description:
            raise ReferenceRefused("state which attachment is anatomical left and which is right (left_description, right_description): camera-left is not anatomical left")
        comp = ("with " + ", ".join(components) + "; ") if components else ""
        prompt = SHEET.format(asset=asset, pose=pose, components=comp, left=left_description, right=right_description)
        out = _generate(d, "sheet", [prompt], approved_reference, live, count, model_purpose, generate, record, asset)
        st["sheet"] = {"passed": False, "candidates": out.get("files", []), "views": list(sheet_views or ["Front"]), "prompt": out["prompt_files"][0]}
        _save(d, st)
        return out
    if stage == "audit":
        if not image or not os.path.exists(image):
            raise ReferenceRefused("audit needs image (a candidate to check against the approved source)")
        im = Image.open(image).convert("RGBA")
        adm = VV.admit(im)
        ver = VV.verify(im, view="front", category="sheet", image=np.asarray(im.convert("RGB")))
        iou = silhouette_iou(image, approved_reference)
        reasons = list(adm["reasons"])
        if ver.get("verdict") == "hard_fail":
            reasons.append("view_verify: " + str(ver.get("reason")))
        if iou < IOU_MIN:
            reasons.append(f"silhouette IoU {iou:.2f} against the approved source < {IOU_MIN}")
        which = "sheet" if not st.get("sheet", {}).get("passed") else "part or view"
        out = {"stage": "audit", "image": image, "passed": not reasons, "audit": {"silhouette_iou": round(iou, 4), "admit": adm, "verify_verdict": ver.get("verdict"),
               "iou_min_status": "UNVERIFIED"}, "reasons": reasons}
        if reasons:
            out["stop"] = f"identity failed at {which}: fix the reference or prompt, not the batch size ({'; '.join(reasons)})"
        elif which == "sheet":
            st.setdefault("sheet", {"views": list(sheet_views or ["Front"])})
            st["sheet"].update(passed=True, image=image)
            _save(d, st)
        return out
    sheet = st.get("sheet") or {}
    if stage in ("extract", "views", "run") and not sheet.get("passed"):
        if stage == "run":
            return {"dry_run": True, "stage": "run", "order": ["sheet", "audit", "extract", "views"], "next": "sheet (the first stage that has not passed)"}
        raise ReferenceRefused(f"{stage} needs a sheet that passed its audit: run stage sheet, then audit a candidate")
    if stage == "extract":
        comps = list(components or [])
        if not comps:
            raise ReferenceRefused("extract needs components (the parts to extract)")
        return _generate(d, "extract", [EXTRACT.format(asset=asset, component=c) for c in comps], sheet["image"], live, count, model_purpose, generate, record, asset)
    if stage == "views":
        vs = list(views or [])
        bad = [v for v in vs if v not in VIEWS]
        if not vs or bad:
            raise ReferenceRefused(f"views names the missing views among {', '.join(VIEWS)}")
        have = [v for v in vs if v in sheet.get("views", [])]
        if have:
            raise ReferenceRefused(f"{have} already in the approved sheet: request only missing views (never chain a drifting view as a new authority)")
        return _generate(d, "views", [VIEW.format(asset=asset, view=v) for v in vs], sheet["image"], live, count, model_purpose, generate, record, asset)
    return {"dry_run": True, "stage": "run", "order": ["sheet", "audit", "extract", "views"], "sheet_passed": True, "next": "extract or views"}
