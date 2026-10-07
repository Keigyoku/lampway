# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated Blender half of the real loopback Mode 1 integration fixture.

File commands stand in for test-user clicks; network, event ingress, executor, RNA and disk remain real.
No provider credentials are read. Run only through test_agent_modes_integrated_live.py.
"""
import json
import os
from pathlib import Path
import time
import traceback

import bpy

ROOT = Path(os.environ['LW_INTEGRATION_ROOT'])
STATE = {'last': 0, 'booted': False, 'replies': {}, 'script_gates': [], 'worker_processes': {}}


def snapshot():
    from mixar.modules.space_mixie_chat.core import turn_events as TE
    from mixar.modules.space_mixie_chat.core import connection_manager as CM
    from mixar.bootstrap import sandbox_supervisor
    with sandbox_supervisor._lock:
        children = list(sandbox_supervisor._children.items())
    for cid, proc in children:
        STATE['worker_processes'][cid] = {'pid': proc.pid, 'returncode': proc.poll()}
    sc = bpy.context.scene
    return {'connected': CM.get_connection_manager().is_connected, 'sid': sc.mixie_session_id,
            'delivery_blocked': sc.mixie_session_id in TE._blocked,
            'state': sc.mixie_chat_state, 'run_open': sc.mixie_run_open,
            'mutation': sc.get('fixture_mutation'),
            'messages': [{'sender': m.sender, 'text': m.text, 'content': m.content, 'bubble_id': m.bubble_id,
                          'steps': [{'label': s.label, 'status': s.status} for s in m.step_items]} for m in sc.mixie_chat_messages],
            'turns': {k: {'complete': v.complete, 'pane': v.pane, 'observed': v.observed} for k, v in TE._turns.items()},
            'replies': STATE['replies'], 'command': STATE['last'],
            'script_gates': STATE['script_gates'],
            'worker_processes': STATE['worker_processes'],
            'scene_objects': sorted(o.name for o in sc.objects),
            'collections': {c.name: sorted(o.name for o in c.objects) for c in bpy.data.collections},
            'collection_children': {c.name: sorted(child.name for child in c.children) for c in bpy.data.collections},
            'conversation': str(sc.get('mixie_pane_conversation') or '')}


def publish(value):
    tmp = ROOT / 'status.tmp'
    tmp.write_text(json.dumps(value, default=str))
    tmp.replace(ROOT / 'status.json')


def reply(rid, result):
    STATE['replies'][str(rid)] = result


def act(command):
    from mixar.modules.space_mixie_chat.core import turn_events as TE, mode1_pane as MP
    from mixar.modules.common.agent_rpc import client as rpc
    sc = bpy.context.scene
    action = command['action']
    if action == 'chat':
        sc.mixie_chat_input = command['text']
        result = bpy.ops.mixie_chat.send_message()
        assert result == {'FINISHED'}, result
    elif action == 'stop':
        assert bpy.ops.mixie_chat.abort_session() == {'FINISHED'}
    elif action == 'enable_fixture_swarm':
        # Synthetic fixture user click, using only its generated loopback bearer.
        from urllib.request import Request, urlopen
        from mixar.modules.auth.core import auth
        url = os.environ['LAMPWAY_BACKEND_URL'] + '/app/capabilities/swarm'
        request = Request(url, data=b'{"enabled":true}', method='PUT',
                          headers={'Authorization': 'Bearer ' + auth.get_access_token(),
                                   'Content-Type': 'application/json'})
        with urlopen(request, timeout=15) as response:
            reply(command['id'], json.load(response))
    elif action == 'rpc':
        rid = command['id']
        rpc.command(command['method'], command['payload'], lambda result: reply(rid, result))
    elif action == 'undo':
        assert bpy.ops.ed.undo() == {'FINISHED'}
    elif action == 'seed_media_checkpoint':
        from mixar.modules.space_mixie_chat.core import chat_history as CH, checkpoint_store as CS
        media = ROOT / 'fixture.png'
        image = bpy.data.images.new('Fixture', width=2, height=2)
        image.filepath_raw = str(media); image.file_format = 'PNG'; image.save()
        msg = next(m for m in reversed(sc.mixie_chat_messages) if m.sender == 'USER')
        att = msg.attachments.add(); att.image_path = str(media); att.image_source = 'FILE'
        assert CH.archive_current(sc)
        checkpoint = Path(CS.session_dir(sc.mixie_session_id)) / 'fixture.mixar'
        bpy.ops.wm.save_as_mainfile(filepath=str(checkpoint), copy=True)
        CS._write_index(sc.mixie_session_id, [{'id': 'fixture', 'session_id': sc.mixie_session_id, 'file': 'fixture.mixar',
             'kind': 'turn', 'turn': 1, 'created_at': '2026-10-07T10:00:00+00:00', 'seq': 1}])
    elif action == 'archive_status':
        from mixar.modules.space_mixie_chat.core import chat_history as CH, checkpoint_store as CS
        rows = CH.list_sessions(); result = []
        for row in rows:
            sid = row['session_id']; record = CH.load_session(sid)
            media = [a['image_path'] for m in record['messages'] for a in m.get('attachments') or []]
            result.append({'sid': sid, 'messages': record['messages'], 'media': media,
                           'media_exists': all(Path(p).is_file() for p in media),
                           'checkpoints': CS.list_checkpoints(sid)})
        reply(command['id'], result)
    elif action == 'unknown_script_gate':
        result = MP.script_refusal(sc.mixie_session_id, {'chat_session_id': sc.mixie_session_id,
                    'turn_id': 'pane_unannounced_fixture', 'call_id': 'fixture-call'})
        assert result and result['error_type'] == 'unknown_turn', result
        reply(command['id'], result)
    elif action == 'quit':
        publish({**snapshot(), 'done': True})
        bpy.ops.wm.quit_blender()
    else:
        raise AssertionError(action)


def tick():
    try:
        if not STATE['booted']:
            import bootstrap
            for _ in range(100000):
                if bootstrap._load_ui_batch_tick() is None: break
            from mixar.modules.lampway_tools import api
            assert api.status()['ok']
            from mixar.modules.auth.core import auth
            answer = auth.login('owner@lampway.local', 'correct-horse')
            assert answer['success'], {k:v for k,v in answer.items() if k != 'token'}
            from mixar.modules.space_mixie_chat.core.connection_manager import get_connection_manager
            assert get_connection_manager().connect()
            from mixar.modules.space_mixie_chat.core import mode1_pane as MP, turn_events as TE
            original_gate = MP.script_refusal
            def record_gate(sid, context):
                tid = MP.pane_turn_id(context)
                before = TE._turns.get(tid)
                result = original_gate(sid, context)
                after = TE._turns.get(tid)
                STATE['script_gates'].append({'turn': tid, 'known_before': before is not None,
                    'known_after': after is not None, 'complete': after.complete if after else None,
                    'refusal': result.get('error_type') if result else None})
                return result
            MP.script_refusal = record_gate
            STATE['booted'] = True
        file = ROOT / 'command.json'
        if file.exists():
            command = json.loads(file.read_text())
            if command['id'] > STATE['last']:
                STATE['last'] = command['id']
                act(command)
        publish(snapshot())
        return 0.1
    except Exception:
        publish({'error': traceback.format_exc(), 'command': STATE['last']})
        print('RESULT ' + json.dumps({'ok': False, 'error': traceback.format_exc()}), flush=True)
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(tick, first_interval=15.0)
