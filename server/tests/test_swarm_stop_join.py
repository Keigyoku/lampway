# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stop joins workers it cancels even when no swarm_collect request is active."""
import asyncio
from types import SimpleNamespace
import pytest

from lampway_server.agent.turns import AgentHub


@pytest.mark.parametrize('cancel_stop_request, cancel_tool_join', [(False, False), (True, False), (False, True)])
def test_stop_without_a_collector_joins_cancelled_workers_and_leaves_independent_workers(cancel_stop_request, cancel_tool_join):
    async def scenario():
        hub = AgentHub(object())
        closing, release = asyncio.Event(), asyncio.Event()
        if cancel_tool_join:
            async def tool_join(unit):
                if unit == 'a':
                    await closing.wait()
                    raise asyncio.CancelledError
                return 0
            hub.engine = SimpleNamespace(is_running=lambda unit: False, cancel_tool_calls=tool_join)
        records = {'owned':'live', 'other':'live', 'independent':'live'}
        async def worker():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                closing.set()
                await release.wait()
                records['owned'] = 'ended'
                raise
        owned = SimpleNamespace(status='running', task=asyncio.create_task(worker()))
        other = SimpleNamespace(status='running', task=asyncio.create_task(asyncio.Event().wait()))
        independent = SimpleNamespace(status='running', task=asyncio.create_task(asyncio.Event().wait()))
        hub.swarm.swarms = {
            'owned':SimpleNamespace(parent_session='a', collected=False, workers=[owned]),
            'other':SimpleNamespace(parent_session='b', collected=False, workers=[other]),
            'independent':SimpleNamespace(parent_session='finished', collected=False, workers=[independent]),
        }
        session = hub._session('a')
        island = asyncio.create_task(asyncio.Event().wait())
        session.current = SimpleNamespace(task=island, turn_id='island')
        await asyncio.sleep(0)
        stop = asyncio.create_task(hub._cancel(object(), {'command_id':'stop','payload':{'session_id':'a'}}))
        try:
            await closing.wait()
            await asyncio.sleep(0)
            assert not stop.done(), 'Stop acknowledged before its cancelled worker finished owned cleanup'
            if cancel_stop_request:
                stop.cancel()
                await asyncio.sleep(0)
                assert not stop.done(), 'Cancelling the Stop request abandoned owned worker cleanup'
            # No task or collector at this other unit: Stop is not a global swarm-cancel policy.
            reply = await hub._cancel(object(), {'command_id':'stop-independent','payload':{'session_id':'finished'}})
            assert not reply['result']['cancelled']
            assert independent.status == 'running' and not independent.task.done()
            release.set()
            result = await asyncio.gather(stop, return_exceptions=True)
            if cancel_stop_request or cancel_tool_join:
                assert isinstance(result[0], asyncio.CancelledError)
            else:
                assert result[0]['result']['cancelled']
            assert owned.status == 'cancelled' and owned.task.done() and records['owned'] == 'ended'
            assert other.status == 'running' and not other.task.done() and records['other'] == 'live'
        finally:
            release.set()
            for task in (other.task, independent.task, island): task.cancel()
            await asyncio.gather(stop, owned.task, other.task, independent.task, island, return_exceptions=True)
    asyncio.run(scenario())
