# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The source-part check, the detached-glove guard (canon 03 G, canon 09 G): a piece about to be fitted must be ONE similarity of
its source per rigid group (residual < SOURCE_CHECK_MAX_MM), checked part by part. On 2026-09-29 a glove moved 22 deg off its
bracer by an experiment became every later stage's input (memory gauntlet-glove-detached).

The piece and its source share vertex identity (same count and order: the source before any weld or fit). Parts are the source's
vertex groups (else the piece's); ``rigid_groups`` lists the parts that must move as one (default: every part, one shell). For a
group that fails, each part's own similarity is fitted and its rotation RELATIVE to the group's first part is reported, so the
refusal names the part that moved and by how much."""

import numpy as np

from . import common as C
from .. import canon_geom as G

SOURCE_CHECK_MAX_MM = 0.5       # canon 03 G: "one similarity per rigid group, residual < 0.5 mm"


def _P(ob):
    mw = np.array(ob.matrix_world)
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def _parts(ob):
    out = {}
    for g in ob.vertex_groups:
        idx = [v.index for v in ob.data.vertices if any(x.group == g.index and x.weight > 0 for x in v.groups)]
        if idx:
            out[g.name] = np.array(idx, int)
    return out


def run(piece, source, rigid_groups=None):
    ob, src = C.need_object(piece), C.need_object(source)
    if len(ob.data.vertices) != len(src.data.vertices):
        raise C.FeatureError(f"{piece} has {len(ob.data.vertices)} vertices and its source {source} {len(src.data.vertices)}: the source is the same "
                             "mesh before any weld or fit (vertex identity is how the parts are compared)")
    parts = _parts(src) or _parts(ob) or {"whole": np.arange(len(ob.data.vertices))}
    groups = [list(g) for g in rigid_groups] if rigid_groups else [sorted(parts)]
    unknown = sorted({p for g in groups for p in g} - set(parts))
    if unknown:
        raise C.FeatureError(f"rigid_groups name parts the source does not have: {unknown}; its parts are {sorted(parts)}")
    S, P = _P(src), _P(ob)
    rows, failed = [], []
    for g in groups:
        idx = np.unique(np.concatenate([parts[p] for p in g]))
        fit = G.similarity_fit(S[idx], P[idx])
        row = {"parts": list(g), "residual_max_mm": round(fit["max"] * 1000, 6), "residual_rms_mm": round(fit["rms"] * 1000, 6),
               "scale": round(float(fit["s"]), 9), "pass": bool(fit["max"] * 1000 < SOURCE_CHECK_MAX_MM)}
        if not row["pass"]:
            own = {p: G.similarity_fit(S[parts[p]], P[parts[p]]) for p in g if len(parts[p]) >= 3}
            ref = own.get(g[0])
            row["relative_deg"] = {p: (0.0 if p == g[0] else round(float(G.rotation_angle_axis(f["R"] @ ref["R"].T)[0]), 4))
                                   for p, f in own.items()} if ref is not None else {}
            failed.append(row)
        rows.append(row)
    reason = None
    if failed:
        worst = max(failed, key=lambda r: r["residual_max_mm"])
        moved = sorted(((d, p) for p, d in worst.get("relative_deg", {}).items() if d), reverse=True)
        reason = (f"the rigid group {worst['parts']} is not one similarity of its source: residual {worst['residual_max_mm']:.3f} mm (limit "
                  f"{SOURCE_CHECK_MAX_MM})" + (f"; {moved[0][1]} is turned {moved[0][0]:.1f} deg off {worst['parts'][0]}" if moved else "")
                  + " - go back to the step that produced this piece (canon 03 INV-03.13), never fit it as it is")
    return {"pass": not failed, "groups": rows, "limit_mm": SOURCE_CHECK_MAX_MM, "reason": reason}
