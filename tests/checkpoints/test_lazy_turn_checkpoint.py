# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deferred disk checkpoints certify complete read scripts, never their labels."""
import ast
from pathlib import Path
from types import SimpleNamespace

from helpers import _scene, _send

ROOT = Path(__file__).parents[2]


def summary_script():
    tree = ast.parse((ROOT / 'server/lampway_server/agent/tools.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SCENE_SUMMARY_SCRIPT' for t in node.targets):
            return '_LIMIT, _OFFSET, _FULL = 100, 0, False\n' + ast.literal_eval(node.value)
    raise AssertionError('server summary template missing')


def request(script, name='unknown'):
    return SimpleNamespace(script=script, tool_name=name, agent_ctx={'read_only': True})


def test_read_turn_writes_zero_snapshot_bytes(tc):
    scene = _scene()
    pending = tc.m.arm(scene, 'inspect')
    _send(scene)
    tc.m.bind_request(pending, 'command-read')
    for req in [request(summary_script(), 'scene_summary'), request("from mixar.modules.lampway_tools import api\n__RESULT__ = api.call(\"inspect\", '{\"view\": \"mesh\"}')\n", "lampway_inspect")]:
        assert tc.m.before_script(scene, req) is None
    tc.bpy.ops.wm.save_as_mainfile.assert_not_called()
    assert not tc.m.list_checkpoints('sess-1')


def test_unknown_and_forged_read_script_snapshot_before_first_mutation(tc):
    scene = _scene(users=2)
    pending = tc.m.arm(scene, 'mutate')
    _send(scene)
    tc.m.bind_request(pending, 'command-write')
    script = summary_script() + '\nbpy.data.objects.remove(bpy.data.objects[0])\n'
    record = tc.m.before_script(scene, request(script, 'scene_summary'))
    assert record['turn_index'] == 3 and record['message_count'] == 2
    assert record['request_id'] == 'command-write'
    assert record['trim_transcript'] is True
    assert tc.m.before_script(scene, request('bpy.data.objects.clear()')) is None
    assert tc.bpy.ops.wm.save_as_mainfile.call_count == 1
    tc.m._after_load(scene, record, '')
    assert len(scene.mixie_chat_messages) == 2


def test_new_session_remembered_even_after_transport_assigns_id(tc):
    scene = _scene(session_id='', users=0)
    pending = tc.m.arm(scene, 'first')
    scene.mixie_session_id = 'transport-new-session'
    _send(scene)
    tc.m.bind_request(pending, 'first-command')
    record = tc.m.before_script(scene, request('__RESULT__ = {}'))
    assert record['session_was_new'] and record['turn_index'] == 1
    tc.m._after_load(scene, record, '')
    assert scene.mixie_session_id == '' and not scene.mixie_chat_messages


def test_certification_rejects_arbitrary_calls_and_extra_statements(tc):
    for script in [
        'from mixar.modules.lampway_tools import api\n__RESULT__ = api.call("run_tool", {"read_only": True})',
        'from mixar.modules.lampway_tools import api\n__RESULT__ = api.call("inspect", {})\napi.call("delete", {})',
        'from mixar.modules.lampway_tools import api\n__RESULT__ = api.call("inspect", evil())',
        summary_script().replace('100, 0, False', 'evil(), 0, False'),
    ]:
        assert not tc.m.certified_read_script(script)


def test_send_arms_instead_of_capturing_and_executor_runs_hook_before_script():
    send = (ROOT / 'src/scripts/mixar/modules/space_mixie_chat/ui/operators/chat_ops.py').read_text()
    dispatch = (ROOT / 'src/scripts/mixar/modules/space_mixie_chat/core/main_thread_executor.py').read_text()
    assert 'checkpoint = turn_checkpoints.arm(scene, message_text)' in send
    assert dispatch.index('turn_checkpoints.before_script(chat_scene, req)') < dispatch.index('result_dict = pump.execute_request')


def test_scene_rename_keeps_pending_boundary_and_other_turn_cannot_consume_it(tc):
    scene = _scene()
    pending = tc.m.arm(scene, 'write later')
    _send(scene)
    tc.m.bind_request(pending, 'current-turn')
    scene.name = 'Renamed Scene'
    foreign = request('bpy.data.objects.clear()')
    foreign.agent_ctx = {'turn_id': 'other-turn'}
    assert tc.m.before_script(scene, foreign) is None
    tc.bpy.ops.wm.save_as_mainfile.assert_not_called()
    own = request('bpy.data.objects.clear()')
    own.agent_ctx = {'turn_id': 'current-turn'}
    assert tc.m.before_script(scene, own)['request_id'] == 'current-turn'


def test_admitted_typed_mutation_captures_once(tc):
    scene = _scene()
    pending = tc.m.arm(scene, 'append artifact')
    _send(scene)
    tc.m.bind_request(pending, 'typed-command')
    record = tc.m.before_mutation(scene)
    assert record['bytes'] == len(tc.document['bytes'])
    assert record['request_id'] == 'typed-command'
    assert tc.m.before_mutation(scene) is None
    assert tc.bpy.ops.wm.save_as_mainfile.call_count == 1


def test_read_turn_from_reverted_position_drops_dead_branch_without_copy(tc):
    scene = _scene(users=1)
    future = tc.m.capture(scene, 'old turn two')
    assert future['turn_index'] == 2
    tc.bpy.ops.wm.save_as_mainfile.reset_mock()
    tc.m.arm(scene, 'new read turn two')
    assert tc.m.list_checkpoints('sess-1') == []
    tc.bpy.ops.wm.save_as_mainfile.assert_not_called()


def test_summary_certification_accepts_only_bounded_literal_paging(tc):
    script = summary_script()
    for header in ['1000, 12, True', '1, 0, False']:
        assert tc.m.certified_read_script(script.replace('100, 0, False', header, 1))
    for header in ['True, 0, False', '100, False, False', '0, 0, False', '1001, 0, False', '100, -1, False', '100, 0, 1']:
        assert not tc.m.certified_read_script(script.replace('100, 0, False', header, 1))


def test_text_only_turn_has_zero_full_copy_bytes(tc):
    scene = _scene()
    pending = tc.m.arm(scene, 'answer with text')
    _send(scene)
    tc.m.bind_request(pending, 'text-command')
    assert not tc.m.list_checkpoints('sess-1')
    tc.bpy.ops.wm.save_as_mainfile.assert_not_called()
    tc.m.discard_pending(scene)
    assert tc.m.before_mutation(scene) is None


def test_file_load_clears_pending_even_when_checkpoint_restore_keeps_session(tc, monkeypatch):
    from types import ModuleType
    from unittest.mock import MagicMock
    import sys
    scene = _scene()
    tc.m.arm(scene, 'pending read turn')
    tc.m._restoring = True
    for relative, function in [('export_destination', 'clear_all_destinations'), ('import_source', 'clear_all_sources')]:
        module = ModuleType('mixar.modules.space_mixie_chat.core.' + relative)
        setattr(module, function, MagicMock())
        monkeypatch.setitem(sys.modules, module.__name__, module)
    tree = ast.parse((ROOT / 'src/scripts/mixar/modules/space_mixie_chat/core/file_handlers.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_on_load_pre')
    node.decorator_list = []
    namespace = {'__package__': 'mixar.modules.space_mixie_chat.core', 'logger': MagicMock()}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual load_pre>', 'exec'), namespace)
    namespace['_on_load_pre']()
    assert tc.m._pending_turns == {}
    assert tc.session.calls == []  # restoration retains its live session
    for relative, function in [('export_destination', 'clear_all_destinations'), ('import_source', 'clear_all_sources')]:
        getattr(sys.modules['mixar.modules.space_mixie_chat.core.' + relative], function).assert_not_called()
