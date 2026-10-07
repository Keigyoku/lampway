# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""L0 scene dashboard and collection tree: read-only bpy facts."""
from pathlib import Path
import bpy


def triangle_count(mesh):
    """Valid Blender polygons partition loops and each has at least three.

    Summing (polygon loop count - 2) therefore uses two O(1) RNA lengths;
    degenerate geometry still has its topological triangle count.
    """
    return len(mesh.loops) - 2 * len(mesh.polygons)


def dashboard(scene):
    objects = list(scene.objects)
    counts = {kind: sum(ob.type == kind.upper().rstrip('S') for ob in objects) for kind in ('meshes', 'lights', 'cameras')}
    counts['meshes'] = sum(ob.type == 'MESH' for ob in objects)
    counts.update(objects=len(objects), materials=len(bpy.data.materials), images=len(bpy.data.images))
    from ._vendor import missing_files
    missing = len(missing_files.main(None).missing_files)
    return {'file': Path(bpy.data.filepath).name or None, 'unsaved': bool(bpy.data.is_dirty or not bpy.data.filepath),
            'units': 'm', 'counts': counts,
            'tris_total': sum(triangle_count(ob.data) for ob in objects if ob.type == 'MESH'),
            'selected': [ob.name for ob in objects if ob.select_get()],
            'active': bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
            'warnings': [{'kind': 'missing_files', 'count': missing}] if missing else []}


def collection_tree(collection):
    return {'name': collection.name, 'objects': len(collection.objects),
            'hidden': bool(collection.hide_viewport), 'children': [collection_tree(child) for child in collection.children]}


def scene_data(scene, scale):
    world = {'hdri': None, 'strength': None}
    if scene.world and scene.world.use_nodes:
        for node in scene.world.node_tree.nodes:
            if node.type == 'TEX_ENVIRONMENT' and node.image:
                world['hdri'] = Path(node.image.filepath).name
            if node.type == 'BACKGROUND':
                world['strength'] = float(node.inputs['Strength'].default_value)
    return {'collections': collection_tree(scene.collection),
            'cameras': [{'name': ob.name, 'lens_mm': float(ob.data.lens), 'sensor_mm': float(ob.data.sensor_width),
                         'clip_start': round(ob.data.clip_start * scale, 4), 'clip_end': round(ob.data.clip_end * scale, 4)} for ob in scene.objects if ob.type == 'CAMERA'],
            'lights': [{'name': ob.name, 'type': ob.data.type, 'energy_w': float(ob.data.energy),
                        'color': list(ob.data.color), 'size_m': round(float(getattr(ob.data, 'size', 0)) * scale, 4)} for ob in scene.objects if ob.type == 'LIGHT'],
            'world': world, 'frames': {'start': scene.frame_start, 'end': scene.frame_end, 'current': scene.frame_current,
                                      'fps': scene.render.fps / scene.render.fps_base},
            'render': {'engine': scene.render.engine, 'resolution': [scene.render.resolution_x, scene.render.resolution_y],
                       'percentage': scene.render.resolution_percentage}}
