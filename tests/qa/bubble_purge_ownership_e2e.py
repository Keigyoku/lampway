# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual native purge owns floating children, never a main editor window.

Run only inside an isolated matching GUI app with an explicit native slot.
No auth, provider, agent-send, account or engine command is invoked by this test.
The outer owned-process runner must retain source/build fingerprints and cleanup.
"""
import json
import os
from pathlib import Path
import re
import time
import traceback

import bpy

HEAD = os.environ.get('LAMPWAY_BUBBLE_OWNERSHIP_SLOT_AUTHORIZED', '')
assert re.fullmatch('[0-9a-f]{40}', HEAD), 'Explicit exact-head native slot required'
assert (Path(bpy.app.binary_path).parent.parent / 'BUILT_FROM').read_text().strip() == HEAD
OUT = Path(os.environ['LAMPWAY_BUBBLE_OWNERSHIP_OUT']).resolve()
assert OUT.is_relative_to(Path('/workspace/scratch')) and OUT.is_dir()
assert not (OUT / 'result.json').exists(), 'Retain every previous native result'
STATE = {'status': 'running', 'started': time.monotonic(), 'cases': [], 'head': HEAD}


def topology():
    return [{'ptr': wm.as_pointer(), 'windows': [
        {'ptr': w.as_pointer(), 'parent': w.parent.as_pointer() if w.parent else None,
         'temporary': w.screen.is_temporary if w.screen else None,
         'areas': [a.type for a in w.screen.areas] if w.screen else []}
        for w in wm.windows]} for wm in bpy.data.window_managers]


def run_case(pill):
    wm = bpy.context.window_manager
    mains = [w for w in wm.windows if w.parent is None]
    assert len(mains) == 1, ('Exactly one owned host is required', topology())
    main = mains[0]
    area = next(a for a in main.screen.areas if a.type == 'VIEW_3D')
    original_type = area.type
    main_id = main.as_pointer()
    draft = 'Owned native purge must preserve this draft'
    main.scene.mixie_chat_input = draft
    wm.lampway_floating_agent_pill = pill
    # Create through the real native operator while the host remains VIEW_3D.
    with bpy.context.temp_override(window=main, area=area):
        assert bpy.ops.mixar.agent_bubble_open_window() == {'FINISHED'}
    bubbles = [w for w in wm.windows if w.parent == main and w.screen.is_temporary
               and any(a.type == 'AGENT_BUBBLE' for a in w.screen.areas)]
    assert len(bubbles) == 1, ('Actual owned transient bubble absent/ambiguous', topology())
    bubble = bubbles[0]
    pills = [w for w in wm.windows if w.parent == bubble and not w.screen.is_temporary
             and any(a.type == 'AGENT_BUBBLE' for a in w.screen.areas)]
    assert len(pills) == int(pill), ('Actual non-temporary pill ownership', topology())
    children = {w.as_pointer() for w in [bubble, *pills]}
    caller = pills[0] if pills else bubble
    caller_id = caller.as_pointer()
    area.type = 'AGENT_BUBBLE'
    before = topology()
    record = {'pill_enabled': pill, 'host': main_id, 'owned_children': sorted(children),
              'caller': caller_id, 'before': before}
    STATE['cases'].append(record)
    (OUT / ('before-purge-pill-' + str(pill).lower() + '.json')).write_text(json.dumps(STATE, indent=2))
    # Invoke from the real child context to also exercise restoration after
    # the native close recursively destroys the current child/pill.
    child_area = next(a for a in caller.screen.areas if a.type == 'AGENT_BUBBLE')
    with bpy.context.temp_override(window=caller, area=child_area):
        result = bpy.ops.mixar.agent_bubble_purge_windows()
        context_after = bpy.context.window.as_pointer() if bpy.context.window else None
    # Never dereference a destroyed child or a destroyed host wrapper.
    after = topology()
    live = [w for manager in bpy.data.window_managers for w in manager.windows]
    live_ids = {w.as_pointer() for w in live}
    record.update(result=sorted(result), after=after, context_after=context_after)
    assert main_id in live_ids, ('Purge destroyed the main window hosting AGENT_BUBBLE', record)
    assert children.isdisjoint(live_ids), ('Purge retained owned transient children', record)
    assert context_after == main_id, ('Purge did not restore a live surviving host context', record)
    preserved = next(w for w in live if w.as_pointer() == main_id)
    assert preserved.scene.mixie_chat_input == draft, ('Host draft changed', record)
    assert area.type == 'AGENT_BUBBLE', ('Host editor changed', record)
    # A second purge is a no-op for the surviving main editor.
    with bpy.context.temp_override(window=preserved, area=area):
        assert bpy.ops.mixar.agent_bubble_purge_windows() == {'FINISHED'}
    assert topology() == after, ('No-op purge changed surviving native windows', record)
    area.type = original_type
    record['passed'] = True


def finish():
    STATE['completed'] = time.monotonic()
    STATE['final_topology'] = topology()
    (OUT / 'result.json').write_text(json.dumps(STATE, indent=2))
    print('RESULT', json.dumps(STATE), flush=True)
    bpy.ops.wm.quit_blender()


def tick():
    try:
        assert time.monotonic() - STATE['started'] < 60, 'Native ownership proof exceeded its original bound'
        import bootstrap
        for _ in range(100000):
            if bootstrap._load_ui_batch_tick() is None:
                break
        wm = getattr(bpy.context, 'window_manager', None)
        if wm is None or not wm.windows:
            STATE.setdefault('startup_topology', []).append(topology())
            return .2
        assert hasattr(bpy.types.Scene, 'mixie_chat_input')
        assert hasattr(wm, 'lampway_floating_agent_pill')
        wm.lampway_floating_agent_pill = False
        # Retire only native startup children before constructing the case;
        # host is still VIEW_3D here, so this does not exercise the defect yet.
        assert bpy.ops.mixar.agent_bubble_purge_windows() == {'FINISHED'}
        run_case(False)
        run_case(True)
        STATE['status'] = 'passed'
    except BaseException:
        STATE.update(status='failed', error=traceback.format_exc())
    finish()
    return None


bpy.app.timers.register(tick, first_interval=3)
