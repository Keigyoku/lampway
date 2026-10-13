# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure original QA lifecycle mechanics; native receipts remain required."""
import ast
import copy
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

QA = Path(os.environ.get(
    'LAMPWAY_NATIVE_PANES_QA',
    str(Path(__file__).with_name('grok_worker_validation.py')),
))
SPEC = importlib.util.spec_from_file_location('qa_pane_causal', QA)
Q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(Q)
TREE = ast.parse(QA.read_text())
METHOD = next(
    node for node in ast.walk(TREE)
    if isinstance(node, ast.FunctionDef) and node.name == 'native_panes'
)


@pytest.fixture(autouse=True)
def no_external_execution(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('causal mechanics must not execute process/socket/signal')

    monkeypatch.setattr(Q.subprocess, 'run', refuse)
    monkeypatch.setattr(Q.subprocess, 'Popen', refuse)
    monkeypatch.setattr(Q.socket, 'socket', refuse)
    monkeypatch.setattr(Q.os, 'kill', refuse)


def test_pending_ctrlc_fixture_starts_with_genuine_unheld_native_readiness():
    loop = next(
        node for node in ast.walk(METHOD)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Tuple)
        and ast.unparse(node.target) == '(index, action)'
    )
    hold = next(
        node for node in loop.body
        if isinstance(node, ast.Assign)
        and any(ast.unparse(target) == 'self.http.hold_model' for target in node.targets)
    )
    start = next(
        node for node in loop.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == 'command'
        and isinstance(node.value.args[0], ast.List)
        and ast.literal_eval(node.value.args[0].elts[0]) == 'agent'
    )
    observed = []
    http = SimpleNamespace(hold_model=False)

    def command(args):
        observed.append((args, http.hold_model))
        if args[:2] == ['agent', 'start']:
            assert http.hold_model is False, (
                'fixture holds model15s while original herdrstart10s '
                'waits for nonworking readiness'
            )
        if args[:2] == ['agent', 'prompt']:
            assert observed[0][0][:2] == ['agent', 'start'] and observed[0][1] is False
            assert http.hold_model is True

    end_index = next(
        index for index, node in enumerate(loop.body)
        if index > loop.body.index(start)
        and isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'end' for target in node.targets)
    )
    nodes = copy.deepcopy(loop.body[loop.body.index(hold):end_index])
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    scope = {
        'self': SimpleNamespace(http=http),
        'action': 'ctrl-c',
        'index': 0,
        'pane': 'owned-pane',
        'native_args': ['original-native-argv-unchanged'],
        'command': command,
    }
    exec(compile(module, 'actual-qa-startup-slice', 'exec'), scope)
    assert observed[0][0][-1] == 'original-native-argv-unchanged'
    assert observed[1][0] == ['agent', 'prompt', 'owned-0', 'synthetic_pending_ctrlc_probe']
    assert observed[1][1] is True


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_owned_adopted_zombie_is_reaped_before_original_cleanup_assertion(monkeypatch):
    pid = 12345
    row = {'pid': pid, 'start': 'owned-start', 'parent': os.getpid(), 'state': 'Z'}
    current = {pid: row.copy()}
    waited = []
    monkeypatch.setattr(Q, 'process_rows', lambda: current.copy())

    def waitpid(target, flags):
        assert target == pid and flags == os.WNOHANG
        waited.append(target)
        current.pop(target)
        return target, 0

    monkeypatch.setattr(Q.os, 'waitpid', waitpid)
    owned = {pid: row}
    gone = copy.deepcopy(next(
        node for node in METHOD.body
        if isinstance(node, ast.FunctionDef) and node.name == 'gone'
    ))
    scope = {'time': Clock(), 'still_alive': Q.still_alive, 'reap_owned': Q.reap_owned}
    module = ast.fix_missing_locations(ast.Module(body=[gone], type_ignores=[]))
    exec(compile(module, 'actual-qa-gone-slice', 'exec'), scope)
    assert scope['gone'](list(owned.values())) is True, (
        'original gone only polls same-start Z; no exact-owned reaping occurs'
    )
    assert waited == [pid]


@pytest.mark.parametrize('change', [
    {'start': 'reused'},
    {'parent': -1},
    {'state': 'S'},
])
def test_original_reaper_refuses_reused_foreign_or_live_identity(monkeypatch, change):
    row = {'pid': 12345, 'start': 'owned-start', 'parent': os.getpid(), 'state': 'Z'}
    current = {12345: {**row, **change}}
    waited = []
    monkeypatch.setattr(Q, 'process_rows', lambda: current)
    monkeypatch.setattr(Q.os, 'waitpid', lambda *args: waited.append(args))
    Q.reap_owned({12345: row}, exclude=None)
    assert waited == []


def test_direct_child_owned_by_asyncio_is_not_reaped(monkeypatch):
    row = {'pid': 12345, 'start': 'owned-start', 'parent': os.getpid(), 'state': 'Z'}
    waited = []
    monkeypatch.setattr(Q, 'process_rows', lambda: {12345: row})
    monkeypatch.setattr(Q.os, 'waitpid', lambda *args: waited.append(args))
    Q.reap_owned({12345: row}, exclude=12345)
    assert waited == []


@pytest.mark.parametrize('fail_capture', [False, True])
def test_actual_monitor_records_precise_exception_or_exact_owned_rows(fail_capture):
    import threading
    import traceback

    functions = [
        node for node in METHOD.body
        if isinstance(node, ast.FunctionDef) and node.name in {'capture', 'watch_owned'}
    ]
    assert {node.name for node in functions} == {'capture', 'watch_owned'}
    stop = threading.Event()
    owned = {}
    errors = []

    def snapshot(pid, start):
        assert (pid, start) == (100, 'owned-server-start')
        if fail_capture:
            raise RuntimeError('planted exact-owned snapshot failure')
        stop.set()
        return [{'pid': 10, 'start': 'owned-worker-start'}]

    scope = {
        'server_identity': {'pid': 100, 'start': 'owned-server-start'},
        'owned_snapshot': snapshot,
        'owned_lock': threading.Lock(),
        'owned': owned,
        'monitor_stop': stop,
        'monitor_errors': errors,
        'traceback': traceback,
    }
    module = ast.fix_missing_locations(ast.Module(
        body=copy.deepcopy(functions), type_ignores=[],
    ))
    exec(compile(module, str(QA), 'exec'), scope)
    thread = threading.Thread(target=scope['watch_owned'])
    thread.start()
    thread.join(1)
    assert not thread.is_alive()
    if fail_capture:
        assert len(errors) == 1 and 'RuntimeError: planted exact-owned snapshot failure' in errors[0]
        assert owned == {}
    else:
        assert errors == [] and set(owned) == {(10, 'owned-worker-start')}


@pytest.mark.parametrize('failure', ['save', 'capability', 'monitor'])
def test_actual_finally_restores_environment_even_when_save_capability_or_monitor_fails(failure):
    import threading

    outer = next(node for node in METHOD.body if isinstance(node, ast.Try))
    cleanup = next(node for node in outer.finalbody if isinstance(node, ast.Try))
    restoration = cleanup.finalbody[0]
    assert isinstance(restoration, ast.Try) and restoration.finalbody
    calls = []
    before = {'PATH': 'owned-original', 'HOME': 'owned-original-home'}
    environment = {'HOME': 'temporary-fixture'}

    def save():
        calls.append('save')
        if failure == 'save':
            raise RuntimeError('planted save failure')

    def restore_capability(value):
        calls.append(('restore_capability', value))
        if failure == 'capability':
            raise RuntimeError('planted capability restore failure')

    scope = {
        'monitor_stop': threading.Event(),
        'monitor': None,
        'owned_rows': lambda: [],
        'monitor_errors': ['planted monitor failure'] if failure == 'monitor' else [],
        'self': SimpleNamespace(receipt={}, save=save),
        'CAP': SimpleNamespace(set_active=restore_capability),
        'old_capabilities': 'owned-prior-store',
        'os': SimpleNamespace(environ=environment),
        'old_env': before,
        'native_failure': None,
    }
    module = ast.fix_missing_locations(ast.Module(
        body=[copy.deepcopy(restoration)], type_ignores=[],
    ))
    with pytest.raises(RuntimeError):
        exec(compile(module, str(QA), 'exec'), scope)
    assert environment == before
    assert ('restore_capability', 'owned-prior-store') in calls


@pytest.mark.parametrize('action, pending, persona, inner_present, stale_pending, expected', [
    ('ctrl-c', False, True, True, False, False),
    ('ctrl-c', True, True, True, False, True),
    ('hup-term', False, True, True, False, True),
    ('hard-close', False, True, True, False, True),
    ('ctrl-c', True, False, True, False, False),
    ('ctrl-c', True, True, False, False, False),
    ('ctrl-c', False, True, True, True, False),
])
def test_actual_observation_condition_waits_for_current_pending_ctrlc_request(
        action, pending, persona, inner_present, stale_pending, expected):
    observation = next(
        node for node in ast.walk(METHOD)
        if isinstance(node, ast.If)
        and any(isinstance(child, ast.Break) for child in node.body)
    )
    expression = ast.fix_missing_locations(ast.Expression(body=copy.deepcopy(observation.test)))
    earlier_events = [{'persona_present': True, 'model_pending': True, 'request': 'earlier'}] if stale_pending else []
    current_events = [{'persona_present': persona, 'model_pending': pending, 'request': 'current'}]
    scope = {
        'held_turn': Q.held_turn,
        'action': action,
        'current': {'inner_socket': 'owned-inner.sock'},
        'observed': [{'argv': ['owned-native', 'owned-inner.sock' if inner_present else 'other.sock']}],
        'self': SimpleNamespace(http=SimpleNamespace(events=earlier_events + current_events)),
        'offset': len(earlier_events),
    }
    # Evaluate only the actual production QA condition. These are pure owned
    # HTTP-fixture event values, never emitted native frames or readiness state.
    assert eval(compile(expression, str(QA), 'eval'), scope) is expected


@pytest.mark.parametrize('witness_failure, save_failure, restore_failure', [
    (False, False, False),
    (True, False, False),
    (False, True, False),
    (False, False, True),
    (True, True, True),
])
def test_actual_failure_witness_preserves_primary_and_owned_cleanup(
        witness_failure, save_failure, restore_failure):
    import sys
    import threading

    outer = next(node for node in METHOD.body if isinstance(node, ast.Try))
    primary = RuntimeError('original native startup timeout')
    receipt = {}
    calls = []
    environment = {'LAMPWAY_OWNED_FIXTURE_ONLY': 'temporary'}
    before = {'LAMPWAY_GROK_DIAGNOSTIC_SLOT_AUTHORIZED': 'original'}

    def command(args):
        calls.append(args)
        assert args in [
            ['pane', 'read', 'owned-pane'],
            ['agent', 'get', 'owned-0'],
            ['pane', 'close', 'owned-pane'],
        ]
        if witness_failure and args[1] in ['read', 'get']:
            raise RuntimeError('owned witness unavailable')
        return 'controlled owned witness value'

    def save():
        if save_failure:
            raise RuntimeError('owned receipt save unavailable')

    def restore(value):
        assert value == 'original-capabilities'
        calls.append('capabilities-restored')
        if restore_failure:
            raise RuntimeError('owned capability restore unavailable')

    controlled = copy.deepcopy(outer)
    controlled.body = [ast.Raise(exc=ast.Name(id='primary', ctx=ast.Load()), cause=None)]
    module = ast.fix_missing_locations(ast.Module(body=[controlled], type_ignores=[]))
    scope = {
        'primary': primary, 'native_failure': None, 'sys': sys, 'traceback': Q.traceback,
        'panes': ['owned-pane'], 'pane_agents': {'owned-pane': 'owned-0'},
        'command': command, 'self': SimpleNamespace(receipt=receipt, save=save),
        'L': SimpleNamespace(server_info=lambda root: None), 'herdr_root': 'owned-root',
        'monitor_stop': threading.Event(), 'monitor': None, 'monitor_errors': [],
        'owned_rows': lambda: [], 'CAP': SimpleNamespace(set_active=restore),
        'old_capabilities': 'original-capabilities',
        'os': SimpleNamespace(environ=environment), 'old_env': before,
    }
    with pytest.raises(RuntimeError) as failure:
        exec(compile(module, str(QA), 'exec'), scope)
    assert failure.value is primary
    assert 'original native startup timeout' in receipt['native_panes_failure']
    witness = receipt['native_panes_failure_witnesses'][0]
    assert witness['pane'] == 'owned-pane' and witness['agent_name'] == 'owned-0'
    if witness_failure:
        assert 'owned witness unavailable' in witness['screen_failure']
        assert 'owned witness unavailable' in witness['agent_failure']
    else:
        assert witness['screen'] == witness['agent'] == 'controlled owned witness value'
    assert calls[:2] == [['pane', 'read', 'owned-pane'], ['agent', 'get', 'owned-0']]
    assert ['pane', 'close', 'owned-pane'] in calls
    assert 'capabilities-restored' in calls
    assert environment == before


def test_ctrlc_close_is_attributed_to_the_turns_own_request_not_a_side_request():
    """Native panes hold two requests at once (receipt at 33024c9f): a side request without the persona and the turn's own. Only
    the turn's own close counts."""
    side = [{'path': '/v1/chat/completions', 'persona_present': False, 'request': 'side'},
            {'path': '/v1/chat/completions', 'model_pending': True, 'request': 'side'}]
    turn = [{'path': '/v1/chat/completions', 'persona_present': True, 'request': 'turn'},
            {'path': '/v1/chat/completions', 'model_pending': True, 'request': 'turn'}]
    events = side + turn
    assert Q.held_turn(events) == {'turn'}
    side_closed = events + [{'path': '/v1/chat/completions', 'model_cancelled': True, 'request': 'side'}]
    assert not Q.held_turn(side_closed) <= Q.closed_requests(side_closed), 'a side request closing must not pass'
    turn_closed = events + [{'path': '/v1/chat/completions', 'model_cancelled': True, 'request': 'turn'}]
    assert Q.held_turn(turn_closed) <= Q.closed_requests(turn_closed)
    assert Q.held_turn(side) == set() and Q.held_turn([{'model_pending': True}, {'persona_present': True}]) == set()
