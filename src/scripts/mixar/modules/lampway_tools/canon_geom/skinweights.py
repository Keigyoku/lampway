# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 07: skin-weight primitives (restrict / remap, the welded fill, dress, falloff, the seam band).

* ``remap_table`` / ``remap_rows``: a weight on a bone the profile does not allow moves to its nearest ALLOWED ANCESTOR,
  else to the named fallback; a bone with neither is refused at once; a vertex left with no weight is REFUSED, never
  renormalised silently (``ZeroWeightError``). Ported from Titan tools/weight_profile.py.
* ``inpaint_harmonic``: unmatched rows take the average of their neighbours until the field settles, matched rows fixed -
  over WELDED vertices when ``keys`` (identity.weld_keys) is given, so a seam-split island is reached through its duplicates
  and both copies carry bit-identical rows (golden C04). Weld only generated armour (canon 01 D.2).
* ``dress``: CC5's Dress template by rule (pelvis alone above the hips, the thighs to ``follow`` at the hem by smoothstep).
* ``falloff_weights``: continuous in position - every bone within ``margin`` of the nearest takes (1 - excess/margin)^2.
* ``band_weights``: the seam band - the blend across a cut as a function of POSITION alone (smoothstep over ``width``).
* ``rigid_blend``: a hard part fused to cloth/leather (B.5) - each rigid part's rigidity smoothstep(1 - d/fade) takes its bone,
  the field keeps what remains; the STRICT form (Titan hand_pose.rigid_blend_strict): two different anchors at one point refuse."""

import math

import fnmatch

import numpy as np


class ZeroWeightError(ValueError):
    """Vertices left with no weight; ``vertices`` lists them (up to ``limit``), ``total`` counts them."""

    def __init__(self, vertices, total, where=""):
        self.vertices, self.total = vertices, total
        super().__init__(f"{total} vertices{(' of ' + where) if where else ''} have zero weight after restriction (e.g. {vertices[:10]}): "
                         "no allowed body surface reaches them; widen the part's bones, add a fallback bone, or move the part onto the body")


def _expand(parents, patterns):
    out = []
    for pat in patterns:
        hit = sorted(n for n in parents if fnmatch.fnmatchcase(n, pat))
        if not hit:
            raise ValueError(f"bone pattern {pat!r} matches no bone of the skeleton")
        out += [n for n in hit if n not in out]
    return out


def remap_table(parents, allowed, fallback=None):
    """{bone: the bone its weight lands on}: itself when allowed (names or fnmatch patterns over ``parents``, bone -> parent
    or None), else its nearest allowed ancestor, else ``fallback`` (which must be allowed); a bone with none is refused."""
    keep = set(_expand(parents, allowed))
    if fallback is not None and fallback not in keep:
        raise ValueError(f"fallback {fallback!r} is not among the allowed bones")
    table = {}
    for n in parents:
        b, seen = n, set()
        while b is not None and b not in keep:
            if b in seen:
                raise ValueError(f"the skeleton's parents loop at {b!r}")
            seen.add(b)
            b = parents.get(b)
        if b is None:
            if fallback is None:
                raise ValueError(f"bone {n!r} has no allowed ancestor and there is no fallback")
            b = fallback
        table[n] = b
    return table


def remap_rows(W, names, table, where="", limit=50):
    """(W' (n, k), targets [k]): each row of W (columns = ``names``) moved through ``table``, summed per target bone and
    normalised; a row with no weight raises ZeroWeightError naming its vertices."""
    W = np.asarray(W, float)
    targets = sorted({table[n] for n in names})
    col = {t: i for i, t in enumerate(targets)}
    out = np.zeros((len(W), len(targets)))
    for j, n in enumerate(names):
        out[:, col[table[n]]] += W[:, j]
    s = out.sum(1)
    bad = np.flatnonzero(s <= 1e-12)
    if len(bad):
        raise ZeroWeightError([int(i) for i in bad[:limit]], int(len(bad)), where)
    return out / s[:, None], targets


def inpaint_harmonic(n, edges, matched, W, keys=None, iters=4000, tol=1e-9):
    """(n, k): the rows of ``W`` with every unmatched row replaced by the harmonic fill of its neighbours (matched rows
    fixed). With ``keys`` the fill runs over the welded vertices (rows of one key are one unknown) and scatters back, so
    duplicates are bit-identical; a welded vertex is matched when any of its copies is (the first matched copy's row).
    Filled rows are clamped at 0 and renormalised to sum 1 (skin weights); a row nothing reaches stays 0."""
    matched = np.asarray(matched, bool)
    W = np.asarray(W, float)
    idx = np.arange(n) if keys is None else np.unique(np.asarray(keys), return_inverse=True)[1].reshape(-1)
    m = int(idx.max()) + 1 if n else 0
    fixed = np.zeros(m, bool)
    Wc = np.zeros((m, W.shape[1]))
    for i in range(n):
        if matched[i] and not fixed[idx[i]]:
            fixed[idx[i]] = True
            Wc[idx[i]] = W[i]
    nb = [set() for _ in range(m)]
    for a, b in edges:
        a, b = idx[a], idx[b]
        if a != b:
            nb[a].add(b)
            nb[b].add(a)
    free = [k for k in range(m) if not fixed[k] and nb[k]]
    lists = {k: np.fromiter(nb[k], int) for k in free}
    for _ in range(iters):
        new = Wc.copy()
        for k in free:
            new[k] = Wc[lists[k]].mean(0)
        delta = float(np.abs(new - Wc).max()) if free else 0.0
        Wc = new
        if delta < tol:
            break
    Wc = np.clip(Wc, 0.0, None)                                       # canon 07 B.3: clamp >= 0, renormalise
    s = Wc.sum(1)
    norm = ~fixed & (s > 1e-12)
    Wc[norm] /= s[norm, None]
    return Wc[idx]


def dress(points, top, hem, left_x, right_x, follow, names):
    """[{bone: weight}] for points (x, y, z), z up, x across: the thighs' share f = follow * smoothstep((top - z)/(top - hem)),
    split between left (at ``left_x``) and right (at ``right_x``) by the point's place between them; the pelvis keeps the
    rest. ``names`` = (pelvis, left thigh, right thigh)."""
    if top <= hem:
        raise ValueError(f"the top {top!r} must be above the hem {hem!r}")
    if not 0.0 <= follow <= 1.0:
        raise ValueError(f"follow {follow!r} is outside 0..1")
    if left_x == right_x:
        raise ValueError("the thighs must lie apart across the body")
    pelvis, left, right = names
    out = []
    for x, _y, z in points:
        u = min(1.0, max(0.0, (top - z) / (top - hem)))
        f = follow * u * u * (3.0 - 2.0 * u)
        s = min(1.0, max(0.0, (x - right_x) / (left_x - right_x)))
        w = {pelvis: 1.0 - f, left: f * s, right: f * (1.0 - s)}
        out.append({k: v for k, v in w.items() if v > 0.0})
    return out


def _seg_dist(p, a, b):
    p, a, b = (np.asarray(x, float) for x in (p, a, b))
    ab = b - a
    t = 0.0 if float(ab @ ab) == 0 else min(1.0, max(0.0, float((p - a) @ ab) / float(ab @ ab)))
    return float(np.linalg.norm(p - (a + t * ab)))


def falloff_weights(point, segments, margin, power=2):
    """{bone: weight}, continuous in position: every bone whose segment (head, end) lies within ``margin`` of the nearest
    bone's distance takes (1 - excess / margin) ** power, normalised (Titan hand_pose.falloff_weights)."""
    d = {b: _seg_dist(point, *segments[b]) for b in segments}
    lo = min(d.values())
    w = {b: (1.0 - (x - lo) / margin) ** power for b, x in d.items() if x - lo < margin}
    s = sum(w.values())
    return {b: x / s for b, x in w.items()}


def band_weights(V, cut_point, axis, width):
    """(n, 2) [behind, ahead]: the seam band across a cut through ``cut_point`` square to ``axis`` - the share ahead of the
    cut is smoothstep((s + width/2) / width), s the signed distance along the axis; a function of position alone."""
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    s = (np.asarray(V, float) - np.asarray(cut_point, float)) @ a
    u = np.clip((s + width / 2) / width, 0, 1)
    ahead = u * u * (3 - 2 * u)
    return np.stack([1 - ahead, ahead], 1)


def rigid_blend(field, near, fade):
    """{bone: weight}: canon 07 B.5, ported from Titan hand_pose.rigid_blend_strict. ``near`` = {bone: distance to the nearest
    rigid part riding it}; each part's rigidity r = smoothstep(1 - d / fade); a bone's mass is r_b * prod(1 - r_other), the field's
    prod(1 - r_all), normalised. Exactly on a part (and at its seam, d = 0) only that part's bone survives; past ``fade``, the field.
    Two different bones anchored at one point (r = 1) are refused, never deformed both."""
    if not math.isfinite(fade) or fade <= 0:
        raise ValueError("rigidity fade must be positive and finite")
    if any(not math.isfinite(x) or x < 0 for x in field.values()):
        raise ValueError("field weights must be finite and nonnegative")
    r = {}
    for bone, distance in sorted(near.items()):
        if not math.isfinite(distance) or distance < 0:
            raise ValueError("rigid part distances must be finite and nonnegative")
        x = min(1.0, max(0.0, 1.0 - distance / fade))
        value = x * x * (3.0 - 2.0 * x)
        if value > 0:
            r[bone] = value
    anchors = [bone for bone, value in r.items() if value == 1.0]
    if len(anchors) > 1:
        raise ValueError("conflicting rigid anchors: " + ", ".join(anchors))
    if anchors:
        return {anchors[0]: 1.0}
    field_mass = math.prod(1.0 - value for value in r.values())
    w = {bone: value * math.prod(1.0 - other for name, other in r.items() if name != bone) for bone, value in r.items()}
    if field_mass:
        total_field = sum(field.values())
        if total_field <= 0:
            raise ValueError("a point off every rigid part has no field weight")
        for bone, value in field.items():
            w[bone] = w.get(bone, 0.0) + field_mass * value / total_field
    total = sum(w.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("rigidity blend has no finite positive mass")
    return {bone: value / total for bone, value in sorted(w.items()) if value > 0}
