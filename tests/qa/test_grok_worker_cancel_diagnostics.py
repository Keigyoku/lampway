# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure diagnostic mechanics only; no native frame or status evidence."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

REPO = Path(os.environ.get('LAMPWAY_CANCEL_DIAGNOSTIC_REPO', str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(REPO / 'tests/qa'))
PATH = Path(__file__).with_name('grok_worker_cancel_diagnostics.py')
SPEC = importlib.util.spec_from_file_location('owned_cancel_controls', PATH)
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


@pytest.fixture(autouse=True)
def refuse_external_execution(monkeypatch):
    import subprocess
    import socket
    import os

    def refuse(*args, **kwargs):
        raise AssertionError('pure control refuses subprocess/socket/signal')

    # asyncio owns an internal AF_UNIX wakeup pair; construct its loop before
    # refusing all new sockets in the controlled diagnostic body.
    loop = asyncio.new_event_loop()
    monkeypatch.setattr(asyncio, 'run', loop.run_until_complete)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(subprocess, 'run', refuse)
    monkeypatch.setattr(socket, 'socket', refuse)
    monkeypatch.setattr(os, 'kill', refuse)
    yield
    loop.close()


def test_expired_budget_refuses_write_and_drain():
    class Input:
        def write(self, data):
            raise AssertionError('expired frame must not be written')

        async def drain(self):
            raise AssertionError('expired frame must not be drained')

    async def run():
        with pytest.raises(asyncio.TimeoutError, match='before write'):
            await D.write_frame(SimpleNamespace(stdin=Input()), {}, asyncio.get_running_loop().time() - 1)
    asyncio.run(run())


@pytest.mark.parametrize('peer_closed', [False, True, 'late'])
def test_real_driver_order_and_peer_close_are_independent_of_reply(peer_closed, monkeypatch):
    async def run():
        original_sleep = asyncio.sleep
        clock = SimpleNamespace(now=0)
        monkeypatch.setattr(D.asyncio, 'get_running_loop', lambda: SimpleNamespace(time=lambda: clock.now))
        monkeypatch.setattr(D.time, 'monotonic', lambda: clock.now)
        server = SimpleNamespace(events=[{'model_cancelled': True,
            'diagnostic_request_id': 'old', 'diagnostic_at': -1}], hold_model=False)
        frames = []
        cancelled = asyncio.Event()

        class Input:
            def write(self, data):
                frame = json.loads(data)
                frames.append(frame)
                if frame['method'] == 'session/prompt':
                    assert server.hold_model is True
                    server.events.extend([{'persona_present': True, 'diagnostic_probe_present': True,
                        'diagnostic_request_id': 'target', 'diagnostic_at': clock.now},
                        {'model_pending': True, 'diagnostic_request_id': 'target', 'diagnostic_at': clock.now}])
                else:
                    assert frame['method'] == 'session/cancel'
                    assert any(event.get('model_pending') for event in server.events[1:])
                    assert 'id' not in frame
                    if peer_closed is True:
                        server.events.append({'model_cancelled': True,
                            'diagnostic_request_id': 'target', 'diagnostic_at': clock.now})
                    cancelled.set()

            async def drain(self):
                await original_sleep(0)

        async def read(deadline):
            await cancelled.wait()
            # Pure controlled protocol value, never saved as native evidence.
            return {'id': 1, 'result': {'stopReason': 'cancelled'}}

        async def advance(delay):
            clock.now += delay
            if peer_closed == 'late' and clock.now >= 8:
                server.events.append({'model_cancelled': True,
                    'diagnostic_request_id': 'target', 'diagnostic_at': 8.01})
            await original_sleep(0)

        monkeypatch.setattr(D.asyncio, 'sleep', advance)
        process = SimpleNamespace(stdin=Input(), returncode=None)
        channel = SimpleNamespace(rid=0, read=read)
        result = await D.observe_cancel(channel, server, 'owned-session', process)
        assert [frame['method'] for frame in frames] == ['session/prompt', 'session/cancel']
        assert result['prompt_reply']['result']['stopReason'] == 'cancelled'
        assert result['peer_closed_within_original_eight_seconds'] is (peer_closed is True)
        assert result['native_retained_before_cleanup'] is True
        if peer_closed is not True:
            assert 8 <= clock.now < 8.02
        assert server.hold_model is True  # driver does not release the pending request to force success

    asyncio.run(run())


@pytest.mark.parametrize('missing', [
    'peer_closed_within_original_eight_seconds', 'native_retained_before_cleanup',
    'all_owned_absent_including_z', 'protected_held', 'constructed_persona_auth_held',
])
def test_missing_obligation_never_promotes_cancelled_reply_to_success(missing):
    case = {key: True for key in [
        'peer_closed_within_original_eight_seconds', 'native_retained_before_cleanup',
        'all_owned_absent_including_z', 'protected_held', 'constructed_persona_auth_held']}
    case['prompt_reply'] = {'result': {'stopReason': 'cancelled'}}
    case[missing] = False
    assert missing in D.failed_obligations(case)


def test_admission_and_byte_guard_precede_output_and_fixture_construction():
    import ast

    tree = ast.parse(PATH.read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    source = ast.unparse(main)
    assert source.index('admission_gate(options.head)') < source.index('inline.load_qa(options.repo)')
    assert source.index('check_checkout(options.repo, options.head)') < source.index('options.output.mkdir()')
    assert source.index('qa.digest(options.grok) != qa.GROK_SHA256') < source.index('options.output.mkdir()')
    assert "'acceptance': False, 'worker_ready': False" in source


@pytest.mark.parametrize('event_id, at, accepted', [
    ('target', 7.99, True), ('target', 8.01, False),
    ('other', 1.0, False), ('target', -0.1, False),
])
def test_same_request_timestamp_required_for_peer_close(event_id, at, accepted):
    events = [{'model_cancelled': True, 'diagnostic_request_id': event_id, 'diagnostic_at': at}]
    assert D.closed_in_window(events, 'target', 0, 8) is accepted


def test_pending_target_requires_matching_persona_probe_and_request_id():
    persona = {'persona_present': True, 'diagnostic_probe_present': True,
               'diagnostic_request_id': 'target'}
    assert D.pending_request([persona, {'model_pending': True, 'diagnostic_request_id': 'other'}]) is None
    assert D.pending_request([persona, {'model_pending': True, 'diagnostic_request_id': 'target'}]) == 'target'
    with pytest.raises(RuntimeError, match='multiple held'):
        D.pending_request([persona, {'model_pending': True, 'diagnostic_request_id': 'target'},
            dict(persona, diagnostic_request_id='other'),
            {'model_pending': True, 'diagnostic_request_id': 'other'}])


def test_traced_handler_annotates_actual_emissions_without_changing_original_body(monkeypatch):
    import io
    import threading
    import grok_worker_validation as qa

    context = threading.local()
    handler = D.traced_handler(qa.HTTPFixture, context)
    instance = handler.__new__(handler)
    body = json.dumps({'prompt': qa.PERSONA + D.PROBE}).encode()
    original = io.BytesIO(body)
    instance.rfile = original
    instance.wfile = io.BytesIO()
    instance.headers = {'Content-Length': str(len(body))}
    instance.path = '/v1/chat/completions'
    instance.server = SimpleNamespace(events=D.RequestEvents(context), hold_model=True)
    instance.connection = SimpleNamespace(recv=lambda *args: b'')
    instance.do_POST()
    events = instance.server.events
    assert [set(event) & {'persona_present', 'model_pending', 'model_cancelled'} for event in events] == [
        {'persona_present'}, {'model_pending'}, {'model_cancelled'}]
    assert all(event['diagnostic_probe_present'] for event in events)
    assert len({event['diagnostic_request_id'] for event in events}) == 1
    assert all(isinstance(event['diagnostic_at'], float) for event in events)
    assert D.pending_request(events) == events[0]['diagnostic_request_id']
    assert instance.rfile is original and not hasattr(context, 'request_id')


@pytest.mark.parametrize('reply_error', [False, True])
def test_reply_after_peer_window_uses_remaining_shared_budget_and_preserves_witness(reply_error, monkeypatch):
    async def run():
        original_sleep = asyncio.sleep
        clock = SimpleNamespace(now=0)
        monkeypatch.setattr(D.asyncio, 'get_running_loop', lambda: SimpleNamespace(time=lambda: clock.now))
        monkeypatch.setattr(D.time, 'monotonic', lambda: clock.now)
        server = SimpleNamespace(events=[], hold_model=False)
        peer_window_done = asyncio.Event()

        class Input:
            def write(self, data):
                frame = json.loads(data)
                if frame['method'] == 'session/prompt':
                    server.events.extend([
                        {'persona_present': True, 'diagnostic_probe_present': True, 'diagnostic_request_id': 'target'},
                        {'model_pending': True, 'diagnostic_request_id': 'target'}])

            async def drain(self):
                await original_sleep(0)

        async def read(deadline):
            assert deadline == 20
            await peer_window_done.wait()
            clock.now = 9
            if reply_error:
                raise RuntimeError('controlled native read failure after peer window')
            return {'id': 1, 'result': {'stopReason': 'cancelled'}}

        async def advance(delay):
            clock.now += delay
            if clock.now >= 8:
                peer_window_done.set()
            await original_sleep(0)

        monkeypatch.setattr(D.asyncio, 'sleep', advance)
        result = await D.observe_cancel(SimpleNamespace(rid=0, read=read), server,
            'owned-session', SimpleNamespace(stdin=Input(), returncode=None))
        assert result['peer_closed_within_original_eight_seconds'] is False
        assert result['target_request_id'] == 'target'
        assert result['cancel_sent'] is True
        if reply_error:
            assert result['prompt_reply'] is None
            assert 'controlled native read failure' in result['prompt_reply_failure']
        else:
            assert result['prompt_reply']['result']['stopReason'] == 'cancelled'
        assert clock.now == 9

    asyncio.run(run())


def test_missing_identity_never_discovers_or_signals_unscoped_children(tmp_path, monkeypatch):
    async def run():
        waited = []

        async def wait():
            waited.append('direct-child-reaped')
            return 0

        async def create(*args, **kwargs):
            return SimpleNamespace(pid=123, wait=wait, returncode=0)

        def refuse(*args):
            raise AssertionError('unscoped ownership discovery or cleanup forbidden')

        monkeypatch.setattr(D.asyncio, 'create_subprocess_exec', create)
        qa = SimpleNamespace(process_rows=lambda: {}, cleanup_acp=refuse,
            owned_snapshot=refuse, still_alive=refuse)
        v = SimpleNamespace(output=tmp_path, http=SimpleNamespace(events=[]))
        result = await D.exchange(v, qa, ['controlled-native'], {}, tmp_path)
        assert result['ownership_uncertain'] is True
        assert result['all_owned_absent_including_z'] is False
        assert 'missing PID/start' in result['cleanup_error']
        assert waited == ['direct-child-reaped']

    asyncio.run(run())
