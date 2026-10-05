# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/proportion/proportion_fit.py, sha256 7a6b01fcf345) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# AUDITED 2026-10-04 - FRAGILE, do not rank on it alone: an independent landmark audit (<shelf scratch>/proportion/audit/
# report.md) measured that single switches (A-pose arm rays, neck rays, the 20 mm target, the cape's back sector, free vertical
# placement, first-hit inner lining) each move a score by up to 10 mm against a 3.7 mm spread, and flip the winner. Use scale-free
# landmark ratios at axilla-aligned placement (audit/indep.py) as the primary proportion measure; keep this for overlays.
# SPIKE (2026-10-04): PROPORTIONS against the project's MetaHuman body. The user: "Best proportions trump bad meshes because a
# mesh can be repaired, proportions are in the seed generation". A Tripo piece comes normalised (about 1 m), so its true scale is
# unknown; proportion is judged by how well ONE uniform scale plus a translation makes it enclose the body evenly.
#
# Body: NewMetaHumanCharacter_FullBody.glb (geometry and joints only; weights unused). Frame: Z up, faces -Y, wearer's left +X.
# Rays (body distances computed once, from the body's own axis outward, so the first hit is the skin):
#   torso: 12 heights from spine_01 to spine_05, 24 azimuths, from the torso slice centre;
#   neck:  3 heights just above the neck base (neck_01), 24 azimuths - the collar must surround the neck;
#   arms:  3 points along each upper arm (25/45/65 % shoulder->elbow), 8 directions perpendicular to the bone - the arm
#          opening must clear the arm.
# For a fit (s, tx, ty, tz) each ray is replayed in the piece's frame; clearance c = armour hit - body hit (metres). c < 0: the
# body passes through the armour (penetration). No hit: the ray leaves through an opening (expected at sleeves, recorded).
# Fit: grid over s, ty, tz then Nelder-Mead minimising (see cost()) the 10-90 % trimmed clearance variance, the 10th percentile held
# above zero (torso+neck, and arms), median clearance near 20 mm, and misses at torso/neck height. Score (lower is better): the
# trimmed clearance standard deviation over torso+neck at the best fit, with penetration reported separately
# (worst mm, fraction of rays). A seed whose shape matches the body needs no penetration to sit evenly.
# Usage: blender -b -P proportion_fit.py -- <out_dir> <body.glb> <piece>:<turn_deg> [<piece>:<turn_deg> ...]
#   turn_deg: rotation about Z that brings the piece to face -Y with its wearer's left at +X (Tripo FBX and Triangle glb: -90).
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['blender -b -P scripts/proportion/proportion_fit.py -- <out_dir> <body.glb> <piece>:<turn_deg> [...]']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, 'Clearance-fit overlays of pieces on the body (FRAGILE as a ranking; use proportion_ratios.py)')
    else: print(f'error: {len(_A)} argument(s); at least 3 needed')
    _ax.helps(['blender -b -P scripts/proportion/proportion_fit.py -- <out_dir> <body.glb> <piece>:<turn_deg> [...]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import bpy, sys, os, json, math, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

a = sys.argv[sys.argv.index('--') + 1:]; OUT, BODY = a[0], a[1]; PIECES = [(p.rsplit(':', 1)[0], float(p.rsplit(':', 1)[1])) for p in a[2:]]
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)


def imported(f):
    before = set(bpy.data.objects)
    (bpy.ops.import_scene.fbx if f.lower().endswith('.fbx') else bpy.ops.import_scene.gltf)(filepath=f)
    return [o for o in bpy.data.objects if o not in before]


# ---- body ----
new = imported(BODY)
arm = next(o for o in new if o.type == 'ARMATURE'); body = max((o for o in new if o.type == 'MESH'), key=lambda o: len(o.data.vertices))
J = {b.name: np.array((arm.matrix_world @ b.head_local)[:]) for b in arm.data.bones}
BV = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices])
bvh_body = BVHTree.FromPolygons([tuple(x) for x in BV], [tuple(p.vertices) for p in body.data.polygons])
for o in new: o.hide_render = True

rays = []                                                               # (region, origin, direction, body_distance)
z0, z1 = J['spine_01'][2], J['spine_05'][2]
az = [2 * math.pi * k / 24 for k in range(24)]
for z in np.linspace(z0, z1, 12):
    sl = BV[(np.abs(BV[:, 2] - z) < 0.01) & (np.abs(BV[:, 0]) < 0.16)]
    c = np.array([0.0, (sl[:, 1].min() + sl[:, 1].max()) / 2, z])
    for t in az:
        rays.append(('torso', c, np.array([math.sin(t), -math.cos(t), 0.0]), t))   # t = 0: straight forward (-Y)
nk = J['neck_01']
for dz in (0.015, 0.035, 0.055):
    z = nk[2] + dz; sl = BV[(np.abs(BV[:, 2] - z) < 0.006) & (np.abs(BV[:, 0]) < 0.09)]
    c = np.array([0.0, (sl[:, 1].min() + sl[:, 1].max()) / 2, z])
    for t in az: rays.append(('neck', c, np.array([math.sin(t), -math.cos(t), 0.0]), t))
for side in ('l', 'r'):
    p0, p1 = J[f'upperarm_{side}'], J[f'lowerarm_{side}']; ax = (p1 - p0) / np.linalg.norm(p1 - p0)
    u = np.cross(ax, [0, 1.0, 0]); u /= np.linalg.norm(u); w = np.cross(ax, u)
    for f in (0.25, 0.45, 0.65):
        c = p0 + f * (p1 - p0)
        for k in range(8):
            t = 2 * math.pi * k / 8; rays.append((f'arm_{side}', c, math.cos(t) * u + math.sin(t) * w, t))
R = []
for reg, o, d, t in rays:
    h = bvh_body.ray_cast(Vector(o), Vector(d), 1.0)
    if h[0] is not None: R.append((reg, o, d, t, h[3]))
REG = np.array([r[0] for r in R]); O = np.array([r[1] for r in R]); D = np.array([r[2] for r in R]); DB = np.array([r[4] for r in R])
print('rays', len(R), {k: int((REG == k).sum()) for k in set(REG)})


def piece_bvh(f, turn):
    obs = [o for o in imported(f) if o.type == 'MESH']
    V, F, off = [], [], 0
    for o in obs:
        M = o.matrix_world; V += [(M @ v.co)[:] for v in o.data.vertices]; F += [tuple(i + off for i in p.vertices) for p in o.data.polygons]; off += len(o.data.vertices)
        o.hide_render = True
    V = np.array(V); th = math.radians(turn); Rz = np.array([[math.cos(th), -math.sin(th), 0], [math.sin(th), math.cos(th), 0], [0, 0, 1]])
    V = V @ Rz.T; lo, hi = V.min(0), V.max(0); h = hi[2] - lo[2]
    V = (V - [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]) / h          # centred in x/y, z 0..1
    return BVHTree.FromPolygons([tuple(x) for x in V], F), V, F, obs


def clear(bvh, p):
    s, tx, ty, tz = p; t = np.array([tx, ty, tz]); out = np.full(len(O), np.nan)
    for i in range(len(O)):
        h = bvh.ray_cast(Vector((O[i] - t) / s), Vector(D[i]), 2.0)
        if h[0] is not None: out[i] = h[3] * s - DB[i]
    return out


def cost(bvh, p):
    """robust: inner junk (cloth backs, a relief mirrored inside the shell) reads as penetration on a few rays, so the 10 % tails are
    trimmed for the evenness term and only the 10th percentile is held above zero; openings at torso/neck height (the piece sits too
    low or too high) are penalised as misses"""
    c = clear(bvh, p); m = (REG == 'torso') | (REG == 'neck'); cc = c[m & ~np.isnan(c)]
    if len(cc) < 50: return 1e3, c
    lo, hi = np.percentile(cc, [10, 90]); tr = cc[(cc >= lo) & (cc <= hi)]
    ar = c[((REG == 'arm_l') | (REG == 'arm_r')) & ~np.isnan(c)]; arq = np.percentile(ar, 10) if len(ar) > 4 else 0.0
    miss = np.isnan(c[REG == 'torso']).mean() + 2 * np.isnan(c[REG == 'neck']).mean()
    return float(tr.var() + 50 * min(lo, 0) ** 2 + 20 * min(arq, 0) ** 2 + (np.median(cc) - 0.02) ** 2 + 0.003 * miss), c


def nelder(f, x0, step, iters=120):
    xs = [np.array(x0, float)] + [np.array(x0, float) + np.eye(len(x0))[k] * step[k] for k in range(len(x0))]
    fs = [f(x) for x in xs]
    for _ in range(iters):                                              # bounded
        o = np.argsort(fs); xs = [xs[k] for k in o]; fs = [fs[k] for k in o]
        cen = np.mean(xs[:-1], 0); xr = cen + (cen - xs[-1]); fr = f(xr)
        if fr < fs[0]:
            xe = cen + 2 * (cen - xs[-1]); fe = f(xe)
            xs[-1], fs[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < fs[-2]: xs[-1], fs[-1] = xr, fr
        else:
            xc = cen + 0.5 * (xs[-1] - cen); fc = f(xc)
            if fc < fs[-1]: xs[-1], fs[-1] = xc, fc
            else:
                xs = [xs[0]] + [xs[0] + 0.5 * (x - xs[0]) for x in xs[1:]]; fs = [fs[0]] + [f(x) for x in xs[1:]]
    k = int(np.argmin(fs)); return xs[k], fs[k]


chest_y = O[REG == 'torso'][:, 1].mean()
results = []
for idx, (f, turn) in enumerate(PIECES):
    bvh, PV, PF, obs = piece_bvh(f, turn)
    best = None
    for s in np.arange(0.56, 0.96, 0.03):                               # coarse grid (bounded)
        for tz in np.arange(nk[2] + 0.06 - s * 1.05, nk[2] + 0.06 - s * 0.85, 0.02):
            for ty in (chest_y - 0.03, chest_y, chest_y + 0.03):
                cst = cost(bvh, (s, 0.0, ty, tz))[0]
                if best is None or cst < best[0]: best = (cst, (s, 0.0, ty, tz))
    x, fx = nelder(lambda p: cost(bvh, p)[0], best[1], [0.02, 0.005, 0.01, 0.01])
    fx, c = cost(bvh, x)
    row = {'piece': os.path.basename(f), 'turn_deg': turn, 'fit': {'scale_m_per_unit': round(float(x[0]), 4), 't_m': [round(float(v), 4) for v in x[1:]]},
           'implied_height_m': round(float(x[0]), 3), 'cost': round(fx, 6)}
    for reg in ('torso', 'neck', 'arm_l', 'arm_r'):
        cr = c[REG == reg]; hit = cr[~np.isnan(cr)]
        row[reg] = {'rays': int(len(cr)), 'miss_frac': round(float(np.isnan(cr).mean()), 3),
                    'clear_mean_mm': round(float(hit.mean()) * 1000, 1) if len(hit) else None, 'clear_std_mm': round(float(hit.std()) * 1000, 1) if len(hit) else None,
                    'pen_frac': round(float((hit < 0).mean()), 3) if len(hit) else None, 'worst_pen_mm': round(float(min(hit.min(), 0)) * 1000, 1) if len(hit) else None}
    tn = c[(REG == 'torso') | (REG == 'neck')]; tn = tn[~np.isnan(tn)]
    lo, hi = np.percentile(tn, [10, 90]); row['score_std_mm'] = round(float(tn[(tn >= lo) & (tn <= hi)].std()) * 1000, 1)   # trimmed, as fitted
    row['p10_clear_mm'] = round(float(lo) * 1000, 1); row['raw_std_mm'] = round(float(tn.std()) * 1000, 1)
    np.save(os.path.join(OUT, f'clear_{idx}.npy'), c)
    results.append(row); print(json.dumps(row))
    # placed copy for renders
    me = bpy.data.meshes.new(f'fit{idx}'); me.from_pydata([tuple(v) for v in (PV * x[0] + x[1:])], [], PF); ob = bpy.data.objects.new(f'fit{idx}', me)
    bpy.context.scene.collection.objects.link(ob); ob.hide_render = True
json.dump({'body': BODY, 'joints_used': {k: [round(float(v), 4) for v in J[k]] for k in ('spine_01', 'spine_05', 'neck_01', 'upperarm_l', 'upperarm_r', 'lowerarm_l', 'lowerarm_r')},
           'regions': {k: int((REG == k).sum()) for k in set(REG)}, 'ray_meta': [[r[0], round(float(r[3]), 4)] for r in R],
           'method': 'see header of scripts/proportion/proportion_fit.py', 'results': results}, open(os.path.join(OUT, 'proportion.json'), 'w'), indent=1)
# renders: body + each fitted piece, x-ray, front and side
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'OBJECT'
sc.display.shading.show_xray = True; sc.display.shading.xray_alpha = 0.55; sc.render.resolution_x, sc.render.resolution_y = 600, 800; sc.render.film_transparent = True
body.hide_render = False; body.color = (0.9, 0.35, 0.3, 1)
cam = bpy.data.cameras.new('c'); co = bpy.data.objects.new('c', cam); sc.collection.objects.link(co); sc.camera = co; cam.type = 'ORTHO'; cam.ortho_scale = 0.95
for idx in range(len(PIECES)):
    ob = bpy.data.objects[f'fit{idx}']; ob.hide_render = False; ob.color = (0.75, 0.75, 0.8, 1)
    for vn, (pos, rot) in {'front': ((0, -4, 1.25), (90, 0, 0)), 'side': ((4, 0, 1.25), (90, 0, 90))}.items():
        co.location = pos; co.rotation_euler = [math.radians(v) for v in rot]
        sc.render.filepath = os.path.join(OUT, f'fit{idx}_{vn}.png'); bpy.ops.render.render(write_still=True)
    ob.hide_render = True
print('PROPORTION DONE')
