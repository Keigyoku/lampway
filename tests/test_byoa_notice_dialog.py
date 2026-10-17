# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Human notice queue and cancellation controls, with bpy and threads replaced by fakes."""
import ast
import inspect
import pytest
from mixar.modules.lampway_tools.ui import launch_notice as N

# Execute the production operator body with a plain base; bpy.types.Operator is a MagicMock here.
def operator_type():
    tree = ast.parse(inspect.getsource(N))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    node.bases = [ast.Name(id='object', ctx=ast.Load())]
    space = dict(N.__dict__)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), N.__file__, 'exec'), space)
    return space[node.name]

@pytest.fixture(autouse=True)
def clean(monkeypatch):
    N._PENDING.clear()
    while not N._READY.empty():
        N._READY.get_nowait()
    N._WORKING[0] = 0
    monkeypatch.setattr(N.human_gate, 'script_running', lambda: False)
    yield
    N._PENDING.clear()

@pytest.mark.parametrize('fails', [False, True])
def test_failed_dialog_does_not_retain_pending_nonce(monkeypatch, fails):
    outcomes = []
    def invoke(*a, **k):
        if fails:
            raise RuntimeError('synthetic popup failure')
        return {'CANCELLED'}
    monkeypatch.setattr(N.bpy.ops.lampway, 'native_launch_confirm', invoke)
    N.confirm({'required': True, 'nonce': 'synthetic'}, lambda _: pytest.fail('not confirmed'),
              lambda value, error: outcomes.append((value, error)))
    assert N._PENDING == {} and len(outcomes) == 1 and outcomes[0][1]

def test_callback_failure_does_not_strand_later_queue_items():
    observed = []
    def broken():
        raise RuntimeError('synthetic callback failure')
    N._READY.put(broken)
    N._READY.put(lambda: observed.append(True))
    assert N._tick() is None and observed == [True]

def test_explicit_cancel_discards_nonce_without_launch():
    operator = operator_type()()
    operator.ticket = 'owned-ticket'
    N._PENDING[operator.ticket] = ({'nonce': 'synthetic'}, lambda _: pytest.fail('cancel launched'),
                                 lambda *a: None, None)
    operator.cancel(None)
    assert N._PENDING == {}

def test_script_cannot_consume_or_leave_first_confirmation(monkeypatch):
    operator = operator_type()()
    operator.ticket = 'owned-ticket'
    N._PENDING[operator.ticket] = ({'nonce': 'synthetic'}, lambda _: pytest.fail('script launched'),
                                 lambda *a: None, None)
    monkeypatch.setattr(N.human_gate, 'script_running', lambda: True)
    assert operator.execute(None) == {'CANCELLED'}
    assert N._PENDING == {}


def test_human_execute_sends_exact_nonce_once(monkeypatch):
    operator = operator_type()()
    operator.ticket = 'owned-ticket'
    sent = []
    monkeypatch.setattr(N, '_background', lambda call, done: done(call(), None))
    N._PENDING[operator.ticket] = ({'nonce': 'synthetic-issued'}, lambda nonce: sent.append(nonce),
                                 lambda *a: None, lambda: True)
    assert operator.execute(None) == {'FINISHED'}
    assert operator.execute(None) == {'CANCELLED'}
    assert sent == ['synthetic-issued'] and N._PENDING == {}


def test_stale_scene_cannot_confirm(monkeypatch):
    operator = operator_type()()
    operator.ticket = 'owned-ticket'
    outcomes = []
    N._PENDING[operator.ticket] = ({'nonce': 'synthetic-issued'}, lambda _: pytest.fail('stale launch'),
                                 lambda value, error: outcomes.append(error), lambda: False)
    assert operator.execute(None) == {'CANCELLED'}
    assert outcomes and N._PENDING == {}


def test_failed_worker_start_does_not_strand_queue(monkeypatch):
    outcomes = []
    class FailedThread:
        def __init__(self, *a, **k):
            pass
        def start(self):
            raise RuntimeError('synthetic thread refusal')
    monkeypatch.setattr(N.threading, 'Thread', FailedThread)
    N._background(lambda: pytest.fail('not started'), lambda result, error: outcomes.append(error))
    assert N._WORKING == [0] and len(outcomes) == 1 and outcomes[0]
