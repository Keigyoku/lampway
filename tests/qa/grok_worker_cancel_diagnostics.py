# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent real ACP preheaders cancellation diagnosis; never acceptance."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
import traceback

import grok_worker_inline_diagnostics as inline
from grok_worker_transport_diagnostics import ACPChannel, admission_gate, check_checkout


PROBE = 'synthetic_pending_cancel_probe'


class RequestEvents(list):
    def __init__(self, context):
        super().__init__()
        self.context = context

    def append(self, event):
        event = dict(event)
        event.update(diagnostic_request_id=getattr(self.context, 'request_id', None),
            diagnostic_at=time.monotonic(),
            diagnostic_probe_present=getattr(self.context, 'probe_present', False))
        super().append(event)


def traced_handler(base, context):
    class Traced(base):
        def do_POST(self):
            context.request_id = uuid.uuid4().hex
            context.probe_present = False
            original = self.rfile

            class WitnessRead:
                def read(inner, *args, **kwargs):
                    body = original.read(*args, **kwargs)
                    try:
                        context.probe_present = PROBE in json.dumps(json.loads(body))
                    except (ValueError, TypeError, UnicodeError):
                        context.probe_present = False
                    return body

                def __getattr__(inner, name):
                    return getattr(original, name)

            self.rfile = WitnessRead()
            try:
                return super().do_POST()
            finally:
                self.rfile = original
                del context.request_id
                del context.probe_present
    return Traced


def pending_request(events):
    persona = {event.get('diagnostic_request_id') for event in events
        if event.get('persona_present') is True and event.get('diagnostic_probe_present') is True}
    pending = {event.get('diagnostic_request_id') for event in events
        if event.get('model_pending') is True}
    targets = (persona & pending) - {None}
    if len(targets) > 1:
        raise RuntimeError('multiple held owned probe requests; refuse ambiguous cancellation witness')
    return next(iter(targets)) if targets else None


def closed_in_window(events, target, sent_at, deadline):
    return any(event.get('model_cancelled') is True
        and event.get('diagnostic_request_id') == target
        and isinstance(event.get('diagnostic_at'), (int, float))
        and sent_at <= event['diagnostic_at'] <= deadline for event in events)


async def write_frame(process, frame, deadline):
    loop = asyncio.get_running_loop()
    if deadline <= loop.time():
        raise asyncio.TimeoutError('original twenty-second budget expired before write')
    process.stdin.write((json.dumps(frame) + '\n').encode())
    remaining = deadline - loop.time()
    if remaining <= 0:
        raise asyncio.TimeoutError('original twenty-second budget expired before drain')
    await asyncio.wait_for(process.stdin.drain(), remaining)


async def observe_cancel(channel, server, session_id, process):
    """One real prompt/cancel exchange: shared20s and peer-close8s, no retry."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 20
    offset = len(server.events)
    server.hold_model = True
    channel.rid += 1
    prompt_id = channel.rid
    await write_frame(process, {'jsonrpc': '2.0', 'id': prompt_id,
        'method': 'session/prompt', 'params': {'sessionId': session_id,
        'prompt': [{'type': 'text', 'text': PROBE}]}}, deadline)

    async def prompt_reply():
        while True:
            frame = await channel.read(deadline)
            if frame.get('id') == prompt_id:
                return frame

    reader = asyncio.create_task(prompt_reply())
    try:
        target = pending_request(server.events[offset:])
        while target is None:
            if reader.done():
                raise RuntimeError('native prompt ended before actual held HTTP request: ' + repr(reader.result()))
            if deadline <= loop.time():
                raise asyncio.TimeoutError('original twenty-second budget expired awaiting held request')
            await asyncio.sleep(min(0.01, deadline - loop.time()))
            target = pending_request(server.events[offset:])
        sent_at = time.monotonic()
        cancel_started = loop.time()
        await write_frame(process, {'jsonrpc': '2.0', 'method': 'session/cancel',
            'params': {'sessionId': session_id}}, deadline)
        cancel_deadline = min(deadline, cancel_started + 8)
        peer_deadline = sent_at + min(8, max(0, deadline - cancel_started))
        peer_closed = False
        while loop.time() < cancel_deadline:
            if pending_request(server.events[offset:]) != target:
                raise RuntimeError('owned pending target changed or became ambiguous')
            if closed_in_window(server.events[offset:], target, sent_at, peer_deadline):
                peer_closed = True
                break
            await asyncio.sleep(min(0.01, cancel_deadline - loop.time()))
        # A later event cannot reopen the original peer-close window.
        peer_closed = peer_closed or closed_in_window(
            server.events[offset:], target, sent_at, peer_deadline)
        remaining = deadline - loop.time()
        reply = None
        reply_failure = None
        try:
            if reader.done():
                reply = reader.result()
            elif remaining > 0:
                reply = await asyncio.wait_for(asyncio.shield(reader), remaining)
            else:
                reply_failure = 'original twenty-second reply budget expired'
        except Exception:
            reply_failure = traceback.format_exc()
        return {'prompt_reply': reply, 'prompt_reply_failure': reply_failure,
            'cancel_sent': True, 'target_request_id': target,
            'cancel_sent_at': sent_at, 'peer_close_deadline': peer_deadline,
            'peer_closed_within_original_eight_seconds': peer_closed,
            'native_retained_before_cleanup': process.returncode is None,
            'events_before_cleanup': list(server.events[offset:])}
    finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)


async def exchange(v, qa, argv, env, cwd):
    traffic = []
    owned = {}
    errors = []
    proc = None
    start = None
    watcher = None
    observation = {'argv': argv, 'acceptance': False, 'worker_ready': False}
    with (v.output / 'native-stderr.log').open('wb') as stderr:
        try:
            proc = await asyncio.create_subprocess_exec(*argv, env=env, cwd=cwd,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=stderr, start_new_session=True)
            start = qa.process_rows().get(proc.pid, {}).get('start')
            if start is None:
                raise RuntimeError('native exited before exact PID/start capture')
            observation.update(pid=proc.pid, start=start)
            def capture():
                for row in qa.owned_snapshot(proc.pid, start):
                    owned[(row['pid'], row['start'])] = row
            async def monitor():
                try:
                    while True:
                        capture()
                        await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    errors.append(traceback.format_exc())
            capture()
            watcher = asyncio.create_task(monitor())
            channel = ACPChannel(proc, traffic, capture)
            deadline = asyncio.get_running_loop().time() + 20
            observation['initialize'] = await channel.request('initialize', {
                'protocolVersion': 1, 'clientCapabilities': {},
                'clientInfo': {'name': 'owned-cancel-diagnostic', 'version': '1'}}, deadline)
            created = await channel.request('session/new', {'cwd': str(cwd), 'mcpServers': []}, deadline)
            sid = created['result']['sessionId']
            # Actual MCP completion is a prerequisite, never injected state.
            while not any(frame.get('method') == '_x.ai/mcp_initialized'
                    and frame.get('params', {}).get('sessionId') == sid
                    and type(frame.get('params', {}).get('mcpToolCount')) is int
                    and frame['params']['mcpToolCount'] >= 0 for frame in traffic):
                await channel.read(deadline)
            observation.update(await observe_cancel(channel, v.http, sid, proc))
        except Exception:
            observation['failure'] = traceback.format_exc()
        finally:
            if proc is not None:
                try:
                    if start is None:
                        observation['ownership_uncertain'] = True
                        # The asyncio direct child can be waited/reaped without
                        # unscoped discovery or signals to an unverified PID.
                        try:
                            await asyncio.wait_for(proc.wait(), 3)
                        except asyncio.TimeoutError:
                            pass
                        raise RuntimeError('missing PID/start identity; refuse unscoped cleanup')
                    await qa.cleanup_acp(proc, start, owned)
                except Exception:
                    observation['cleanup_error'] = traceback.format_exc()
            if watcher is not None:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
            observation['monitor_errors'] = errors
            observation['owned_identities'] = list(owned.values())
            observation['all_owned_absent_including_z'] = not observation.get('ownership_uncertain') and not any(qa.still_alive(row) for row in owned.values())
            observation['http_events_after_cleanup'] = list(v.http.events)
            (v.output / 'frames.json').write_text(json.dumps(traffic, indent=2) + '\n')
    return observation


def failed_obligations(observation):
    failed = []
    if observation.get('failure'):
        failed.append('native_exchange')
    reply = observation.get('prompt_reply') or {}
    if reply.get('result', {}).get('stopReason') != 'cancelled':
        failed.append('real_prompt_cancelled_reply')
    for name in ['peer_closed_within_original_eight_seconds',
                 'native_retained_before_cleanup', 'all_owned_absent_including_z',
                 'protected_held', 'constructed_persona_auth_held']:
        if observation.get(name) is not True:
            failed.append(name)
    if observation.get('cleanup_error') or observation.get('monitor_errors'):
        failed.append('owned_cleanup_or_monitor')
    return failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['repo', 'grok', 'bwrap', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--head', required=True)
    options = parser.parse_args()
    admission_gate(options.head)
    options.repo = check_checkout(options.repo, options.head)
    qa = inline.load_qa(options.repo)
    sys.path.insert(0, str(options.repo / 'server'))
    from lampway_server import grok_worker as worker
    if qa.digest(options.grok) != qa.GROK_SHA256:
        raise ValueError('reviewed native fingerprint required before fixture construction')
    if options.output.exists():
        raise ValueError('fresh owned diagnostic output required')
    options.output.mkdir()
    qa.enable_owned_reaping()
    summary = {'acceptance': False, 'worker_ready': False, 'cases': []}
    try:
        for restricted in [False, True]:
            for permanent in [False, True]:
                label = ('restricted' if restricted else 'native') + ('-400' if permanent else '-503')
                case_options = argparse.Namespace(**vars(options))
                case_options.output = options.output / label
                case_options.phase = 'loopback'
                case_options.cursor_fixture = 'present'
                case_options.compatibility_layer = True
                v = inline.validator_type(qa)(case_options)
                handler, refusal = inline.model_refusal_fixture(qa, permanent=permanent)
                context = threading.local()
                v.http = qa.ThreadingHTTPServer(('127.0.0.1', 0), traced_handler(handler, context))
                v.http.events = RequestEvents(context)
                v.http.binding = 'swarm:owned:one'
                v.http.hold_model = False
                threading.Thread(target=v.http.serve_forever, daemon=True).start()
                try:
                    path, env, cwd, config = v.make_fixture()
                    qa.enroll_compatibility_fixture(config)
                    protected = {str(p): qa.file_state(p) for p in [options.grok,
                        options.bwrap, Path(qa.__file__), Path(worker.__file__),
                        Path(config['connector']['command'])]}
                    persona_auth = {str(p): qa.file_state(p) for p in [
                        Path(env['GROK_AUTH_PATH']), Path(env['GROK_HOME']) / 'original-agent.md']}
                    argv = [str(options.grok.resolve()), 'agent', '--no-leader', 'stdio']
                    if restricted:
                        with qa.fixture_environment(env):
                            plan = worker.build_plan(path)
                            worker.prepare(plan)
                        argv = plan['argv'][:plan['argv'].index('--') + 1] + argv
                    observation = asyncio.run(exchange(v, qa, argv, env, cwd))
                    observation.update(label=label, model_refusal_fixture=refusal,
                        protected_held=protected == {p: qa.file_state(Path(p)) for p in protected},
                        constructed_persona_auth_held=persona_auth == {p: qa.file_state(Path(p)) for p in persona_auth})
                    observation['failed_obligations'] = failed_obligations(observation)
                    observation['status'] = 'FAILED' if observation['failed_obligations'] else 'MET'
                    v.receipt.update(observation)
                    v.save()
                    summary['cases'].append(observation)
                    if (not observation['all_owned_absent_including_z'] or observation.get('cleanup_error')
                            or observation.get('monitor_errors') or not observation['protected_held']
                            or not observation['constructed_persona_auth_held']):
                        raise RuntimeError('owned cleanup or protected guard failed; refuse subsequent native cases')
                finally:
                    v.http.shutdown()
                    v.http.server_close()
    finally:
        summary['head'] = options.head
        summary['driver_sha256'] = qa.digest(Path(__file__))
        summary['qa_sha256'] = qa.digest(Path(qa.__file__))
        summary['native_sha256'] = qa.digest(options.grok)
        summary['status'] = 'FAILED' if len(summary['cases']) != 4 or any(
            case['failed_obligations'] for case in summary['cases']) else 'MET'
        try:
            check_checkout(options.repo, options.head)
            if summary['native_sha256'] != qa.GROK_SHA256 or summary['qa_sha256'] != inline.QA_SHA256:
                raise ValueError('native or original QA fingerprint changed')
            summary['final_source_guard'] = 'clean exact HEAD confirmed'
        except Exception:
            summary['final_guard_failure'] = traceback.format_exc()
            summary['status'] = 'FAILED'
            raise
        finally:
            (options.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    if summary['status'] == 'FAILED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
