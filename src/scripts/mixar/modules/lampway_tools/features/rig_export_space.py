# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit centimetre export copies and pinned importer representation decoding.

The caller must admit the raw FBX unit/container carrier before decoding a
readback. Neither function changes the owner's geometry, actions or scene units.
"""
from contextlib import contextmanager
import math

import bpy
from mathutils import Matrix

from .. import canon_io
from . import rig_tools as RT


def _preflight(armature, meshes, action):
    if bpy.context.mode != 'OBJECT' or armature.type != 'ARMATURE':
        raise ValueError('Centimetre copies require an armature in Object mode')
    if armature.parent or armature.constraints or any(b.constraints for b in armature.pose.bones):
        raise ValueError('Detach parents and bake constraints before centimetre export')
    ad = armature.animation_data
    if ad and (ad.drivers or ad.nla_tracks):
        raise ValueError('Bake drivers and NLA to one action before centimetre export')
    for mesh in meshes:
        if mesh.type != 'MESH' or mesh.parent not in (None, armature) or mesh.parent_type != 'OBJECT':
            raise ValueError('Meshes must be detached or object-parented to the export armature')
        if mesh.constraints or mesh.animation_data or (mesh.data.shape_keys and mesh.data.shape_keys.animation_data):
            raise ValueError('Bake animated meshes and shape keys before centimetre export')
        if any(m.type == 'ARMATURE' and m.object != armature for m in mesh.modifiers):
            raise ValueError('Mesh skin must reference only the export armature')
    if action:
        for fc in RT._fcurves(action):
            if (fc.data_path == 'location' or fc.data_path.endswith('.location')) and fc.modifiers:
                raise ValueError('Bake location curve modifiers before centimetre export')
            if fc.data_path.endswith('.location') and not fc.data_path.startswith('pose.bones['):
                raise ValueError('Only object and bone location channels support centimetre conversion')


def _centimetre_matrix(matrix):
    result = matrix.copy()
    result.translation *= 100.0
    return result


@contextmanager
def centimetre_copies(armature, meshes, action, exporter):
    """Yield disposable centimetre coordinates plus their effective FBX settings.

    Location keys and their handles change representation together. Rotation,
    scale, frame numbers and weights retain their original values. Unsupported
    dependencies are refused before creating IDs. Every newly created ID and the
    original selection are restored even if export raises inside the context.
    """
    meshes = list(meshes)
    _preflight(armature, meshes, action)
    if (exporter.get('global_scale') != 1.0 or exporter.get('apply_unit_scale') is not True
            or exporter.get('apply_scale_options') != 'FBX_SCALE_NONE'):
        raise ValueError('Centimetre coordinates require the unscaled unit-aware FBX_SCALE_NONE template')
    unit = bpy.context.scene.unit_settings.scale_length
    if not math.isfinite(unit) or unit <= 0:
        raise ValueError('Scene unit scale must be finite and positive')
    from io_scene_fbx.fbx_utils import units_blender_to_fbx_factor
    scene_factor = units_blender_to_fbx_factor(bpy.context.scene)
    effective_scale = 1.0 / scene_factor
    if not math.isfinite(effective_scale) or effective_scale <= 0:
        raise ValueError('Effective centimetre exporter scale must be finite and positive')
    scale_property = bpy.ops.export_scene.fbx.get_rna_type().properties['global_scale']
    if not scale_property.hard_min <= effective_scale <= scale_property.hard_max:
        raise ValueError('Scene display units require an effective FBX scale outside the pinned exporter operator limits')
    before = canon_io.snapshot_ids()
    shape_keys = set(bpy.data.shape_keys)
    try:
        copied_arm = armature.copy()
        copied_arm.data = armature.data.copy()
        bpy.context.scene.collection.objects.link(copied_arm)
        copied_arm.animation_data_clear()
        copied_arm.data.transform(Matrix.Scale(100.0, 4))
        copied_arm.matrix_world = _centimetre_matrix(armature.matrix_world)
        for bone in copied_arm.pose.bones:
            bone.location *= 100.0
        copied_action = action.copy() if action else None
        if copied_action:
            for fc in RT._fcurves(copied_action):
                if fc.data_path == 'location' or (fc.data_path.startswith('pose.bones[') and fc.data_path.endswith('.location')):
                    for key in fc.keyframe_points:
                        key.co.y *= 100.0
                        key.handle_left.y *= 100.0
                        key.handle_right.y *= 100.0
            copied_arm.animation_data_create().action = copied_action
            source_ad = armature.animation_data
            if source_ad and source_ad.action == action and source_ad.action_slot:
                copied_arm.animation_data.action_slot = next(
                    slot for slot in copied_action.slots
                    if slot.handle == source_ad.action_slot.handle)
        copied_meshes = []
        for mesh in meshes:
            copied = mesh.copy()
            copied.data = mesh.data.copy()
            copied.parent = None
            bpy.context.scene.collection.objects.link(copied)
            copied.data.transform(Matrix.Scale(100.0, 4), shape_keys=True)
            if mesh.parent:
                copied.parent = copied_arm
            copied.matrix_world = _centimetre_matrix(mesh.matrix_world)
            for modifier in copied.modifiers:
                if modifier.type == 'ARMATURE':
                    modifier.object = copied_arm
            copied_meshes.append(copied)
        bpy.context.view_layer.update()
        settings = dict(exporter, global_scale=effective_scale,
                        apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE')
        yield {'armature': copied_arm, 'meshes': copied_meshes, 'action': copied_action,
               'exporter': settings, 'receipt': {'coordinates': 'cm', 'coordinate_factor': 100.0,
                                               'scene_scale_length': unit,
                                               'scene_unit_system': bpy.context.scene.unit_settings.system,
                                               'blender_to_fbx_factor': scene_factor,
                                               'effective_global_scale': settings['global_scale']}}
    finally:
        canon_io.remove_new_ids(before)
        for key in list(bpy.data.shape_keys):
            if key not in shape_keys:
                bpy.data.shape_keys.remove(key)



def readback_representation(armature, importedobjects, unit_scale_factor):
    """Decode an admitted temporary readback without changing scene or geometry.

    Pinned add-on import_fbx multiplies global_scale by UnitScaleFactor divided
    by fbx_utils.units_blender_to_fbx_factor(scene). Its scene-relative position
    and object-scale carrier must be decoded separately. The caller first audits
    raw identity Null ancestors, UnitScaleFactor=1 and direct bone scales=1.
    """
    if armature not in importedobjects or armature.type != 'ARMATURE':
        raise ValueError('Readback armature must belong to the temporary imported objects')
    if unit_scale_factor != 1.0:
        raise ValueError('Centimetre readback requires admitted UnitScaleFactor=1')
    from io_scene_fbx.fbx_utils import units_blender_to_fbx_factor
    scene = bpy.context.scene
    factor = units_blender_to_fbx_factor(scene)
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError('Importer scene representation factor must be finite and positive')
    divisor = unit_scale_factor / factor
    scales = armature.matrix_world.decompose()[2]
    if max(abs(component / divisor - 1.0) for component in scales) > 1e-4:
        raise ValueError('Readback armature has scale beyond the pinned importer unit carrier')
    return {'translation_to_metres': factor / 100.0, 'scale_divisor': divisor,
            'unit_scale_factor': unit_scale_factor,
            'blender_to_fbx_factor': factor,
            'scene_unit_system': scene.unit_settings.system,
            'scene_scale_length': scene.unit_settings.scale_length,
            'armature_world_scale': list(scales),
            'mutated_readback': False}
