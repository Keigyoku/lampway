# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/proportion/pose_clearance.py, sha256 90dd53931112) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): the MetaHuman's CLOSEST POSE to a placed piece, then clearance (the user: "always put the MetaHuman in the
# closest pose to solve those issues before fit/skinng/weighting ... back:hip arching too"). The body is deformed through its own
# skeleton (glTF armature, A-pose rest), never moved by hand.
#   arms:  both upper arms rotated together, mirrored: lowered from the A-pose (about the body's front-back axis; env PC_LOWS) and
#          swung (about the side axis, + = backward; env PC_SWINGS); per pose, each upper-arm vertex is tested by a ray from the posed bone axis out
#          to the vertex - an armour hit before the vertex = penetration (depth = how far the skin lies past the surface).
#   chain: the neck:chest and back:hips links (captain) - spine_01 (hips), spine_03 (chest), neck_01 (neck) pitched -8..+8 deg in
#          turn at the best arm pose, each keeping the earlier best; torso and neck vertices tested from their axes. The neck metric
#          includes any cap/bowl inside the collar (a mesh defect, not pose).
# Env PC_CLASSES=<labels.npy> (one label per placed triangle, e.g. metal/cloth): the residual blocking hits are counted by label.
# Writes pose_clearance.json; prints a TOON table per sweep and the closest pose.
# blender -b -P pose_clearance.py -- <out_dir> <body.glb> <placed.npz>   (placed.npz from place_piece.py, body frame)
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
import lw_canon
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['blender -b -P scripts/proportion/pose_clearance.py -- <out_dir> <body.glb> <placed.npz>   (env PC_LOWS / PC_SWINGS)']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, "The MetaHuman's closest pose to a placed piece (arms, hips, chest, neck), clearance and residual blocking surfaces")
    else: print(f'error: {len(_A)} argument(s); at least 3 needed')
    _ax.helps(['blender -b -P scripts/proportion/pose_clearance.py -- <out_dir> <body.glb> <placed.npz>   (env PC_LOWS / PC_SWINGS)']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import bpy, sys, os, json, math, numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
a = sys.argv[sys.argv.index('--') + 1:]; OUT, BODY, PLACED = a[0], a[1], a[2]; os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
lw_canon.io.import_raw(BODY)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE'); body = max((o for o in bpy.data.objects if o.type == 'MESH'), key=lambda o: len(o.data.vertices))
d = np.load(PLACED); tree = BVHTree.FromPolygons([tuple(map(float, v)) for v in d['V']], [tuple(map(int, t)) for t in d['T']])
dg = bpy.context.evaluated_depsgraph_get()


def verts():
    dg.update(); ev = body.evaluated_get(dg); me = ev.to_mesh(); M = np.array(body.matrix_world)
    V = np.array([v.co[:] for v in me.vertices]) @ M[:3, :3].T + M[:3, 3]; ev.to_mesh_clear(); return V


def joint(name, tail=False):
    pb = arm.pose.bones[name]; return np.array((arm.matrix_world @ (pb.tail if tail else pb.head))[:])


def first_hit(o, dvec, rmax):
    h = tree.ray_cast(Vector(o), Vector(dvec), rmax); return h[3] if h[0] is not None else None


def rotate(bone, axis_world, deg):
    """rotate a pose bone about a WORLD axis through its head (pose-space composition)"""
    bpy.context.view_layer.update()                                     # pb.matrix / pb.head are stale until the pose is re-evaluated (measured: a first
    pb = arm.pose.bones[bone]; Mw = arm.matrix_world                     # version without these updates left the elbow fixed for every pose)
    ax3 = (Mw.inverted().to_3x3() @ Vector(axis_world)).normalized()
    h = pb.head.copy(); R = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, ax3) @ Matrix.Translation(-h)
    pb.matrix = R @ pb.matrix; bpy.context.view_layer.update()


def reset():
    for pb in arm.pose.bones: pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


arm.data.pose_position = 'POSE'
reset(); _e0 = joint('lowerarm_l'); rotate('upperarm_l', (0, 1, 0), 20); _e1 = joint('lowerarm_l'); reset()
print('SIGN CHECK elbow_l z', round(float(_e0[2]), 3), '->', round(float(_e1[2]), 3), '(lowering must decrease z)', flush=True)
if not _e1[2] < _e0[2] - 0.02: raise SystemExit('REFUSED: rotating upperarm_l by +20 deg about +Y did not lower the elbow (measured: +deg lowers the left arm); the pose sweep would be meaningless')


V0 = verts()
ARM_SEL = {}
for s, sg in (('l', 1), ('r', -1)):                                    # rest-pose upper-arm vertices (indices), wearer's left = +X
    A, B = joint(f'upperarm_{s}'), joint(f'lowerarm_{s}'); axv = (B - A) / np.linalg.norm(B - A); rel = V0 - A; t = rel @ axv
    rr = np.linalg.norm(rel - np.outer(t, axv), axis=1); ARM_SEL[s] = np.where((t > 0.02) & (t < np.linalg.norm(B - A)) & (rr < 0.11) & (sg * V0[:, 0] > 0.15))[0]
TORSO = np.where((V0[:, 2] > 1.15) & (V0[:, 2] < 1.52) & (np.abs(V0[:, 0]) < 0.17) & (V0[:, 1] > -0.2) & (V0[:, 1] < 0.15))[0]


hit_faces = {}
CLASSES = np.load(os.environ['PC_CLASSES'], allow_pickle=True).astype(str) if os.environ.get('PC_CLASSES') else None   # per-triangle labels aligned with placed T


def arm_pen(V, keep_hits=False):
    out = {}; hit_faces.clear()
    for s in ('l', 'r'):
        A, B = joint(f'upperarm_{s}'), joint(f'lowerarm_{s}'); L = np.linalg.norm(B - A); axv = (B - A) / L; dep = []; hits = []
        for i in ARM_SEL[s][::2]:                                       # every 2nd vertex (bounded)
            rel = V[i] - A; t = rel @ axv; perp = rel - t * axv; rv = np.linalg.norm(perp)
            if rv < 0.01: continue
            o = A + t * axv; hh = tree.ray_cast(Vector(o), Vector(perp / rv), rv); h = hh[3] if hh[0] is not None else None
            dep.append(rv - h if h is not None else 0.0)
            if h is not None and rv - h > 0.01: hits.append((o + perp / rv * h).tolist()); hit_faces.setdefault(s, []).append(int(hh[2]))   # surface + its triangle
        dep = np.array(dep); out[s] = {'n': int(len(dep)), 'gt10mm': int((dep > 0.01).sum()), 'worst_mm': round(float(dep.max() * 1000), 1)}
        if keep_hits: out[s]['hits'] = hits
    return out


def torso_pen(V):
    dep = []
    for i in TORSO[::3]:
        v = V[i]; band = (np.abs(V[:, 2] - v[2]) < 0.01) & (np.abs(V[:, 0]) < 0.17); yc = (V[band, 1].min() + V[band, 1].max()) / 2
        o = np.array([0.0, yc, v[2]]); dv = v - o; rv = np.linalg.norm(dv[:2])
        if rv < 0.02: continue
        h = first_hit(o, np.array([dv[0], dv[1], 0]) / rv, rv); dep.append(rv - h if h is not None else 0.0)
    dep = np.array(dep); return {'n': int(len(dep)), 'gt2mm_frac': round(float((dep > 0.002).mean()), 4), 'worst_mm': round(float(dep.max() * 1000), 1)}


res = {'arms': [], 'spine': []}
LOWS = [int(x) for x in os.environ.get('PC_LOWS', '0,5,10,15,20,25,30,35,40').split(',')]          # deg lowered from the A-pose (negative = raised)
SWINGS = [int(x) for x in os.environ.get('PC_SWINGS', '-10,-5,0,5,10').split(',')]                # deg about +X: positive swings the arm BACKWARD (body faces -Y)
for low in LOWS:
    for swing in SWINGS:
        reset()
        # +deg about +Y lowers the left arm (+X), -deg the right: measured by the SIGN CHECK above
        for s, sg in (('l', 1), ('r', -1)):
            rotate(f'upperarm_{s}', (0, 1, 0), sg * low); rotate(f'upperarm_{s}', (1, 0, 0), swing)
        bpy.context.view_layer.update(); V = verts(); p = arm_pen(V)
        el = joint('lowerarm_l'); res['arms'].append({'lower_deg': low, 'swing_deg': swing, 'elbow_l_z': round(float(el[2]), 3), 'elbow_l_x': round(float(el[0]), 3),
                                                       'l_gt10mm': p['l']['gt10mm'], 'l_worst_mm': p['l']['worst_mm'], 'r_gt10mm': p['r']['gt10mm'], 'r_worst_mm': p['r']['worst_mm'], 'n': p['l']['n']})
        print(json.dumps(res['arms'][-1]), flush=True)
best = min(res['arms'], key=lambda r: (r['l_gt10mm'] + r['r_gt10mm'], r['l_worst_mm'] + r['r_worst_mm'], r['lower_deg']))
NECK = np.where((V0[:, 2] > 1.50) & (V0[:, 2] < 1.62) & (np.abs(V0[:, 0]) < 0.12))[0]


def neck_pen(V):
    dep = []
    for i in NECK[::2]:
        v = V[i]; band = (np.abs(V[:, 2] - v[2]) < 0.01) & (np.abs(V[:, 0]) < 0.12); yc = (V[band, 1].min() + V[band, 1].max()) / 2
        o = np.array([0.0, yc, v[2]]); dv = v - o; rv = np.linalg.norm(dv[:2])
        if rv < 0.01: continue
        h = first_hit(o, np.array([dv[0], dv[1], 0]) / rv, rv); dep.append(rv - h if h is not None else 0.0)
    dep = np.array(dep); return {'n': int(len(dep)), 'gt2mm_frac': round(float((dep > 0.002).mean()), 4), 'worst_mm': round(float(dep.max() * 1000), 1)}


# the neck:chest and back:hips links (captain), solved one after another, each on torso + neck penetration, at the best arm pose:
# hips (spine_01) first, then chest (spine_03), then neck (neck_01); each step keeps the earlier steps' best angle.
CHAIN = [('spine_01', 'hips'), ('spine_03', 'chest'), ('neck_01', 'neck')]; fixed = {}
for bone, label in CHAIN:
    rows = []
    for ang in (-8, -4, 0, 4, 8):
        reset()
        for s_, sg in (('l', 1), ('r', -1)):
            rotate(f'upperarm_{s_}', (0, 1, 0), sg * best['lower_deg']); rotate(f'upperarm_{s_}', (1, 0, 0), best['swing_deg'])
        for b2, a2 in fixed.items(): rotate(b2, (1, 0, 0), a2)
        rotate(bone, (1, 0, 0), ang); bpy.context.view_layer.update(); V = verts(); t = torso_pen(V); n = neck_pen(V)
        row = {'link': label, 'bone': bone, 'pitch_deg': ang, 'torso_gt2mm': t['gt2mm_frac'], 'torso_worst_mm': t['worst_mm'], 'neck_gt2mm': n['gt2mm_frac'], 'neck_worst_mm': n['worst_mm']}
        rows.append(row); res['spine'].append(row); print(json.dumps(row), flush=True)
    b = min(rows, key=lambda r: (r['torso_gt2mm'] + r['neck_gt2mm'], abs(r['pitch_deg']))); fixed[bone] = b['pitch_deg']
res['best_arm_pose'] = best; res['a_pose'] = next((r for r in res['arms'] if r['lower_deg'] == 0 and r['swing_deg'] == 0), None)
# where the arm still passes through the armour in the closest arm pose: the blocking surface points, placed frame and the piece's own
# (import) frame via place_piece.py's meta (<placed.npz>.json), for exact Edit Mesh regions
reset()
for s_, sg in (('l', 1), ('r', -1)):
    rotate(f'upperarm_{s_}', (0, 1, 0), sg * best['lower_deg']); rotate(f'upperarm_{s_}', (1, 0, 0), best['swing_deg'])
P_ = arm_pen(verts(), keep_hits=True); meta_f = PLACED + '.json'
if os.path.exists(meta_f):
    m = json.load(open(meta_f)); lo, hi = np.array(m['norm_lo']), np.array(m['norm_hi']); th = math.radians(m['turn_deg'])
    Rz = np.array([[math.cos(th), -math.sin(th), 0], [math.sin(th), math.cos(th), 0], [0, 0, 1]])
    def to_piece(Pp):
        Pp = np.array(Pp, float).copy(); Pp[:, 1] -= m['y_shift']; Pp[:, 2] -= m['tz']; Pp = Pp / m['scale'] * (hi[2] - lo[2]) + [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]
        return Pp @ Rz                                                  # undo the turn (row vectors: R^-1 = R^T)
    res['blocking'] = {}
    for s_ in ('l', 'r'):
        H = np.array(P_[s_]['hits'])
        if len(H): Q = to_piece(H); res['blocking'][s_] = {'points': int(len(H)), 'bbox_piece_frame': [Q.min(0).round(3).tolist(), Q.max(0).round(3).tolist()],
                                                         'p10_p90_piece_frame': [np.percentile(Q, 10, 0).round(3).tolist(), np.percentile(Q, 90, 0).round(3).tolist()]}
    if CLASSES is not None:                                             # which material the arm passes through (e.g. metal vs cloth)
        for s_ in ('l', 'r'):
            fl = hit_faces.get(s_, []); labs, cnts = np.unique(CLASSES[fl], return_counts=True) if fl else ([], [])
            res['blocking'].setdefault(s_, {})['by_class'] = {str(k): int(v) for k, v in zip(labs, cnts)}
    print('BLOCKING', json.dumps(res['blocking']), flush=True)
res['best_chain_deg'] = fixed; res['a_pose_chain'] = next(r for r in res['spine'] if r['bone'] == 'spine_01' and r['pitch_deg'] == 0)
res['best_spine'] = min(res['spine'], key=lambda r: (r['torso_gt2mm'] + r['neck_gt2mm'], abs(r['pitch_deg'])))
json.dump(res, open(os.path.join(OUT, 'pose_clearance.json'), 'w'), indent=1)
print('POSE DONE', json.dumps({'a_pose': res['a_pose'], 'best_arm_pose': best, 'best_chain_deg': fixed, 'best_spine_row': res['best_spine']}))
