# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""L1 object facts, read from the executor's bound scene."""
import json
import math


def canon(ob):
    raw = ob.get('lw_canon')
    if raw:
        try:
            document = json.loads(raw) if isinstance(raw, str) else dict(raw)
            return {'state': 'canonical', 'kind': document.get('kind'), 'scale': document.get('scale')}
        except (ValueError, TypeError):
            return {'state': 'invalid_stamp'}
    return {'state': 'raw' if ob.get('lw_raw') else 'unstamped'}


def world_bounds(ob, scale=1):
    from mathutils import Vector
    points = [ob.matrix_world @ Vector(point) for point in ob.bound_box]
    if not points or all(tuple(point) == (-1, -1, -1) for point in ob.bound_box):
        points = [ob.matrix_world.translation]
    return {'min': [float(min(p[i] for p in points)) * scale for i in range(3)],
            'max': [float(max(p[i] for p in points)) * scale for i in range(3)]}


def bounds(ob, scale=1):
    return {key: [round(value, 4) for value in values]
            for key, values in world_bounds(ob, scale).items()}


def row(ob, scale=1, evaluated=False):
    if evaluated:
        import bpy
        measured = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    else:
        measured = ob
    mesh = measured.data if measured.type == 'MESH' else None
    raw_bound = world_bounds(measured, scale)
    bound = {key: [round(value, 4) for value in values] for key, values in raw_bound.items()}
    polygons = mesh.polygons if mesh else []
    return {'name': ob.name, 'type': ob.type, 'tris': sum(max(0, len(p.vertices) - 2) for p in polygons),
            'parent': ob.parent.name if ob.parent else None,
            'collection': [c.name for c in ob.users_collection],
            'location': [round(float(v) * scale, 4) for v in ob.matrix_world.translation],
            'rotation_deg': [round(math.degrees(float(v)), 2) for v in ob.matrix_world.to_euler()],
            'scale': [round(float(v), 4) for v in ob.matrix_world.to_scale()],
            'size': [round(hi - lo, 4) for lo, hi in zip(raw_bound['min'], raw_bound['max'])], 'bounds': bound,
            'verts': len(mesh.vertices) if mesh else 0, 'faces': len(polygons),
            'materials': [slot.material.name if slot.material else None for slot in ob.material_slots],
            'modifiers': [m.name for m in ob.modifiers], 'hidden': bool(ob.hide_get() or ob.hide_viewport),
            'selected': bool(ob.select_get()), 'uv_layers': [uv.name for uv in mesh.uv_layers] if mesh else [],
            'vertex_groups': [group.name for group in ob.vertex_groups],
            'armature': next((m.object.name for m in ob.modifiers if m.type == 'ARMATURE' and m.object), None),
            'canon': canon(ob)}


def detail(ob, scale=1, evaluated=False):
    result = row(ob, scale, evaluated)
    result.update(modifiers=[{'name': m.name, 'type': m.type, 'show_viewport': bool(m.show_viewport)} for m in ob.modifiers],
                  constraints=[{'name': c.name, 'type': c.type, 'target': getattr(c, 'target', None).name if getattr(c, 'target', None) else None} for c in ob.constraints],
                  materials=[{'slot': i, 'name': s.material.name if s.material else None, 'link': s.link} for i, s in enumerate(ob.material_slots)],
                  collections=[c.name for c in ob.users_collection], children=[child.name for child in ob.children])
    return result
