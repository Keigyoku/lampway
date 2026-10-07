# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Disposable GUI fixture: native masks, editor crops, undo, async still delivery."""
import bpy
import sys
import json
import traceback
import os
from pathlib import Path
OVERLAY = os.environ['LAMPWAY_VIEW_OVERLAY']
sys.path.insert(0, OVERLAY)
import mixar, mixar.modules
mixar.__path__.insert(0, OVERLAY + '/mixar')
mixar.modules.__path__.insert(0, OVERLAY + '/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0, OVERLAY + '/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools import api, api_view, jobs
assert api.__file__.startswith(OVERLAY), api.__file__
from mixar.modules.lampway_tools.view import runtime
from mixar.modules.common.ui_control.core import observe
from mixar.config.config import add_config
from PIL import Image
ROOT = Path(os.environ['LAMPWAY_PROJECT_ROOT'])
ROOT.mkdir(exist_ok=True)
add_config('mcp_enabled', True)
add_config('mcp_ui_control', True)
bpy.types.Scene.t2_password = bpy.props.StringProperty(default='SYNTHETIC_FIXTURE_ONLY', subtype='PASSWORD')

class T2_PT_secret(bpy.types.Panel):
    bl_label = 'Synthetic secret fixture'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'T2'

    def draw(self, context):
        self.layout.prop(context.scene, 't2_password')
bpy.utils.register_class(T2_PT_secret)

def secret_header(self, context):
    self.layout.prop(context.scene, 't2_password', text='')
bpy.types.VIEW3D_HT_header.prepend(secret_header)
state = {'stage': -1, 'captures': [], 'renders': []}

def fail():
    traceback.print_exc()
    (ROOT / 'failure.txt').write_text(traceback.format_exc())
    bpy.ops.wm.quit_blender()

def inspection_undo_checks():
    views = ['home', 'scene', 'objects', 'object', 'mesh', 'uv', 'parts',
             'layers', 'relations', 'file', 'schema', 'help']
    for view in views:
        for marker in (0, 1, 2):
            bpy.data.objects['Cube']['t1_undo_marker'] = marker
            bpy.ops.ed.undo_push(message=f'T1 fixture marker {marker}')
        before = sorted(obj.name for obj in bpy.context.selected_objects)
        args = {} if view == 'home' else {'view': view}
        if view in ('object', 'mesh', 'uv', 'parts', 'layers'):
            args['name'] = 'Cube'
        if view in ('schema', 'help'):
            args['name'] = 'mesh'
        result = api.call('inspect', json.dumps(args))
        assert result.get('ok'), (view, result)
        assert before == sorted(obj.name for obj in bpy.context.selected_objects)
        if os.environ.get('LAMPWAY_VIEW_PLANT_INSPECT_UNDO') == '1':
            bpy.ops.ed.undo_push(message='Planted inspection undo regression')
        assert bpy.ops.ed.undo() == {'FINISHED'}
        assert bpy.data.objects['Cube']['t1_undo_marker'] == 1, (view, 'inspection added an undo checkpoint')
        assert bpy.ops.ed.undo() == {'FINISHED'}
        assert bpy.data.objects['Cube']['t1_undo_marker'] == 0, (view, 'inspection changed existing history')
    return views

def current_settings(scene):
    render = scene.render
    return {
        'engine': render.engine,
        'resolution': [render.resolution_x, render.resolution_y, render.resolution_percentage],
        'filepath': render.filepath,
        'cycles_samples': scene.cycles.samples,
        'cycles_device': scene.cycles.device,
        'eevee_samples': getattr(scene.eevee, 'taa_render_samples', None),
        'image': {name: getattr(render.image_settings, name) for name in
                  ('media_type', 'file_format', 'color_mode', 'color_depth')},
        'frame': [scene.frame_current, scene.frame_subframe],
    }

def step():
    try:
        window = bpy.context.window
        area = next((a for a in window.screen.areas if a.type in ('VIEW_3D', 'IMAGE_EDITOR', 'NODE_EDITOR')))
        if state['stage'] == -1:
            window.event_simulate(type='ESC', value='PRESS')
            window.event_simulate(type='ESC', value='RELEASE')
            state['stage'] = 0
            return 1
        if state['stage'] == 0:
            state['inspect_undo_views'] = inspection_undo_checks()
            c = bpy.data.objects['Cube']
            c.location = (3, 4, 5)
            bpy.context.view_layer.update()
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            camera = bpy.data.objects['Camera']
            camera.select_set(True)
            bpy.context.view_layer.objects.active = camera
            c.hide_set(True)
            bpy.ops.ed.undo_push(message='T2 hidden baseline')
            assert api_view.view(action='focus', object='Cube', shot=False)['code'] == 'hidden'
            result = api_view.view(action='focus', object='Cube', shot=True, unhide=True, max_bytes=50000)
            assert 'image_path' in result, result
            assert result['image']['bytes'] <= 50000
            state['focus_capture'] = result
            assert result['unhidden'], result
            assert sorted((o.name for o in bpy.context.selected_objects)) == ['Camera']
            assert bpy.context.view_layer.objects.active.name == 'Camera'
            assert all((abs(a - b) < 1e-05 for a, b in zip(area.spaces.active.region_3d.view_location, (3, 4, 5))))
            assert bpy.ops.ed.undo() == {'FINISHED'}
            assert bpy.data.objects['Cube'].hide_get(), 'one actual GUI undo did not restore hidden'
            assert sorted((o.name for o in bpy.context.selected_objects)) == ['Camera'], 'undo changed selection'
            assert bpy.context.view_layer.objects.active.name == 'Camera'
            state['undo'] = 'one real GUI undo restored visibility and preserved Camera selection'
            area.spaces.active.show_region_ui = True
            state['stage'] = 1
            return 2
        if state['stage'] == 1:
            widgets = observe.widgets()
            (ROOT / 'widgets.json').write_text(json.dumps([{k: v for k, v in w.items() if not k.startswith('_')} for w in widgets], indent=2))
            secrets = [w for w in widgets if w.get('secret') and w.get('secret')]
            print('SECRETS', [(w['prop'], w['rect']) for w in secrets], flush=True)
            assert secrets, 'synthetic password widget was not drawn'
            if os.environ.get('LAMPWAY_VIEW_PLANT_UNMASKED') == '1':
                original_image = observe.image
                observe.image = lambda win, items: original_image(win, [])
            result = api_view.view(action='screenshot', area='VIEW_3D', max_bytes=50000)
            assert 'image_path' in result, result
            image = Image.open(ROOT / result['image_path'])
            rect = secrets[0]['rect']
            x = (rect[0] + rect[2]) / 2 - area.x
            y = area.height - ((rect[1] + rect[3]) / 2 - area.y)
            pt = (int(x * image.width / area.width), int(y * image.height / area.height))
            assert max(image.convert('RGB').getpixel(pt)) < 8, (pt, image.getpixel(pt))
            state['captures'].append(result)
            state['mask_pixel'] = image.getpixel(pt)
            area.type = 'IMAGE_EDITOR'
            state['stage'] = 2
            return 1
        if state['stage'] == 2:
            result = api_view.view(action='screenshot', area='IMAGE_EDITOR', max_bytes=50000)
            assert 'image_path' in result, result
            state['captures'].append(result)
            area.type = 'NODE_EDITOR'
            area.ui_type = 'ShaderNodeTree'
            state['stage'] = 3
            return 1
        if state['stage'] == 3:
            result = api_view.view(action='screenshot', area='ShaderNodeTree', max_bytes=50000)
            assert 'image_path' in result, result
            state['captures'].append(result)
            area.type = 'VIEW_3D'
            scene = window.scene
            scene.render.engine = 'CYCLES'
            scene.render.resolution_x = 320
            scene.render.resolution_y = 240
            state['settings'] = [scene.render.engine, scene.render.resolution_x, scene.render.resolution_y, scene.render.filepath]
            result = api_view.view(action='render_still', preset='thumbnail')
            assert 'job' in result, result
            state['pending'] = result['job']
            state['stage'] = 4
            busy = api_view.view(action='render_still', preset='thumbnail')
            assert busy['code'] == 'render_in_progress', busy
            state['busy'] = busy
            return 0.5
        if state['stage'] in (4, 5):
            job = jobs.get(state['pending'])
            if job.state == 'running':
                return 0.5
            assert job.state == 'done', (job.state, job.error)
            state['renders'].append(job.result)
            scene = window.scene
            assert state['settings'] == [scene.render.engine, scene.render.resolution_x, scene.render.resolution_y, scene.render.filepath], 'settings not restored'
            if state['stage'] == 4:
                result = api_view.view(action='render_still', preset='thumbnail')
                assert 'job' in result, result
                state['pending'] = result['job']
                state['stage'] = 5
                return 0.5
            assert [r['path'] for r in state['renders']] == ['renders/still.png', 'renders/still-2.png'], state['renders']
            # Only this disposable scene chooses CPU rendering and a small current preset.
            scene.render.resolution_percentage = 100
            scene.cycles.device = 'CPU'
            scene.cycles.samples = 1
            state['current_settings'] = current_settings(scene)
            result = api.call('view', json.dumps({'action': 'render_still', 'out': 'renders/current.png'}))
            assert result.get('ok') and 'job' in result, result
            assert result['preset'] == 'current', result
            state['current_receipt'] = result
            state['pending'] = result['job']
            state['stage'] = 6
            return 0.5
        if state['stage'] == 6:
            job = jobs.get(state['pending'])
            if job.state == 'running':
                return 0.5
            assert job.state == 'done', (job.state, job.error)
            state['current_render'] = job.result
            assert current_settings(window.scene) == state['current_settings'], 'current render settings changed'
            assert job.result['path'] == 'renders/current.png', job.result
            with Image.open(ROOT / job.result['path']) as current:
                assert current.format == 'PNG' and current.size == (320, 240), (current.format, current.size)
            for item in state['captures'] + state['renders']:
                with Image.open(ROOT / (item.get('image_path') or item['path'])) as im:
                    assert im.format == 'PNG'
            (ROOT / 'receipt.json').write_text(json.dumps(state, indent=2))
            print('T2_GUI_RESULT ' + json.dumps(state), flush=True)
            bpy.ops.wm.quit_blender()
    except BaseException:
        fail()
bpy.app.timers.register(step, first_interval=6)
