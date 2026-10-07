# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native M0 chip GUI proof on an isolated cloud Xvfb app, with no server/provider.

Launch with --enable-event-simulate -P this_file and LW_QA_OUT=<isolated output dir>.
The timer opens the island, checks real uiBut geometry, captures it, and clicks the mode menu.
It never selects a harness or sends a prompt. RESULT reports pass/failure before quitting.
"""
import json
import os
from pathlib import Path
import traceback

import bpy

OUT = Path(os.environ['LW_QA_OUT'])
assert OUT.is_absolute()
OUT.mkdir(parents=True, exist_ok=True)
STATE = {'stage': 0}
MODE_TIP = 'Lampway Agent: switch to your own agent. Conversations stay in History'
YOUR_TIP = 'Your agent: choose a harness or switch to Lampway Agent. Conversations stay in History'
MODEL_TIP = 'Choose which model the agent runs on'


def widgets():
    return json.loads(bpy.context.window_manager.mixar_qa_ui_dump)['widgets']


def find_tip(tip):
    found = [w for w in widgets() if w.get('tip') == tip]
    assert len(found) == 1, f'Expected one native chip with tooltip {tip!r}; found {len(found)}'
    return found[0]


def finish(result):
    (OUT / 'result.json').write_text(json.dumps(result, indent=2))
    print('RESULT ' + json.dumps(result), flush=True)
    bpy.ops.wm.quit_blender()


def tick():
    try:
        if STATE['stage'] == 0:
            import bootstrap
            for _ in range(100000):
                if bootstrap._load_ui_batch_tick() is None:
                    break
            from mixar.modules.lampway_tools import api
            assert api.status()['ok']
            sc = bpy.context.scene
            sc.lampway_agent_mode = 'runtime'
            sc.mixie_chat_state = 'IDLE'
            sc.mixie_chat_messages.clear()
            bpy.context.window_manager.mixar_agent_model_label = 'Fixture model'
            bpy.ops.mixar.agent_bubble_show_window()
            STATE['stage'] = 1
            return 2.0
        if STATE['stage'] == 1:
            mode, model = find_tip(MODE_TIP), find_tip(MODEL_TIP)
            assert mode['w'] == model['w'], (mode, model)
            left, right = mode['rect'], model['rect']
            assert left[2] > left[0] and left[3] > left[1], left
            assert left[2] <= right[0], (left, right)
            assert left[1] == right[1] and left[3] == right[3], (left, right)
            win = next(w for w in bpy.context.window_manager.windows if w.as_pointer() == mode['w'])
            assert win.mixar_ui_capture(filepath=str(OUT / 'mode-chip.png')), 'native frame capture failed'
            STATE.update(window=win, rect=left, geometry={'mode': left, 'model': right})
            win.scene.lampway_agent_mode = 'byoa'
            for area in win.screen.areas:
                area.tag_redraw()
            STATE['stage'] = 2
            return 1.0
        if STATE['stage'] == 2:
            find_tip(YOUR_TIP)  # Saved scene mode changes the native chip's observed state.
            STATE['window'].scene.lampway_agent_mode = 'runtime'
            for area in STATE['window'].screen.areas:
                area.tag_redraw()
            STATE['stage'] = 3
            return 1.0
        if STATE['stage'] == 3:
            target = find_tip(MODE_TIP)
            x0, y0, x1, y1 = target['rect']
            x, y = int((x0+x1)/2), int((y0+y1)/2)
            win = STATE['window']
            win.cursor_warp(x, y)
            win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
            win.event_simulate(type='LEFTMOUSE', value='PRESS', x=x, y=y)
            STATE.update(x=x, y=y, stage=4)
            return 0.2
        if STATE['stage'] == 4:
            STATE['window'].event_simulate(type='LEFTMOUSE', value='RELEASE', x=STATE['x'], y=STATE['y'])
            STATE['stage'] = 5
            return 1.0
        popup = [w for w in widgets() if w.get('popup')]
        assert any(w.get('op') == 'mixie_chat.agent_mode_set' and w.get('text') == 'Lampway Agent' for w in popup), popup
        assert any(w.get('op') == 'mixie_chat.agent_mode_refresh' for w in popup), popup
        assert not any(w.get('op') == 'mixar.agent_model_set' for w in popup), popup
        assert STATE['window'].mixar_ui_capture(filepath=str(OUT / 'mode-menu.png'))
        finish({'ok': True, 'geometry': STATE['geometry'], 'popup_rows': [w.get('text') for w in popup],
                'scope': 'native uiBut geometry and mouse-opened registered menu; no provider or TUI'})
    except Exception:
        finish({'ok': False, 'stage': STATE['stage'], 'error': traceback.format_exc()})
    return None


bpy.app.timers.register(tick, first_interval=15.0)
