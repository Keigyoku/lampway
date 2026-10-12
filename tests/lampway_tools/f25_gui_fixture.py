# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Normal mock-provider sends in a disposable GUI, measuring real snapshot files."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback
import bpy

ROOT = Path(os.environ['LAMPWAY_PROJECT_ROOT'])
OVERLAY = os.environ['LAMPWAY_VIEW_OVERLAY']
sys.path.insert(0, OVERLAY)
import mixar, mixar.modules
mixar.__path__.insert(0, OVERLAY + '/mixar')
mixar.modules.__path__.insert(0, OVERLAY + '/mixar/modules')
from mixar.modules.space_mixie_chat.core import turn_checkpoints, main_thread_executor
from mixar.modules.space_mixie_chat.ui.operators import chat_ops
from mixar.modules.space_mixie_chat.core.connection_manager import get_connection_manager
from mixar.modules.space_mixie_chat.core.session import get_session_manager
from mixar.modules.space_mixie_chat.core.jsonrpc_client import get_jsonrpc_client
from mixar.modules.auth.core.sso import local_signin



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
if os.environ.get('LAMPWAY_F25_PLANT_EAGER_COPY') == '1':
    # Replay the old eager send behavior in this disposable fixture only.
    for cls in chat_ops.classes:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    code = Path(chat_ops.__file__).read_text()
    assert 'checkpoint = turn_checkpoints.arm(scene, message_text)' in code
    code = code.replace('checkpoint = turn_checkpoints.arm(scene, message_text)',
                        'checkpoint = turn_checkpoints.capture(scene, message_text)', 1)
    exec(compile(code, chat_ops.__file__, 'exec'), chat_ops.__dict__)
state = {'phase': 0, 'deadline': time.monotonic() + 95, 'receipt': {}}


def snapshots():
    root = Path(turn_checkpoints.checkpoints_root())
    return {str(path.relative_to(root)): path.stat().st_size for path in root.rglob('*.mixar')}


def finished(scene):
    return get_session_manager().get_state(scene).value == 'idle' and not get_session_manager().run_open(scene)


def send(text):
    scene = bpy.context.scene
    scene.mixie_chat_mode = 'AGENT'
    scene.mixie_chat_input = text
    assert bpy.ops.mixie_chat.send_message() == {'FINISHED'}
    state['command'] = __import__('mixar.modules.space_mixie_chat.core.turn_transport', fromlist=['get_turn_handler']).get_turn_handler(scene.name).last_command_id


def tick():
    try:
        assert time.monotonic() < state['deadline'], ('phase timeout', state['phase'])
        scene = bpy.context.scene
        if state['phase'] == 0:
            if not hasattr(bpy.context.window_manager, 'mixie_chat_is_logged_in'):
                return .1
            try:
                bpy.ops.mixie_chat.send_message.get_rna_type()
            except (RuntimeError, KeyError):
                for cls in chat_ops.classes:
                    bpy.utils.register_class(cls)
            result = local_signin()
            assert result['success'], result.get('message')
            bpy.context.window_manager.mixie_chat_is_logged_in = True
            get_connection_manager().connect()
            state['phase'] = 1
        elif state['phase'] == 1:
            client = get_jsonrpc_client()
            if not client or not client.connection_id or not get_connection_manager().is_connected:
                return .1
            from mixar.modules.space_mixie_chat.core.composer_send import can_send
            if not can_send(scene)[0]:
                return .1
            from mixar.modules.lampway_tools import chat_route
            if chat_route.refusal(bpy.context):
                return .1
            state['before'] = snapshots()
            send('Inspect the current scene')
            state['phase'] = 2
        elif state['phase'] == 2:
            if not finished(scene):
                return .1
            assert any(m.sender == 'AGENT' and 'Scene summary' in m.text for m in scene.mixie_chat_messages)
            after = snapshots()
            assert after == state['before'], ('read turn copied document', after)
            state['receipt']['read_turn'] = {'full_copy_bytes': 0, 'command_id': state['command']}
            state['prior_messages'] = len(scene.mixie_chat_messages)
            send('py:bpy.data.objects["Cube"].location.x = 9\n__RESULT__ = {"written": True}')
            state['phase'] = 3
        elif state['phase'] == 3:
            if not finished(scene):
                return .1
            assert bpy.data.objects['Cube'].location.x == 9
            after = snapshots()
            added = {k: v for k, v in after.items() if k not in state['before']}
            assert len(added) == 1 and sum(added.values()) > 0, after
            records = turn_checkpoints.list_checkpoints(scene.mixie_session_id)
            assert len(records) == 1 and records[0]['request_id'] == state['command'], records
            assert records[0]['message_count'] == state['prior_messages'] and records[0]['trim_transcript']
            state['receipt']['write_turn'] = {'full_copy_bytes': sum(added.values()), 'copies': len(added), 'turn_index': records[0]['turn_index']}
            state['receipt']['executed_source_sha256'] = {name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() for name, module in [('chat_ops.py', chat_ops), ('turn_checkpoints.py', turn_checkpoints), ('main_thread_executor.py', main_thread_executor)]}
            (ROOT / 'receipt.json').write_text(json.dumps(state['receipt'], indent=2))
            bpy.ops.wm.quit_blender()
            return None
        return .1
    except Exception:
        (ROOT / 'failure.txt').write_text(traceback.format_exc())
        traceback.print_exc()
        bpy.ops.wm.quit_blender()
        return None

bpy.app.timers.register(tick, first_interval=2)
