# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cloud binary regressions with real RNA/slots/disk, scripted server frames and no agent/provider.

These prove client protocol behavior and registered menus, not TUI interaction or native chip pixels.
"""
from blender_run import run_script

PRE = r'''
import bpy, json, os
from pathlib import Path
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools import api
status = api.status()
assert status['ok'], status
from mixar.modules.space_mixie_chat.core import agent_mode as AM, turn_events as TE, mode1_pane as MP
from mixar.modules.space_mixie_chat.core import byoa_view as BV, session as S
from mixar.modules.space_mixie_chat.constants import SessionState
TE.reset()
sc = bpy.context.scene
sc.mixie_chat_messages.clear()
sc.mixie_chat_state = 'IDLE'
sc.mixie_session_id = '33333333-3333-4333-8333-333333333333'
sc.lampway_agent_mode = 'runtime'
sc.mixie_run_open = False
sc.mixie_run_id = ''
SID = sc.mixie_session_id
TE.bind(sc)
def start(tid, **kw):
    TE._consume('agent.turn.started', {'session_id': SID, 'turn_id': tid, **kw})
def event(tid, seq, payload):
    TE._consume('agent.turn.event', {'session_id': SID, 'turn_id': tid, 'seq': seq, 'event': payload})
def bubble(tid):
    return next(m for m in sc.mixie_chat_messages if m.bubble_id == tid + ':agent')
'''


def checked(body, **kw):
    r = run_script(PRE + body, **kw)
    assert r.rc == 0, r.out[-7000:]
    assert r.results and r.results[-1]['ok'], r.out[-7000:]
    return r.results[-1]


def test_registered_mode_ui_refuses_busy_and_two_saved_tabs_keep_their_mode_and_pane(tmp_path):
    blend = tmp_path / 'agent-modes.blend'
    out = checked(r'''
from mixar.modules.byok.ui.menus import agent_model_menu as MM
assert bpy.types.Menu.bl_rna_get_subclass_py('MIXIE_CHAT_MT_agent_mode') is MM.MIXIE_CHAT_MT_agent_mode
assert bpy.types.Menu.bl_rna_get_subclass_py('MIXIE_CHAT_MT_agent_model') is MM.MIXIE_CHAT_MT_agent_model
assert hasattr(bpy.ops.mixie_chat, 'agent_mode_set')
refused = []
for state in ('BUSY', 'MODIFYING', 'AWAITING_INPUT'):
    sc.mixie_chat_state = state
    assert AM.prepare(sc, 'byoa', 'codex')['code'] == 'scene_busy'
    try:
        result = bpy.ops.mixie_chat.agent_mode_set(mode='byoa', harness='codex')
    except RuntimeError as exc:
        assert 'working' in str(exc).lower() and 'Stop' in str(exc), str(exc)
        result = {'CANCELLED'}
    assert result == {'CANCELLED'}
    assert sc.lampway_agent_mode == 'runtime' and sc.lampway_byoa_pane == ''
    refused.append(state)
sc.mixie_chat_state = 'IDLE'
sc.name = 'Mode1 tab'
sc['mixie_pane_conversation'] = 'scripted-conversation'
yours = bpy.data.scenes.new('Mode2 tab')
yours.lampway_agent_mode = 'byoa'
yours.lampway_byoa_pane = 'fixture-pane'
yours['lampway_byoa_harness'] = 'codex'
path = Path(os.environ['LW_FIXTURE_BLEND'])
bpy.ops.wm.save_as_mainfile(filepath=str(path))
print('RESULT ' + json.dumps({'ok': True, 'refused': refused}))
''', env={'LW_FIXTURE_BLEND': str(blend)})
    assert out['refused'] == ['BUSY', 'MODIFYING', 'AWAITING_INPUT']
    reopened = run_script(r'''
import bpy, json, os
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
bpy.ops.wm.open_mainfile(filepath=os.environ['LW_FIXTURE_BLEND'])
a, b = bpy.data.scenes['Mode1 tab'], bpy.data.scenes['Mode2 tab']
print('RESULT ' + json.dumps({'mode1': a.lampway_agent_mode, 'conversation': a['mixie_pane_conversation'],
    'mode2': b.lampway_agent_mode, 'pane': b.lampway_byoa_pane, 'harness': b['lampway_byoa_harness']}))
''', env={'LW_FIXTURE_BLEND': str(blend)})
    assert reopened.rc == 0, reopened.out[-7000:]
    assert reopened.results[-1] == {'mode1': 'runtime', 'conversation': 'scripted-conversation',
                                   'mode2': 'byoa', 'pane': 'fixture-pane', 'harness': 'codex'}


def test_mode1_standalone_swarm_card_does_not_settle_a_concurrent_pane_turn():
    checked(r'''
start('pane_fixture', origin='pane', run_id='fixture-main-run', user_text='scripted pane prompt')
event('pane_fixture', 0, {'bubble_id': 'pane_fixture:agent', 'loader': {'visible': True, 'texts': ['Working']},
                          'steps': {'items': [{'id': 'active', 'label': 'Scene inspection', 'status': 'running'}]}})
assert sc.mixie_chat_state == 'BUSY' and sc.mixie_run_open
main = bubble('pane_fixture')
assert main.loader_visible and main.step_items[0].status == 'RUNNING'
cursor = json.dumps(dict(sc['mixie_ws_resume']))
start('card_fixture', observed=True, swarm='fixture-swarm', pane='fixture-pane')
event('card_fixture', 0, {'bubble_id': 'card_fixture:agent',
    'todo': [{'id': 'worker-1', 'text': 'Worker one', 'status': 'in_progress'}]})
assert bubble('card_fixture').todo_items[0].status == 'IN_PROGRESS'
event('card_fixture', 1, {'bubble_id': 'card_fixture:agent',
    'todo': [{'id': 'worker-1', 'text': 'Worker one', 'status': 'failed'}],
    'actions': [{'label': 'Retry failed tasks', 'value': 'continue', 'style': 'PRIMARY'}]})
event('card_fixture', 2, {'type': 'turn_end', 'status': 'completed'})
assert TE._turns['card_fixture'].complete
assert not TE._turns['pane_fixture'].complete and sc.mixie_chat_state == 'BUSY'
assert sc.mixie_run_open and sc.mixie_run_id == 'fixture-main-run'
assert main.loader_visible and main.step_items[0].status == 'RUNNING'
assert json.dumps(dict(sc['mixie_ws_resume'])) == cursor
card = bubble('card_fixture')
assert card.todo_items[0].status == 'FAILED' and card.action_items[0].value == 'continue'
event('pane_fixture', 1, {'bubble_id': 'pane_fixture:agent', 'content': {'set': 'Main turn finished.'}})
event('pane_fixture', 2, {'type': 'turn_end', 'status': 'completed', 'run_id': 'fixture-main-run'})
assert sc.mixie_chat_state == 'IDLE' and TE._turns['pane_fixture'].complete
print('RESULT ' + json.dumps({'ok': True}))
''')


def test_mode2_card_end_preserves_the_working_pane_loader_steps_and_cursor():
    checked(r'''
sc.lampway_agent_mode = 'byoa'
sc.lampway_byoa_pane = 'fixture-pane'
start('observed_fixture', observed=True, pane='fixture-pane', user_text='pane prompt')
event('observed_fixture', 0, {'type': 'run_status', 'status': 'in_progress'})
event('observed_fixture', 1, {'bubble_id': 'observed_fixture:agent', 'loader': {'visible': True, 'texts': ['Working']},
    'steps': {'items': [{'id': 'active', 'label': 'Harness inspection', 'status': 'running'}]}})
assert (BV.ACTIVITY.get(SID) == 'working')
sc[BV.CURSOR_KEY] = {'pane': 'fixture-pane', 'offset': 17}
main = bubble('observed_fixture')
start('card_fixture', observed=True, swarm='fixture-swarm', pane='fixture-pane')
event('card_fixture', 0, {'bubble_id': 'card_fixture:agent',
    'todo': [{'id': 'worker-1', 'text': 'Worker one', 'status': 'done'}]})
event('card_fixture', 1, {'type': 'turn_end', 'status': 'completed'})
assert (BV.ACTIVITY.get(SID) == 'working') and sc.mixie_chat_is_busy and sc.mixie_chat_state == 'IDLE'
assert sc[BV.CURSOR_KEY]['offset'] == 17
assert main.loader_visible and main.step_items[0].status == 'RUNNING'
assert TE._turns['card_fixture'].complete and not TE._turns['observed_fixture'].complete
event('observed_fixture', 2, {'type': 'turn_end', 'status': 'completed', 'offset': 31})
assert not (BV.ACTIVITY.get(SID) == 'working') and sc[BV.CURSOR_KEY]['offset'] == 31
print('RESULT ' + json.dumps({'ok': True}))
''')


def test_pane_new_files_real_history_checkpoint_media_and_fences_scripts_and_late_frames():
    checked(r'''
from mixar.modules.space_mixie_chat.core import chat_history as CH, checkpoint_store as CS
ctx = {'chat_session_id': SID, 'turn_id': 'pane_fixture', 'call_id': 'fixture-call'}
assert MP.script_refusal(SID, ctx)['error_type'] == 'unknown_turn'
TE.handle_turn_notification('agent.turn.started', {'session_id': SID, 'turn_id': 'pane_fixture',
    'origin': 'pane', 'run_id': 'fixture-run', 'user_text': 'Keep my chair'})
assert MP.script_refusal(SID, ctx) is None, 'queued start must be drained before script decision'
media = Path(os.environ['TMPDIR']) / 'fixture.png'
# Small synthetic image; no external fixture or media metadata.
image = bpy.data.images.new('Fixture', width=2, height=2)
image.filepath_raw = str(media); image.file_format = 'PNG'; image.save()
event('pane_fixture', 0, {'bubble_id': 'pane_fixture:agent', 'content': {'set': 'Saved chair.'},
    'images': [{'local_path': str(media), 'url': str(media), 'thumbnail_url': str(media)}]})
assert CH.archive_current(sc)
checkpoint = Path(CS.session_dir(SID)) / 'c1.mixar'
# Save a real binary scene snapshot instead of claiming an arbitrary byte string is a checkpoint.
bpy.ops.wm.save_as_mainfile(filepath=str(checkpoint), copy=True)
CS._write_index(SID, [{'id': 'c1', 'session_id': SID, 'file': 'c1.mixar', 'kind': 'turn', 'turn': 1,
    'created_at': '2026-10-07T10:00:00+00:00', 'seq': 1}])
TE._consume('agent.pane.new_conversation', {'session_id': SID, 'origin': 'pane', 'conversation_id': 'fixture-new'})
assert sc.mixie_session_id == SID and sc['mixie_pane_conversation'] == 'fixture-new'
assert len(sc.mixie_chat_messages) == 1 and sc.mixie_chat_messages[0].text == MP.NEW_CONVERSATION_NOTICE
assert MP.script_refusal(SID, ctx)['error_type'] == 'unknown_turn'
rows = CH.list_sessions()
assert len(rows) == 1 and rows[0]['session_id'] != SID, rows
filed = rows[0]['session_id']; record = CH.load_session(filed)
assert record['messages'][0]['text'] == 'Keep my chair'
images = next(m['image_items'] for m in record['messages'] if m.get('image_items'))
for field in ('local_path', 'url', 'thumbnail_url'):
    path = Path(images[0][field]); assert path.is_file() and str(path).startswith(CH.media_dir(filed)), images
assert not Path(CH.media_dir(SID)).exists()
assert CS.list_checkpoints(SID) == [] and CS.list_checkpoints(filed)[0]['id'] == 'c1'
assert (Path(CS.session_dir(filed)) / 'c1.mixar').is_file()
event('pane_fixture', 1, {'bubble_id': 'pane_fixture:agent', 'content': {'set': 'STALE'}})
assert len(sc.mixie_chat_messages) == 1 and 'STALE' not in sc.mixie_chat_messages[0].text
print('RESULT ' + json.dumps({'ok': True}))
''')
