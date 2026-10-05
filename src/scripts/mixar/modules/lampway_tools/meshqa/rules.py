# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh QA proposal rules: proven code first, the model second.

Pure Python over the typed descriptors ``candidates.analyse`` writes (no bpy), so the rules are testable and a reason can always
name the rule that produced it. Each candidate is DECIDED by a rule or left AMBIGUOUS for the model slot, which then sees
``compact`` descriptors (never ``segments_m``) in small batches.

  float           loose_shell, nothing within ``float_band`` x float_mm of it (or nothing at all)   -> delete
  see_through     open_loop whose behind-ray hits nothing                                          -> hole
  rim             open_loop with a surface behind it, front-facing, not large                       -> keep
  float_threshold loose_shell within the band above the float threshold                             -> ambiguous
  backfacing_hit  open_loop whose behind-ray hits the BACK of a surface (an opening into a hollow)  -> ambiguous
  large_rim       open_loop with a surface behind it and a perimeter of ``large_rim_m`` or more     -> ambiguous
  flood_guard     more see-through loops than ``flood_fraction`` of all loops: the largest stay hole,
                  the rest are ambiguous (Tripo smart meshes are genuinely many open shells; the Boots
                  original has 8,203 boundary edges, mostly plate rims)

Measured 2026-10-05 on the captain's pieces (the rule script this replaces): Waist1 12 delete / 4 hole / 85 keep; Helmet1 11 / 0 / 111;
Boots1 0 / 0 / 76.
"""

import math
from dataclasses import dataclass


@dataclass
class Params:
    float_mm: float = 3.0
    float_band: float = 2.0            # a shell is DELETE only when its gap exceeds float_band x float_mm
    large_rim_m: float = 1.0
    flood_fraction: float = 0.15
    flood_min: int = 6


def classify(c: dict, params: Params = None):
    """(verdict or None, rule, reason). None = ambiguous: ``rule`` is then the code saying why."""
    params = params or Params()
    if c["kind"] == "loose_shell":
        gap, tris = c.get("gap_to_nearest_mm"), c.get("tris")
        if gap is None:
            return "delete", "float", f"rule float: nothing within reach of it; a {tris}-tri shell floats free"
        if gap > params.float_band * params.float_mm:
            return "delete", "float", f"rule float: floats {gap} mm from the nearest surface (float threshold {params.float_mm} mm), {tris} tris"
        return None, "float_threshold", f"rule float_threshold: {gap} mm from the surface is within {params.float_band}x the float threshold ({params.float_mm} mm)"
    behind = c.get("behind") or {}
    per = c.get("perimeter_m", 0.0)
    if behind.get("hit") == "nothing":
        return "hole", "see_through", f"rule see_through: a ray through it hits nothing behind; perimeter {per} m"
    if behind.get("backfacing"):
        return None, "backfacing_hit", f"rule backfacing_hit: the surface behind it faces away ({behind.get('depth_mm')} mm): an opening into a hollow?"
    if per >= params.large_rim_m:
        return None, "large_rim", f"rule large_rim: perimeter {per} m is large; surface {behind.get('depth_mm')} mm behind it"
    return "keep", "rim", f"rule rim: rim with surface {behind.get('depth_mm')} mm behind it (front-facing), perimeter {per} m"


def propose(candidates: list, params: Params = None) -> dict:
    """Rule verdicts for every candidate: ``verdicts`` [{id, kind, verdict, rule, reason}], ``ambiguous`` [ids], ``ambiguous_why`` {id: code}."""
    params = params or Params()
    rows = {}
    for c in candidates:
        verdict, rule, reason = classify(c, params)
        rows[c["id"]] = {"id": c["id"], "kind": c["kind"], "verdict": verdict, "rule": rule, "reason": reason,
                         "perimeter": c.get("perimeter_m", 0.0)}
    loops = sum(c["kind"] == "open_loop" for c in candidates)
    holes = sorted((r for r in rows.values() if r["verdict"] == "hole"), key=lambda r: -r["perimeter"])
    cap = max(params.flood_min, math.ceil(params.flood_fraction * loops))
    for r in holes[cap:]:
        r["verdict"], r["rule"] = None, "flood_guard"
        r["reason"] = (f"rule flood_guard: see-through, but only the {cap} largest see-through loops of {loops} are marked hole "
                       "(a plate rim often has nothing behind it)")
    verdicts = [{k: r[k] for k in ("id", "kind", "verdict", "rule", "reason")} for r in rows.values() if r["verdict"]]
    ambiguous = [r["id"] for r in rows.values() if not r["verdict"]]
    return {"verdicts": verdicts, "ambiguous": ambiguous, "ambiguous_why": {i: rows[i]["rule"] for i in ambiguous}}


def compact(c: dict) -> dict:
    """The descriptor a model may read: everything that decides the question, nothing that is geometry (no segments_m)."""
    out = {"id": c["id"], "kind": c["kind"], "side": c.get("side"), "extent_m": c.get("extent_m"),
           "seen_from_pct": {k: v for k, v in (c.get("seen_from_pct") or {}).items() if v}}
    if c["kind"] == "open_loop":
        parts = c.get("bordering_parts_pct") or {}
        out.update(edges=c.get("edges"), perimeter_m=c.get("perimeter_m"), behind=c.get("behind"),
                   bordering_parts_pct=dict(list(parts.items())[:3]), bordering_classes=c.get("bordering_classes"))
    else:
        parts = c.get("parts_pct") or {}
        out.update(tris=c.get("tris"), gap_to_nearest_mm=c.get("gap_to_nearest_mm"), parts_pct=dict(list(parts.items())[:3]))
    return out
