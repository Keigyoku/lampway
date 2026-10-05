#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/texlib/material_masks.py, sha256 292283d3c370) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): material masks for a parts set's shared UV atlas, from the V3 colour projected by relief_project.py
# (v3_colour_atlas.png + texel_face.npy) and each part's motion class (the captain's rulings: rigid-metal parts are metal;
# cloth-sim and skinned-flex parts are cloth). V3 has lighting painted in, so colour only CLASSIFIES, never becomes albedo.
#   metal part : gold (warm hue, light)  |  leather (red, saturated: the belt band, straps)  |  dark plate (the rest)
#   cloth part : gold embroidery (warm hue, light)  |  black linen (dark)  |  red cloth (the rest)
# Classification runs on the colour blurred by BLUR px, then each mask is cleaned by a MEDIAN px median filter; masks are
# exclusive and sum to 1 on covered texels. Writes mask_<name>.png (8-bit) and masks_preview.png and masks.json (shares).
# Shell vote (mesh_npz given): within a metal part, each connected shell (faces sharing welded vertices) of at most
# SHELL_MAX faces takes its majority of gold vs plate when that majority is at least SHELL_MAJ - V3's shadows and the side
# views' misregistration made gold ornaments patchy (the pauldron lion heads); bigger shells keep per-texel labels.
# Usage: material_masks.py <projection_out_dir> <owner.npy> <recipe.json> [out_dir] [mesh_npz]
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = _sys.argv[1:]
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['python scripts/texlib/material_masks.py <projection_out_dir> <owner.npy> <recipe.json> [out_dir] [mesh_npz]']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, "Material masks (gold, plate, red, linen, embroidery, leather) for a parts set's shared UV atlas from the projected V3 colour")
    else: print(f'error: {len(_A)} argument(s); at least 3 needed')
    _ax.helps(['python scripts/texlib/material_masks.py <projection_out_dir> <owner.npy> <recipe.json> [out_dir] [mesh_npz]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import json, os, sys, numpy as np
from PIL import Image
from scipy.ndimage import label as _cc_label
from scipy.ndimage import gaussian_filter, median_filter, binary_closing

BLUR, MEDIAN = 1.5, 5
SHELL_MAX, SHELL_MAJ = 300, 0.6
RELIEF_GOLD = 0.9       # robust spreads of the fine band: on plate, line work raised above this is gold (V3's gold is the raised detail)
RELIEF_GOLD_SMOOTH = 0.8   # px blur of the fine band before the threshold       # 6000 voted the whole cuirass to plate and erased V3's painted gold filigree (pass 6): only small shells (rivets, studs)
GOLD_HUE = (18, 62)        # degrees
GOLD_MIN_SAT, GOLD_MIN_VAL = 0.50, 0.25      # measured on V3 Chest1 Front: gold S 0.56-0.75, dark plate S 0.36-0.44 at the same hue
# Opt-in overrides (env, recorded in masks.json) from the r7 texture critique (tex_r7/critique_v2, 2026-10-04); defaults keep the
# approved r6 passes reproducible. MM_GOLD_MIN_SAT/VAL, MM_BLUR; MM_EMB_MIN_SAT/VAL + MM_EMB_MIN_BLOB (embroidery on cloth, drop
# components under N texels); MM_NO_VOTE_CLASSES (comma list of part classes excluded from the shell vote); MM_EXTRA_GOLD (comma list
# of parts made solid gold); MM_LINEN_FORCE=1 (linen parts: every non-gold texel is linen); MM_HEIGHT_GOLD_MM (when the fine band is
# absent: on plate, gold = colour-gold at S >= MM_HEIGHT_GOLD_SAT AND detail height above this many mm - raised line work).
# Round 2 (tex_r7/critique_v2/critique_v3.json): MM_CLOTH_MEDIAN (median px on cloth texels; the 5 px median erased 1-3 texel key
# strokes); MM_PART_GOLD_SV="part:S:V,..." (per-part colour-gold cut: the pauldron plates, so only border bands and rivets stay);
# MM_PLATE_GOLD_MIN_BLOB + MM_PLATE_GOLD_AND_MM (on plate parts a gold component survives only if it has this many texels AND
# touches a texel that is colour-gold AND raised at least this many mm - specks were the OR of two noisy tests) then
# MM_PLATE_GOLD_CLOSE px closing; MM_LEATHER_FORCE=1 (leather parts: every non-gold texel is leather - an assumption to confirm).
# Round 3 (critique_v4.json): MM_PART_GOLD_SV takes an optional 4th field, a per-part minimum gold blob (part:S:V:blob - the
# pauldron rim at 0.55:0.45:40, while 8 keeps the rivets elsewhere); MM_EMB_CLOSE (px closing of embroidery before the blob filter,
# so a band's fragments merge); MM_LINEN_FORCE=2 (linen parts forced LAST, over embroidery: V3's undersuit is black);
# MM_PART_HEIGHT_GOLD="part:mm:S,..." (inside that part, texels raised >= mm with S >= S are gold - the belt's domes).
# Round 4 (critique_v5b.json): MM_PART_GOLD_BLOB="glob:blob,..." (per-part minimum gold blob by part-name glob, e.g. cuirass_*:40 -
# the big plates' confetti dies while their stars and cross (>= 400 texels) survive; rivet-sized gold elsewhere keeps the global 8).
# MM_RIM_GOLD="part:mm,..." (needs mesh_npz with UV): texels of the part's main shell within mm of its OUTLINE are gold - V3's gold
# border band on the pauldron plates is ~11-15 mm wide and is not in the projected colour (V3 is 704 px; side views IoU 0.75-0.81),
# so it is drawn from geometry. Outline = edges of the part's faces with no face on the other side, or whose other face belongs to
# neither the part nor a part split from it (recipe 'from' starting '<part>:'). Each texel's 3D point comes from its UV barycentrics
# (the v axis orientation is picked by the inside test). A third field "part:mm:deg" switches the source to CREASE edges (dihedral
# above deg between the part's own faces): measured 2026-10-04, the pauldron's open edges are its underside and strap seams, while
# the visible border is the fold to the plate's thickness and the step of the raised band - both creases.
# Round 5 (critique_v7c.json): MM_RIM_CLOSE (px closing of each rim mask inside its part: the step's flat top read as a brown
# channel between two gold lines); MM_STUD_GOLD="glob|glob...:max_tris:max_mm" (every mesh shell of at most max_tris triangles and
# at most max_mm extent owned by a matching part is gold - V3's rivets and studs; ~145 such 24-triangle shells on this seed);
# MM_SOFTEN_GOLD=sigma (gold vs plate written as a continuous factor, Gaussian sigma texels, inside metal - binary masks
# stair-stepped every gold edge at atlas resolution; the two still sum to 1).
# MM_GOLD_FROM_MESH="raised_mm:reach_px" (needs mesh_height_m.npy from relief_project.py RP_MESH_HEIGHT): on plate parts gold is the
# MESH's own raised detail (>= raised_mm above its smoothed self) within reach_px of the projected V3 gold - V3's painted ornament
# lands 1-2 cm off the modelled one (the abdomen emblem's gold sat beside it, the captain's mark 2026-10-04); colour-gold that is
# not on raised detail goes back to plate. The geometry decides the shape, V3 only which ornaments are gold.
# MM_ORNAMENT_GOLD="max_tris:reach_px:min_share" (needs mesh_npz): a SEPARATE mesh shell of at most max_tris on a plate part (the
# abdomen emblem is one: 134 faces, 8 islands) turns gold WHOLE when the projected colour-gold, dilated by reach_px, covers at least
# min_share of its texels; colour-gold left on the surrounding plate within reach of such a shell is the misregistered painted copy
# and goes back to plate. Measured 2026-10-04: per-texel mesh height (MM_GOLD_FROM_MESH) on this low-poly plate golded whole flat
# faces beside the emblem and left the emblem dark - rejected for this piece.
# MM_FORCE_CLASS=<json {"<class>": [triangle ids]}> - the captain's per-face material rulings (e.g. embroidery specks on the cowl ->
# red), applied after every rule; ids are THIS mesh's triangles (convert from source face ids per rebuild).
_E = os.environ.get
GOLD_MIN_SAT, GOLD_MIN_VAL, BLUR = float(_E('MM_GOLD_MIN_SAT', GOLD_MIN_SAT)), float(_E('MM_GOLD_MIN_VAL', GOLD_MIN_VAL)), float(_E('MM_BLUR', BLUR))
EMB_MIN_SAT, EMB_MIN_VAL, EMB_MIN_BLOB = float(_E('MM_EMB_MIN_SAT', GOLD_MIN_SAT)), float(_E('MM_EMB_MIN_VAL', GOLD_MIN_VAL)), int(_E('MM_EMB_MIN_BLOB', 0))
NO_VOTE_CLASSES = tuple(x for x in _E('MM_NO_VOTE_CLASSES', '').split(',') if x); EXTRA_GOLD = tuple(x for x in _E('MM_EXTRA_GOLD', '').split(',') if x)
CLOTH_MEDIAN = int(_E('MM_CLOTH_MEDIAN', 0)); PLATE_GOLD_MIN_BLOB = int(_E('MM_PLATE_GOLD_MIN_BLOB', 0)); PLATE_GOLD_AND_MM = float(_E('MM_PLATE_GOLD_AND_MM', 'nan'))
PLATE_GOLD_CLOSE = int(_E('MM_PLATE_GOLD_CLOSE', 0)); LEATHER_FORCE = _E('MM_LEATHER_FORCE', '0') == '1'
PART_GOLD_SV = {x.split(':')[0]: (float(x.split(':')[1]), float(x.split(':')[2])) for x in _E('MM_PART_GOLD_SV', '').split(',') if x}
PART_GOLD_BLOB = {x.split(':')[0]: int(x.split(':')[3]) for x in _E('MM_PART_GOLD_SV', '').split(',') if x and len(x.split(':')) > 3}
PART_HEIGHT_GOLD = {x.split(':')[0]: (float(x.split(':')[1]), float(x.split(':')[2])) for x in _E('MM_PART_HEIGHT_GOLD', '').split(',') if x}
PART_GOLD_BLOB_GLOB = [(x.split(':')[0], int(x.split(':')[1])) for x in _E('MM_PART_GOLD_BLOB', '').split(',') if x]
RIM_GOLD = {x.split(':')[0]: (float(x.split(':')[1]), float(x.split(':')[2]) if len(x.split(':')) > 2 else None) for x in _E('MM_RIM_GOLD', '').split(',') if x}
RIM_CLOSE = int(_E('MM_RIM_CLOSE', 0)); SOFTEN_GOLD = float(_E('MM_SOFTEN_GOLD', 0))
_sg = _E('MM_STUD_GOLD', ''); STUD_GOLD = (_sg.split(':')[0].split('|'), int(_sg.split(':')[1]), float(_sg.split(':')[2])) if _sg else None
FORCE_CLASS = _E('MM_FORCE_CLASS', '')
_og = _E('MM_ORNAMENT_GOLD', ''); ORNAMENT_GOLD = (int(_og.split(':')[0]), int(_og.split(':')[1]), float(_og.split(':')[2])) if _og else None
_gm = _E('MM_GOLD_FROM_MESH', ''); GOLD_FROM_MESH = (float(_gm.split(':')[0]), int(_gm.split(':')[1])) if _gm else None
EMB_CLOSE = int(_E('MM_EMB_CLOSE', 0)); LINEN_LAST = _E('MM_LINEN_FORCE', '0') == '2'
LINEN_FORCE = _E('MM_LINEN_FORCE', '0') in ('1', '2'); HEIGHT_GOLD_MM = float(_E('MM_HEIGHT_GOLD_MM', 'nan')); HEIGHT_GOLD_SAT = float(_E('MM_HEIGHT_GOLD_SAT', 0.55))
# leather and black linen are DECLARED per part (inferring them from colour share picked the back plate and the studs, where
# the cape's red bleeds in): elsewhere red on metal is plate and dark on cloth is shadowed red cloth
LEATHER_PARTS = ('belt_studded',)                                   # the red belt band (assumption, for the captain to confirm)
LINEN_PARTS = ('undersuit_sleeve_L', 'undersuit_sleeve_R')
GOLD_PARTS = ('breastplate_lion_boss', 'belt_lion_boss', 'roundel_front_R', 'roundel_front_L', 'roundel_back_R', 'roundel_back_L',
              'pendant_front_R', 'pendant_front_L', 'pendant_side_R', 'pendant_side_L', 'cape_collar_studs', 'cape_flank_studs_R', 'cape_flank_studs_L')   # solid gold in V3; V3's shadows made them patchy          # the captain's ruling: "keep sleeves (ruffles, black linen arms)"
OPTIONAL_GOLD_PARTS = ('pendant_back_R', 'pendant_back_L')        # gold like the other pendants, used when the recipe has them
RED_MIN_SAT = 0.45
DARK_MAX_VAL = 0.16
COLORS = {'gold': (214, 160, 70), 'plate': (60, 52, 46), 'red': (170, 25, 25), 'linen': (18, 18, 20), 'embroidery': (240, 200, 90), 'leather': (110, 30, 25)}


def hsv(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1); d = mx - mn + 1e-9
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    return h, np.where(mx > 0, (mx - mn) / (mx + 1e-9), 0), mx


def rim_mask(d, own, names, rec, tf, spec):
    from scipy.spatial import cKDTree
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    P, UV = d['P'], d['UV']; nf = len(P)
    _, w = np.unique(np.round(P.reshape(-1, 3) / 1e-5).astype(np.int64), axis=0, return_inverse=True); w = w.reshape(nf, 3)
    Vw = np.zeros((w.max() + 1, 3)); Vw[w.ravel()] = P.reshape(-1, 3)
    E = np.sort(np.stack([w[:, [0, 1]], w[:, [1, 2]], w[:, [2, 0]]], 1).reshape(-1, 2), 1); ef = np.repeat(np.arange(nf), 3)
    key = E[:, 0] * (w.max() + 1) + E[:, 1]; order = np.argsort(key); ks = key[order]
    A = coo_matrix((np.ones(w.size), (np.repeat(np.arange(nf), 3), w.ravel())), shape=(nf, w.max() + 1)).tocsr()
    shell = connected_components(A @ A.T, directed=False)[1]
    area = np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1) / 2; out = {}
    fn = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]); nrm = fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    for n, (mm, crease) in spec.items():
        k = names.index(n); kids = [names.index(m) for m in names if str(rec['parts'][m].get('from', [''])[0]).startswith(n + ':')]
        fam = np.isin(own, [k] + kids); faces = np.flatnonzero(own == k)
        main = np.argmax(np.bincount(shell[faces], weights=area[faces])); faces = faces[shell[faces] == main]
        segs = []
        for f in faces:                                                   # outline edges of the part's main shell
            for c in range(3):
                kk = key[f * 3 + c]; lo, hi = np.searchsorted(ks, kk), np.searchsorted(ks, kk, 'right'); other = ef[order[lo:hi]]; other = other[other != f]
                if crease is None:
                    if len(other) == 0 or not fam[other].any(): segs.append(E[f * 3 + c])
                else:
                    mine = other[own[other] == k]
                    if len(mine) and np.degrees(np.arccos(np.clip(nrm[mine] @ nrm[f], -1, 1))).max() > crease and f < mine.min(): segs.append(E[f * 3 + c])
        if not segs: raise RuntimeError(f'{n}: no outline edges')
        pts = []
        for a_, b_ in segs:
            m_ = max(2, int(np.linalg.norm(Vw[a_] - Vw[b_]) / 0.002)); t = np.linspace(0, 1, m_)[:, None]; pts.append(Vw[a_] * (1 - t) + Vw[b_] * t)
        tr = cKDTree(np.vstack(pts)); ys, xs = np.nonzero(np.isin(tf, faces)); fid = tf[ys, xs]; R = tf.shape[0]; best = None
        for flip in (0, 1):                                               # texel -> 3D by UV barycentrics; pick the v orientation
            u = (xs + .5) / R; v = (ys + .5) / R; v = 1 - v if flip else v
            a, b, c = UV[fid, 0], UV[fid, 1], UV[fid, 2]; dn = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
            l1 = ((b[:, 1] - c[:, 1]) * (u - c[:, 0]) + (c[:, 0] - b[:, 0]) * (v - c[:, 1])) / dn; l2 = ((c[:, 1] - a[:, 1]) * (u - c[:, 0]) + (a[:, 0] - c[:, 0]) * (v - c[:, 1])) / dn
            L = np.stack([l1, l2, 1 - l1 - l2]); ins = (L > -0.05).all(0).mean()
            if best is None or ins > best[0]: best = (ins, L)
        L = np.clip(best[1], 0, 1); L /= L.sum(0); X = (L.T[:, :, None] * P[fid]).sum(1)
        m = np.zeros(tf.shape, bool); m[ys, xs] = tr.query(X)[0] < mm / 1000; out[n] = m
    return out


def main(pdir, owner_npy, recipe, out=None, mesh_npz=None):
    out = out or pdir; os.makedirs(out, exist_ok=True)
    C = np.asarray(Image.open(os.path.join(pdir, 'v3_colour_atlas.png')).convert('RGB')).astype(np.float32) / 255
    tf = np.load(os.path.join(pdir, 'texel_face.npy')); own = np.load(owner_npy)
    rec = json.load(open(recipe)); names = list(rec['parts']); cls = np.array([rec['parts'][n]['class'] for n in names])
    covered = tf >= 0
    part = np.where(covered, own[np.maximum(tf, 0)], -1)
    is_metal = covered & np.isin(part, np.flatnonzero(np.char.startswith(cls.astype(str), 'rigid')))
    is_cloth = covered & ~is_metal
    Cb = np.stack([gaussian_filter(C[..., c], BLUR) for c in range(3)], -1)
    h, s, v = hsv(Cb)
    warm = (h >= GOLD_HUE[0]) & (h <= GOLD_HUE[1]) & (s >= GOLD_MIN_SAT) & (v >= GOLD_MIN_VAL)
    red = ((h <= 15) | (h >= 340)) & (s >= RED_MIN_SAT) & ~warm
    lab = np.zeros(tf.shape, np.uint8)                     # 0 none, 1 gold, 2 plate, 3 red, 4 linen, 5 embroidery, 6 leather
    dark = v <= DARK_MAX_VAL
    pid = np.maximum(part, 0)
    for n in LEATHER_PARTS + LINEN_PARTS + GOLD_PARTS + tuple(PART_GOLD_SV) + tuple(PART_HEIGHT_GOLD) + tuple(RIM_GOLD):
        if n not in names: raise RuntimeError(f'declared part {n} is not in the recipe')
    hue_ok = (h >= GOLD_HUE[0]) & (h <= GOLD_HUE[1])
    for n, (ps, pv) in PART_GOLD_SV.items():                              # per-part colour-gold cut
        m = covered & (pid == names.index(n)); warm[m] = (hue_ok & (s >= ps) & (v >= pv))[m]
    gold_parts = GOLD_PARTS + tuple(n for n in OPTIONAL_GOLD_PARTS if n in names) + tuple(n for n in EXTRA_GOLD if n in names)   # r7 adds the rear pendants (captain D1)
    leather_ok = covered & np.isin(pid, [names.index(n) for n in LEATHER_PARTS]); linen_ok = covered & np.isin(pid, [names.index(n) for n in LINEN_PARTS])
    lab[is_metal] = 2; lab[is_metal & warm] = 1; lab[is_metal & red & leather_ok] = 6
    emb = (h >= GOLD_HUE[0]) & (h <= GOLD_HUE[1]) & (s >= EMB_MIN_SAT) & (v >= EMB_MIN_VAL)
    lab[is_cloth] = 3; lab[is_cloth & dark & linen_ok] = 4; lab[is_cloth & emb] = 5
    if LINEN_FORCE: lab[is_cloth & linen_ok & (lab != 5)] = 4
    lab_m = median_filter(lab, MEDIAN)
    if CLOTH_MEDIAN: lab_m = np.where(is_cloth, median_filter(lab, CLOTH_MEDIAN), lab_m)
    lab = np.where(covered, lab_m, 0)
    shells_voted = 0
    if mesh_npz:
        P = np.load(mesh_npz)['P']; nf = len(P)
        _, weld = np.unique(np.round(P.reshape(-1, 3) / 1e-5).astype(np.int64), axis=0, return_inverse=True); weld = weld.reshape(nf, 3)
        par = np.arange(nf)
        def find(x):
            while par[x] != x: par[x] = par[par[x]]; x = par[x]
            return x
        first = {}
        for f in range(nf):
            for w in weld[f]:
                g = first.setdefault((int(w), int(own[f])), f)             # same welded vertex AND same part
                if g != f: a_, b_ = find(f), find(g); par[a_] = b_
        root = np.array([find(f) for f in range(nf)])
        tfc = np.maximum(tf, 0); rt = np.where(covered, root[tfc], -1)
        sel = covered & is_metal & ~np.isin(pid, [k for k, c in enumerate(cls) if c in NO_VOTE_CLASSES])
        ids, inv = np.unique(rt[sel], return_inverse=True)
        g_ = np.bincount(inv, weights=(lab[sel] == 1)); p_ = np.bincount(inv, weights=(lab[sel] == 2)); fsz = np.bincount(root, minlength=nf)[ids]
        tot = g_ + p_ + 1e-9; vote = np.zeros(len(ids), np.uint8)
        vote[(fsz <= SHELL_MAX) & (g_ / tot >= SHELL_MAJ)] = 1; vote[(fsz <= SHELL_MAX) & (p_ / tot >= SHELL_MAJ)] = 2
        newlab = lab[sel].copy(); v_ = vote[inv]; m_ = (v_ > 0) & np.isin(newlab, (1, 2)); newlab[m_] = v_[m_]; lab[sel] = newlab
        shells_voted = int((vote > 0).sum())
    fp = os.path.join(pdir, 'fine_atlas.npy'); relief_gold = 0
    if os.path.exists(fp):                                               # gold follows the relief: exact on the embossing, 4x V3's resolution
        Fa = gaussian_filter(np.load(fp), RELIEF_GOLD_SMOOTH)
        rg = covered & is_metal & (lab == 2) & (Fa >= RELIEF_GOLD); lab[rg] = 1; relief_gold = int(rg.sum())
        lg = covered & is_metal & (lab == 1) & (Fa < 0) & ~np.isin(pid, [names.index(n) for n in gold_parts])
        lab[lg & (gaussian_filter((lab == 1).astype(float), 3) < 0.5)] = 2   # isolated colour-gold sitting in a recess is smear: back to plate
    hp = os.path.join(pdir, 'detail_height_m.npy'); height_gold = 0
    if HEIGHT_GOLD_MM == HEIGHT_GOLD_MM and os.path.exists(hp) and relief_gold == 0:      # no fine band: gold from raised line work
        Hm = np.load(hp); Hm = Hm if Hm.shape == tf.shape else np.asarray(Image.fromarray(Hm.astype(np.float32)).resize(tf.shape[::-1]))
        warm55 = (h >= GOLD_HUE[0]) & (h <= GOLD_HUE[1]) & (s >= HEIGHT_GOLD_SAT) & (v >= GOLD_MIN_VAL * 0.8)
        for n in PART_GOLD_SV: m = pid == names.index(n); warm55[m] = warm[m]       # a per-part cut binds the height path too
        hg = covered & is_metal & (lab == 2) & warm55 & (Hm * 1000 >= HEIGHT_GOLD_MM); lab[hg] = 1; height_gold = int(hg.sum())
    plate_gold_dropped = 0
    if PLATE_GOLD_MIN_BLOB or PLATE_GOLD_AND_MM == PLATE_GOLD_AND_MM:     # plate parts: gold components must be real ornament
        elig = covered & is_metal & ~np.isin(pid, [names.index(n) for n in gold_parts + LEATHER_PARTS])
        cc, ncc = _cc_label(elig & (lab == 1)); keep = np.ones(ncc + 1, bool); keep[0] = False
        part_blob = dict(PART_GOLD_BLOB)
        for g, b in PART_GOLD_BLOB_GLOB:
            hit = [n for n in names if __import__('fnmatch').fnmatch(n, g)]
            if not hit: raise RuntimeError(f'MM_PART_GOLD_BLOB pattern {g} matches no part')
            for n in hit: part_blob.setdefault(n, b)
        if PLATE_GOLD_MIN_BLOB or part_blob:
            need = np.full(ncc + 1, PLATE_GOLD_MIN_BLOB)
            for n, b in part_blob.items(): need[np.unique(cc[(cc > 0) & (pid == names.index(n))])] = b   # a component takes its part's minimum
            keep &= np.bincount(cc.ravel(), minlength=ncc + 1) >= need
        if PLATE_GOLD_AND_MM == PLATE_GOLD_AND_MM and os.path.exists(hp):
            Hm2 = np.load(hp); Hm2 = Hm2 if Hm2.shape == tf.shape else np.asarray(Image.fromarray(Hm2.astype(np.float32)).resize(tf.shape[::-1]))
            touch = np.zeros(ncc + 1, bool); t_ = (cc > 0) & warm & (Hm2 * 1000 >= PLATE_GOLD_AND_MM); touch[np.unique(cc[t_])] = True; keep &= touch
        drop = (cc > 0) & ~keep[cc]; lab[drop] = 2; plate_gold_dropped = int(drop.sum())
        if PLATE_GOLD_CLOSE: lab[elig & (lab == 2) & binary_closing(elig & (lab == 1), iterations=PLATE_GOLD_CLOSE)] = 1
    mesh_gold = {}
    if GOLD_FROM_MESH:
        from scipy.ndimage import binary_dilation
        mhp = os.path.join(pdir, 'mesh_height_m.npy')
        if not os.path.exists(mhp): raise RuntimeError('MM_GOLD_FROM_MESH needs mesh_height_m.npy (relief_project.py with RP_MESH_HEIGHT)')
        mh = np.load(mhp); rmm, reach = GOLD_FROM_MESH
        elig2 = covered & is_metal & ~np.isin(pid, [names.index(n) for n in gold_parts + LEATHER_PARTS])
        G = elig2 & (lab == 1); near = binary_dilation(G, iterations=reach) if reach > 0 else G
        raised = mh * 1000 >= rmm
        newg = elig2 & near & raised; lab[elig2 & (lab == 1) & ~newg] = 2; lab[newg] = 1
        mesh_gold = {'colour_gold_texels': int(G.sum()), 'mesh_gold_texels': int(newg.sum()), 'kept_of_colour': int((G & newg).sum())}
    orn = {}
    if ORNAMENT_GOLD:
        if not mesh_npz: raise RuntimeError('MM_ORNAMENT_GOLD needs mesh_npz')
        from scipy.ndimage import binary_dilation
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        Pm = np.load(mesh_npz)['P']; nfm = len(Pm); _, wq = np.unique(np.round(Pm.reshape(-1, 3) / 1e-5).astype(np.int64), axis=0, return_inverse=True); wq = wq.reshape(nfm, 3)
        Aq = coo_matrix((np.ones(wq.size), (np.repeat(np.arange(nfm), 3), wq.ravel())), shape=(nfm, wq.max() + 1)).tocsr(); shq = connected_components(Aq @ Aq.T, directed=False)[1]
        cnt_q = np.bincount(shq); mt, reach, share = ORNAMENT_GOLD
        elig3 = covered & is_metal & ~np.isin(pid, [names.index(n) for n in gold_parts + LEATHER_PARTS])
        st = np.where(covered, shq[np.maximum(tf, 0)], -1)
        small_sh = (cnt_q <= mt); tex_small = elig3 & small_sh[np.maximum(st, 0)] & (st >= 0)
        G = elig3 & (lab == 1); Gd = binary_dilation(G, iterations=reach)
        ids_ = st[tex_small]; tot = np.bincount(ids_, minlength=len(cnt_q)); hit = np.bincount(ids_, weights=Gd[tex_small], minlength=len(cnt_q))
        gold_sh = (tot > 0) & (hit / np.maximum(tot, 1) >= share)
        orn_tex = tex_small & gold_sh[np.maximum(st, 0)]; lab[orn_tex] = 1
        near_orn = binary_dilation(orn_tex, iterations=reach) & elig3 & ~tex_small & (lab == 1)
        cc_, ncc_ = _cc_label(elig3 & ~tex_small & (lab == 1)); inside_share = np.bincount(cc_.ravel(), weights=near_orn.ravel(), minlength=ncc_ + 1) / np.maximum(np.bincount(cc_.ravel(), minlength=ncc_ + 1), 1)
        copy_ = (cc_ > 0) & (inside_share[cc_] >= 0.5); lab[copy_] = 2
        orn = {'shells_gold': int(gold_sh.sum()), 'ornament_texels': int(orn_tex.sum()), 'painted_copies_to_plate_texels': int(copy_.sum())}
    if PART_HEIGHT_GOLD and os.path.exists(hp):
        Hm3 = np.load(hp); Hm3 = Hm3 if Hm3.shape == tf.shape else np.asarray(Image.fromarray(Hm3.astype(np.float32)).resize(tf.shape[::-1]))
        for n, (mm, ps) in PART_HEIGHT_GOLD.items(): lab[covered & (pid == names.index(n)) & hue_ok & (s >= ps) & (Hm3 * 1000 >= mm)] = 1
    rim_texels = {}
    if RIM_GOLD:
        if not mesh_npz: raise RuntimeError('MM_RIM_GOLD needs mesh_npz (with UV)')
        rim = rim_mask(np.load(mesh_npz), own, names, rec, tf, RIM_GOLD)
        for n, m_ in rim.items():
            if RIM_CLOSE: m_ = binary_closing(m_, iterations=RIM_CLOSE) & (pid == names.index(n))
            lab[m_ & covered] = 1; rim_texels[n] = int(m_.sum())
    stud_texels = 0
    if STUD_GOLD:
        if not mesh_npz: raise RuntimeError('MM_STUD_GOLD needs mesh_npz')
        import fnmatch
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        Pm = np.load(mesh_npz)['P']; nf_ = len(Pm); _, w_ = np.unique(np.round(Pm.reshape(-1, 3) / 1e-5).astype(np.int64), axis=0, return_inverse=True); w_ = w_.reshape(nf_, 3)
        A_ = coo_matrix((np.ones(w_.size), (np.repeat(np.arange(nf_), 3), w_.ravel())), shape=(nf_, w_.max() + 1)).tocsr(); sh_ = connected_components(A_ @ A_.T, directed=False)[1]
        cnt = np.bincount(sh_); pts = Pm.reshape(-1, 3); sv = np.repeat(sh_, 3)
        lo = np.full((cnt.size, 3), np.inf); hi = np.full((cnt.size, 3), -np.inf); np.minimum.at(lo, sv, pts); np.maximum.at(hi, sv, pts)
        small = (cnt <= STUD_GOLD[1]) & ((hi - lo).max(1) * 1000 <= STUD_GOLD[2])
        okp = [k for k, n in enumerate(names) if any(fnmatch.fnmatch(n, g) for g in STUD_GOLD[0])]
        if not okp: raise RuntimeError(f'MM_STUD_GOLD patterns {STUD_GOLD[0]} match no part')
        stud_face = small[sh_] & np.isin(own, okp); m_ = covered & stud_face[np.maximum(tf, 0)]; lab[m_] = 1; stud_texels = int(m_.sum())
    lab[covered & np.isin(pid, [names.index(n) for n in gold_parts])] = 1
    if LEATHER_FORCE: lab[covered & np.isin(pid, [names.index(n) for n in LEATHER_PARTS]) & (lab != 1)] = 6
    if EMB_CLOSE: lab[is_cloth & (lab == 3) & binary_closing(lab == 5, iterations=EMB_CLOSE)] = 5   # merge a band's fragments (red only)
    if EMB_MIN_BLOB > 0:                                                  # embroidery: drop specks, keep bands
        cc, ncc = _cc_label(lab == 5); sz = np.bincount(cc.ravel()); small = (sz < EMB_MIN_BLOB); small[0] = False; lab[small[cc] & (lab == 5)] = 3
    if LINEN_LAST: lab[is_cloth & linen_ok] = 4                               # undersuit forced last, over embroidery
    forced = {}
    if FORCE_CLASS:
        CI = {'gold': 1, 'plate': 2, 'red': 3, 'linen': 4, 'embroidery': 5, 'leather': 6}
        for cl, tris in json.load(open(FORCE_CLASS)).items():
            m_ = covered & np.isin(tf, tris); lab[m_] = CI[cl]; forced[cl] = int(m_.sum())
    lab[covered & is_metal & ~np.isin(lab, (1, 2, 6))] = 2   # the median must not move a texel across the metal/cloth line
    lab[covered & is_cloth & ~np.isin(lab, (3, 4, 5))] = 3
    rep = {'blur_px': BLUR, 'median_px': MEDIAN, 'gold_hue_deg': GOLD_HUE, 'gold_min_sat': GOLD_MIN_SAT, 'gold_min_val': GOLD_MIN_VAL,
           'dark_max_val': DARK_MAX_VAL, 'red_min_sat': RED_MIN_SAT, 'leather_parts': LEATHER_PARTS, 'linen_parts': LINEN_PARTS, 'gold_parts': gold_parts, 'shell_max_faces': SHELL_MAX, 'shell_majority': SHELL_MAJ, 'covered_texels': int(covered.sum()), 'shares_of_covered': {}}
    prev = np.zeros(tf.shape + (3,), np.uint8)
    for k, name in enumerate(('gold', 'plate', 'red', 'linen', 'embroidery', 'leather'), 1):
        m = lab == k; mv = m.astype(np.float32)
        if SOFTEN_GOLD and name in ('gold', 'plate'):                    # continuous gold factor inside metal; plate = the rest of metal
            met = np.isin(lab, (1, 2)); g = gaussian_filter((lab == 1).astype(np.float32), SOFTEN_GOLD) / np.maximum(gaussian_filter(met.astype(np.float32), SOFTEN_GOLD), 1e-6)
            g = np.clip(g, 0, 1) * met; mv = g if name == 'gold' else (met - g)
        Image.fromarray(np.round(mv * 255).astype(np.uint8)).save(os.path.join(out, f'mask_{name}.png'))
        prev[m] = COLORS[name]; rep['shares_of_covered'][name] = round(float(m.sum() / covered.sum()), 4)
    Image.fromarray(prev).resize((1400, 1400), Image.NEAREST).save(os.path.join(out, 'masks_preview.png'))
    rep.update(height_gold_texels=height_gold, overrides={k: v for k, v in os.environ.items() if k.startswith('MM_')}); rep['shells_voted'] = shells_voted; rep['plate_gold_dropped_texels'] = plate_gold_dropped; rep['rim_gold_texels'] = rim_texels; rep['stud_gold_texels'] = stud_texels; rep['forced_texels'] = forced; rep['gold_from_mesh'] = mesh_gold; rep['ornament_gold'] = orn; rep['relief_gold_texels'] = relief_gold; rep['relief_gold_threshold'] = RELIEF_GOLD
    json.dump(rep, open(os.path.join(out, 'masks.json'), 'w'), indent=1); print(rep['shares_of_covered'], 'shells voted', shells_voted)


if __name__ == '__main__':
    main(*sys.argv[1:])
