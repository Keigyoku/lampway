# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ue_parity's comparison maths (specs/ue_parity/contracts/ue_parity.md §5): two linear renders of one standard scene, the
regions the scene description names, and a verdict per difference class against the contract's tolerances.

  COL  per chart patch: 8-bit display code after the profile's cube, max <= 3 and mean <= 1; linear ratio within 1 %
  SHD  per furnace sphere: mean linear radiance ratio within 3 % (a placeholder until the first furnace run; the captain's)
  NRM  per bump: the sign of the shading gradient along the light axis agrees (100 %); mean CIEDE2000 <= 2 after the cube
  LGT  at the probe points: plane radiance ratio within 2 % (k is already in both sides)
  GEO  silhouette IoU of the alpha masks >= 0.995
  PST  the edge band (3 px around either silhouette) is excluded from everything above and reported alone (TSR vs EEVEE AA)
  TEX  report only (the preview samples source textures unless the profile says bc_decoded)

"within X" is strict: an error equal to the tolerance fails. Without a display cube (the generator decision is open) the COL
display half is needs_decision and only the linear half decides. Pure numpy."""

import math

import numpy as np

TOLERANCES = {"COL": {"display_max_codes": 3.0, "display_mean_codes": 1.0, "linear_ratio": 0.01}, "SHD": {"radiance_ratio": 0.03},
              "NRM": {"sign_agreement": 1.0, "mean_de2000": 2.0}, "LGT": {"radiance_ratio": 0.02}, "GEO": {"silhouette_iou": 0.995}}
EDGE_BAND_PX = 3
_Y = np.array([0.2126, 0.7152, 0.0722])
EXR_MAGIC, PNG_MAGIC = b"\x76\x2f\x31\x01", b"\x89PNG"


class CaptureError(ValueError):
    pass


def check_capture(path, linear=True) -> str:
    """The file's real format by its magic bytes; a mislabelled file and a quantised .hdr for linear checks are refused."""
    from pathlib import Path
    p = Path(path)
    head = p.read_bytes()[:16]
    kind = "exr" if head.startswith(EXR_MAGIC) else "png" if head.startswith(PNG_MAGIC) else "hdr" if head.startswith((b"#?RADIANCE", b"#?RGBE")) else "unknown"
    if kind != p.suffix.lower().lstrip(".") and not (kind == "unknown"):
        raise CaptureError(f"{p.name} is mislabelled: its bytes are {kind.upper()} under a {p.suffix} name (UE writes float targets as EXR "
                           "whatever the extension): name it .exr")
    if kind == "hdr" and linear:
        raise CaptureError(f"{p.name} is Radiance .hdr: about 1 % quantisation, too coarse for the linear checks: capture EXR (CMP-01)")
    if kind == "unknown":
        raise CaptureError(f"{p.name} is not EXR, PNG or HDR")
    return kind


def _dilate(m, n):
    out = m.copy()
    for _ in range(n):
        p = np.pad(out, 1)
        out = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] | p[:-2, :-2] | p[:-2, 2:] | p[2:, :-2] | p[2:, 2:]
    return out


def edge_band(alpha_a, alpha_b, px=EDGE_BAND_PX):
    band = np.zeros(alpha_a.shape, bool)
    for a in (alpha_a > 0.5, alpha_b > 0.5):
        boundary = a & _dilate(~a, 1)                                      # mask pixels touching the outside
        band |= _dilate(boundary, px)
    return band


def _mean(img, rect, keep):
    x0, y0, x1, y1 = rect
    sub, k = img[y0:y1, x0:x1, :3], keep[y0:y1, x0:x1]
    return sub[k].mean(axis=0) if k.any() else np.full(3, np.nan)


def _within(err, tol):
    """Strictly inside the tolerance, compared at 1e-9: an error equal to the tolerance (a 2 % error against 2 %) fails."""
    return err is not None and round(err, 9) < tol


def _ratio(a, b):
    ok = np.abs(a) > 1e-6
    return float(np.max(np.abs(b[ok] / a[ok] - 1.0))) if ok.any() else 0.0


def srgb_to_lab(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def de2000(lab1, lab2):
    """CIEDE2000 (Sharma, Wu and Dalal 2005), vectorised over the last axis."""
    L1, a1, b1 = np.moveaxis(np.asarray(lab1, float), -1, 0)
    L2, a2, b2 = np.moveaxis(np.asarray(lab2, float), -1, 0)
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb7 = ((C1 + C2) / 2) ** 7
    G = 0.5 * (1 - np.sqrt(Cb7 / (Cb7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    dh = np.where(C1p * C2p == 0, 0, np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh)))
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1p + h2p
    hbp = np.where(C1p * C2p == 0, hs, np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp)) + 0.32 * np.cos(np.radians(3 * hbp + 6))
         - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dth = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dth)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def compare(lampway, ue, regions, display=None) -> dict:
    """lampway, ue: linear RGBA float images of one view. regions: {COL: [rect], SHD: [rect], NRM: [{rect, axis}], LGT: [[x, y]],
    TEX?: ...}; rect = [x0, y0, x1, y1] in pixels, row 0 at the top. display: linear -> display code 0..1 (the cube), or None."""
    a, b = np.asarray(lampway, float), np.asarray(ue, float)
    band = edge_band(a[..., 3], b[..., 3])
    keep = ~band
    out = {}
    T = TOLERANCES
    # COL
    la = np.array([_mean(a, r, keep) for r in regions.get("COL", [])])
    lb = np.array([_mean(b, r, keep) for r in regions.get("COL", [])])
    col = {"patches": len(la), "linear_ratio": _ratio(la, lb) if len(la) else None}
    ok = _within(col["linear_ratio"], T["COL"]["linear_ratio"])
    if display is None:
        col["display"] = "needs_decision"
    else:
        d = np.abs(np.asarray(display(lb)) - np.asarray(display(la))) * 255.0
        col.update(display="cube", display_max_codes=float(d.max()), display_mean_codes=float(d.mean()))
        ok = ok and col["display_max_codes"] <= T["COL"]["display_max_codes"] and col["display_mean_codes"] <= T["COL"]["display_mean_codes"]
    out["COL"] = dict(col, verdict="pass" if ok else "fail")
    # SHD
    sa = np.array([_mean(a, r, keep) @ _Y for r in regions.get("SHD", [])])
    sb = np.array([_mean(b, r, keep) @ _Y for r in regions.get("SHD", [])])
    r = _ratio(sa, sb) if len(sa) else None
    out["SHD"] = {"spheres": len(sa), "radiance_ratio": r, "verdict": "pass" if _within(r, T["SHD"]["radiance_ratio"]) else "fail"}
    # NRM
    agree, des = [], []
    for bump in regions.get("NRM", []):
        x0, y0, x1, y1 = bump["rect"]
        mid = (y0 + y1) // 2 if bump.get("axis", "y") == "y" else None
        def grad(img):
            lum = img[..., :3] @ _Y
            return float(lum[y0:mid, x0:x1].mean() - lum[mid:y1, x0:x1].mean()) if mid else float(lum[y0:y1, x0:(x0 + x1) // 2].mean() - lum[y0:y1, (x0 + x1) // 2:x1].mean())
        agree.append(np.sign(grad(a)) == np.sign(grad(b)))
        if display is not None:
            des.append(float(de2000(srgb_to_lab(display(a[y0:y1, x0:x1, :3])), srgb_to_lab(display(b[y0:y1, x0:x1, :3]))).mean()))
    sign = float(np.mean(agree)) if agree else None
    nrm = {"bumps": len(agree), "sign_agreement": sign, "mean_de2000": float(np.mean(des)) if des else None}
    ok = sign is not None and sign >= T["NRM"]["sign_agreement"] and (nrm["mean_de2000"] is None or nrm["mean_de2000"] <= T["NRM"]["mean_de2000"])
    out["NRM"] = dict(nrm, verdict="pass" if ok else "fail")
    # LGT
    def probe(img, x, y):
        return float(img[y - 1:y + 2, x - 1:x + 2, :3].mean(axis=(0, 1)) @ _Y)
    pa = np.array([probe(a, x, y) for x, y in regions.get("LGT", [])])
    pb = np.array([probe(b, x, y) for x, y in regions.get("LGT", [])])
    r = _ratio(pa, pb) if len(pa) else None
    out["LGT"] = {"probes": len(pa), "radiance_ratio": r, "verdict": "pass" if _within(r, T["LGT"]["radiance_ratio"]) else "fail"}
    # GEO
    ma, mb = a[..., 3] > 0.5, b[..., 3] > 0.5
    iou = float((ma & mb).sum() / max(1, (ma | mb).sum()))
    out["GEO"] = {"silhouette_iou": iou, "verdict": "pass" if iou >= T["GEO"]["silhouette_iou"] else "fail"}
    # PST (report)
    pst = {"edge_band_px": EDGE_BAND_PX, "band_pixels": int(band.sum()), "verdict": "report"}
    if band.any():
        pst["mean_abs_linear"] = float(np.abs(a[band][:, :3] - b[band][:, :3]).mean())
        if display is not None:
            pst["mean_de2000"] = float(de2000(srgb_to_lab(display(a[band][:, :3])), srgb_to_lab(display(b[band][:, :3]))).mean())
    out["PST"] = pst
    out["TEX"] = {"verdict": "report", "note": regions.get("TEX") or "no texture pair in this scene (TEX-02: compression is not matched by default)"}
    return {"classes": out, "tolerances": TOLERANCES}


def ue_hfov_deg(lens_mm, sensor_mm) -> float:
    """UE's horizontal field of view for a Blender lens on a horizontal sensor fit: 2 atan(sensor / (2 lens))."""
    return math.degrees(2.0 * math.atan(sensor_mm / (2.0 * lens_mm)))


def project_blender(pts, lens_mm, sensor_mm, width, height):
    """Pixel coordinates (row 0 at the top) of points in a camera frame: +Y forward, +X right, +Z up; horizontal sensor fit."""
    p = np.asarray(pts, float)
    f = lens_mm / sensor_mm * width
    return np.stack([width / 2 + p[:, 0] / p[:, 1] * f, height / 2 - p[:, 2] / p[:, 1] * f], -1)


def project_ue(pts, hfov_deg, width, height):
    """The same points through UE's pinhole: focal = (width / 2) / tan(hfov / 2)."""
    p = np.asarray(pts, float)
    f = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
    return np.stack([width / 2 + p[:, 0] / p[:, 1] * f, height / 2 - p[:, 2] / p[:, 1] * f], -1)
