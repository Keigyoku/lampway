# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A cancelled collector closes its own swarm and leaves Retry cards usable."""
import asyncio
from types import SimpleNamespace

import pytest

from lampway_server.agent.harness import Run, TaskHandle
from lampway_server.agent.swarm import Swarm, SwarmContext, SwarmManager, Worker
from lampway_server.agent.swarm_island import SwarmIsland, RETRY_ACTIONS


@pytest.mark.parametrize("repeat_cancel", [False, True])
@pytest.mark.parametrize("shared_run", [False, True])
def test_cancelled_collect_joins_workers_finishes_cards_and_preserves_independent_work(repeat_cancel, shared_run):
    async def scenario():
        mgr = SwarmManager(None)
        closing, release, revoking, release_revoke = (asyncio.Event() for _ in range(4))
        running = asyncio.Event()
        frames, revoked, shutdown, commits = [], [], [], []

        class Socket:
            async def notify(self, method, params):
                frames.append((method, params))

        socket = Socket()

        class Harness:
            async def spawn_worker(self):
                return "owned-process"

            async def bind_task(self, run, task_id, connection):
                return TaskHandle(task_id, connection)

            async def run_script(self, *args, **kwargs):
                return {"success": True}

            async def revoke(self, run, task_id=None):
                if task_id is None:
                    revoking.set()
                    await release_revoke.wait()
                    run.revoked = True
                revoked.append(task_id)

            async def shutdown_worker(self, connection):
                shutdown.append(connection)

            async def commit(self, *args):
                commits.append(args)
                return {}

        harness = Harness()
        harness.socket = socket
        run = Run("run", "unit", 1)
        worker = Worker("worker-1", "owned", "make owned")
        staged = Worker("worker-2", "staged", "make staged", status="staged", connection_id="staged-process")
        staged.handle = TaskHandle("staged-task", staged.connection_id, artifact={"object_count": 1})
        swarm = Swarm("sw1", "unit", [worker, staged], run=run, harness=harness, mode="byoa")
        independent = Worker("worker-1", "independent", "keep working", status="running")
        other = Swarm("sw2", "unit", [independent], run=run if shared_run else Run("other", "unit", 2))
        foreign = Swarm("sw3", "other-unit", [], run=Run("foreign", "other-unit", 1))
        mgr.swarms = {s.id: s for s in (swarm, other, foreign)}
        session = SimpleNamespace(turns={})
        mgr.island = SwarmIsland(SimpleNamespace(engine=None, _session=lambda unit: session, socket_for=lambda unit: socket))
        ctx = SwarmContext(socket, "unit", "collect-turn", "collect-call")

        class Brain:
            async def run(self, job):
                running.set()
                await asyncio.Event().wait()

            async def stop(self, job):
                closing.set()
                await release.wait()

        swarm.brain = Brain()
        worker.task = asyncio.create_task(mgr._run_worker(swarm, worker, ctx))
        independent.task = asyncio.create_task(asyncio.Event().wait())
        await running.wait()
        await mgr._todo(swarm)
        collector = asyncio.create_task(mgr._collect({"swarm_id": swarm.id}, ctx))
        revoke_waiter = asyncio.create_task(revoking.wait())
        await asyncio.sleep(0)
        collector.cancel("original Stop")
        try:
            await asyncio.wait_for(closing.wait(), 1)
            assert not collector.done(), "collector abandoned its worker's owned cleanup"
            if repeat_cancel:
                collector.cancel("second Stop")
                await asyncio.sleep(0)
                assert not collector.done(), "second Stop abandoned owned cleanup"
                assert not worker.task.done(), "second Stop interrupted worker cleanup"
            release.set()
            if not shared_run:
                # Baseline raises before finishing, so wait on both possible outcomes.
                await asyncio.wait({collector, revoke_waiter}, timeout=1,
                                   return_when=asyncio.FIRST_COMPLETED)
                if repeat_cancel and revoking.is_set():
                    collector.cancel("Stop during revoke")
                    await asyncio.sleep(0)
                    assert not collector.done(), "Stop interrupted capability revocation"
            release_revoke.set()
            with pytest.raises(asyncio.CancelledError, match="original Stop"):
                await collector
            assert swarm.collected, "cancelled collection never terminalized, so its failed tasks cannot be retried"
            assert worker.task.done() and worker.status == staged.status == "cancelled"
            assert commits == [], "cancelled collection committed a staged artifact"
            assert set(revoked) == {"sw1:worker-1", "staged-task", *([] if shared_run else [None])}
            assert set(shutdown) == {"owned-process", "staged-process"}
            assert run.revoked is (not shared_run), "revoked a run still owned by an independent swarm"
            assert not other.collected and not foreign.collected and not foreign.run.revoked
            assert independent.status == "running" and not independent.task.done()
            assert mgr.failed_tasks("unit") == [{"name": "owned", "prompt": "make owned"},
                                                 {"name": "staged", "prompt": "make staged"}]
            assert mgr.retryable("unit")
            card = mgr.island.cards[swarm.id]
            assert card.ended
            assert [e["actions"] for e in card.turn.events if "actions" in e] == [[dict(a) for a in RETRY_ACTIONS]]
            assert [r["status"] for e in card.turn.events if "todo" in e for r in e["todo"]][-2:] == ["FAILED", "FAILED"]
            assert frames[-1][0] == "agent.turn.ended"
        finally:
            release.set()
            release_revoke.set()
            independent.task.cancel()
            revoke_waiter.cancel()
            await asyncio.gather(collector, worker.task, independent.task, revoke_waiter, return_exceptions=True)

    asyncio.run(scenario())
