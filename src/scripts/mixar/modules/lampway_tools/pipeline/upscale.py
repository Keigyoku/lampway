# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""image_upscale (specs/generation/image_upscale.md): raise a plate or texture to 2048..4096 px without changing its content; the original is never replaced.

lanczos  Pillow LANCZOS: deterministic, free, the baseline every other route is judged against
model    the image slot as an EDIT with the source as the reference, at most 2880 x 2880 (GPT Image 2.5's 8.3 MP budget); a dry run unless live. The result
         passes the FAITHFULNESS gate or is kept as a rejected file: downscaled back to the source size it must keep the source's structure (SSIM >= 0.95, the
         minimum over R, G and B, so a recolour fails) and its edges (edge IoU >= 0.90), and it must carry MORE fine detail than the Lanczos baseline
         (Laplacian variance >= the baseline's), or it is a soft upscale that adds nothing. [thresholds UNVERIFIED: set on synthetic plates]
tripo    the Studio's free 4K image tool (Studio action tripo.image, whose price must read back 0) with the source as its reference: a plan, nothing clicked
Every output carries <file>.upscale.json (source and output sha256, method, size, the gate)."""

import hashlib
import io
import json
import os

import numpy as np
from PIL import Image

from .imgops import gaussian

MODEL_MAX = 2880
SSIM_MIN = 0.95
EDGE_IOU_MIN = 0.90
PROMPT = ("Reproduce this image exactly at a higher resolution: the same composition, shapes, colours and lighting; add no content, remove nothing, "
          "change no colour; only sharpen the detail that is there.")


class UpscaleRefused(ValueError):
    pass


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def ssim(a, b):
    """Mean SSIM of two equal-size single-channel float images (0..255), gaussian window sigma 1.5."""
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    mu_a, mu_b = gaussian(a, 1.5), gaussian(b, 1.5)
    va = gaussian(a * a, 1.5) - mu_a ** 2
    vb = gaussian(b * b, 1.5) - mu_b ** 2
    cov = gaussian(a * b, 1.5) - mu_a * mu_b
    s = ((2 * mu_a * mu_b + C1) * (2 * cov + C2)) / ((mu_a ** 2 + mu_b ** 2 + C1) * (va + vb + C2))
    return float(s.mean())


def _edges(g):
    gx = np.zeros_like(g); gy = np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1] = g[2:] - g[:-2]
    m = np.hypot(gx, gy)
    return m > 0.2 * m.max()                                              # the strong edges (ornament, outlines): a smooth gradient field does not count


def _lap_var(g):
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())


def faithfulness(src_img, out_img, baseline_img):
    """The gate on a model result: back at the source size it keeps structure and colour, and at full size it is sharper than the Lanczos baseline."""
    s = np.asarray(src_img.convert("RGB")).astype(np.float64)
    down = np.asarray(out_img.convert("RGB").resize(src_img.size, Image.LANCZOS)).astype(np.float64)
    ss = min(ssim(s[..., c], down[..., c]) for c in range(3))
    e1, e2 = _edges(s.mean(2)), _edges(down.mean(2))
    edge_iou = float((e1 & e2).sum() / max((e1 | e2).sum(), 1))
    hue = float(np.abs(s.mean((0, 1)) - down.mean((0, 1))).max())
    sharp_out = _lap_var(np.asarray(out_img.convert("L")).astype(np.float64))
    sharp_base = _lap_var(np.asarray(baseline_img.convert("L")).astype(np.float64))
    reasons = []
    if ss < SSIM_MIN:
        reasons.append(f"the model repainted instead of upscaling: SSIM {ss:.2f} < {SSIM_MIN} against the downscaled output (the minimum over R, G, B); use lanczos")
    if edge_iou < EDGE_IOU_MIN:
        reasons.append(f"the edges moved: edge IoU {edge_iou:.2f} < {EDGE_IOU_MIN}")
    if sharp_out < sharp_base:
        reasons.append(f"it adds no detail: Laplacian variance {sharp_out:.1f} < the Lanczos baseline's {sharp_base:.1f}; keep the baseline")
    return {"ssim": round(ss, 4), "edge_iou": round(edge_iou, 4), "max_mean_channel_shift": round(hue, 3), "sharpness": round(sharp_out, 2),
            "baseline_sharpness": round(sharp_base, 2)}, reasons


def _out_path(src, target, method, suffix):
    stem, _ = os.path.splitext(src)
    return f"{stem}_up{target}_{method}{suffix}.png"


def _write(path, img, src, method, target, fa, reasons, extra=None):
    if os.path.exists(path):
        raise UpscaleRefused(f"{os.path.basename(path)} exists: never overwritten (pass another target or suffix)")
    img.save(path)
    side = {"method": method, "target": target, "source": os.path.basename(src), "source_sha256": _sha(src), "output": os.path.basename(path),
            "output_sha256": _sha(path), "size": list(img.size), "faithfulness": fa, "gate": {"passed": not reasons, "reasons": reasons}, **(extra or {})}
    with open(path + ".upscale.json", "w") as fh:
        json.dump(side, fh, indent=1)
    return side


def upscale(image, target=4096, method="lanczos", live=False, prompt="", generate=None, suffix=""):
    if method not in ("lanczos", "model", "tripo"):
        raise UpscaleRefused("method is lanczos | model | tripo")
    t = int(target)
    if not 2048 <= t <= 4096:
        raise UpscaleRefused("target is 2048..4096 px (the long edge)")
    src = Image.open(image)
    if min(src.size) < 512:
        raise UpscaleRefused(f"the source is {src.size[0]} x {src.size[1]}: under 512 px there is not enough to upscale faithfully")
    scale = t / max(src.size)
    size = (round(src.size[0] * scale), round(src.size[1] * scale))
    base = src.convert("RGB").resize(size, Image.LANCZOS)
    if method == "tripo":
        pf = os.path.splitext(image)[0] + "_upscale_prompt.txt"
        with open(pf, "w", encoding="utf-8") as fh:
            fh.write(PROMPT)
        return {"needs_approval": True, "studio_action": "tripo.image", "plan_args": {"prompt_file": pf, "refs": [image], "aspect": "1:1"},
                "how": "call studio_plan with action tripo.image and these plan_args: the 4K image is free on the image quota, so the price must read back 0 "
                       "(a non-zero price becomes the user's approval); judge the result with this tool's gate (method=model's faithfulness) before using it",
                "source_size": list(src.size)}
    if method == "lanczos":
        path = _out_path(image, t, "lanczos", suffix)
        fa, reasons = faithfulness(src, base, base)
        side = _write(path, base, image, "lanczos", t, fa, reasons)
        return {"file": path, "method": "lanczos", "source_size": list(src.size), "size": list(size), "faithfulness": fa, "gate": side["gate"], "cost_usd": 0.0}
    if t > MODEL_MAX:
        raise UpscaleRefused(f"GPT Image 2.5 tops out at {MODEL_MAX}x{MODEL_MAX} within 8.3 MP: use method=tripo or lanczos for {t}")
    text = prompt or PROMPT
    if not live:
        return {"dry_run": True, "method": "model", "prompt": text, "size": list(size),
                "cost_note": "one edit on the server's image slot with the source as reference (the 2048 px 3-reference call was $0.1449; 2880 px is UNVERIFIED); "
                             "the source image goes to openrouter.ai", "how": "live=true only when the user asked for it"}
    with open(image, "rb") as fh:
        data = generate(text, fh.read(), 1, params_extra={"purpose": "plates", "size": f"{size[0]}x{size[1]}"})[0]
    out = Image.open(io.BytesIO(data)).convert("RGB")
    fa, reasons = faithfulness(src, out, base)
    path = _out_path(image, t, "model" if not reasons else "model_rejected", suffix)
    side = _write(path, out, image, "model", t, fa, reasons)
    return {"file": path, "method": "model", "source_size": list(src.size), "size": list(out.size), "faithfulness": fa, "gate": side["gate"],
            "cost_usd": None, "cost_note": "the image job's own ledger row carries the price"}
