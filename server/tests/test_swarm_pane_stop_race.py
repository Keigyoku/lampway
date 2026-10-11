# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A cancelled worker is not done until its owned pane's closing thread settles."""
import asyncio
import threading
from types import SimpleNamespace

from lampway_server.herdr.swarm_brain import PaneBrain, WorkerBindings
from lampway_server.agent.swarm import SwarmManager


def test_repeated_worker_cancellation_cannot_outlive_the_owned_pane_record_update():
    async def scenario():
        entered, release = threading.Event(), threading.Event()
        records = {'owned': {'state': 'live', 'end_reason': ''}, 'other': {'state': 'live', 'end_reason': ''}}
        calls = []
        bindings = WorkerBindings()
        job = SimpleNamespace(worker=SimpleNamespace(id='worker-2', status='running'), meta={'swarm_id':'fixture'})
        binding, _ = bindings.issue('swarm:fixture:worker-2', job)
        def close(sid, name, why, close_pane):
            calls.append((sid, name, close_pane, binding.live))
            entered.set()
            assert release.wait(2), 'fixture failed to release the closing thread'
            records[sid].update(state='ended', end_reason=why)
        brain = PaneBrain(SimpleNamespace(end_swarm_pane=close), 'lampway_hermes', cwd='.', project_root=None, bindings=bindings)
        brain._panes[job.worker.id] = ('owned', binding.name)
        async def worker():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                job.worker.status = 'cancelled'
                await brain.stop(job)
                raise
        task = asyncio.create_task(worker())
        job.worker.task = task
        swarm = SimpleNamespace(workers=[job.worker], collected=False)
        manager = SwarmManager.__new__(SwarmManager)
        manager._get = lambda arguments: swarm
        collector = asyncio.create_task(manager._collect({}, SimpleNamespace(emit_todo=None)))
        await asyncio.sleep(0)
        SwarmManager.cancel_worker(job.worker)              # Hub Stop cancels this scope.
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            collector.cancel()                             # Front Stop cancels the MCP swarm_collect.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not task.done(), 'Worker task finished while its pane record was still live'
            assert not binding.live and records['owned']['state'] == 'live'
            assert records['other'] == {'state':'live', 'end_reason':''}
            release.set()
            await asyncio.gather(task, collector, return_exceptions=True)
            assert task.cancelled()
            assert records['owned']['state'] == 'ended' and 'cancelled' in records['owned']['end_reason']
            assert calls == [('owned', binding.name, True, False)]
            assert records['other'] == {'state':'live', 'end_reason':''}
        finally:
            release.set()
            await asyncio.gather(task, collector, return_exceptions=True)
    asyncio.run(scenario())


def test_two_stop_callers_share_the_owned_close_and_join_it_once():
    async def scenario():
        entered, release = threading.Event(), threading.Event()
        bindings, calls = WorkerBindings(), []
        job = SimpleNamespace(worker=SimpleNamespace(id='worker-1', status='cancelled'), meta={'swarm_id':'fixture'})
        binding, _ = bindings.issue('swarm:fixture:worker-1', job)
        def close(*args):
            calls.append(args)
            entered.set()
            assert release.wait(2)
        brain = PaneBrain(SimpleNamespace(end_swarm_pane=close), 'lampway_hermes', cwd='.', project_root=None, bindings=bindings)
        brain._panes[job.worker.id] = ('owned', binding.name)
        first = asyncio.create_task(brain.stop(job))
        second = None
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            second = asyncio.create_task(brain.stop(job))
            first.cancel()
            await asyncio.sleep(0)
            first.cancel()
            await asyncio.sleep(0)
            assert not first.done() and not second.done() and len(calls) == 1
            release.set()
            result = await asyncio.gather(first, second, return_exceptions=True)
            assert isinstance(result[0], asyncio.CancelledError) and result[1] is None
            await brain.stop(job)                           # Settled cleanup is not started again.
            assert len(calls) == 1 and not binding.live
        finally:
            release.set()
            await asyncio.gather(*(t for t in (first, second) if t is not None), return_exceptions=True)
    asyncio.run(scenario())


def test_failed_close_keeps_existing_reconcile_behavior_and_revokes_the_binding():
    async def scenario():
        bindings, calls = WorkerBindings(), []
        job = SimpleNamespace(worker=SimpleNamespace(id='worker-1', status='failed'), meta={'swarm_id':'fixture'})
        binding, _ = bindings.issue('swarm:fixture:worker-1', job)
        def close(*args):
            calls.append(args)
            raise RuntimeError('fixture herdr unavailable')
        brain = PaneBrain(SimpleNamespace(end_swarm_pane=close), 'lampway_hermes', cwd='.', project_root=None, bindings=bindings)
        brain._panes[job.worker.id] = ('owned', binding.name)
        await brain.stop(job)
        await brain.stop(job)
        assert not binding.live and len(calls) == 1
        assert calls[0] == ('owned', binding.name, 'closed by its swarm: the task failed', True)
    asyncio.run(scenario())
