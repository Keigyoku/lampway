# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""In-process early-ACP-exit control; no child/native process is launched."""
import asyncio
import importlib.util
import os
from pathlib import Path
import signal
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[2] / 'tests/qa/grok_worker_validation.py'
spec = importlib.util.spec_from_file_location('owned_grok_qa_control', SOURCE)
QA = importlib.util.module_from_spec(spec)
spec.loader.exec_module(QA)


def test_native_exit_during_first_request_cleans_orphan_exactly(tmp_path, monkeypatch):
    state = {'exited': False, 'child_live': True}
    child = {'pid': 543212, 'start': 'original-child', 'parent': 1,
             'session': 543211, 'group': 543211, 'argv': ['owned-fixture'], 'pid_namespace': 'fixture'}
    signals = []
    class Input:
        def write(self, value): pass
        async def drain(self): pass
    class Output:
        async def readline(self):
            state['exited'] = True
            raise RuntimeError('planted native ACP early exit')
    class Process:
        pid = 543211
        stdin = Input()
        stdout = Output()
        @property
        def returncode(self): return 1 if state['exited'] else None
        async def wait(self): return 1
    async def create(*args, **kwargs): return Process()
    monkeypatch.setattr(QA.asyncio, 'create_subprocess_exec', create)
    monkeypatch.setattr(QA, 'process_rows', lambda: {} if state['exited'] else {
        543211: {'pid': 543211, 'start': 'original-parent'}})
    # Old ancestry-only snapshot loses the reparented child; the corrected
    # private-session capture still identifies its recorded session origin.
    monkeypatch.setattr(QA, 'owned_snapshot', lambda root, start=None:
        [child] if start is not None and state['exited'] and state['child_live'] else [])
    monkeypatch.setattr(QA, 'still_alive', lambda row: row == child and state['child_live'])
    def kill(pid, sig):
        signals.append((pid, sig)); state['child_live'] = False
    monkeypatch.setattr(QA.os, 'kill', kill)
    monkeypatch.setattr(QA.os, 'killpg', lambda *a: pytest.fail('broad group signal prohibited'))
    validator = QA.Validator(SimpleNamespace(output=tmp_path / 'out', phase='stdio'))
    with pytest.raises(RuntimeError, match='planted native ACP early exit'):
        asyncio.run(validator.acp(['synthetic-no-process'], {}, tmp_path, 'early-exit'))
    assert signals == [(child['pid'], signal.SIGTERM)]
    assert not state['child_live']
    assert validator.receipt['cases'][-1]['name'] == 'early-exit owned ACP cleanup'
    assert validator.receipt['cases'][-1]['passed']


def test_session_snapshot_retains_orphan_and_rejects_reused_leader(monkeypatch):
    pid = os.getpid(); root = 99999999
    row = {'pid': pid, 'parent': 1, 'group': root, 'session': root, 'start': 'child-start'}
    monkeypatch.setattr(QA, 'process_rows', lambda: {pid: row})
    assert [r['pid'] for r in QA.owned_snapshot(root, 'original-parent')] == [pid]
    monkeypatch.setattr(QA, 'process_rows', lambda: {pid: row, root: {
        'pid': root, 'parent': 1, 'group': root, 'session': root, 'start': 'reused-parent'}})
    assert QA.owned_snapshot(root, 'original-parent') == []


def test_cleanup_does_not_signal_reused_child_identity(monkeypatch):
    row = {'pid': 543212, 'start': 'old-start'}
    monkeypatch.setattr(QA, 'owned_snapshot', lambda *a: [])
    monkeypatch.setattr(QA, 'still_alive', lambda value: False)
    monkeypatch.setattr(QA.os, 'kill', lambda *a: pytest.fail('reused or foreign PID must not be signalled'))
    class Process:
        pid = 543211
        async def wait(self): return 1
    asyncio.run(QA.cleanup_acp(Process(), 'parent-start', {(row['pid'], row['start']): row}))
