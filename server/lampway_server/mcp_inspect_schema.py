# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small input contract and per-view field reference for read-only inspection."""
VIEWS = ['scene', 'objects', 'object', 'mesh', 'uv', 'parts', 'layers', 'relations', 'file', 'schema', 'help']
INPUT_SCHEMA = {'type': 'object', 'additionalProperties': False, 'properties': {
    'view': {'type': 'string', 'enum': VIEWS}, 'name': {'type': 'string'},
    'names': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 200},
    'collection': {'type': 'string'}, 'match': {'type': 'string'},
    'fields': {'type': 'array', 'items': {'type': 'string'}},
    'limit': {'type': 'integer', 'minimum': 1, 'maximum': 1000, 'default': 50},
    'offset': {'type': 'integer', 'minimum': 0, 'default': 0},
    'full': {'type': 'boolean', 'default': False}, 'evaluated': {'type': 'boolean', 'default': False},
    'method': {'type': 'string', 'enum': ['shells', 'sharp', 'uv_islands', 'materials'], 'default': 'shells'},
    'angle': {'type': 'number', 'minimum': 1, 'maximum': 179, 'default': 40},
    'deep': {'type': 'boolean', 'default': False},
    'texture_size': {'type': 'integer', 'enum': [256, 512, 1024, 2048, 4096, 8192, 16384], 'default': 2048},
    'tolerance_m': {'type': 'number', 'minimum': 0, 'maximum': 1, 'default': 0.005},
    'budget_ms': {'type': 'integer', 'minimum': 100, 'maximum': 60000, 'default': 2000}}}
FIELDS = {
    'objects': ['name', 'type', 'tris', 'parent', 'collection', 'location', 'rotation_deg', 'scale', 'size', 'bounds', 'verts', 'faces', 'materials', 'modifiers', 'hidden', 'selected', 'uv_layers', 'vertex_groups', 'armature', 'canon'],
    'relations': ['a', 'b', 'relation', 'gap_m', 'size_ratio', 'height_ratio', 'overlap_fraction', 'aligned_axes'],
    'shells': ['id', 'faces', 'closed', 'area_m2'],
    'holes': ['id', 'edges', 'rim_length_m', 'centroid', 'normal'],
    'parts': ['id', 'faces', 'area_m2', 'material', 'bounds', 'centroid'],
    'layers': ['index', 'name', 'type', 'blend', 'opacity', 'enabled', 'channels', 'mask'],
    'islands': ['id', 'faces', 'uv_area', 'density_px_m', 'bounds', 'tiles'],
    'intersections': ['id', 'kind', 'descriptor', 'severity', 'rule_verdict', 'rule'],
    'thin_regions': ['id', 'kind', 'descriptor', 'severity', 'rule_verdict', 'rule'],
}
DEFAULT_FIELDS = {key: fields[:4] for key, fields in FIELDS.items()}
DEFAULT_FIELDS['shells'] = ['id', 'faces', 'closed']
DEFAULT_FIELDS['holes'] = ['id', 'edges', 'rim_length_m']



def _object(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required)}


def _array(items):
    return {'type': 'array', 'items': items}


def _nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


_STRING = {'type': 'string'}
_NUMBER = {'type': 'number'}
_COUNT = {'type': 'integer', 'minimum': 0}
_BOOL = {'type': 'boolean'}
_VECTOR = {**_array(_NUMBER), 'minItems': 3, 'maxItems': 3}
_BOUNDS = _object({'min': _VECTOR, 'max': _VECTOR}, ['min', 'max'])
_CANON = _object({'state': {'enum': ['canonical', 'raw', 'unstamped', 'invalid_stamp']},
                  'kind': _nullable(_STRING), 'scale': {'type': ['object', 'string', 'number', 'null']}}, ['state'])
_OBJECT_FIELDS = {
    'name': _STRING, 'type': _STRING, 'tris': _COUNT, 'parent': _nullable(_STRING),
    'collection': _array(_STRING), 'location': _VECTOR, 'rotation_deg': _VECTOR,
    'scale': _VECTOR, 'size': _VECTOR, 'bounds': _BOUNDS, 'verts': _COUNT, 'faces': _COUNT,
    'materials': _array(_nullable(_STRING)), 'modifiers': _array(_STRING),
    'hidden': _BOOL, 'selected': _BOOL, 'uv_layers': _array(_STRING),
    'vertex_groups': _array(_STRING), 'armature': _nullable(_STRING), 'canon': _CANON,
}
_PAINT_LAYER = _object({
    'index': _COUNT, 'name': _STRING, 'type': _STRING, 'blend': _STRING,
    'opacity': _NUMBER, 'enabled': _BOOL, 'channels': _array(_STRING),
    'mask': _nullable(_object({'type': _STRING, 'name': _STRING, 'blend': _nullable(_STRING), 'invert': _BOOL})),
})
_UV_LAYER = _object({'name': _STRING, 'active': _BOOL})
_ISLAND = _object({'id': _COUNT, 'faces': _COUNT, 'uv_area': _NUMBER,
                   'density_px_m': _nullable(_NUMBER), 'bounds': _array(_NUMBER), 'tiles': _array(_COUNT)})
_COLLECTION = _object({'name': _STRING, 'objects': _COUNT, 'hidden': _BOOL,
                       'children': _array({'$ref': '#/$defs/collection'})})


_DEFECT = _object({'id': _STRING, 'kind': _STRING, 'severity': _STRING,
                   'rule_verdict': _STRING, 'rule': _STRING,
                   'descriptor': _object({'faces': _COUNT, 'area_m2': _NUMBER,
                       'centroid': _VECTOR, 'bbox': _array(_NUMBER), 'normal': _VECTOR,
                       'rim_length_m': _NUMBER, 'shells': _array(_COUNT)})})


def _view_data(view):
    if view == 'home':
        return _object({'file': _nullable(_STRING), 'unsaved': _BOOL, 'units': {'const': 'm'},
                        'counts': _object({key: _COUNT for key in ('objects', 'meshes', 'lights', 'cameras', 'materials', 'images')}),
                        'tris_total': _COUNT, 'selected': _array(_STRING), 'active': _nullable(_STRING),
                        'warnings': _array(_object({'kind': _STRING, 'count': _COUNT}))})
    if view == 'scene':
        return _object({'collections': {'$ref': '#/$defs/collection'},
                        'cameras': _array(_object({'name': _STRING, 'lens_mm': _NUMBER, 'sensor_mm': _NUMBER,
                                                  'clip_start': _NUMBER, 'clip_end': _NUMBER})),
                        'lights': _array(_object({'name': _STRING, 'type': _STRING, 'energy_w': _NUMBER,
                                                 'color': _VECTOR, 'size_m': _NUMBER})),
                        'world': _object({'hdri': _nullable(_STRING), 'strength': _nullable(_NUMBER)}),
                        'frames': _object({key: {'type': 'integer'} for key in ('start', 'end', 'current')} | {'fps': _NUMBER}),
                        'render': _object({'engine': _STRING, 'resolution': {**_array(_COUNT), 'minItems': 2, 'maxItems': 2}, 'percentage': _COUNT, 'resolution_percentage': _COUNT})})
    if view == 'objects':
        return _object({'objects': _array(_object(_OBJECT_FIELDS))})
    if view == 'object':
        return _object({**_OBJECT_FIELDS,
                        'modifiers': _array(_object({'name': _STRING, 'type': _STRING, 'show_viewport': _BOOL})),
                        'constraints': _array(_object({'name': _STRING, 'type': _STRING, 'target': _nullable(_STRING)})),
                        'materials': _array(_object({'slot': _COUNT, 'name': _nullable(_STRING), 'link': _STRING})),
                        'collections': _array(_STRING), 'children': _array(_STRING),
                        'layers': _object({'count': _COUNT, 'top': _nullable(_PAINT_LAYER)})})
    if view == 'mesh':
        return _object({'object': _STRING, 'canon': _CANON,
                        'counts': _object({key: _COUNT for key in ('verts', 'edges', 'faces', 'tris', 'quads', 'ngons', 'loose_verts', 'loose_edges')}),
                        'manifold': _object({'non_manifold_edges': _COUNT, 'boundary_edges': _COUNT}),
                        'shells': _array(_object({'id': _COUNT, 'faces': _COUNT, 'closed': _BOOL, 'area_m2': _NUMBER})),
                        'holes': _array(_object({'id': _COUNT, 'edges': _COUNT, 'rim_length_m': _NUMBER,
                                                'centroid': _object(dict.fromkeys('xyz', _NUMBER)),
                                                'normal': _object(dict.fromkeys('xyz', _NUMBER))})),
                        'defects': _object({'degenerate': _COUNT, 'isolated_tri': _COUNT, 'flipped_shells': _nullable(_COUNT)}),
                        'holes_total': _COUNT, 'intersections': _array(_DEFECT), 'thin_regions': _array(_DEFECT),
                        'intersections_total': _COUNT, 'thin_regions_total': _COUNT})
    if view == 'uv':
        return _object({'object': _STRING, 'canon': _CANON, 'layers': _array(_UV_LAYER),
                        'islands': _array(_ISLAND), 'islands_total': _COUNT,
                        'utilization': _NUMBER, 'overlap_fraction': _NUMBER, 'flipped_faces': _COUNT,
                        'seam_length_m': _NUMBER,
                        'density': _object({'mean_px_m': _nullable(_NUMBER), 'cv': _nullable(_NUMBER)}),
                        'tiles': _array(_COUNT), 'crossing_tiles': _COUNT})
    if view == 'parts':
        return _object({'object': _STRING, 'canon': _CANON, 'method': INPUT_SCHEMA['properties']['method'],
                        'parts': _array(_object({'id': _COUNT, 'faces': _COUNT, 'area_m2': _NUMBER,
                                                'material': _nullable(_COUNT), 'bounds': _BOUNDS, 'centroid': _VECTOR}))})
    if view == 'layers':
        return _object({'object': _STRING, 'canon': _CANON, 'layers': _array(_PAINT_LAYER),
                        'material': _nullable(_STRING), 'active_layer_index': {'type': 'integer', 'minimum': -1}})
    if view == 'relations':
        return _object({'pairs': _array(_object({'a': _STRING, 'b': _STRING,
            'relation': {'enum': ['inside', 'overlaps', 'on_top_of', 'under', 'touching', 'near', 'apart']},
            'gap_m': _NUMBER, 'size_ratio': _nullable(_NUMBER), 'height_ratio': _nullable(_NUMBER),
            'overlap_fraction': _NUMBER, 'aligned_axes': _array({'type': 'integer', 'minimum': 0, 'maximum': 2})}))})
    if view == 'file':
        return _object({'path': _nullable(_STRING), 'unsaved': _BOOL, 'saved_age_s': _nullable(_NUMBER),
                        'backups': _array(_object({'path': _STRING, 'age_seconds': _NUMBER, 'size_bytes': _COUNT})),
                        'datablocks': {'type': 'object', 'additionalProperties': _COUNT},
                        'missing_files': _array(_object({'kind': _STRING, 'name': _STRING, 'path': _STRING})),
                        'libraries': _array(_object({'name': _STRING, 'path': _STRING, 'indirect': _BOOL})),
                        'usage_guess': _array(_object({'use': _STRING, 'score': _NUMBER}))})
    if view == 'help':
        return _object({'view': _STRING, 'arguments': {'type': 'object'}, 'defaults': {'type': 'object'},
                        'fields': {'type': ['object', 'array']}, 'refusals': _array(_STRING)})
    if view == 'schema':
        return _object({'$schema': _STRING, 'title': _STRING, 'type': _STRING, 'properties': {'type': 'object'},
                        'required': _array(_STRING), '$defs': {'type': 'object'}})
    raise ValueError('Unknown inspection view: ' + str(view))


def view_schema(view):
    """Typed per-view data; projected rows may omit unrequested columns.

    Skipped computations may omit sections; every section which is present
    retains its types. The small tools/list envelope is defined separately.
    """
    from copy import deepcopy
    data = _view_data(view)
    required = {
        'home': ['file', 'unsaved', 'units', 'counts', 'tris_total', 'selected', 'active', 'warnings'],
        'scene': ['collections', 'cameras', 'lights', 'world', 'frames', 'render'],
        'objects': ['objects'], 'object': ['name', 'type', 'bounds', 'canon'],
        'mesh': ['counts', 'manifold', 'shells', 'holes', 'defects'],
        'uv': ['layers', 'islands', 'islands_total'], 'parts': ['parts', 'method'],
        'layers': ['layers'], 'relations': ['pairs'],
        'file': ['path', 'unsaved', 'saved_age_s', 'backups', 'datablocks', 'missing_files', 'libraries', 'usage_guess'],
        'help': ['view', 'arguments', 'defaults', 'fields', 'refusals'],
        'schema': ['$schema', 'title', 'type', 'properties', 'required'],
    }[view]
    result = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
              '$comment': 'Generated from inspect/schema.py. SPDX-FileCopyrightText: 2026 Lampway contributors; SPDX-License-Identifier: GPL-3.0-or-later',
              'title': 'lampway_inspect ' + view, 'type': 'object',
              'properties': {'ok': _BOOL, 'tool': {'const': 'lampway_inspect'}, 'description': _STRING,
                             'view': {'const': view}, 'scene': _STRING, 'count': _COUNT, 'total': _COUNT,
                             'data': data,
                             'skipped': _array(_object({'object': _STRING, 'section': _STRING, 'reason': _STRING}, ['object', 'section', 'reason'])),
                             'help': _array(_STRING)},
              'required': ['view', 'scene', 'count', 'total', 'data', 'skipped', 'help'],
              'if': {'properties': {'skipped': {'maxItems': 0}}},
              'then': {'properties': {'data': {'required': required}}}}
    if view == 'scene':
        result['$defs'] = {'collection': _COLLECTION}
    return deepcopy(result)


def reference_fields(view):
    """Enumerate the actual per-view list columns, including nested sections."""
    result = {}
    def visit(node):
        for name, child in node.get('properties', {}).items():
            if child.get('type') == 'array':
                columns = child.get('items', {}).get('properties', {})
                if columns:
                    result[name] = list(columns)
                visit(child.get('items', {}))
            else:
                visit(child)
    visit(view_schema(view)['properties']['data'])
    return result


def generate_schemas(directory, *, check=False):
    """Deterministic artifacts with a stale-file check; independent of Blender."""
    import json
    from pathlib import Path
    directory = Path(directory)
    expected = {view + '.schema.json': json.dumps(view_schema(view), indent=2, sort_keys=True) + '\n'
                for view in ['home', *VIEWS]}
    stale = [name for name, text in expected.items()
             if not (directory / name).exists() or (directory / name).read_text() != text]
    stale += [path.name for path in directory.glob('*.schema.json') if path.name not in expected]
    if check:
        return sorted(stale)
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in expected.items():
        (directory / name).write_text(text)
    return sorted(stale)


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Generate T1 per-view JSON schemas')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[6] / 'docs/schemas/inspect')
    options = parser.parse_args()
    stale = generate_schemas(options.output, check=options.check)
    if options.check and stale:
        print('Stale inspection schemas: ' + ', '.join(stale))
        raise SystemExit(1)
