# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact authored FACE ownership on a disposable copy; source seams are not approved."""
import hashlib
import itertools
import json
from pathlib import Path

import bpy
import numpy as np

from . import common as C
from .workflows import mesh_hash


_ID_ATTRS = ('lw_part_source_vertex', 'lw_part_source_face')
_NORMAL_ATTR = 'lw_part_source_normal'
_INTRINSIC = {'position', '.edge_verts', '.corner_vert', '.corner_edge'}


def _mapping(spec, recipe_path, owners, max_parts):
    if not recipe_path:
        raise C.FeatureError('separate_parts needs recipe and explicit part_names {face ID: recipe part}; name the source ownership')
    recipe = json.loads(Path(recipe_path).read_text())
    vocabulary = set((recipe.get('parts') or {}).keys())
    given = spec.get('part_names')
    if not isinstance(given, dict) or not given:
        raise C.FeatureError('separate_parts needs explicit part_names {face ID: recipe part}')
    mapping = {}
    for key, value in given.items():
        if not isinstance(key, str) or not key.isdigit() or str(int(key)) != key or not isinstance(value, str):
            raise C.FeatureError('part_names keys are exact nonnegative integer strings and values are recipe part names')
        mapping[int(key)] = value
    if len(set(mapping.values())) != len(mapping):
        raise C.FeatureError('conflicting ownership: each authored face ID must name a distinct recipe part')
    if set(mapping.values()) - vocabulary:
        raise C.FeatureError('part_names contains a name absent from the supplied recipe; use its exact parts vocabulary')
    used = set(int(x) for x in owners)
    if used != set(mapping):
        raise C.FeatureError(f'face ownership and part_names must match exactly: missing {sorted(used-set(mapping))[:20]}, unused {sorted(set(mapping)-used)[:20]}')
    if len(mapping) > int(max_parts):
        raise C.FeatureError(f'{len(mapping)} authored parts exceeds max_parts={max_parts}; review ownership or explicitly raise max_parts')
    return mapping


def _attribute_values(attr):
    if not len(attr.data):
        return None
    props = [p for p in attr.data[0].bl_rna.properties if p.identifier != 'rna_type']
    if len(props) != 1 or props[0].type not in {'FLOAT', 'INT', 'BOOLEAN'}:
        raise C.FeatureError(f'unsupported copied attribute {attr.name} ({attr.data_type}); use a supported explicit prepared source')
    prop = props[0]
    width = prop.array_length if prop.is_array else 1
    dtype = np.float32 if prop.type == 'FLOAT' else np.bool_ if prop.type == 'BOOLEAN' else np.int32
    values = np.empty(len(attr.data)*width, dtype=dtype)
    attr.data.foreach_get(prop.identifier, values)
    return prop.identifier, values.reshape(len(attr.data), width)


def separate(object, spec, recipe_path, max_parts=200):
    src = C.need_object(object, 'MESH')
    if src.mode != 'OBJECT' or src.data.shape_keys:
        raise C.FeatureError('separate_parts needs Object Mode and a mesh without shape keys; prepare an explicit static source copy')
    me = src.data
    attr = me.attributes.get(spec.get('face_attribute', 'part'))
    if attr is None or attr.domain != 'FACE' or attr.data_type != 'INT' or not len(me.polygons):
        raise C.FeatureError('separate_parts needs a nonempty FACE INT face_attribute with exact authored ownership; supply it, never infer by proximity')
    if any(me.attributes.get(n) for n in (*_ID_ATTRS, _NORMAL_ATTR)):
        raise C.FeatureError('source already has part-copy identity attributes; use the original source, not a recursively separated copy')
    owners = np.array([x.value for x in attr.data], dtype=np.int64)
    mapping = _mapping(spec, recipe_path, owners, max_parts)
    source_normals = np.array([n.vector[:] for n in me.corner_normals], dtype=np.float32)
    old_points = np.array([v.co[:] for v in me.vertices], dtype=np.float32)
    point_ids, point_parts, faces, lookup = [], [], [], {}
    sharing = {}
    for face, owner in zip(me.polygons, owners):
        row = []
        for original in face.vertices:
            key = (int(owner), int(original))
            if key not in lookup:
                lookup[key] = len(point_ids)
                point_ids.append(int(original)); point_parts.append(int(owner))
                sharing.setdefault(int(original), set()).add(int(owner))
            row.append(lookup[key])
        faces.append(row)
    point_ids = np.array(point_ids, dtype=np.int32)
    source_seams = [{'source_vertex': i, 'parts': [mapping[a], mapping[b]]}
                    for i, parts in sorted(sharing.items()) for a, b in itertools.combinations(sorted(parts), 2)]
    # Read every supported custom layer before allocation/publication.
    layers = [(a.name, a.data_type, a.domain, _attribute_values(a)) for a in me.attributes if a.name not in _INTRINSIC and a.name != 'custom_normal']
    if any(domain not in {'POINT', 'EDGE', 'FACE', 'CORNER'} for _, _, domain, _ in layers):
        raise C.FeatureError('unsupported attribute domain: preserve it through an explicit supported source preparation')
    source_hash = mesh_hash(src)
    new = None; out = None
    try:
        new = me.copy(); new.clear_geometry()
        new.from_pydata(old_points[point_ids].tolist(), [], faces); new.update()
        original_edges = {tuple(sorted(e.vertices)): e.index for e in me.edges}
        edge_ids = np.array([original_edges[tuple(sorted(int(point_ids[i]) for i in e.vertices))] for e in new.edges], dtype=np.int32)
        indices = {'POINT': point_ids, 'EDGE': edge_ids, 'FACE': np.arange(len(me.polygons)), 'CORNER': np.arange(len(me.loops))}
        for name, kind, domain, payload in layers:
            if payload is None:
                continue
            field, values = payload
            target = new.attributes.get(name) or new.attributes.new(name, kind, domain)
            if target.data_type != kind or target.domain != domain:
                raise C.FeatureError(f'copied attribute {name} changed type/domain')
            expected = values[indices[domain]].ravel()
            target.data.foreach_set(field, expected)
            actual = np.empty_like(expected); target.data.foreach_get(field, actual)
            if not np.array_equal(expected, actual):
                raise C.FeatureError(f'copied attribute {name} changed values; no prepared object published')
        for old, copied in zip(me.polygons, new.polygons):
            copied.material_index = old.material_index
            copied.use_smooth = old.use_smooth
        # Packed normal coordinates depend on the old smooth-fan basis. Transport
        # world-independent corner vectors, not those packed coordinates.
        normal_control = me.copy()
        try:
            normal_control.normals_split_custom_set(source_normals.tolist())
            control_vectors = np.array([n.vector[:] for n in normal_control.corner_normals], dtype=np.float32)
            source_roundtrip_delta = float(np.linalg.norm(control_vectors-source_normals, axis=1).max())
        finally:
            bpy.data.meshes.remove(normal_control)
        new.normals_split_custom_set(source_normals.tolist())
        decoded = np.array([n.vector[:] for n in new.corner_normals], dtype=np.float32)
        normal_delta = float(np.linalg.norm(decoded-source_normals, axis=1).max())
        preserved = new.attributes.new(_NORMAL_ATTR, 'FLOAT_VECTOR', 'CORNER')
        preserved.data.foreach_set('vector', source_normals.ravel())
        observed = np.empty_like(source_normals); preserved.data.foreach_get('vector', observed.ravel())
        if not np.array_equal(observed, source_normals):
            raise C.FeatureError('source corner normal provenance changed; no output published')
        for old in me.uv_layers:
            uv = new.uv_layers.get(old.name) or new.uv_layers.new(name=old.name)
            uv.active_render = old.active_render
        if me.uv_layers.active:
            new.uv_layers.active = new.uv_layers[me.uv_layers.active.name]
        for name, domain, ids in [(_ID_ATTRS[0], 'POINT', point_ids), (_ID_ATTRS[1], 'FACE', np.arange(len(me.polygons), dtype=np.int32))]:
            new.attributes.new(name, 'INT', domain).data.foreach_set('value', ids)
        if len(new.polygons) != len(me.polygons) or any(tuple(int(point_ids[i]) for i in f.vertices) != tuple(me.polygons[f.index].vertices) for f in new.polygons):
            raise C.FeatureError('prepared face/corner identity mismatch; no output published')
        if not np.array_equal(np.array([v.co[:] for v in new.vertices], dtype=np.float32), old_points[point_ids]):
            raise C.FeatureError('prepared coordinates changed; no output published')
        receipt = {'schema': 'lampway.authored-part-copy/1', 'source': src.name, 'source_sha256': source_hash,
                   'source_ownership_sha256': hashlib.sha256(owners.astype(np.int32).tobytes()).hexdigest(),
                   'recipe': spec['recipe'], 'recipe_sha256': hashlib.sha256(Path(recipe_path).read_bytes()).hexdigest(), 'face_attribute': attr.name,
                   'part_names': {str(k): v for k, v in sorted(mapping.items())}, 'source_seams': source_seams,
                   'omitted_faceless_source_vertices': sorted(set(range(len(me.vertices)))-set(point_ids.tolist())),
                   'physical_status': 'unreviewed', 'separation_accepts_open_seams': False,
                   'source_corner_normal_attribute': _NORMAL_ATTR, 'source_corner_vectors_exact': True,
                   'native_decoded_normal_max_vector_delta': normal_delta,
                   'source_normal_writer_roundtrip_max_vector_delta': source_roundtrip_delta,
                   'decoded_normal_equivalence': 'not certified; measured native encoding quantization, physical/render review required'}
        out = src.copy(); out.data = new
        out.name = src.name+'_partcopy'; new.name = out.name
        for group in list(out.vertex_groups):
            out.vertex_groups.remove(group)
        for owner, name in sorted(mapping.items()):
            group = out.vertex_groups.new(name=name)
            group.add([i for i, p in enumerate(point_parts) if p == owner], 1.0, 'REPLACE')
        # The source topology stamp cannot certify a newly separated topology.
        if 'lw_canon' in out:
            del out['lw_canon']
        receipt['output_sha256'] = mesh_hash(out)
        receipt['output_topology_sha256'] = _topology_pin(out, attr.name)
        out['lw_authored_part_copy'] = json.dumps(receipt, sort_keys=True)
        bpy.context.scene.collection.objects.link(out)
        return {'ok': True, 'object': out.name, 'source': src.name, 'vertices': len(new.vertices), 'faces': len(new.polygons),
                'parts': len(mapping), 'source_seam_pairs': len(source_seams), 'source_vertex_attribute': _ID_ATTRS[0],
                'source_face_attribute': _ID_ATTRS[1], 'omitted_faceless_vertices': len(receipt['omitted_faceless_source_vertices']),
                'source_sha256': source_hash, 'output_sha256': receipt['output_sha256'], 'physical_status': 'unreviewed',
                'native_decoded_normal_max_vector_delta': normal_delta,
                'source_normal_writer_roundtrip_max_vector_delta': source_roundtrip_delta,
                'note': 'Prepared ownership copy only; source seam/opening gates remain required'}
    except Exception:
        if out is not None:
            bpy.data.objects.remove(out, do_unlink=True)
        if new is not None and new.users == 0:
            bpy.data.meshes.remove(new)
        raise


def _topology_pin(ob, face_attribute="part"):
    h = hashlib.sha256()
    for name in (*_ID_ATTRS, face_attribute):
        attr = ob.data.attributes.get(name)
        if attr is not None:
            h.update(name.encode())
            h.update(np.array([x.value for x in attr.data], dtype=np.int32).tobytes())
    h.update(np.array([l.vertex_index for l in ob.data.loops], dtype=np.int32).tobytes())
    h.update(json.dumps({g.name: [v.index for v in ob.data.vertices if any(x.group == g.index and x.weight > 0 for x in v.groups)]
                         for g in ob.vertex_groups}, sort_keys=True).encode())
    return h.hexdigest()


def source_seams(ob, root):
    """Validate copied identity/ownership and retain the actual original source seam ledger."""
    if 'lw_authored_part_copy' not in ob:
        return {}, None
    try:
        receipt = json.loads(ob['lw_authored_part_copy'])
        for name, domain in [(_ID_ATTRS[0], 'POINT'), (_ID_ATTRS[1], 'FACE'), (receipt['face_attribute'], 'FACE')]:
            attr = ob.data.attributes.get(name)
            if attr is None or attr.data_type != 'INT' or attr.domain != domain:
                raise ValueError('copied identity/ownership attribute changed type/domain')
        if receipt['schema'] != 'lampway.authored-part-copy/1' or receipt['output_topology_sha256'] != _topology_pin(ob, receipt['face_attribute']):
            raise ValueError('stale copied topology/ownership')
        src = bpy.data.objects.get(receipt['source'])
        if src is None or src.type != 'MESH' or mesh_hash(src) != receipt['source_sha256']:
            raise ValueError('original source missing or changed')
        from ..settings import resolve_in_root
        recipe = resolve_in_root(receipt['recipe'], root)
        if hashlib.sha256(recipe.read_bytes()).hexdigest() != receipt['recipe_sha256']:
            raise ValueError('source recipe changed')
        source_owner = src.data.attributes[receipt['face_attribute']]
        if source_owner.domain != 'FACE' or source_owner.data_type != 'INT':
            raise ValueError('source ownership attribute changed type/domain')
        original_owners = np.array([x.value for x in source_owner.data], dtype=np.int32)
        if hashlib.sha256(original_owners.tobytes()).hexdigest() != receipt['source_ownership_sha256']:
            raise ValueError('original source ownership changed')
        if not np.array_equal(original_owners, np.array([x.value for x in ob.data.attributes[receipt['face_attribute']].data], dtype=np.int32)):
            raise ValueError('copied face ownership changed')
        mapping = _mapping({'part_names': receipt['part_names']}, recipe, original_owners, len(receipt['part_names']))
        ids = np.array([x.value for x in ob.data.attributes[_ID_ATTRS[0]].data], dtype=np.int32)
        faces = np.array([x.value for x in ob.data.attributes[_ID_ATTRS[1]].data], dtype=np.int32)
        if not np.array_equal(faces, np.arange(len(src.data.polygons))) or len(faces) != len(ob.data.polygons):
            raise ValueError('source face identities changed')
        if len(ids) != len(ob.data.vertices) or (ids < 0).any() or (ids >= len(src.data.vertices)).any():
            raise ValueError('source vertex identities changed')
        sharing = {}
        for f in ob.data.polygons:
            original = src.data.polygons[f.index]
            if tuple(int(ids[i]) for i in f.vertices) != tuple(original.vertices):
                raise ValueError('face corner ownership changed')
            owner = int(original_owners[f.index])
            for i in original.vertices:
                sharing.setdefault(int(i), set()).add(owner)
        expected = [{'source_vertex': i, 'parts': [mapping[a], mapping[b]]}
                    for i, parts in sorted(sharing.items()) for a, b in itertools.combinations(sorted(parts), 2)]
        if expected != receipt['source_seams']:
            raise ValueError('original seam ledger changed')
        seams = {}
        for row in expected:
            seams.setdefault(tuple(sorted(row['parts'])), set()).add(row['source_vertex'])
        return seams, ids
    except (KeyError, TypeError, ValueError, OSError) as e:
        raise C.FeatureError(f'authored part copy has invalid source identity/seam provenance ({e}); re-run lampway_segment_mesh from the unchanged original ownership/recipe') from e
