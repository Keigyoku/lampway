# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon_door: what a tool declares it consumes and produces, and the check at its door (specs/canon/normalization DOOR.md 2).

Declarations (``api.tool(consumes=..., produces=...)``, ``runner.Tool(consumes=...)``):
* ``{"<arg>": Need(...)}`` - the argument must name a canonical datablock (or a file with its ``.canon.json`` / an npz with its
  ``canon`` header) satisfying the Need; a raw, unstamped or changed asset is refused with "normalize first";
* ``NONE("why")`` - the tool reads no asset (the reason is mandatory text);
* ``LEGACY("issue")`` - during migration (decision D7, the ratchet): logged and let through. The count of ``LEGACY(`` calls in
  the tree is committed in ``canon_legacy_count.txt`` and may only fall (tests/lampway_tools/test_canon_doors.py).
* produces: ``Inherit(src, remeasure=...)``, ``Fresh(kind)``, ``Raw()`` (the stamping of outputs lands with the tools that
  produce canonical datablocks)."""

import json
import os
from dataclasses import dataclass, field

from . import canon_asset as CA
from .canon_asset import Need  # noqa: F401  (re-exported for the decorator's users)


class Declared:
    """Base of the non-Need declarations."""


@dataclass(frozen=True)
class NONE(Declared):
    why: str

    def __post_init__(self):
        if not isinstance(self.why, str) or len(self.why.strip()) < 3:
            raise TypeError("NONE(why): say why this tool reads no asset")


@dataclass(frozen=True)
class LEGACY(Declared):
    issue: str

    def __post_init__(self):
        if not isinstance(self.issue, str) or not self.issue.strip():
            raise TypeError("LEGACY(issue): name the migration issue or group")


@dataclass(frozen=True)
class Inherit:
    src: str
    remeasure: tuple = ()


@dataclass(frozen=True)
class Fresh:
    kind: str


@dataclass(frozen=True)
class Raw:
    note: str = field(default="")


def validate_declaration(consumes):
    """Raise TypeError unless ``consumes`` is NONE(...), LEGACY(...) or {arg: Need}."""
    if isinstance(consumes, (NONE, LEGACY)):
        return
    if isinstance(consumes, dict) and consumes and all(isinstance(k, str) and isinstance(v, CA.Need) for k, v in consumes.items()):
        return
    raise TypeError("@tool needs consumes=: declare what this tool reads ({arg: Need(...)}), or NONE('why') if it reads no asset")


def _doc_of_datablock(name):
    try:
        import bpy
    except ImportError:                                            # outside Blender only paths resolve
        return None, None, "missing"
    for coll in (bpy.data.objects, bpy.data.armatures, bpy.data.images, bpy.data.materials, bpy.data.actions):
        db = coll.get(name) if isinstance(name, str) else None
        if db is not None:
            if "lw_canon" in db:
                return db, json.loads(db["lw_canon"]), None
            return db, None, ("raw" if "lw_raw" in db else "unstamped")
    return None, None, "missing"


def _doc_of_path(path):
    side = str(path) + ".canon.json"
    if os.path.exists(side):
        return json.loads(open(side).read()), None
    if str(path).endswith(".npz") and os.path.exists(path):
        from . import canon_io
        canon = canon_io.read_npz(path)[2]
        return (canon, None) if canon else (None, "raw")
    return None, "unstamped"


def first_bad(arg, value, need):
    """(label, element, reasons) of the first element of a LIST argument that fails its Need (label ``arg[i]``), or None."""
    for i, elem in enumerate(value):
        reasons = unmet(f"{arg}[{i}]", elem, need)
        if reasons:
            return f"{arg}[{i}]", elem, reasons
    return None


def unmet(arg, value, need):
    """[str] for one argument: empty when the door opens; else each reason, the first naming raw / unstamped / changed. A list or
    tuple passes only when every element does (the reasons are the first failing element's, named ``arg[i]``)."""
    if need.accept_raw:
        return []
    if isinstance(value, (list, tuple)):
        bad = first_bad(arg, value, need)
        return bad[2] if bad else []
    db, doc, why = _doc_of_datablock(value)                  # a datablock by that name first: images are named "x.png" (the tools read it)
    if why == "missing" and isinstance(value, str) and (os.sep in value or value.endswith((".npz", ".glb", ".fbx", ".obj", ".blend", ".png", ".exr"))):
        doc, why = _doc_of_path(value)
    if doc is None:
        return [{"raw": f"{arg} {value!r} is a RAW import (lw_raw), not canonical",
                 "unstamped": f"{arg} {value!r} carries no canonical stamp (lw_canon)",
                 "missing": f"{arg} {value!r} names no datablock"}.get(why, f"{arg} {value!r} is not canonical")]
    out = CA.validate(doc)
    if db is not None and getattr(db, "type", None) == "MESH":
        from . import canon_io
        out += CA.check(doc, canon_io.facts(db))
    elif db is not None and doc.get("kind") == "texture" and hasattr(db, "colorspace_settings"):
        from .features import normalize_texture as NT
        out += CA.check(doc, NT.facts(db))
    out += CA.satisfies(doc, need)
    return out


def _skinned(name):
    try:
        import bpy
    except ImportError:
        return False
    ob = bpy.data.objects.get(name) if isinstance(name, str) else None
    return bool(ob is not None and ob.type == "MESH" and any(m.type == "ARMATURE" for m in ob.modifiers))


def refusal(arg, value, reasons, need):
    if isinstance(value, (list, tuple)):
        arg, value, reasons = first_bad(arg, value, need) or (arg, value, reasons)
    kind = need.kind[0] if need.kind else "mesh"
    if kind == "mesh" and _skinned(value):
        kind = "rigged_mesh"                                       # lampway_normalize_mesh refuses a skinned mesh: name the right normalizer
    helps = [f"lampway_normalize_{'rigged' if kind == 'rigged_mesh' else kind} input={value}"
             + (" (not built yet: canon R1/R3, lane orphans)" if kind == "rigged_mesh" else "")]
    if any(r.startswith("scale is ") for r in reasons):                # the scale STATE (satisfies), not an object scaled in the scene
        helps.append("real scale comes from lampway_fit_place (armour) or lampway_scale_to_measure")
    return {"ok": False, "error": f"normalize first: {arg} {value!r} is not canonical: " + "; ".join(reasons), "help": helps}
