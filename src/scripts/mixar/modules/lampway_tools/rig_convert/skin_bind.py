# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/skin_bind.py, sha256 1b827d93cf7a), on 2026-10-06. WIP: skin and morph (canon 07/22 DRAFT).
"""Explicit bind skinning in canonical cm coordinates; no inferred bone frames.

Matrices are row-major arrays acting on column vectors. Each bind and pose is
global in the mesh's coordinate system. This packet preserves native joint axes;
it does not claim conformance to the pending semantic humanoid reference pose.
"""
from fractions import Fraction
from collections import Counter
import math

try:
    from . import canon                  # inside the rig_convert package
except ImportError:
    import canon                         # loaded by path (the recipes and the ported suite put rig_convert on sys.path)

SCHEMA = 'titan.native-bind-skin/1'    # a stable wire contract shared with TITAN: never renamed
WIP = True                               # skin and morph are WIP tooling (canon pages 07 and 22 are DRAFT): dogfooded and improved through Lampway


def _number(value):
    if type(value) not in (int, float): raise ValueError('expected a finite number')
    try: value = float(value)
    except OverflowError as exc: raise ValueError('number exceeds finite range') from exc
    if not math.isfinite(value): raise ValueError('expected a finite number')
    return value if value else 0.0


def _name(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError('invalid native joint name')
    return value


def validate_affine(value):
    if not isinstance(value, list) or len(value) != 4 or any(
            not isinstance(row, list) or len(row) != 4 for row in value):
        raise ValueError('matrix must be an affine 4x4 row array')
    result = [[_number(x) for x in row] for row in value]
    if result[3] != [0,0,0,1]: raise ValueError('matrix must be affine')
    try:
        inverse = _inverse(result)
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError('matrix inverse exceeds finite range') from exc
    if any(not math.isfinite(x) for row in inverse for x in row):
        raise ValueError('matrix inverse exceeds finite range')
    return result


def _joints(rows):
    if not isinstance(rows, list) or not rows: raise ValueError('bind table is empty')
    by_name = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'name','parent','bind'}:
            raise ValueError('joint requires only name, parent and global bind')
        name = _name(row['name'])
        if name in by_name: raise ValueError('duplicate joint '+name)
        parent = None if row['parent'] is None else _name(row['parent'])
        by_name[name] = {'name': name, 'parent': parent, 'bind': validate_affine(row['bind'])}
    if sum(row['parent'] is None for row in by_name.values()) != 1:
        raise ValueError('bind hierarchy must have exactly one root')
    for name in by_name:
        seen = set()
        while name is not None:
            if name not in by_name: raise ValueError('missing parent '+name)
            if name in seen: raise ValueError('cycle in bind hierarchy at '+name)
            seen.add(name); name = by_name[name]['parent']
    return [by_name[name] for name in sorted(by_name)]


def _weights(mesh, joints, weights, *, rational=False):
    names = {joint['name'] for joint in joints}
    if not isinstance(weights, dict) or set(weights) != {m['name'] for m in mesh['meshes']}:
        raise ValueError('weight mesh names must match the canonical mesh document')
    result = {}
    for item in mesh['meshes']:
        rows = weights[item['name']]
        if not isinstance(rows, list) or len(rows) != len(item['verts']):
            raise ValueError('weight rows must match every vertex')
        normalized = []
        for row in rows:
            if not isinstance(row, list) or not row: raise ValueError('vertex has no weight mass')
            combined = {}
            for influence in row:
                if not isinstance(influence, (list, tuple)) or len(influence) != (3 if rational else 2):
                    raise ValueError('invalid named influence')
                name = _name(influence[0])
                if name not in names: raise ValueError('unknown weighted joint '+name)
                if rational:
                    n,d = influence[1:]
                    if type(n) is not int or type(d) is not int or n <= 0 or d <= 0:
                        raise ValueError('packet weights require positive integer ratios')
                    weight = Fraction(n,d)
                else:
                    _number(influence[1])
                    weight = Fraction(str(influence[1]))
                    if weight < 0: raise ValueError('negative skin weight')
                combined[name] = combined.get(name, Fraction(0)) + weight
            total = sum(combined.values())
            if total <= 0: raise ValueError('vertex has no positive weight mass')
            canonical = [[name,(weight/total).numerator,(weight/total).denominator]
                         for name,weight in sorted(combined.items()) if weight]
            if rational and (total != 1 or row != canonical):
                raise ValueError('packet weights must be sorted unique reduced ratios with mass one')
            normalized.append(canonical)
        result[item['name']] = normalized
    return result


def _inverse(m):
    # Affine inverse: inverse(linear) and -inverse(linear) * translation.
    a,b,c = m[0][:3]; d,e,f = m[1][:3]; g,h,i = m[2][:3]
    adj = [[e*i-f*h,c*h-b*i,b*f-c*e],
           [f*g-d*i,a*i-c*g,c*d-a*f],
           [d*h-e*g,b*g-a*h,a*e-b*d]]
    det = math.fsum((a*adj[0][0],b*adj[1][0],c*adj[2][0]))
    if det == 0: raise ValueError('singular matrix')
    linear = [[x/det for x in row] for row in adj]
    return [row + [-math.fsum(row[k]*m[k][3] for k in range(3))]
            for row in linear] + [[0,0,0,1]]


def _multiply(a, b):
    return [[math.fsum(a[i][k]*b[k][j] for k in range(4))
             for j in range(4)] for i in range(4)]


def capture(mesh_document, joints, weights):
    """Capture unchanged geometry, explicit global binds and named skin weights."""
    mesh = canon.normalize_mesh(mesh_document)
    if mesh_document.get('schema') != canon.SCHEMA:
        raise ValueError('capture requires canonical mesh data')
    joints = _joints(joints)
    normalized = _weights(mesh, joints, weights)
    return {'schema': SCHEMA, 'mesh': mesh,
            'joints': joints,
            'weights': normalized}


def validate_packet(packet):
    """Validate a canonical native-bind packet and return an independent copy."""
    if not isinstance(packet, dict) or set(packet) != {'schema','mesh','joints','weights'} or packet['schema'] != SCHEMA:
        raise ValueError('invalid native bind skin packet')
    result = canon.normalize_mesh(packet['mesh'])
    if packet['mesh'].get('schema') != canon.SCHEMA: raise ValueError('packet mesh must be canonical')
    joints = _joints(packet['joints'])
    weights = _weights(result, joints, packet['weights'], rational=True)
    normalized = {'schema': SCHEMA, 'mesh': result, 'joints': joints, 'weights': weights}
    if canon.serialize(normalized) != canon.serialize(packet): raise ValueError('noncanonical bind packet')
    return normalized


def rebind(packet, target_joints, joint_map):
    """Bind already-fitted geometry to explicit target joints, without moving it.

    The map names every weighted source joint, including explicit identities.
    Many-to-one merges conserve exact mass but lose independent deformation;
    they are reported, never described as lossless animation transfer.
    """
    source = validate_packet(packet)
    target = _joints(target_joints)
    names = {j['name'] for j in target}
    used = {name for rows in source['weights'].values()
            for row in rows for name,_,_ in row}
    if not isinstance(joint_map, dict) or set(joint_map) != used:
        raise ValueError('joint map must name every weighted source joint and no others')
    for mapped in joint_map.values():
        if _name(mapped) not in names: raise ValueError('mapped target joint is absent: '+mapped)
    mass = {name: Counter() for name in sorted(used)}
    weights = {}
    for mesh, rows in source['weights'].items():
        mapped_rows = []
        for row in rows:
            combined = {}
            for name,n,d in row:
                value = Fraction(n,d); mapped = joint_map[name]
                mass[name][value] += 1
                combined[mapped] = combined.get(mapped, Fraction(0)) + value
            mapped_rows.append([[name,w.numerator,w.denominator]
                                for name,w in sorted(combined.items())])
        weights[mesh] = mapped_rows
    result = {'schema':SCHEMA, 'mesh':source['mesh'], 'joints':target, 'weights':weights}
    inverse = {}
    for name in sorted(used): inverse.setdefault(joint_map[name], []).append(name)
    receipt = {'geometry_sha256':canon.digest(canon.serialize(source['mesh'])),
               'vertices':sum(len(rows) for rows in weights.values()),
               'mapped_mass':{name:{'target':joint_map[name],
                                    'mass_approx':math.fsum(float(term)*count for term,count in sorted(terms.items())),
                                    'mass_terms':[[term.numerator,term.denominator,count]
                                                  for term,count in sorted(terms.items())]}
                              for name,terms in mass.items()},
               'merged_targets':{name:rows for name,rows in sorted(inverse.items()) if len(rows)>1},
               'dropped_mass':[0,1]}
    return result, receipt


def evaluate(packet, pose_by_joint, *, geometry_only=False):
    """Evaluate positions/morph directions P * inverse(B), without mutation.

    Shaded packets require explicit geometry_only: this oracle does not model
    world-specific corner-normal deformation and must not return stale normals.
    """
    if type(geometry_only) is not bool: raise ValueError('geometry_only must be boolean')
    normalized = validate_packet(packet)
    result, joints, weights = normalized['mesh'], normalized['joints'], normalized['weights']
    for mesh in result['meshes']:
        if 'shading' in mesh:
            if not geometry_only:
                raise ValueError('shaded evaluation requires geometry_only=True; verify posed normals in the world adapter')
            del mesh['shading']
    if not isinstance(pose_by_joint, dict) or set(pose_by_joint) != {j['name'] for j in joints}:
        raise ValueError('pose must explicitly provide every joint and no others')
    transforms = {j['name']: _multiply(validate_affine(pose_by_joint[j['name']]), _inverse(j['bind']))
                  for j in joints}
    decimals = canon.FORM['position_decimals_cm']
    for mesh in result['meshes']:
        verts = []
        morphs = {name: [] for name in mesh['morphs']}
        for index, (vertex, influences) in enumerate(zip(mesh['verts'], weights[mesh['name']])):
            blended = [[math.fsum((num/den)*transforms[name][axis][k]
                                  for name,num,den in influences)
                        for k in range(4)] for axis in range(3)]
            def apply(vector, w):
                point = list(vector) + [w]
                rounded = [round(math.fsum(row[k]*point[k] for k in range(4)), decimals)
                           for row in blended]
                return [value if value else 0.0 for value in rounded]
            verts.append(apply(vertex, 1))
            for name, deltas in mesh['morphs'].items():
                morphs[name].append(apply(deltas[index], 0))
        mesh['verts'] = verts
        mesh['morphs'] = morphs
    return canon.normalize_mesh(result)
