# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Issue 2 UI evidence in one disposable software GL document."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback
import threading
import uuid
import bpy

ROOT = Path(os.environ['LAMPWAY_PROJECT_ROOT'])
OVERLAY = os.environ['LAMPWAY_VIEW_OVERLAY']
sys.path.insert(0, str(Path(__file__).parent))
from issue2_graphics import validate_renderer
sys.path.insert(0, OVERLAY)
import mixar, mixar.modules
mixar.__path__.insert(0, OVERLAY + '/mixar')
mixar.modules.__path__.insert(0, OVERLAY + '/mixar/modules')
from mixar.config.config import add_config
from mixar.modules.mcp_bridge.core import runtime
from mixar.modules.common.ui_control.core import observe
# This disposable mock account has no desktop credential service. Keep its
# transient local tokens in the fixture's memory-only keyring, never on disk.
import keyring
from keyring.backend import KeyringBackend
class FixtureKeyring(KeyringBackend):
    priority = 1
    def __init__(self):
        self.values = {}
    def get_password(self, service, username):
        return self.values.get((service, username))
    def set_password(self, service, username, password):
        self.values[service, username] = password
    def delete_password(self, service, username):
        self.values.pop((service, username), None)
keyring.set_keyring(FixtureKeyring())

import webbrowser
browser_opens = []
webbrowser.open = lambda url, *args, **kw: browser_opens.append(url) or False

add_config('mcp_enabled', True)
add_config('mcp_ui_control', True)
state = {'phase': 0, 'steps': [], 'deadline': time.monotonic() + 95, 'browser_opens': browser_opens,
         'source': json.loads(os.environ['LAMPWAY_GUI_SOURCE'])}
OWNER = str(uuid.uuid4())
pending = {}

def submit(name, args):
    from mixar.modules.common.ui_control.core import service
    pending.clear()
    # Read scene identity on the main thread; thread never accesses bpy.
    session = bpy.context.scene.mixie_session_id
    def work():
        try:
            pending['result'] = service.submit(OWNER, name, args, str(uuid.uuid4()), session)
        except Exception as exc:
            pending['error'] = repr(exc)
    threading.Thread(target=work, daemon=True).start()

def submit_scene():
    """Use the actual connector release path before a backend scene tool."""
    from mixar.modules.mcp_bridge.core.connector import Connector
    client = Connector(session=bpy.context.scene.mixie_session_id)
    client.owner = OWNER
    pending.clear()
    def work():
        try:
            pending['result'] = client.call('lampway_inspect', {'view': 'scene'}, str(uuid.uuid4()))
        except Exception as exc:
            if callable(getattr(exc, 'result', None)):
                pending['result'] = {'isError': True, 'structuredContent': {'result': exc.result()}}
            else:
                pending['error'] = repr(exc)
    threading.Thread(target=work, daemon=True).start()

def submitted():
    assert not pending.get('error'), pending
    return pending.get('result')


def submit_connected_context():
    """Exercise the public MCP status enrichment after a real scene call."""
    from mixar.modules.mcp_bridge.core.connector import Connector
    session = bpy.context.scene.mixie_session_id
    pending.clear()
    def work():
        import asyncio
        from mcp import Client
        from mixar.modules.mcp_bridge.core import stdio_server
        async def check():
            async with Client(stdio_server.create_server(Connector(session=session))) as client:
                result = await client.call_tool('lampway_ui_context', {})
                assert not result.is_error, result
                return result.structured_content['result']
        try:
            pending['result'] = asyncio.run(check())
        except Exception:
            pending['error'] = traceback.format_exc()
    threading.Thread(target=work, daemon=True).start()


def source(module, relative, override=None):
    path = override or (OVERLAY + '/mixar/modules/' + relative)
    spec = importlib.util.spec_from_file_location(module.__name__, path)
    module.__spec__ = spec
    spec.loader.exec_module(module)


def click(rect):
    win = bpy.context.window
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    win.cursor_warp(x, y)
    win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    def press():
        win.event_simulate(type='LEFTMOUSE', value='PRESS', x=x, y=y)
        def release():
            win.event_simulate(type='LEFTMOUSE', value='RELEASE', x=x, y=y)
            return None
        bpy.app.timers.register(release, first_interval=0.025)
        return None
    bpy.app.timers.register(press, first_interval=0.05)


def capture(name):
    block, frame = observe.image(bpy.context.window, observe.widgets())
    (ROOT / name).write_bytes(base64.b64decode(block['data']))
    return frame


def step():
    try:
        if state['phase'] == 0:
            snap = runtime.snapshot()
            if not (snap.get('ui_contract') == 'mixar_ui_v1' and snap.get('ui_control') is True
                    and snap.get('ui_controller_ready', True)):
                assert time.monotonic() < state['deadline'], snap
                return 0.1
            bpy.context.window.event_simulate(type='ESC', value='PRESS')
            bpy.context.window.event_simulate(type='ESC', value='RELEASE')
            import gpu
            state['graphics'] = {'requested_software_gl': os.environ['LAMPWAY_VIEW_SOFTWARE_GL'],
                                 'renderer': gpu.platform.renderer_get(),
                                 'vendor': gpu.platform.vendor_get(), 'version': gpu.platform.version_get()}
            validate_renderer(state['graphics']['requested_software_gl'], state['graphics']['renderer'])
            state['phase'] = 0.5
            return 1
        if state['phase'] == 0.5:
            bpy.ops.wm.splash('INVOKE_DEFAULT')
            state['phase'] = 0.75
            return 1
        if state['phase'] == 0.75:
            widgets = [w for w in observe.widgets() if w.get('popup')]
            texts = [w.get('text', '') for w in widgets]
            assert any('Language' in t for t in texts), ('step 1 not drawn', texts)
            assert any(t == 'Continue' for t in texts), ('step 1 Continue not drawn', texts)
            state['step1'] = {'texts': texts, 'frame': capture('step-1-language-and-keys.png')}
            bpy.context.window.event_simulate(type='ESC', value='PRESS')
            bpy.context.window.event_simulate(type='ESC', value='RELEASE')
            state['phase'] = 1
            return 1
        if state['phase'] == 1:
            source(observe, 'common/ui_control/core/observe.py')
            result, _ = observe.observe('issue2-fixture', {'limit': 200})
            assert result['targets'] and all(t['label'].strip() for t in result['targets']), result
            state['observed'] = result
            # Run the original covering state's inventory/pagination facts here,
            # using this no-sync runtime instead of its legacy sync harness.
            import runpy
            covering = runpy.run_path(str(Path(__file__).parents[1] /
                                         'lampway_visual/states/observe_labels.py'))
            state['covering_label_facts'] = covering['facts'](bpy, None)
            capture('labeled-controls.png')
            from mixar.modules.lampway_tools import onboarding as ob
            source(ob, 'lampway_tools/onboarding.py')
            ui = sys.modules['mixar.modules.lampway_tools.ui.onboarding']
            ui.unregister()
            source(ui, 'lampway_tools/ui/onboarding.py', os.environ.get('LAMPWAY_ONBOARDING_BASELINE'))
            ui.register()
            original_refresh = getattr(ui, '_refresh_step', None)
            if original_refresh:
                def track_refresh(context):
                    state.setdefault('transitions', []).append({'step': ui.WALK['walk'].step,
                        'region': getattr(context.region, 'type', None),
                        'region_pointer': context.region.as_pointer() if context.region else None})
                    return original_refresh(context)
                ui._refresh_step = track_refresh
            routes = json.loads((ROOT / 'routes.json').read_text())
            walk = ob.Walk(routes=routes, provider='mock')
            ui.WALK['walk'] = walk
            wm = bpy.context.window_manager
            wm.lampway_onboarding_routes.clear()
            for route in routes:
                row = wm.lampway_onboarding_routes.add()
                row.route_id = route['id']
            wm.lampway_onboarding_provider = 'mock'
            walk.next()
            win = bpy.context.window
            win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=win.width // 2, y=win.height // 2)
            area = max(win.screen.areas, key=lambda a: a.width * a.height)
            with bpy.context.temp_override(window=win, area=area):
                bpy.ops.lampway.onboarding('INVOKE_DEFAULT')
            state['phase'] = 2
            return 1
        if state['phase'] in (2, 3, 4, 5):
            expected = {2: 2, 3: 3, 4: 4, 5: 3}[state['phase']]
            widgets = [w for w in observe.widgets() if w.get('popup')]
            (ROOT / f'widgets-{state["phase"]}.json').write_text(json.dumps([{k: v for k, v in w.items() if not k.startswith('_')} for w in widgets], indent=2))
            texts = [w.get('text', '') for w in widgets]
            words = {2: 'Every route is off until', 3: 'The agent thinks with the provider', 4: 'OpenRouter, in dollars'}
            shown = [n for n, word in words.items() if any(t.startswith(word) for t in texts)]
            assert shown == [expected], ('stale onboarding panel', expected, shown)
            cont = next(w['rect'] for w in widgets if w.get('text', '').startswith('Continue'))
            back = next((w['rect'] for w in widgets if w.get('text') == 'Back'), None)
            assert back and abs((back[1]+back[3]) - (cont[1]+cont[3])) <= 2, ('Back must share Continue footer', back, cont)
            state['steps'].append({'step': expected, 'shown': shown, 'continue': cont, 'back': back,
                                   'texts': texts, 'frame': capture(f'step-{expected}-{state["phase"]}.png')})
            if state['phase'] == 5:
                first = state['steps'][0]['continue']
                assert all(s['continue'] == first for s in state['steps']), state['steps']
                bpy.context.window.event_simulate(type='ESC', value='PRESS')
                bpy.context.window.event_simulate(type='ESC', value='RELEASE')
                state['phase'] = 6
                return 1
            click(back if expected == 4 else cont)
            state['phase'] += 1
            return 1
        if state['phase'] >= 6:
            assert time.monotonic() < state['deadline'], ('UI integration deadline', state['phase'], pending)
        if state['phase'] == 6:
            from mixar.modules.auth.core.sso import local_signin
            from mixar.modules.space_mixie_chat.core.connection_manager import get_connection_manager
            result = local_signin()
            assert result.get('success'), {k: v for k, v in result.items() if k != 'token'}
            bpy.context.window_manager.mixie_chat_is_logged_in = True
            get_connection_manager().connect()
            state['phase'] = 7
            return 0.1
        if state['phase'] == 7:
            from mixar.modules.space_mixie_chat.core.connection_manager import get_connection_manager
            from mixar.modules.mcp_bridge.core import eligibility
            if not get_connection_manager().is_connected or not eligibility.valid():
                return 0.1
            submit('mixar_ui_observe', {'limit': 200})
            state['phase'] = 8
            return 0.1
        if state['phase'] == 8:
            result = submitted()
            if result is None:
                return 0.1
            assert not result.get('isError'), result
            observed = result['structuredContent']['result']
            target = next(t for t in observed['targets'] if t.get('text') == 'File')
            submit('mixar_ui_act', {'context': observed['context'], 'target': target['target'], 'action': 'click'})
            state['phase'] = 9
            return 0.1
        if state['phase'] == 9:
            result = submitted()
            if result is None:
                return 0.1
            assert not result.get('isError'), result
            assert any(w.get('popup') for w in observe.widgets()), 'UI act did not open File menu'
            state['popup_frame'] = capture('controller-popup.png')
            submit_scene()
            state['phase'] = 10
            return 0.1
        if state['phase'] == 10:
            result = submitted()
            if result is None:
                return 0.1
            refused = result['structuredContent']['result']
            assert result.get('isError') and refused['error_type'] == 'modal_active', result
            assert 'ESC' in refused['next_step'] and 'lampway_ui_act' in refused['next_step'], refused
            state['popup_refusal'] = refused
            submit('mixar_ui_observe', {'limit': 200})
            state['phase'] = 11
            return 0.1
        if state['phase'] == 11:
            result = submitted()
            if result is None:
                return 0.1
            observed = result['structuredContent']['result']
            target = next(t for t in observed['targets'] if t.get('popup') and t.get('enabled'))
            submit('mixar_ui_act', {'context': observed['context'], 'target': target['target'], 'action': 'press', 'key': 'ESC'})
            state['phase'] = 12
            return 0.1
        if state['phase'] == 12:
            result = submitted()
            if result is None:
                return 0.1
            assert not result.get('isError'), result
            assert not any(w.get('popup') for w in observe.widgets()), 'ESC did not settle controller popup'
            submit_scene()
            state['phase'] = 13
            return 0.1
        if state['phase'] == 13:
            result = submitted()
            if result is None:
                return 0.1
            assert not result.get('isError'), result
            assert browser_opens == [], ('automatic browser launch', browser_opens)
            state['popup_recovered'] = True
            submit_connected_context()
            state['phase'] = 14
            return 0.1
        if state['phase'] == 14:
            context = submitted()
            if context is None:
                return 0.1
            assert context['server_connected'] is True, context
            assert context['scene_tools'] == 'available' and context['next_step'] == '', context
            state['connected_ui_context_after_scene_call'] = context
            (ROOT / 'receipt.json').write_text(json.dumps(state, indent=2))
            bpy.context.preferences.view.use_save_prompt = False
            bpy.ops.wm.quit_blender()
            return None
    except Exception:
        (ROOT / 'partial-receipt.json').write_text(json.dumps(state, indent=2))
        (ROOT / 'failure.txt').write_text(traceback.format_exc())
        traceback.print_exc()
        bpy.context.preferences.view.use_save_prompt = False
        bpy.ops.wm.quit_blender()
        return None

bpy.app.timers.register(step, first_interval=6)
