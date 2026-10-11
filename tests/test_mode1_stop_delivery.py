# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stop fences retired turns while the bound scene keeps receiving new pane turns."""
import ast

import pytest

from test_mode1_pane_turns import SID, TID, RUN, TE, MP, CHAT, world, pane_started, script_ctx


@pytest.fixture
def bound(world, monkeypatch):
    scene, seen = world
    import bpy
    monkeypatch.setattr(bpy.data.scenes, 'get', lambda name: scene if name == scene.name else None)
    return scene, seen


def test_retired_known_and_queued_turns_stay_fenced_after_history_is_pruned(bound):
    scene, seen = bound
    TE._consume('agent.turn.started', pane_started())
    old_command = 'cancelled-before-start'
    TE._commands[old_command] = (SID, lambda *_: pytest.fail('retired callback ran'))
    queued = 'pane_queued_before_stop'
    TE.handle_turn_notification('agent.turn.started', pane_started(tid=queued))
    recovered = 'pane_queued_recovery_before_stop'
    TE.handle_turn_notification('agent.recovery.status', {'session_id': SID, 'info': {'turn_id': recovered}})
    TE._bindings[SID] = id(scene)
    TE.retire_scene(scene.name)
    assert SID not in TE._blocked
    assert TE._bindings[SID] == id(scene)
    assert TE._turns[TID].complete and not TE._turns[TID].pending
    assert SID not in TE._inbox and old_command not in TE._commands
    # A bounded completed-turn cache may prune these identities; retirement still fences them.
    TE._turns.clear()
    scene.mixie_chat_state, scene.mixie_run_open = 'IDLE', False
    for tid in (TID, queued, recovered, old_command):
        TE._consume('agent.turn.started', pane_started(tid=tid))
        assert tid not in TE._turns
    TE._consume('agent.recovery.status', {'session_id': SID, 'info': {'turn_id': recovered, 'run_id': RUN}})
    assert recovered not in TE._turns
    TE._consume('agent.command.reply', {'command_id': old_command, 'result': {'state': 'complete'}})
    assert MP.script_refusal(SID, script_ctx())['error_type'] == 'unknown_turn'
    fresh = 'pane_new_user_turn_after_stop'
    TE._consume('agent.turn.started', pane_started(tid=fresh, run_id='new-run', user_text='After Stop'))
    assert TE._turns[fresh].pane and not TE._turns[fresh].complete
    assert scene.mixie_chat_state == 'BUSY'
    assert any(m.text == 'After Stop' for m in scene.mixie_chat_messages)
    before = len(seen['slots'])
    TE._consume('agent.turn.event', {'session_id': SID, 'turn_id': TID, 'seq': 0,
                                   'event': {'bubble_id': TID + ':agent', 'content': {'set': 'late old reply'}}})
    assert len(seen['slots']) == before


def test_retire_scene_keeps_other_units_queue_turn_and_callback(bound):
    scene, _ = bound
    other = 'another-bound-unit'
    TE._turns['other-turn'] = TE.Turn(other, 'other-turn', 'other-run')
    callback = lambda *_: None
    TE._commands['other-command'] = (other, callback)
    TE.handle_turn_notification('agent.turn.started', pane_started())
    TE.handle_turn_notification('agent.turn.started', {'session_id': other, 'turn_id': 'other-queued'})
    other_lane = list(TE._inbox[other])
    TE.retire_scene(scene.name)
    assert list(TE._inbox[other]) == other_lane
    assert TE._inbox_bytes == sum(item[2] for item in other_lane)
    assert not TE._turns['other-turn'].complete
    assert TE._commands['other-command'] == (other, callback)
    assert other not in TE._blocked


def test_destructive_scene_drop_still_blocks_new_pane_turns(bound):
    scene, _ = bound
    TE.drop_scene(scene.name)
    assert SID in TE._blocked
    TE._consume('agent.turn.started', pane_started())
    assert TID not in TE._turns


def test_only_stop_cleanup_keeps_the_scene_bound():
    tree = ast.parse((CHAT / 'ui/operators/session_ops.py').read_text())
    abort = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MIXIE_CHAT_OT_abort_session')
    calls = [n for n in ast.walk(abort) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id in ('cleanup_turn_handler', 'cleanup_event_queue_for_scene')]
    assert len(calls) == 2
    assert all(any(k.arg == 'keep_bound' and isinstance(k.value, ast.Constant) and k.value.value is True
                   for k in call.keywords) for call in calls)
