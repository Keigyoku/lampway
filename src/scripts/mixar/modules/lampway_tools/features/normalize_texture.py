# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""lampway_normalize_texture (specs/canon/normalization contracts/normalize_texture.md): an image into a canonical ``texture``.

* The ROLE is declared, or read from the naming table of the DECLARED source (``source_naming``: ambientcg | polyhaven | lampway);
  an undeclared source has no table and ``role=auto`` refuses ("role unknown for <file>: declare role=...").
* The COLOUR SPACE is bound to the role (canon_io.colour_space: basecolor / emission / reference sRGB, hdri Linear Rec.709, every
  data role Non-Color) and set on the image (a flag: no pixel changes).
* A NORMAL map's convention comes from the naming (``_NormalGL``, ``_nor_dx``, ``Normal_GL``) or is declared; it is never assumed
  ("normal convention unknown: declare normal_convention=gl|dx"). The sign test of the contract (section 6) is unverified and not
  built: ``auto`` without naming refuses.
* ORM is packed r ao, g roughness, b metallic (Unreal's order; Poly Haven's ``arm``).
* Measured: width, height, power of two, bit depth per channel, channels, alpha, and the sha256 of the image file (= the raw sha).
The image is stamped ``lw_canon`` (``lw_raw`` removed) and a receipt written under ``canon/receipts/``. The material normalizer
(``lampway_normalize_material``) is not built."""

import hashlib
import json
import re
from pathlib import Path

import bpy

from .. import canon_asset as CA
from .. import canon_io
from . import common as C

TOOL, TOOL_VERSION = "lampway_normalize_texture", "1.0.0"
ROLES = canon_io.SRGB_ROLES + canon_io.LINEAR_ROLES + canon_io.DATA_ROLES
# (pattern on the file stem, role, normal convention or None): the public naming of each source, first match wins.
NAMING = {
    "ambientcg": [(r"_NormalGL$", "normal", "gl"), (r"_NormalDX$", "normal", "dx"), (r"_Color$", "basecolor", None), (r"_Roughness$", "roughness", None),
                  (r"_Metalness$", "metallic", None), (r"_AmbientOcclusion$", "ao", None), (r"_Displacement$", "displacement", None),
                  (r"_Opacity$", "opacity", None), (r"_Emission$", "emission", None)],
    "polyhaven": [(r"_nor_gl(_|$)", "normal", "gl"), (r"_nor_dx(_|$)", "normal", "dx"), (r"_diff(_|$)", "basecolor", None), (r"_rough(_|$)", "roughness", None),
                  (r"_metal(_|$)", "metallic", None), (r"_ao(_|$)", "ao", None), (r"_disp(_|$)", "displacement", None), (r"_arm(_|$)", "orm", None)],
    "lampway": [(r"(^|_)Normal_GL$", "normal", "gl"), (r"(^|_)Normal_DX$", "normal", "dx"), (r"(^|_)BaseColor$", "basecolor", None), (r"(^|_)ORM$", "orm", None),
                (r"(^|_)Roughness$", "roughness", None), (r"(^|_)Metallic$", "metallic", None), (r"_albedo$", "basecolor", None)],
}
SOURCES = tuple(NAMING) + ("tripo", "none")
GENERATOR = {"ambientcg": "cc0_ambientcg", "polyhaven": "cc0_polyhaven", "lampway": "lampway_tool"}   # tripo: studio or API cannot be told


def _from_naming(stem, source):
    for pat, role, conv in NAMING.get(source, ()):
        if re.search(pat, stem):
            return role, conv
    return None, None


def _image(input, root):
    img = bpy.data.images.get(input)
    if img is not None:
        return img
    p = Path(root) / input
    if not p.exists():
        raise C.FeatureError(f"{input} is neither an image nor a file under the project root")
    img = canon_io.load_image(str(p))
    img.name = p.name
    return img


def _file_sha(img):
    path = bpy.path.abspath(img.filepath) if img.filepath else ""
    if path and Path(path).exists():
        return canon_io.file_sha256(path), Path(path)
    if img.packed_file is not None:
        return hashlib.sha256(bytes(img.packed_file.data)).hexdigest(), None
    raise C.FeatureError(f"image {img.name} has no file and is not packed: save it first (its bytes are what the document hashes)")


_PNG_CHANNELS = {0: 1, 2: 3, 3: 3, 4: 2, 6: 4}                    # IHDR colour type -> channels (3: a palette of RGB)


def _format(img, path):
    """(channels, bits per channel) of the FILE: a PNG's IHDR exactly (Blender's ``channels`` is its buffer's - 4 for an RGB PNG);
    otherwise Blender's bits per pixel (8 / 24 / 32 at 8 bits, 96 / 128 float)."""
    if path is not None and path.suffix.lower() == ".png":
        head = path.read_bytes()[:26]
        if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            depth, ctype = head[24], head[25]
            if ctype not in _PNG_CHANNELS:
                raise C.FeatureError(f"{path.name}: PNG colour type {ctype} is not a known one")
            return _PNG_CHANNELS[ctype], (8 if ctype == 3 or depth <= 8 else 16)
    d = int(img.depth)
    per = 32 if img.is_float and d in (32, 96, 128) else 8
    ch = d // per
    if ch not in (1, 2, 3, 4) or d % per:
        raise C.FeatureError(f"image {img.name}: {d} bits per pixel is not 1-4 channels of {per} bits")
    return ch, per


def facts(img):
    """What a door re-measures on an image now: its colour space and the sha256 of its file."""
    out = {"colour_space": img.colorspace_settings.name}
    try:
        out["image_sha256"] = _file_sha(img)[0]
    except C.FeatureError:
        pass
    return out


def run(input, role="auto", normal_convention="auto", tiling_real_world_m=None, source_naming="none", root="."):
    """A refused FILE leaves no image behind (audit F5): an image this call loaded is removed when it refuses."""
    before = {i.as_pointer() for i in bpy.data.images}
    try:
        return _run(input, role, normal_convention, tiling_real_world_m, source_naming, root)
    except Exception:
        new = [i for i in bpy.data.images if i.as_pointer() not in before]
        if new:
            bpy.data.batch_remove(new)
        raise


def _run(input, role, normal_convention, tiling_real_world_m, source_naming, root):
    if source_naming not in SOURCES:
        raise C.FeatureError(f"source_naming {source_naming!r} is one of {', '.join(SOURCES)}")
    if role != "auto" and role not in ROLES:
        raise C.FeatureError(f"role {role!r} is not a texture role: one of {', '.join(ROLES)}")
    if normal_convention not in ("auto", "gl", "dx"):
        raise C.FeatureError("normal_convention is auto, gl or dx")
    img = _image(input, root)
    sha, path = _file_sha(img)
    stem = (path.stem if path else Path(img.name).stem)
    named_role, named_conv = _from_naming(stem, source_naming)
    if role == "auto":
        if named_role is None:
            why = "no naming table for that source" if source_naming in ("tripo", "none") else f"no {source_naming} pattern matches {stem!r}"
            raise C.FeatureError(f"role unknown for {img.name}: declare role=<{' | '.join(ROLES)}> ({why})")
        role, evidence_role = named_role, "source_naming"
    else:
        evidence_role = "declared"
    body = {"role": role, "colour_space": canon_io.colour_space(role)}
    if role == "normal":
        if normal_convention != "auto":
            body["normal"] = {"convention": normal_convention, "space": "tangent", "tangent_basis": "mikktspace", "convention_evidence": "declared"}
        elif named_conv is not None and named_role == "normal":
            body["normal"] = {"convention": named_conv, "space": "tangent", "tangent_basis": "mikktspace", "convention_evidence": "source_naming"}
        else:
            raise C.FeatureError(f"normal convention unknown: declare normal_convention=gl|dx (it is never assumed) for {img.name}")
    if role == "orm":
        body["packing"] = {"r": "ao", "g": "roughness", "b": "metallic"}
    w, h = (int(x) for x in img.size)
    ch, bits = _format(img, path)
    alpha = "none" if ch not in (2, 4) or img.alpha_mode in ("NONE", "CHANNEL_PACKED") else ("premultiplied" if img.alpha_mode == "PREMUL" else "straight")
    body.update(width=w, height=h, power_of_two=bool(w & (w - 1) == 0 and h & (h - 1) == 0), bit_depth=bits, channels=ch, alpha=alpha)
    if tiling_real_world_m is not None:
        body["tiling"] = {"real_world_m": [float(x) for x in tiling_real_world_m]}
    body["image_sha256"] = sha
    was = img.colorspace_settings.name
    img.colorspace_settings.name = body["colour_space"]
    raw_rec = json.loads(img["lw_raw"]) if "lw_raw" in img.keys() else {}
    container = (path.suffix.lstrip(".").lower() if path else raw_rec.get("container")) or "none"
    raw = {"sha256": sha, "container": container, "bytes": int(path.stat().st_size) if path else 0, "generator": {"source": GENERATOR.get(source_naming, "unknown")}}
    if path:
        try:
            raw["path_hint"] = str(path.resolve().relative_to(Path(root).resolve()))
        except ValueError:
            raw["path_hint"] = path.name
    canonical = CA.digest(json.dumps(body, sort_keys=True).encode())
    receipt = {"schema": "lampway.normalize-receipt/1", "tool": TOOL, "tool_version": TOOL_VERSION, "blender_version": bpy.app.version_string,
               "input": {"sha256": sha, "container": container}, "output": {"canonical_sha256": canonical, "asset_id": f"raw-{sha[:12]}"},
               "steps": [{"op": "role", "role": role, "evidence": evidence_role, "source_naming": source_naming},
                         {"op": "colour_space", "set": body["colour_space"], "was": was}], "refused": []}
    rbytes = json.dumps(receipt, sort_keys=True, indent=1).encode()
    I4 = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
    doc = {"schema": "lampway.canonical-asset", "schema_version": 1, "kind": "texture", "asset_id": f"raw-{sha[:12]}", "raw": raw,
           "conventions": {"frame": CA.FRAME, "up": "+Z", "front": "-Y", "wearer_left": "+X", "handedness": "right", "units": "m",
                           "source_frame": {"name": "lampway_body", "up": "+Z", "front": "-Y"}, "axis_map": [r[:3] for r in I4[:3]], "axis_map_det": 1,
                           "turn_deg": 0, "winding_reversed": False, "frame_decision": {"kind": "already_canonical", "evidence": {"method": "identity"}}},
           "transform": {"applied": True, "object_matrix": I4}, "scale": {"state": "unknown", "decision": "none", "factor_applied": 1},
           "normalized_by": {"tool": TOOL, "tool_version": TOOL_VERSION, "blender_version": bpy.app.version_string},
           "canonical_sha256": canonical, "receipt_sha256": hashlib.sha256(rbytes).hexdigest(), "body": body}
    errs = CA.validate(doc)
    if errs:
        raise C.FeatureError(f"the canonical document does not validate (a normalizer bug): {errs[:3]}")
    img["lw_canon"] = json.dumps(doc, sort_keys=True)
    if "lw_raw" in img.keys():
        del img["lw_raw"]
    rel = Path("canon") / "receipts" / f"{canonical[:12]}.json"
    (Path(root) / rel).parent.mkdir(parents=True, exist_ok=True)
    (Path(root) / rel).write_bytes(rbytes)
    return {"image": img.name, "document": doc, "receipt_path": str(rel)}
