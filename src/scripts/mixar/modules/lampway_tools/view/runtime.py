# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Main-thread viewport operations on the executor's session-bound window."""
import base64
import secrets

import bpy

from .. import settings
from . import ViewError, crop_png, reserve_output

_last_capture = None


def bound_window():
    # route_request pins this window before api.call; never consult context.scene.
    window = bpy.context.window
    if window is None:
        from mixar.modules.space_mixie_chat.core.main_thread_routing import _window
        window, _kind = _window()
    if window is None or window.scene is None:
        raise ViewError('no_area', 'No document window for the bound scene', ['lampway_ui_observe'])
    return window


def find_area(window, kind):
    for area in window.screen.areas:
        if area.width > 1 and area.height > 1 and (area.type == kind or area.ui_type == kind):
            return area
    raise ViewError('no_area', f'No visible editor of type {kind}', ['lampway_ui_observe'])


def pixel_gate():
    from mixar.modules.mcp_bridge.core.runtime import ui_control_enabled
    if not ui_control_enabled():
        raise ViewError('ui_control_off', 'Enable AI apps UI control in Lampway settings to capture pixels', ['lampway_ui_observe'])


def capture(window, area, max_bytes):
    global _last_capture
    pixel_gate()
    if bpy.app.driver_namespace.get('mixie_route_switched', False):
        raise ViewError('capture_busy', 'Bound scene switched without a completed redraw', ['lampway_ui_observe'])
    from mixar.modules.common.ui_control.core import observe
    from mixar.modules.common.ui_control.constants import UIError
    try:
        # Includes secret widgets from every window; image applies the native masks first.
        block, geometry = observe.image(window, observe.widgets())
    except UIError as exc:
        raise ViewError(exc.code, str(exc), ['lampway_ui_observe']) from exc
    rect = None if area is None else (area.x, area.y, area.width, area.height)
    png, meta = crop_png(base64.b64decode(block['data']), geometry, rect, max_bytes)
    root = settings.load().project_root.resolve()
    path = reserve_output(root, f'.lampway/captures/{secrets.token_hex(16)}.png')
    try:
        path.write_bytes(png)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    _last_capture = dict(meta)
    return {'image_path': path.relative_to(root).as_posix(), 'image': meta}


def focus(window, name, data, unhide):
    scene, layer = window.scene, window.view_layer
    target = scene.objects.get(name) if name else None
    if data:
        matches = [obj for obj in scene.objects if getattr(getattr(obj, 'data', None), 'name', None) == data]
        if len(matches) != 1:
            raise ViewError('not_found' if not matches else 'ambiguous', 'data must resolve to exactly one scene object', ['lampway_inspect view=objects'])
        target = matches[0]
    if target is None:
        raise ViewError('not_found', 'Object not found in bound scene', ['lampway_inspect view=objects'])
    area = find_area(window, 'VIEW_3D')
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        raise ViewError('no_area', 'VIEW_3D has no window region', ['lampway_ui_observe'])
    hidden = target.hide_get(view_layer=layer) or target.hide_viewport or not target.visible_get(view_layer=layer)
    if hidden and not unhide:
        raise ViewError('hidden', f'{target.name} is hidden', [f'lampway_view action=focus object={quote(target.name)} unhide=true'])
    # Collection visibility is not the target's visibility: do not silently mutate collections.
    old_hidden, old_viewport = target.hide_get(view_layer=layer), target.hide_viewport
    selected = [obj for obj in layer.objects if obj.select_get(view_layer=layer)]
    active = layer.objects.active
    try:
        if hidden:
            target.hide_viewport = False
            target.hide_set(False, view_layer=layer)
            if not target.visible_get(view_layer=layer):
                target.hide_viewport = old_viewport
                target.hide_set(old_hidden, view_layer=layer)
                raise ViewError('hidden', 'Target is hidden by a collection or excluded view layer', ['lampway_ui_observe'])
        for obj in selected:
            obj.select_set(False, view_layer=layer)
        target.select_set(True, view_layer=layer)
        layer.objects.active = target
        with bpy.context.temp_override(window=window, scene=scene, view_layer=layer, area=area, region=region):
            result = bpy.ops.view3d.view_selected(use_all_regions=False)
            if 'FINISHED' not in result:
                raise ViewError('focus_unavailable', 'Cannot frame the object in this editor mode', ['lampway_ui_observe'])
    except Exception:
        if hidden:
            target.hide_viewport = old_viewport
            target.hide_set(old_hidden, view_layer=layer)
        raise
    finally:
        for obj in layer.objects:
            if obj.select_get(view_layer=layer):
                obj.select_set(False, view_layer=layer)
        for obj in selected:
            obj.select_set(True, view_layer=layer)
        layer.objects.active = active
    if hidden:
        with bpy.context.temp_override(window=window, scene=scene):
            bpy.ops.ed.undo_push(message=f'Lampway: unhide {target.name}')
    # Use Blender's world transform rather than deriving a geometry/framing algorithm.
    from mathutils import Vector
    points = [target.matrix_world @ Vector(point) for point in target.bound_box]
    scale = float(getattr(getattr(scene, 'unit_settings', None), 'scale_length', 1.0))
    bounds = {'min': [round(min(p[i] for p in points) * scale, 4) for i in range(3)],
              'max': [round(max(p[i] for p in points) * scale, 4) for i in range(3)]}
    return {'object': target.name, 'framed_bounds': bounds, 'unhidden': bool(hidden),
            **({'undo': f'Lampway: unhide {target.name}'} if hidden else {})}


def quote(value):
    import json
    return json.dumps(value) if any(char.isspace() or char in '\"\\' for char in value) else value


def run(action, name, data, unhide, area, shot, max_bytes, preset, out):
    window = bound_window()
    if action is None:
        return {'tool': 'lampway_view', 'description': 'Frame an object, capture an editor or render a still',
                'action': 'home', 'scene': window.scene.name,
                'editors': [a.ui_type for a in window.screen.areas],
                'active_camera': getattr(window.scene.camera, 'name', None),
                'last_capture': _last_capture, 'help': ['lampway_view action=focus object=<name>',
                                                      'lampway_view action=screenshot', 'lampway_view action=render_still']}
    from mixar.modules.common.render_coordinator import core as slot
    if slot.busy():
        raise ViewError('render_in_progress', 'Another render is in progress', ['lampway_job_status'])
    if action == 'render_still':
        from .rendering import start
        return start(window, preset, out)
    # Verify the capture gate and editor before any unhide or framing mutation.
    if action == 'screenshot' or shot:
        pixel_gate()
        if bpy.context.window_manager.mixar_window_resizing:
            raise ViewError('capture_busy', 'Wait for window resize to finish', ['lampway_ui_observe'])
        if bpy.app.driver_namespace.get('mixie_route_switched', False):
            raise ViewError('capture_busy', 'Bound scene switched without a completed redraw', ['lampway_ui_observe'])
        image_area = None if area == 'WINDOW' else find_area(window, area)
    result = {'action': action, 'area': area}
    if action == 'focus':
        result.update(focus(window, name, data, unhide))
    if action == 'focus' and shot:
        # Existing scene_render_ops uses this single-redraw barrier. The resize and render guards above
        # keep drawing out of resize dispatch; observe.image still owns capture and masks.
        with bpy.context.temp_override(window=window, scene=window.scene):
            redraw = bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        if 'FINISHED' not in redraw:
            raise ViewError('capture_unavailable', 'Framed editor has not completed a redraw', ['lampway_ui_observe'])
    if action == 'screenshot' or shot:
        result.update(capture(window, image_area, max_bytes))
    result['help'] = ['lampway_view action=help']
    return result
