# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""T1 orchestration: validated, read-only views of the executor-bound scene."""
import copy
import json
import time

import bpy
from jsonschema import Draft202012Validator

from . import schema
from .. import settings


class InspectError(ValueError):
    def __init__(self, code, message, help_=None):
        self.code, self.help = code, help_ or ['lampway_inspect view=help']
        super().__init__(message)


class BudgetExpired(Exception):
    pass


class Budget:
    def __init__(self, milliseconds):
        self.deadline = time.monotonic() + milliseconds / 1000

    @property
    def remaining(self):
        return max(0.0, self.deadline - time.monotonic())

    def admit_geometry(self, mesh):
        """Reserve conservative headroom before indivisible RNA/BMesh/BVH calls.

        Native mesh conversion cannot be interrupted by Python. Counts are O(1)
        RNA reads; admission precedes even content hashing and evaluated_get.
        This is a work bound, not a substitute for checks inside Python loops.
        """
        self.check()
        work = (4 * len(mesh.vertices) + 3 * len(mesh.edges)
                + len(mesh.loops) + 20 * len(mesh.polygons))
        if work / 3_000_000 > self.remaining:
            raise BudgetExpired

    def check(self):
        if time.monotonic() > self.deadline:
            raise BudgetExpired


def template(view, name=None, **kwargs):
    parts = ['lampway_inspect', 'view=' + view]
    if name:
        kwargs = {'name': name, **kwargs}
    for key, value in kwargs.items():
        if isinstance(value, (list, tuple)):
            value = '<' + key + '>'  # typed arrays remain placeholders in call templates
        literal = str(value).lower() if isinstance(value, bool) else str(value)
        parts.append(key + '=' + (json.dumps(literal) if any(c.isspace() for c in literal) else literal))
    return ' '.join(parts)


def _fixed_filters(args):
    return {key: args[key] for key in ('names', 'collection', 'match', 'fields', 'evaluated') if key in args}


def _list_columns(data_schema):
    columns = set()
    if data_schema.get('type') == 'array':
        columns.update(data_schema.get('items', {}).get('properties', {}))
    for child in data_schema.get('properties', {}).values():
        columns.update(_list_columns(child))
    return columns


def _page_logical_lists(data, args):
    """Page logical lists, leaving coordinates and already-paged sections intact."""
    if not isinstance(data, dict):
        return
    vectors = {'location', 'rotation_deg', 'scale', 'size', 'min', 'max', 'color', 'centroid', 'normal', 'bbox', 'bounds', 'resolution', 'aligned_axes'}
    for section, value in list(data.items()):
        if isinstance(value, dict):
            _page_logical_lists(value, args)
        elif isinstance(value, list) and section not in vectors and section != 'skipped':
            if section + '_total' in data:
                continue
            offset, limit = args.get('offset', 0), args.get('limit', 50)
            rows = value[offset:offset + limit]
            if rows and all(isinstance(row, dict) for row in rows):
                known = set().union(*(set(row) for row in rows))
                requested = args.get('fields') or []
                fields = list(requested) if requested == ['*'] else [field for field in requested if field in known]
                if not fields:
                    fields = list(rows[0])[:4]
                if fields != ['*']:
                    rows = [{key: row[key] for key in fields if key in row} for row in rows]
                for row in rows:
                    _page_logical_lists(row, args)
            data[section], data[section + '_count'], data[section + '_total'] = rows, len(rows), len(value)


def _page(rows, section, args):
    primary = {'mesh': 'holes', 'uv': 'islands', 'parts': 'parts', 'layers': 'layers',
               'objects': 'objects', 'relations': 'relations'}.get(args.get('view'))
    fields = (args.get('fields') if section == primary else None) or schema.DEFAULT_FIELDS.get(section)
    known = schema.FIELDS.get(section)
    if args.get('view') == 'uv' and section == 'layers':
        fields, known = ['name', 'active'], ['name', 'active']
    if known and fields and fields != ['*']:
        unknown = set(fields) - set(known)
        if unknown:
            raise InspectError('unknown_field', 'Unknown field: ' + ', '.join(sorted(unknown)),
                               [template('help', args.get('view') or 'objects')])
    offset, limit = args.get('offset', 0), args.get('limit', 50)
    paged = rows[offset:offset + limit]
    if fields and fields != ['*'] and all(isinstance(row, dict) for row in paged):
        paged = [{key: row.get(key) for key in fields} for row in paged]
    return paged, len(rows)


def _objects(scene, args):
    objects = list(scene.objects)
    if args.get('names') is not None:
        requested = args['names']
        absent = [name for name in requested if scene.objects.get(name) is None]
        if absent:
            raise InspectError('not_found', 'No object named ' + absent[0], [template('objects', match='<name>')])
        objects = [scene.objects[name] for name in requested]
    elif args.get('view') in ('objects', 'relations'):
        selected = [ob for ob in objects if ob.select_get()]
        objects = selected or objects
    if args.get('collection'):
        collection = bpy.data.collections.get(args['collection'])
        if collection is None:
            raise InspectError('not_found', 'No collection named ' + args['collection'], [template('scene')])
        objects = [ob for ob in objects if ob.name in collection.all_objects]
    if args.get('match'):
        objects = [ob for ob in objects if args['match'].casefold() in ob.name.casefold()]
    if args.get('view') == 'relations' and len(objects) > 200:
        raise InspectError('bad_argument', 'relations accepts at most 200 objects; pass names or collection', [template('objects')])
    return objects


def _named(scene, args):
    name = args.get('name')
    if not name:
        raise InspectError('bad_argument', 'name is required for this view', [template('objects')])
    ob = scene.objects.get(name)
    if ob is None:
        raise InspectError('not_found', 'No object named ' + name, [template('objects', match='<name>')])
    if args['view'] in ('mesh', 'uv', 'parts', 'layers') and ob.type != 'MESH':
        raise InspectError('wrong_type', name + ' is ' + ob.type + ', not MESH', [template('object', name)])
    return ob


def _render_busy():
    from mixar.modules.common.render_coordinator import core as RC
    return RC.busy() or RC.native_render_kind() is not None


def run(**args):
    unknown = set(args) - set(schema.INPUT_SCHEMA['properties'])
    if unknown:
        return {'ok': False, 'error': 'Unknown argument: ' + ', '.join(sorted(unknown)),
                'code': 'unknown_argument', 'help': [template('help')]}
    error = next(iter(Draft202012Validator(schema.INPUT_SCHEMA).iter_errors(args)), None)
    if error:
        return {'ok': False, 'error': error.message, 'code': 'bad_argument', 'help': [template('help')]}
    scene = bpy.context.scene  # the script executor has already bound the requested scene tab
    view = args.get('view') or 'home'
    scale = float(scene.unit_settings.scale_length)
    result = {'ok': True, 'tool': 'lampway_inspect', 'description': 'Read the open scene as typed data; never edits it',
              'view': view, 'scene': scene.name, 'count': 0, 'total': 0, 'data': {}, 'skipped': [], 'help': []}
    budget = Budget(args.get('budget_ms', 2000))
    try:
        if args.get('fields') and args['fields'] != ['*'] and view not in ('schema', 'help'):
            known = _list_columns(schema.view_schema(view)['properties']['data'])
            known.update(schema.FIELDS.get('objects' if view == 'object' else view, []))
            unknown_fields = set(args['fields']) - known
            if unknown_fields:
                raise InspectError('unknown_field', 'Unknown field: ' + ', '.join(sorted(unknown_fields)), [template('help', view)])
        if args.get('evaluated') and _render_busy():
            raise InspectError('render_in_progress', 'Evaluated measurements cannot run during a render',
                               ['lampway_job_status'])
        if view in ('help', 'schema'):
            name = args.get('name') or 'home'
            if name not in ['home', *schema.VIEWS]:
                raise InspectError('bad_argument', 'name must be an inspection view', [template('help')])
            result['data'] = (schema.view_schema(name) if view == 'schema' else {
                'view': name, 'arguments': schema.INPUT_SCHEMA['properties'],
                'defaults': {key: value['default'] for key, value in schema.INPUT_SCHEMA['properties'].items() if 'default' in value},
                'fields': schema.reference_fields(name),
                'refusals': ['unknown_argument', 'unknown_field', 'bad_argument', 'not_found', 'wrong_type', 'render_in_progress']})
            result['help'] = [template(name, '<name>') if name in ('object', 'mesh', 'uv', 'parts', 'layers') else template(name)]
        elif view in ('home', 'scene'):
            from . import home
            result['data'] = home.dashboard(scene) if view == 'home' else home.scene_data(scene, scale)
            result['count'] = result['total'] = len(scene.objects)
            result['help'] = [template('objects'), template('object', '<name>'), template('file')]
        elif view == 'objects':
            from . import objects
            rows = []
            for ob in _objects(scene, args):
                budget.check()
                rows.append(objects.row(ob, scale, args.get('evaluated', False)))
            result['data']['objects'], result['total'] = _page(rows, 'objects', args)
            result['count'] = len(result['data']['objects'])
            result['help'] = [template('objects', offset=args.get('offset', 0) + result['count'], **_fixed_filters(args)), template('object', '<name>')]
        elif view == 'relations':
            from . import relations
            selected = _objects(scene, args)
            pairs = relations.measure(selected, scene, args.get('tolerance_m', .005),
                                      budget=budget, evaluated=args.get('evaluated', False),
                                      deep=args.get('deep', False))
            pairs.sort(key=lambda row: (row['gap_m'], row['a'], row['b']))
            result['data']['pairs'], result['total'] = _page(pairs, 'relations', args)
            result['count'] = len(result['data']['pairs'])
            result['help'] = [template('relations', offset=args.get('offset', 0) + result['count'], **_fixed_filters(args)), template('object', '<name>')]
        elif view == 'file':
            from . import filemeta
            data = filemeta.measure(settings.load().project_root)
            for section in ('backups', 'missing_files', 'libraries', 'usage_guess'):
                data[section], total = _page(data[section], section, args)
                data[section + '_count'], data[section + '_total'] = len(data[section]), total
            result['data'] = data
            result['count'] = result['total'] = len(bpy.data.objects)
            result['help'] = [template('scene'), template('objects')]
        else:
            from . import objects, cache
            ob = _named(scene, args)
            if view == 'object':
                result['data'] = objects.detail(ob, scale, args.get('evaluated', False))
                from . import layers
                layer_rows = []
                if ob.type == 'MESH':
                    layer_rows = layers.measure(ob)['layers']
                result['data']['layers'] = {'count': len(layer_rows), 'top': layer_rows[-1] if layer_rows else None}
                result['count'] = result['total'] = 1
            else:
                if view == 'layers':
                    from . import layers
                    data = layers.measure(ob)
                else:
                    budget.admit_geometry(ob.data)
                    measured = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()) if args.get('evaluated') else ob
                    budget.admit_geometry(measured.data)
                    key = cache.key(measured, args.get('evaluated', False), scale,
                                    [view, args.get('deep', False), args.get('texture_size', 2048), args.get('method', 'shells'), args.get('angle', 40)], budget=budget)
                    budget.check()
                    if view == 'mesh':
                        from . import mesh
                        data = cache.get_or_compute(key, lambda: mesh.measure(measured, scale, args.get('deep', False), budget=budget), budget=budget)
                    elif view == 'uv':
                        from . import uv
                        data = cache.get_or_compute(key, lambda: uv.measure(measured, scale, args.get('texture_size', 2048), budget=budget), budget=budget)
                    else:
                        from . import parts
                        data = cache.get_or_compute(key, lambda: parts.measure(measured, scale, args.get('method', 'shells'), args.get('angle', 40), budget=budget), budget=budget)
                primary = {'mesh': 'holes', 'uv': 'islands', 'parts': 'parts', 'layers': 'layers'}[view]
                result['skipped'].extend(data.pop('skipped', []))
                for section, rows in list(data.items()):
                    if isinstance(rows, list):
                        data[section], total = _page(rows, section, args)
                        data[section + '_count'], data[section + '_total'] = len(data[section]), total
                result['data'] = data
                result['count'], result['total'] = data[primary + '_count'], data[primary + '_total']
            result['data']['canon'] = objects.canon(ob)
            result['help'] = [template('help', view), template('object', ob.name)]
            if view == 'uv' and not result['data']['layers']:
                result['help'].append('lampway_uv_unwrap object=' + json.dumps(ob.name))
            if view == 'layers' and not result['data']['layers']:
                result['help'].append('lampway_layered_material action=init object=' + json.dumps(ob.name))
        if view not in ('schema', 'help'):
            _page_logical_lists(result['data'], args)
        if result['skipped']:
            result['help'].append(template(view, args.get('name')))
        budget.check()
    except BudgetExpired:
        result['skipped'].append({'object': args.get('name') or '', 'section': view, 'reason': 'budget_ms exceeded'})
        retry_args = {key: value for key, value in args.items() if key not in ('view', 'name', 'budget_ms')}
        result['help'].append(template(view, args.get('name'), **retry_args, budget_ms='<more>'))
    except InspectError as exc:
        return {'ok': False, 'error': str(exc), 'code': exc.code, 'help': exc.help}
    except ValueError as exc:
        return {'ok': False, 'error': str(exc), 'code': 'bad_argument', 'help': [template('help', view)]}
    return result
