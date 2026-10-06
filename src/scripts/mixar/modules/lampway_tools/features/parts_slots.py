# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""parts_material_slots: the PIECE_PIPELINE known gap 'one material per piece; the parts are not material slots' (no contract exists; STATUS O32).

On a COPY ``<object>_slots`` the piece's one material becomes one slot per part (``by`` part) or per material class (``by`` class, the recipe's ``class``):
each slot is a copy of the piece's material named ``<material>_<part|class>``, sharing its images (nothing is re-baked: the texels stay where they are),
and every face takes the slot of its part from ``owner`` (.npy, one part index per polygon) or the int face attribute ``part``. The engine then sees
the parts as material slots (a per-part material instance, the class's physical values) without a second texture."""

import json
from pathlib import Path

import numpy as np

from . import common as C

BYS = ("part", "class")


def run(object, recipe, owner="", by="part", name=""):
    if by not in BYS:
        raise C.FeatureError("by is part | class (one slot per recipe part, or per material class)")
    ob = C.need_object(object)
    if not recipe or not Path(recipe).exists():
        raise FileNotFoundError(f"recipe {recipe} not found (the parts json)")
    rec = json.loads(Path(recipe).read_text(encoding="utf-8"))
    parts = list(rec.get("parts") or {})
    if not parts:
        raise C.FeatureError("the recipe has no parts")
    n = len(ob.data.polygons)
    if owner:
        own = np.load(owner).reshape(-1)
    else:
        attr = ob.data.attributes.get("part")
        if attr is None or attr.domain != "FACE":
            raise C.FeatureError(f"{ob.name} carries no part per face: give owner (a .npy, one part index per polygon) or the int face attribute 'part' (segment_mesh / transfer_parts)")
        own = np.empty(n, dtype=np.int64)
        attr.data.foreach_get("value", own)
    if len(own) != n:
        raise C.FeatureError(f"the owner map has {len(own)} entries for {n} polygons")
    bad = sorted({int(k) for k in own if not 0 <= int(k) < len(parts)})
    if bad:
        raise C.FeatureError(f"owner indices {bad[:5]} name no recipe part (0..{len(parts) - 1})")
    if not ob.data.materials or ob.data.materials[0] is None:
        raise C.FeatureError(f"{ob.name} has no material to split into slots")
    base = ob.data.materials[0]
    keys = [parts[int(k)] if by == "part" else str((rec["parts"][parts[int(k)]] or {}).get("class") or "unclassed") for k in own]
    order = list(dict.fromkeys(parts if by == "part" else [str((rec["parts"][p] or {}).get("class") or "unclassed") for p in parts]))
    used = [k for k in order if k in set(keys)]
    new = C.duplicate(ob, "_slots")
    if name:
        new.name = name
        new.data.name = name
    me = new.data
    me.materials.clear()
    mats = {}
    for k in used:
        m = base.copy()
        m.name = f"{base.name}_{k}"
        m["lw_slot"] = json.dumps({"by": by, "key": k, "source_material": base.name})
        me.materials.append(m)
        mats[k] = len(me.materials) - 1
    me.polygons.foreach_set("material_index", np.array([mats[k] for k in keys], dtype=np.int32))
    me.update()
    return {"object": new.name, "source": ob.name, "by": by, "source_material": base.name,
            "slots": [{"index": mats[k], "material": me.materials[mats[k]].name, "key": k, "faces": int(sum(1 for x in keys if x == k))} for k in used],
            "note": "every slot shares the source material's images; an engine material instance per slot is the user's to wire"}
