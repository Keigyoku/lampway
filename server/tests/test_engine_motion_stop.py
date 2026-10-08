# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The pane's real HTTP tool door must join motion work on Stop, independently of its island task."""
import asyncio
import json
import threading
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette

from lampway_server.agent import motion_tools as MT
from lampway_server.agent.turns import AgentHub, Turn
from lampway_server.engine.front import HermesFront, Link, Sink
from lampway_server.engine.mcp_endpoint import engine_mcp_routes


@pytest.mark.parametrize('stop_origin', ['island', 'island-live', 'pane'])
def test_stop_joins_only_its_units_motion_request_and_preserves_the_http_reply(tmp_path, monkeypatch, stop_origin):
    started = {unit: threading.Event() for unit in ('a', 'b')}
    ended = {unit: threading.Event() for unit in ('a', 'b')}
    release = {unit: threading.Event() for unit in ('a', 'b')}
    filed, interrupts = [], []

    def work(vault, root, arguments, capture, cancel):
        unit = arguments['name']
        started[unit].set()
        try:
            while not release[unit].wait(.005):
                cancel.check()
            cancel.check()
            filed.append(unit)
            return {'ok': True, 'vault': {'assets': [unit]}}
        finally:
            ended[unit].set()

    monkeypatch.setattr(MT, '_work', work)

    async def scenario():
        hub = AgentHub(object(), assets=object())
        units = SimpleNamespace(check_mcp=lambda unit, token: token == 'fixture')
        front = HermesFront(hub, units)
        hub.engine = front
        async def rpc(method, params, **kwargs):
            interrupts.append((method, params['session_id']))
            return {}
        for unit in ('a', 'b'):
            hub.client_sockets[unit] = object()
            session = hub._session(unit)
            front.links[unit] = Link(unit, client=SimpleNamespace(call=rpc), live_id=unit, running=True,
                                     sink=Sink(session=session, turn=Turn(unit, unit+'-turn', '')))
        app = Starlette(routes=engine_mcp_routes(lambda: front))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
            async def call(unit):
                return await client.post('/engine/mcp/'+unit, headers={'authorization':'Bearer fixture'},
                    json={'jsonrpc':'2.0','id':unit+'-call','method':'tools/call',
                          'params':{'name':MT.NAME,'arguments':{'html':'fixture','name':unit}}})
            calls = {unit: asyncio.create_task(call(unit)) for unit in ('a', 'b')}
            try:
                for unit in ('a', 'b'):
                    assert await asyncio.to_thread(started[unit].wait, 2)
                if stop_origin == 'island-live':
                    turn = front.links['a'].sink.turn
                    turn.task = asyncio.create_task(asyncio.Event().wait())
                    hub.sessions['a'].current = turn
                if stop_origin.startswith('island'):
                    reply = await hub._cancel(object(), {'command_id':'stop-a','payload':{'session_id':'a'}})
                    assert reply['result']['cancelled']
                else:
                    assert await front.interrupt('a')
                assert ended['a'].is_set(), 'Stop returned while its HTTP motion worker was still running'
                assert not ended['b'].is_set() and not calls['b'].done(), 'Stop touched another unit'
                stopped = (await asyncio.wait_for(calls['a'], 2)).json()
                assert stopped['id'] == 'a-call' and stopped['result']['isError']
                assert 'cancelled' in stopped['result']['content'][0]['text']
                assert 'a' not in filed, 'Stopped motion filed a Vault asset'
                release['b'].set()
                other = (await asyncio.wait_for(calls['b'], 2)).json()
                assert other['id'] == 'b-call' and not other['result']['isError']
                assert filed == ['b'] and ended['b'].is_set()
                (tmp_path/'motion-stop-proof.json').write_text(json.dumps({'origin':stop_origin,
                    'owned_worker_joined':ended['a'].is_set(),'other_unit_completed':ended['b'].is_set(),
                    'filed_units':filed,'paired_cancelled_reply':stopped,'paired_other_reply':other,'interrupts':interrupts},indent=2))
            finally:
                for gate in release.values(): gate.set()
                await asyncio.gather(*calls.values(), return_exceptions=True)
    asyncio.run(scenario())


def test_repeated_stop_joins_cleanup_and_refuses_new_same_unit_admission(monkeypatch):
    async def scenario():
        front = HermesFront(None, None)
        started, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        admitted = []
        async def tool(unit, name, arguments):
            admitted.append(unit)
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup.set()
                await release.wait()
        monkeypatch.setattr(front, '_call_tool', tool)
        call = asyncio.create_task(front.call_tool('a', 'fixture', {}))
        await started.wait()
        stop = asyncio.create_task(front.cancel_tool_calls('a'))
        await cleanup.wait()
        repeat = asyncio.create_task(front.cancel_tool_calls('a'))
        text, error = await front.call_tool('a', 'fixture', {})
        assert error and json.loads(text)['cancelled'] and admitted == ['a']
        stop.cancel()
        await asyncio.sleep(0)
        assert not stop.done() and not repeat.done(), 'Repeated Stop abandoned owned cleanup'
        release.set()
        result = await asyncio.gather(stop, repeat, return_exceptions=True)
        assert isinstance(result[0], asyncio.CancelledError) and result[1] == 1
        text, error = await call
        assert error and json.loads(text)['cancelled']
        assert not front._tool_calls and not front._tool_stops
    asyncio.run(scenario())


def test_http_caller_cancellation_joins_owned_tool_without_losing_other_units(monkeypatch):
    async def scenario():
        front = HermesFront(None, None)
        started, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def tool(unit, name, arguments):
            if unit == 'b':
                return 'other unit result', False
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup.set()
                await release.wait()
        monkeypatch.setattr(front, '_call_tool', tool)
        caller = asyncio.create_task(front.call_tool('a', 'fixture', {}))
        await started.wait()
        caller.cancel()
        await cleanup.wait()
        caller.cancel()
        await asyncio.sleep(0)
        assert not caller.done()
        assert await front.call_tool('b', 'fixture', {}) == ('other unit result', False)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert not front._tool_calls
    asyncio.run(scenario())
