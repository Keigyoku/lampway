# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon03-H2 ARAP candidate (2026-10-08); synthetic proof, physical_status untested.

Internal engine of fit stage=conform, retaining canonical doors without another
public tool. Solve creates an independent candidate. Accept checks its receipt,
source, native package, sampled pose and output again before recording review.
Explicit clearance/seam limits are operational controls, not physical acceptance.
"""
import hashlib
import json
from pathlib import Path

import bpy
import numpy as np

from . import common as C
from . import source_check as SC
from . import fit_bind as FB
from . import fit_body
from .. import canon_asset as CA, canon_door as D, canon_geom as G, canon_io
from ..pipeline.decision_measure import _vertex_clearance

CANDIDATE_DEFAULTS = {'max_iterations': 30, 'convergence_m': 1e-7, 'linear_iterations': 300,
                      'linear_tol': 1e-10, 'weld_m': 1e-5, 'max_handle_updates': 5, 'target_padding_m': 2e-6}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _mesh(ob):
    bpy.context.view_layer.update()
    ob.data.calc_loop_triangles()
    return SC._P(ob), np.asarray([tuple(t.vertices) for t in ob.data.loop_triangles], dtype=int).reshape(-1, 3)


def _identity(ob):
    P, T = _mesh(ob)
    return _hash({'positions': P.tolist(), 'triangles': T.tolist(),
                  'parts': {p: ids.tolist() for p, ids in SC._parts(ob).items()}})


def _directory(root, out_dir):
    base = Path(root).resolve()
    path = (base / out_dir).resolve()
    if not path.is_relative_to(base):
        raise C.FeatureError('conform output must stay inside the project root')
    return path


def _door(name):
    bpy.context.view_layer.update()
    reasons = D.unmet('object', name, CA.Need(kind=('mesh', 'part'), scale=('real',)))
    if reasons:
        raise C.FeatureError('normalize first: ' + '; '.join(reasons))


def _body(body, armature, root, expected):
    bpy.context.view_layer.update()
    package = Path(body) if Path(body).is_absolute() else Path(root) / body
    verified = fit_body.need_weights(str(package))
    if verified['package_sha256'] != expected:
        raise C.FeatureError('body package changed since intake; re-run intake')
    st = verified.get('body') or {}
    if not st.get('head_included') or not (st.get('closed') or st.get('native_openings_accepted')):
        raise C.FeatureError('conform requires the verified native body with head and declared openings')
    arm = C.need_object(armature, 'ARMATURE')
    packaged_joints = json.loads((package / 'joints.json').read_text())['joints']
    if fit_body._joints(arm) != packaged_joints:
        raise C.FeatureError('armature rest/parent identities differ from the verified native body package')
    names = sorted(b.name for b in arm.data.bones)
    _weights, V, T, _region, _sha = FB._sidecar_regions(body, arm, names, root)
    return arm, V, T, FB._pose_record(arm)['sha256']


def _seams(source, ob, roles):
    S, ST = _mesh(source)
    P, PT = _mesh(ob)
    if len(S) != len(P) or not np.array_equal(ST, PT):
        raise C.FeatureError('conform source must preserve vertex order and triangle topology; supply the immutable pre-conform source/ledger')
    groups = SC._parts(source)
    if set(groups) != set(roles):
        raise C.FeatureError('every source part needs its persisted intake role; source groups/roles differ')
    labels = [None] * len(S)
    for name, ids in groups.items():
        for i in ids:
            if labels[i] is not None and labels[i] != name:
                raise C.FeatureError('source ledger requires one part label per original vertex')
            labels[i] = name
    pairs = np.asarray(G.seam_ledger(S, labels), dtype=int).reshape(-1, 2)
    if not all(np.array_equal(ids, SC._parts(ob).get(name)) for name, ids in groups.items()):
        raise C.FeatureError('source part vertex identities changed; conform cannot infer a remapping')
    return groups, pairs


def _limits(clearance_m, seam_limit_m, body_open_band_m):
    for name, value in [('clearance_m', clearance_m), ('seam_limit_m', seam_limit_m)]:
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not np.isfinite(value) or value < 0:
            raise C.FeatureError(f'{name} must be an explicit finite nonnegative metre target')
    return {'min_signed_m': float(clearance_m), 'max_below_min_vertices': 0,
            **({'body_open_band_m': body_open_band_m} if body_open_band_m is not None else {})}


def _verify_geometry(P, original, movable, pairs, seam_limit, V, T, limits):
    if not np.array_equal(P[~movable], original[~movable]):
        raise C.FeatureError('metal and ornaments must remain bit-identical in world coordinates')
    seam = G.seam_gaps(P, pairs, threshold=seam_limit)
    if seam['open']:
        raise C.FeatureError('source-ledger seam gap exceeds explicit seam_limit_m')
    measure = _vertex_clearance(P[movable], V, T, limits)
    if measure['pass'] is None:
        raise C.FeatureError('signed clearance refused in the declared body opening band')
    return seam, measure


def _anchor_clear_components(P, T, movable, pairs, handles):
    """Keep each independently clear component exactly authored, without hiding
    an unanchored solver graph. Analytical welding joins generated duplicates."""
    parent = np.arange(len(P))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def join(a, b):
        parent[root(b)] = root(a)
    for a, b in np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]], pairs]):
        join(int(a), int(b))
    keys = G.weld_keys(P)
    for i, k in enumerate(keys):
        join(i, int(k))
    groups = {}
    for i in range(len(P)):
        groups.setdefault(root(i), []).append(i)
    for ids in groups.values():
        if not any(i in handles for i in ids):
            for i in ids:
                if movable[i]:
                    handles[i] = P[i].copy()


def run(*, root, out_dir, body, body_package_sha256, roles, parts, action='solve',
        object='', source='', armature='', clearance_m=None, seam_limit_m=None,
        body_open_band_m=None, solver=None, candidate_sha256='', captain_seen=False, render_sha256=''):
    path = _directory(root, out_dir)
    if action == 'accept':
        return _accept(path, body, body_package_sha256, root, roles, parts, candidate_sha256, captain_seen, render_sha256)
    if action != 'solve':
        raise C.FeatureError('conform action is solve | accept')
    limits = _limits(clearance_m, seam_limit_m, body_open_band_m)
    settings = dict(CANDIDATE_DEFAULTS, **(solver or {}))
    unknown = set(settings) - set(CANDIDATE_DEFAULTS)
    if unknown:
        raise C.FeatureError(f'unknown ARAP solver settings: {sorted(unknown)}')
    for key in ('max_iterations', 'linear_iterations'):
        value = settings[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise C.FeatureError(f'{key} must be a positive integer')
    for key in ('convergence_m', 'linear_tol', 'weld_m'):
        value = settings[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0 or (key != 'weld_m' and value == 0):
            raise C.FeatureError(f'{key} must be finite and positive (weld_m may be zero)')
    outer_iterations = settings.pop('max_handle_updates')
    padding = settings.pop('target_padding_m')
    if isinstance(outer_iterations, bool) or not isinstance(outer_iterations, int) or outer_iterations < 1:
        raise C.FeatureError('max_handle_updates must be a positive integer')
    if isinstance(padding, bool) or not isinstance(padding, (int, float)) or not np.isfinite(padding) or padding <= 0:
        raise C.FeatureError('target_padding_m must be finite and positive')
    if not parts or any(roles.get(p) not in ('cloth', 'leather') for p in parts):
        raise C.FeatureError('only explicit intake cloth/leather parts may conform')
    _door(object)
    ob, src = C.need_object(object), C.need_object(source)
    if ob == src:
        raise C.FeatureError('conform requires a separate immutable source object')
    if ob.modifiers or src.modifiers or ob.data.shape_keys or src.data.shape_keys:
        raise C.FeatureError('conform requires explicit unmodified fit-pose mesh/source geometry; evaluate to a canonical copy first')
    groups, pairs = _seams(src, ob, roles)
    P, PT = _mesh(ob)
    if not len(PT) or np.any(np.linalg.norm(np.cross(P[PT[:, 1]]-P[PT[:, 0]], P[PT[:, 2]]-P[PT[:, 0]]), axis=1) == 0):
        raise C.FeatureError('conform requires nonempty nondegenerate source triangles')
    movable = np.zeros(len(P), dtype=bool)
    for name in parts:
        movable[groups[name]] = True
    if not movable.any():
        raise C.FeatureError('selected soft parts are empty')
    arm, V, T, pose_sha = _body(body, armature, root, body_package_sha256)
    name = ob.name + '_conform'
    if bpy.data.objects.get(name) is not None or path.exists():
        raise C.FeatureError('conform candidate/output already exists; use its accept action or remove the disposable candidate/receipt explicitly')
    from ..pipeline.soft_conform import solve_arap
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    # Query the existing canon15 signed-clearance instrument before constructing
    # targets. This refuses unsafe opening-band signs and malformed body topology.
    initial = _vertex_clearance(P[movable], V, T, limits)
    if initial['pass'] is None:
        raise C.FeatureError('signed clearance refused in the declared body opening band')
    analytical_T = G.weld_keys(V)[T]
    analytical_T = analytical_T[(analytical_T[:, 0] != analytical_T[:, 1]) &
                                (analytical_T[:, 1] != analytical_T[:, 2]) & (analytical_T[:, 2] != analytical_T[:, 0])]
    tree = BVHTree.FromPolygons(V.tolist(), analytical_T.tolist(), all_triangles=True)
    handles = {}
    current = P.copy()
    solve_metrics = {'iterations': 0, 'converged': True}
    # Each violating point is fixed at a nearest surface clearance target. ARAP
    # propagates the constraints; this is not an outward-push output algorithm.
    for outer in range(outer_iterations):
        seam, measured = _verify_geometry(current, P, movable, pairs, seam_limit_m, V, T, limits)
        if measured['pass']:
            break
        normals = G.PseudoNormals(V, analytical_T) if not G.boundary_edges(analytical_T) else None
        for i in np.flatnonzero(movable):
            loc, normal, tri, distance = tree.find_nearest(Vector(current[i]))
            if loc is None:
                raise C.FeatureError('no body triangle at a clearance handle')
            q = np.array(loc[:]); n = np.array(normal[:])
            sign = (normals.signs(current[i:i+1], q[None], np.array([tri]))[0] if normals is not None
                    else (-1 if G.winding_numbers(V, analytical_T, current[i:i+1])[0] > .5 else 1))
            if distance * sign < clearance_m:
                handles[int(i)] = q + n * (clearance_m + padding)
        _anchor_clear_components(P, PT, movable, pairs, handles)
        try:
            current, solve_metrics = solve_arap(P, PT, movable, handles, pairs, **settings)
        except (ValueError, RuntimeError) as e:
            raise C.FeatureError(f'ARAP candidate refused: {e}') from e
    seam, measured = _verify_geometry(current, P, movable, pairs, seam_limit_m, V, T, limits)
    if not measured['pass']:
        raise C.FeatureError('ARAP candidate failed explicit all-soft-vertex clearance target after bounded handle updates')
    # No Blender allocation occurs before every numerical control passes.
    source_sha, input_sha = _identity(src), _identity(ob)
    out = C.duplicate(ob, '_conform')
    created_directory = False
    try:
        mw = np.asarray(ob.matrix_world)
        local = (current - mw[:3, 3]) @ np.linalg.inv(mw[:3, :3]).T
        out.data.vertices.foreach_set('co', local.astype(np.float32).ravel())
        out.data.update()
        # Retain exact authored rigid coordinates despite float32 conversion.
        for i in np.flatnonzero(~movable):
            out.data.vertices[int(i)].co = ob.data.vertices[int(i)].co
        stored, _ = _mesh(out)
        seam, measured = _verify_geometry(stored, P, movable, pairs, seam_limit_m, V, T, limits)
        if not measured['pass']:
            raise C.FeatureError('serialized candidate failed explicit clearance target')
        doc = json.loads(ob['lw_canon'])
        facts = canon_io.facts(out)
        for field in ('bbox_min_m', 'bbox_max_m', 'geometry_sha256'):
            doc['body'][field] = facts[field]
        doc['canonical_sha256'] = CA.digest(json.dumps({'geometry': facts['geometry_sha256'],
            'uv': [u['layout_sha256'] for u in doc['body'].get('uv_sets', [])],
            'materials': doc['body'].get('material_slots', [])}, sort_keys=True).encode())
        out['lw_canon'] = json.dumps(doc, sort_keys=True)
        _door(out.name)
        receipt = {'schema': 'lampway.soft-conform/1', 'algorithm': 'ARAP-uniform-edge-clearance-handles/1',
            'physical_status': 'untested', 'object': out.name, 'input': ob.name, 'source': src.name, 'armature': arm.name,
            'source_sha256': source_sha, 'input_sha256': input_sha, 'output_sha256': _identity(out),
            'body_package_sha256': body_package_sha256, 'pose_sha256': pose_sha,
            'sampled_body_sha256': _hash({'V': V.tolist(), 'T': T.tolist()}),
            'roles': roles, 'parts': parts, 'clearance_limits': limits, 'seam_limit_m': seam_limit_m,
            'seam_ledger': {'origin': 'source-exact-coordinate-groups', 'pairs': pairs.tolist()},
            'seams': seam, 'clearance': measured, 'solver': solve_metrics, 'solver_overrides': solver or {},
            'settings': dict(settings, max_handle_updates=outer_iterations, target_padding_m=padding),
            'default_provenance': {'ruling_date': '2026-10-08', 'source': 'canon03-H2 captain delegated solver defaults',
                'physical_status': 'untested', 'rationale': 'bounded local/global iterations, positive uniform edge weights and numerical target padding for float32 serialization'},
            'handle_updates': outer + 1, 'handle_count': len(handles), 'metal_and_ornaments_unchanged': True,
            'conventions': G.conventions_block(turn_deg=0, weld_m=G.WELD_M, source_frame='working-canonical'),
            'texture_must_regenerate': True,
            'not_measured': ['self-collision', 'surface crossings', 'innermost gap', 'owner visual acceptance', 'native engine motion']}
        receipt['candidate_sha256'] = _hash(receipt)
        path.mkdir(parents=True)
        created_directory = True
        (path / 'candidate.json').write_text(json.dumps(receipt, indent=1, sort_keys=True))
        doc['receipt_sha256'] = receipt['candidate_sha256']
        out['lw_canon'] = json.dumps(doc, sort_keys=True)
    except Exception:
        data = out.data
        bpy.data.objects.remove(out, do_unlink=True)
        if not data.users:
            bpy.data.meshes.remove(data)
        if created_directory:
            (path / 'candidate.json').unlink(missing_ok=True)
            path.rmdir()
        raise
    return {'ok': True, 'candidate_pending_review': True, 'object': out.name,
            'candidate_sha256': receipt['candidate_sha256'], 'receipt_path': str(path / 'candidate.json'),
            'physical_status': 'untested', 'clearance': measured, 'seams': seam}


def _accept(path, body, expected, root, roles, parts, candidate, seen, render_sha):
    if seen is not True or len(str(render_sha)) != 64 or any(c not in '0123456789abcdef' for c in str(render_sha).lower()):
        raise C.FeatureError('accept requires captain_seen=true with this candidate render SHA beside V3')
    if not (path / 'candidate.json').exists():
        raise C.FeatureError('solve a conform candidate first')
    rec = json.loads((path / 'candidate.json').read_text())
    recorded_sha = rec.pop('candidate_sha256')
    if candidate != recorded_sha or recorded_sha != _hash(rec):
        raise C.FeatureError('candidate receipt SHA changed or does not name the reviewed candidate')
    if roles != rec['roles'] or parts != rec['parts']:
        raise C.FeatureError('candidate roles/parts changed; review a new solve')
    arm, V, T, pose_sha = _body(body, rec['armature'], root, expected)
    if pose_sha != rec['pose_sha256'] or expected != rec['body_package_sha256']:
        raise C.FeatureError('candidate body/fit pose changed since solve')
    if _hash({'V': V.tolist(), 'T': T.tolist()}) != rec['sampled_body_sha256']:
        raise C.FeatureError('candidate sampled native body changed since solve')
    for key, hash_key in [('source', 'source_sha256'), ('input', 'input_sha256'), ('object', 'output_sha256')]:
        item = C.need_object(rec[key])
        if item.modifiers or item.data.shape_keys:
            raise C.FeatureError(f'candidate {key} gained modifiers/shape keys since solve')
        if _identity(item) != rec[hash_key]:
            raise C.FeatureError(f'candidate {key} geometry/part identities changed since solve')
    _door(rec['object'])
    ob, src = C.need_object(rec['object']), C.need_object(rec['source'])
    groups, pairs = _seams(src, ob, roles)
    movable = np.zeros(len(ob.data.vertices), bool)
    for p in parts:
        movable[groups[p]] = True
    P, _ = _mesh(ob)
    original, _ = _mesh(C.need_object(rec['input']))
    seam, measured = _verify_geometry(P, original, movable, pairs, rec['seam_limit_m'], V, T, rec['clearance_limits'])
    if not measured['pass']:
        raise C.FeatureError('reviewed candidate no longer passes explicit clearance controls')
    return {'ok': True, 'object': ob.name, 'candidate_sha256': candidate,
            'captain_seen': True, 'render_sha256': render_sha, 'physical_status': 'untested',
            'clearance': measured, 'seams': seam}
