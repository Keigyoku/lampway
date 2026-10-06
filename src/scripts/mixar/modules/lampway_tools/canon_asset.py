# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon_asset: the typed canonical asset `lampway.canonical-asset/1` (specs/canon/normalization SCHEMA.md, contract canon_asset.md).

A canonical asset is the one form every Lampway tool may assume: metres, right-handed, +Z up, the body faces -Y, the wearer's left
+X (canon 01's body frame, `lampway.body/1`); transforms applied (or the reason recorded); a scale STATE with its evidence (real |
generator_normalised | unknown - never a guess); bones head -> next joint; weld recorded; colour space bound to each texture's role;
the raw source's sha256. Only a `lampway_normalize_<kind>` tool writes one; every door reads it.

Pure (no bpy). The JSON Schema ships beside this module (`canon/canonical-asset.schema.json`, the source of truth); `schema_errors`
runs the vendored validator (Blender's python has no jsonschema); `validate` adds the invariants JSON Schema cannot state; `check`
compares a document with facts measured on its datablock (canon_io.facts); `satisfies` answers a tool's door."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .canon.minischema import Validator

SCHEMA_ID = "lampway.canonical-asset/1"
SCHEMA_VERSION = 1
FRAME = "lampway.body/1"
KINDS = ("mesh", "rigged_mesh", "skeleton", "animation_clip", "texture", "material", "part", "set")
SCALE_STATES = ("real", "generator_normalised", "unknown")
ANY_SCALE = SCALE_STATES
TOL_M = 1e-6

# The normalization decisions (specs/canon/normalization REPORT.md D1-D10), ruled by the captain 2026-10-06 "as recommended" except
# D4. A value nobody gave is None, never invented; `needs_decision` rides on every receipt that uses it.
SETTINGS = {
    "frame_layers": {"value": "working lampway.body/1; canon 22 interchange by adapters only", "decision": "D1", "ruled": "2026-10-06"},
    "container": {"value": ".blend + .canon.json", "decision": "D2", "ruled": "2026-10-06"},
    "real_scale_at": {"value": "intake", "decision": "D3", "ruled": "2026-10-06"},
    "pair_scale_group": {"value": None, "decision": "D4", "needs_decision": True, "why": "one scale per left/right pair or per side: pending a measurement"},
    "weld_m": {"value": 1e-5, "decision": "D5", "ruled": "2026-10-06", "why": "generated meshes only; never an authored rig (canon 01 D.2)"},
    "weld_guard_fraction": {"value": 0.05, "decision": "D5", "ruled": "2026-10-06", "why": "a weld merging more than this share of the vertices is refused"},
    "facing": {"value": "per-piece declared turn, checked against the plates, refused below a margin", "decision": "D6", "ruled": "2026-10-06"},
    "facing_margin": {"value": None, "decision": "D6", "needs_decision": True,
                      "why": "the ruling names a refusal margin but no number; plate registration refuses until it is set"},
    "rollout": {"value": "LEGACY ratchet", "decision": "D7", "ruled": "2026-10-06"},
    "thresholds": {"value": "re-measure at real scale", "decision": "D8", "ruled": "2026-10-06"},
    "stamp_integrity": {"value": "hash-bound", "decision": "D9", "ruled": "2026-10-06"},
    "pivot_rule": {"value": "bbox_bottom_centre", "decision": "D10", "ruled": "2026-10-06"},
}

_SCHEMA = None


def load_schema():
    """The JSON Schema dict (version-pinned to SCHEMA_ID)."""
    global _SCHEMA
    if _SCHEMA is None:
        s = json.loads((Path(__file__).parent / "canon" / "canonical-asset.schema.json").read_text())
        if s.get("$id") != SCHEMA_ID:
            raise ValueError(f"the shipped schema is {s.get('$id')!r}, this module reads {SCHEMA_ID!r}")
        _SCHEMA = s
    return _SCHEMA


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def schema_errors(doc):
    """JSON Schema errors only (the vendored validator)."""
    return Validator(load_schema()).errors(doc)


def _proper(R):
    R = np.asarray(R, float)
    return R.shape == (3, 3) and abs(np.linalg.det(R) - 1) < 1e-6 and np.allclose(R.T @ R, np.eye(3), atol=1e-6)


def validate(doc):
    """[str]: the refusals of contract section 8, the JSON Schema errors, then the (code) invariants needing no datablock."""
    if not isinstance(doc, dict):
        return ["a canonical document is a JSON object"]
    v = doc.get("schema_version")
    if isinstance(v, int) and not isinstance(v, bool) and v > SCHEMA_VERSION:
        return [f"document version {v} is newer than this Lampway: update"]
    frame = (doc.get("conventions") or {}).get("frame")
    if frame is not None and frame != FRAME:
        return [f"not a working-canonical document (frame {frame!r}; interchange documents are adapter output)"]
    errs = schema_errors(doc)
    if errs:
        return errs
    out = []
    c = doc["conventions"]
    det = float(np.linalg.det(np.asarray(c["axis_map"], float)))
    if abs(det - c["axis_map_det"]) > 1e-6:
        out.append(f"conventions.axis_map has determinant {det:+.3g}, the document declares {c['axis_map_det']}")
    body, kind = doc["body"], doc["kind"]
    if kind == "skeleton":
        out += _skeleton_errors(body)
    if kind in ("mesh", "part") or kind == "rigged_mesh":
        mesh = body.get("mesh", body) if kind == "rigged_mesh" else body
        for uv in mesh.get("uv_sets", []) if isinstance(mesh, dict) else []:
            if "texel_density" in uv and doc["scale"]["state"] != "real":
                out.append(f"uv_sets.{uv.get('name')}: texel density is measured in world metres, only at real scale")
    return out


def _skeleton_errors(body):
    out, seen = [], set()
    for b in body["bones"]:
        n = b["name"]
        if b["parent"] is not None and b["parent"] not in seen:
            out.append(f"bone {n} comes before its parent {b['parent']}")
        seen.add(n)
        if abs(float(np.linalg.norm(b["along"])) - 1) > TOL_M:
            out.append(f"bone {n}: along is not a unit vector (|along| = {np.linalg.norm(b['along']):.6g})")
        R = np.asarray(b["frame"], float)
        if not _proper(R):
            out.append(f"bone {n}: frame is not a proper rotation (det {np.linalg.det(R):+.3g})")
    return out


def check(doc, facts):
    """[str]: the document against facts measured on its datablock now (canon_io.facts): the object matrix applied, the scene in
    metres, the bounds, the geometry hash (a mesh changed since normalization reads as a different hash)."""
    out = []
    if "object_matrix" in facts and doc["transform"]["applied"] and not np.allclose(facts["object_matrix"], np.eye(4), atol=TOL_M):
        out.append("the object matrix is not the identity although the document says the transform was applied")
    if "scene_scale_length" in facts and abs(float(facts["scene_scale_length"]) - 1.0) > 1e-9:
        out.append(f"the scene's unit scale_length is {facts['scene_scale_length']}, not 1 (metres)")
    body = doc["body"].get("mesh", doc["body"]) if doc["kind"] == "rigged_mesh" else doc["body"]
    for k in ("bbox_min_m", "bbox_max_m"):
        if k in facts and k in body and not np.allclose(facts[k], body[k], atol=TOL_M):
            out.append(f"{k} measured {np.round(facts[k], 6).tolist()} vs the document's {body[k]}")
    if "geometry_sha256" in facts and "geometry_sha256" in body and facts["geometry_sha256"] != body["geometry_sha256"]:
        out.append("geometry_sha256 differs: the mesh changed since it was normalized (normalize it again)")
    if "colour_space" in facts and doc["kind"] == "texture" and facts["colour_space"] != doc["body"].get("colour_space"):
        out.append(f"colour space {facts['colour_space']!r} vs the document's {doc['body'].get('colour_space')!r}")
    if "image_sha256" in facts and doc["kind"] == "texture" and facts["image_sha256"] != doc["body"].get("image_sha256"):
        out.append("image_sha256 differs: the image file changed since it was normalized (normalize it again)")
    return out


@dataclass(frozen=True)
class Need:
    """What a tool's door asks of one argument."""
    kind: tuple = ("mesh",)
    scale: tuple = ("real",)
    convention: str = None
    welded: bool = None
    roles: tuple = ()
    accept_raw: bool = False


def satisfies(doc, need):
    """[str]: each unmet requirement, named; empty = the door opens."""
    out = []
    kind = doc.get("kind")
    if kind not in need.kind:
        out.append(f"kind {kind!r} is not one of {list(need.kind)}")
    state = (doc.get("scale") or {}).get("state")
    if state not in need.scale and kind != "texture":                    # an image has no world size (a tileable states its tiling)
        out.append(f"scale is {state!r}, this tool needs {list(need.scale)} (real scale comes from fit_place or scale_to_measure)")
    body = doc.get("body") or {}
    if need.convention is not None:
        conv = body.get("convention")
        if conv != need.convention:
            out.append(f"skeleton convention {conv!r}, this tool needs {need.convention!r}")
    if need.welded:
        mesh = body.get("mesh", body) if kind == "rigged_mesh" else body
        if not ((mesh.get("topology") or {}).get("welded")):
            out.append("the mesh is not welded (seam-split vertices): normalize a generated mesh with its weld")
    if need.roles and body.get("role") not in need.roles:
        out.append(f"texture role {body.get('role')!r} is not one of {list(need.roles)}")
    return out
