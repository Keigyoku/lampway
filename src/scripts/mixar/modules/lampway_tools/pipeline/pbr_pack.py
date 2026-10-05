# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""pbr_pack, the file half: pack separate studio/baked maps into the engine set (BaseColor sRGB, ORM, Normal DX and GL, Roughness, Metallic).

ORM is Unreal's order: R = occlusion (1 when no AO map is given, and the result says so), G = roughness, B = metallic, all linear. Normal GL is the map as given (green up); Normal DX flips green.
Metallic is forced to 0 under the masks of cloth and leather classes (the user's law: no metal on cloth). Maps must be square powers of two for engine export. A set is never overwritten.
Numpy and PIL only; `pbr_merge` stays the tool for a PATCHED mesh (it fills patch islands from the albedo atlas)."""

import json
from pathlib import Path

import numpy as np
from PIL import Image

FLAT = (128, 128, 255)
FLAT_TOL = 2


class PackError(ValueError):
    pass


def _load(path, mode):
    im = Image.open(path).convert(mode)
    return im


def _check_size(name, im):
    w, h = im.size
    if w != h or (w & (w - 1)):
        raise PackError(f"{name} is {w}x{h}: engine export needs square power-of-two maps (resize it first)")
    return w


def pack(maps, convention, name, root, metal_zero_masks=None):
    """maps {base, normal, rough, metal, ao|None}. Returns {files, merge, notes}."""
    if convention not in ("dx", "gl", "both"):
        raise PackError("convention is dx, gl or both")
    out = Path(root) / (name or "pbr") / "pbr_pack"
    if out.exists() and any(out.iterdir()):
        raise PackError(f"{out} exists: a set is never overwritten (pick another name)")
    notes = []
    base, normal = _load(maps["base"], "RGB"), _load(maps["normal"], "RGB")
    rough, metal = _load(maps["rough"], "L"), _load(maps["metal"], "L")
    sizes = {n: _check_size(n, im) for n, im in (("base", base), ("normal", normal), ("rough", rough), ("metal", metal))}
    ao = _load(maps["ao"], "L") if maps.get("ao") else None
    if ao is not None:
        sizes["ao"] = _check_size("ao", ao)
    # the base colour keeps its size; the data maps are brought to the largest data size so ORM channels line up
    data = max(sizes[k] for k in sizes if k != "base")
    def fit(im):
        return im if im.size == (data, data) else im.resize((data, data), Image.LANCZOS)
    rough, metal, normal = fit(rough), fit(metal), fit(normal)
    r_arr, m_arr = np.asarray(rough).copy(), np.asarray(metal).copy()
    for mp in metal_zero_masks or ():
        mask = _load(mp, "L")
        mask = mask if mask.size == (data, data) else mask.resize((data, data), Image.NEAREST)
        m_arr[np.asarray(mask) > 127] = 0
    if ao is None:
        notes.append("no AO map: ORM red is 1 (white)")
        ao_arr = np.full((data, data), 255, np.uint8)
    else:
        ao_arr = np.asarray(fit(ao))
    n_arr = np.asarray(normal).astype(int)
    if (np.abs(n_arr - np.array(FLAT)).max(axis=2) <= FLAT_TOL).all():
        notes.append("flat normal: no height information (not a recovered surface; check the source before packing)")
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    def save(key, arr, mode):
        p = out / f"{key}.png"
        Image.fromarray(arr, mode).save(p)
        files[key] = str(p)
    base.save(out / "BaseColor.png"); files["BaseColor"] = str(out / "BaseColor.png")
    save("ORM", np.dstack([ao_arr, r_arr, m_arr]).astype(np.uint8), "RGB")
    save("Roughness", r_arr.astype(np.uint8), "L")
    save("Metallic", m_arr.astype(np.uint8), "L")
    if convention in ("gl", "both"):
        save("Normal_GL", n_arr.astype(np.uint8), "RGB")
    if convention in ("dx", "both"):
        dx = n_arr.copy(); dx[..., 1] = 255 - dx[..., 1]
        save("Normal_DX", dx.astype(np.uint8), "RGB")
    cs = {"BaseColor": "sRGB", "ORM": "Non-Color", **{k: "Non-Color" for k in files if k.startswith("Normal")}}
    merge = {"convention": convention, "sizes": {"BaseColor": sizes["base"], "data_maps": data}, "colorspace": cs, "orm": "R occlusion, G roughness, B metallic (Unreal order), linear",
             "metal_zero_masks": [str(m) for m in (metal_zero_masks or ())], "notes": notes}
    (out / "merge.json").write_text(json.dumps(merge, indent=1))
    files["merge.json"] = str(out / "merge.json")
    return {"ok": True, "files": files, "merge": merge, "notes": notes, "dir": str(out)}
