# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File-level actions of view_verify: read an image under the project root, run the pure checks, write ``view_verify.json`` beside it. Pillow only."""

import json
from pathlib import Path

import numpy as np

from . import retry_policy as RP
from . import view_verify as VV

TEMPLATE_IDS = ("sheet-apose-front", "sheet-multiview-16x9", "part-body", "part-paired", "part-accessory", "part-hair", "part-view", "turntable-360-locked")
CATEGORIES = ("sheet", "body", "paired", "accessory", "hair", "multiview")


class ViewVerifyError(ValueError):
    pass


def _load(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"))


def run(action, root, image=None, category="sheet", view="front", approved_front=None, mask=None, asymmetric_ok=False, judge=None, known_images=None, attempts=None,
        max_attempts=3, original_prompt="", resolve=lambda p: p, judge_fn=None):
    if action == "templates":
        return {"templates": list(TEMPLATE_IDS), "where": "the server's prompt library (built-in)", "note": "list them with lampway_prompt_list; each carries its upstream provenance"}
    if action == "ladder":
        if not 1 <= int(max_attempts) <= 4:
            raise ViewVerifyError("max_attempts is 1..4")
        hist = attempts or []
        d = RP.decide(hist, int(max_attempts))
        if d["action"] == "retry":
            last = hist[-1]
            if not original_prompt:
                raise ViewVerifyError("the ladder needs original_prompt to write the escalated prompt")
            d["next_prompt"] = RP.escalate(original_prompt, last.get("reason", ""), last.get("rotation_deg"))
        return d
    if category not in CATEGORIES:
        raise ViewVerifyError(f"category is {' | '.join(CATEGORIES)}")
    if not image:
        raise ViewVerifyError("image is required")
    img = _load(resolve(image))
    m = VV.to_mask(_load(resolve(mask))) if mask else VV.to_mask(img)
    if action == "admit":
        known = {Path(p).name: VV.phash(VV.to_mask(_load(resolve(p)))) for p in (known_images or [])}
        out = VV.admit(m, known)
        if not out["ok"]:
            out["error_text"] = "rejected at intake: " + "; ".join(out["reasons"])
        return out
    if action == "verify":
        if view not in ("front", "side", "back"):
            raise ViewVerifyError("view is front | side | back")
        if judge not in (None, "none") and judge_fn is None:
            raise ViewVerifyError("no vision judge is configured: set one in Providers or use judge=none for the measured checks only")
        if not mask and img[..., 3].min() == 255:
            corners = np.concatenate([img[:8, :8, :3].reshape(-1, 3), img[-8:, -8:, :3].reshape(-1, 3)])
            if corners.std(axis=0).max() > 12:
                raise ViewVerifyError("the plate needs an alpha or a flat background: see plate_prep")
        ref = VV.to_mask(_load(resolve(approved_front))) if approved_front else None
        out = VV.verify(m, view, category, ref, bool(asymmetric_ok), judge_fn, img[..., :3])
        Path(resolve(image)).with_suffix(".view_verify.json").write_text(json.dumps(out, indent=1, default=float))
        return out
    raise ViewVerifyError("action is admit | verify | ladder | templates")
