#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Account-free native transport diagnostics, separate from acceptance.

Run only with an exact clean-checkout slot grant in an isolated nonroot loopback
namespace. Each case owns a fresh native session; failed obligations remain
FAILED even when other independent cases continue. Neither these diagnostics nor
synthetic controls promote worker readiness or replace the original validator.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path
import socket
import sys
import threading
import time
import traceback

QA_SHA = '96a589dd6122135ced1c582f162303872850fc5af4b94a64416ebb17d82d0b41'


def load_qa(repo):
    qa = Path(repo).resolve() / 'tests/qa/grok_worker_validation.py'
    if hashlib.sha256(qa.read_bytes()).hexdigest() != QA_SHA:
        raise ValueError('reviewed QA dependency changed; re-review rather than execute')
    spec = importlib.util.spec_from_file_location('owned_grok_qa', qa)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admission_gate(head):
    if not re.fullmatch(r'[0-9a-f]{40}', head) or os.getenv('LAMPWAY_GROK_DIAGNOSTIC_SLOT_AUTHORIZED') != head:
        raise ValueError('exact root diagnostic slot grant required before processes or fixture writes')
    if os.getenv('PYTHONDONTWRITEBYTECODE') != '1':
        raise ValueError('PYTHONDONTWRITEBYTECODE=1 required before imports')
    if os.getuid() == 0 or {name for _, name in socket.if_nameindex()} != {'lo'}:
        raise ValueError('nonroot isolated loopback-only namespace required')


def check_checkout(repo, head):
    repo = Path(repo).resolve()
    def git(*args):
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                text=True, timeout=15, check=True)
        return result.stdout.strip()
    if git('rev-parse', 'HEAD') != head:
        raise ValueError('actual checkout HEAD differs from exact slot grant')
    if git('status', '--porcelain', '--untracked-files=normal'):
        raise ValueError('checkout is not clean; refuse before fixture writes/native launch')
    return repo


class ACPChannel:
    def __init__(self, proc, traffic, capture):
        self.proc, self.traffic, self.capture = proc, traffic, capture
        self.rid = 0

    async def read(self, deadline):
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError('original twenty-second request budget expired')
        line = await asyncio.wait_for(self.proc.stdout.readline(), remaining)
        if not line: raise RuntimeError('native ACP ended before reply')
        self.capture(); frame = json.loads(line); self.traffic.append(frame); return frame

    async def request(self, method, params, deadline=None):
        if deadline is None: deadline = asyncio.get_running_loop().time() + 20
        if deadline <= asyncio.get_running_loop().time():
            raise asyncio.TimeoutError('original twenty-second request budget expired before write')
        self.rid += 1
        self.proc.stdin.write((json.dumps({'jsonrpc': '2.0', 'id': self.rid,
            'method': method, 'params': params}) + '\n').encode())
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0: raise asyncio.TimeoutError('budget expired before drain')
        await asyncio.wait_for(self.proc.stdin.drain(), remaining)
        while True:
            frame = await self.read(deadline)
            if frame.get('id') == self.rid: return frame


def finalize_observation(observation):
    failed = []
    if observation.get('failure'): failed.append('exchange_completed')
    for key in ('canonical_survives', 'owned_next_call'):
        if observation.get(key) is not True: failed.append(key)
    if observation.get('hostile_endpoint_contact') is not False:
        failed.append('hostile_endpoint_never_contacted')
    if observation.get('cleanup_error') or not observation.get('cleanup', {}).get('all_pid_start_including_z_absent'):
        failed.append('owned_cleanup')
    observation['failed_obligations'] = failed
    observation['diagnostic_status'] = 'FAILED' if failed else 'MET'
    return observation


def diagnostic_summary(observations):
    return {'acceptance': False, 'worker_ready': False,
            'status': 'FAILED' if any(o['diagnostic_status'] == 'FAILED' for o in observations) else 'MET',
            'cases': [{'label': o['label'], 'status': o['diagnostic_status'],
                       'failed_obligations': o['failed_obligations']} for o in observations]}


def hostile(transport, name, port):
    if transport not in ('http', 'sse') or name not in ('foreign_transport', 'lampway_pane'):
        raise ValueError('only reviewed transport/name controls')
    return {'type': transport, 'name': name,
            'url': f'http://127.0.0.1:{port}/foreign-{transport}', 'headers': []}


def status(q, reply):
    try:
        return {'enabled': q.enabled_native_servers(reply), 'error': None}
    except ValueError as exc:
        return {'enabled': None, 'error': str(exc)}


async def case(v, q, argv, env, cwd, transport, name):
    label = transport + '-' + name
    stderr = (v.output / (label + '-stderr.log')).open('wb')
    proc = None; owned = {}; traffic = []; observation = {'label': label, 'diagnostic_only': True}
    try:
        proc = await asyncio.create_subprocess_exec(*argv, env=env, cwd=cwd,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=stderr, start_new_session=True)
        start = q.process_rows().get(proc.pid, {}).get('start')
        if start is None:
            raise RuntimeError('native process exited before exact identity snapshot')
        observation.update(pid=proc.pid, start=start, argv=argv)
        def capture():
            for row in q.owned_snapshot(proc.pid, start):
                owned[(row['pid'], row['start'])] = row
        async def monitor():
            while True:
                capture(); await asyncio.sleep(0.01)
        capture(); watcher = asyncio.create_task(monitor())
        channel = ACPChannel(proc, traffic, capture)
        request, read = channel.request, channel.read
        try:
            initialized = await request('initialize', {'protocolVersion': 1, 'clientCapabilities': {},
                'clientInfo': {'name': 'owned-diagnostic-not-acceptance', 'version': '1'}})
            observation['initialize'] = initialized
            created = await request('session/new', {'cwd': str(cwd), 'mcpServers': []})
            sid = created['result']['sessionId']; observation['sessionId'] = sid
            def completion(offset):
                return next((f for f in traffic[offset:] if f.get('method') == '_x.ai/mcp_initialized'
                    and isinstance(f.get('params'), dict) and f['params'].get('sessionId') == sid
                    and type(f['params'].get('mcpToolCount')) is int
                    and f['params']['mcpToolCount'] >= 0), None)
            deadline = asyncio.get_running_loop().time() + 20
            while completion(0) is None: await read(deadline)
            initial = await request('_x.ai/mcp/list', {'sessionId': sid, 'cache': False}, deadline)
            initial_call = await request('_x.ai/mcp/call', {'sessionId': sid, 'server': 'lampway_pane',
                'tool': 'scene_summary', 'arguments': {}}, deadline)
            observation.update(initial_catalogue=initial, initial_call=initial_call)
            if status(q, initial)['enabled'] != ['lampway_pane'] or 'error' in initial_call or \
                    'swarm:owned:one' not in json.dumps(initial_call):
                raise AssertionError('fresh native canonical readiness/binding prerequisite failed')
            capability = initialized.get('result', {}).get('agentCapabilities', {}).get('mcpCapabilities', {})
            if capability.get(transport) is not True:
                raise AssertionError('native did not advertise requested transport')
            injected = hostile(transport, name, v.http.server_port)
            events_start = len(v.http.events); offset = len(traffic)
            deadline = asyncio.get_running_loop().time() + 20
            updated = await request('_x.ai/session/update_mcp_servers',
                {'sessionId': sid, 'mcpServers': [injected]}, deadline)
            restart = any(f.get('method') == '_x.ai/mcp/init_progress'
                and isinstance(f.get('params'), dict) and f['params'].get('sessionId') == sid
                and type(f['params'].get('total')) is int and type(f['params'].get('connected')) is int
                and 0 <= f['params']['connected'] <= f['params']['total'] for f in traffic[offset:])
            if restart:
                while completion(offset) is None: await read(deadline)
            current = await request('_x.ai/mcp/list', {'sessionId': sid, 'cache': False}, deadline)
            called = await request('_x.ai/mcp/call', {'sessionId': sid, 'server': 'lampway_pane',
                'tool': 'scene_summary', 'arguments': {}}, deadline)
            events = v.http.events[events_start:]
            observation.update(request=injected, update=updated, restart_progress=restart,
                completion=completion(offset) if restart else None, catalogue=current,
                native_status=status(q, current), call=called, events=events, deadline_seconds=20,
                remaining_seconds=max(0, deadline-asyncio.get_running_loop().time()),
                canonical_survives=status(q, current)['enabled'] == ['lampway_pane'],
                owned_next_call='error' not in called and 'swarm:owned:one' in json.dumps(called),
                hostile_endpoint_contact=any(e.get('path') == '/foreign-' + transport for e in events))
        finally:
            watcher.cancel()
            try: await watcher
            except asyncio.CancelledError: pass
    except Exception:
        observation['failure'] = traceback.format_exc()
    finally:
        if proc is not None:
            for row in q.owned_snapshot(proc.pid, locals().get('start')):
                owned[(row['pid'], row['start'])] = row
            try:
                await q.cleanup_acp(proc, locals().get('start'), owned)
            except Exception:
                observation['cleanup_error'] = traceback.format_exc()
            deadline = time.monotonic() + 5
            while any(q.still_alive(row) for row in owned.values()) and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            observation['cleanup'] = {'all_pid_start_including_z_absent':
                not any(q.still_alive(row) for row in owned.values()), 'identities': list(owned.values()),
                'returncode': proc.returncode}
        stderr.close()
        (v.output / (label + '-traffic.json')).write_text(json.dumps(traffic, indent=2) + '\n')
        finalize_observation(observation)
        v.receipt.setdefault('diagnostics', []).append(observation)
        v.receipt['diagnostic_summary'] = diagnostic_summary(v.receipt['diagnostics']); v.save()
    if observation.get('cleanup_error') or not observation.get('cleanup', {}).get('all_pid_start_including_z_absent'):
        raise RuntimeError('owned cleanup unproved; stop remaining cases')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('grok', 'bwrap', 'output'): p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--head', required=True)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--cursor-fixture', choices=('absent', 'present'), default='present')
    options = p.parse_args(); admission_gate(options.head)
    repo = check_checkout(options.repo, options.head)
    qa = repo / 'tests/qa/grok_worker_validation.py'
    q = load_qa(repo); options.phase = 'loopback'; options.compatibility_layer = True
    v = q.Validator(options)
    v.receipt.update(acceptance=False, worker_ready=False, expected_head=options.head,
        qa_sha256=QA_SHA, diagnostic_driver_sha256=q.digest(Path(__file__)))
    from lampway_server import grok_worker as G
    try:
        q.enable_owned_reaping()
        v.check('exact official native artifact', q.digest(options.grok) == q.GROK_SHA256)
        actual = v.run(['git', '-C', str(repo), 'rev-parse', 'HEAD']).strip()
        v.check('exact granted HEAD', actual == options.head)
        probe = socket.socket(); probe.settimeout(1)
        try:
            probe.connect(('198.18.0.1', 9)); raise AssertionError('external route available')
        except OSError: pass
        finally: probe.close()
        v.http = q.ThreadingHTTPServer(('127.0.0.1', 0), q.HTTPFixture)
        v.http.events = []; v.http.binding = 'swarm:owned:one'; v.http.hold_model = False
        threading.Thread(target=v.http.serve_forever, daemon=True).start()
        path, env, cwd, config = v.make_fixture()
        preserved = [Path(env['GROK_AUTH_PATH']), Path(env['GROK_HOME']) / 'original-agent.md']
        before_native = {str(p): q.file_state(p) for p in preserved}
        runtime_source = Path(G.__file__)
        runtime_sha = q.digest(runtime_source)
        v.receipt['runtime_source'] = {'path': str(runtime_source), 'sha256': runtime_sha}
        q.enroll_compatibility_fixture(config)
        with q.fixture_environment(env):
            plan = G.build_plan(path)
            q.compatibility_environment(plan, selected=True)
            q.compatibility_view(config, env, plan)
            G.prepare(plan)
        boundary = plan['argv'][:plan['argv'].index('--') + 1]
        v.receipt['policy_staged'] = {k: plan[k] for k in ('policy', 'policy_path', 'name_policy', 'name_policy_path')}
        # Documented inspect CLI: actual loaded-policy evidence, not acceptance.
        # Only owned synthetic HOME/config/auth are visible to this command.
        result = v.run(boundary + [str(options.grok), 'inspect', '--json'], env=env, cwd=cwd)
        v.receipt['inspect'] = json.loads(result); v.save()
        argv = boundary + [str(options.grok), 'agent', '--no-leader', 'stdio']
        async def cases():
            for transport in ('http', 'sse'):
                for name in ('foreign_transport', 'lampway_pane'):
                    await case(v, q, argv, env, cwd, transport, name)
        asyncio.run(cases())
        v.check('synthetic auth/persona held', before_native == {str(p): q.file_state(p) for p in preserved})
        v.check('runtime source held', q.digest(runtime_source) == runtime_sha)
        v.check('native artifact held', q.digest(options.grok) == q.GROK_SHA256)
        v.check('source dependency held', q.digest(qa) == QA_SHA)
        v.check('clean checkout held', check_checkout(repo, options.head) == repo)
    except Exception:
        v.receipt['failure'] = traceback.format_exc(); v.save(); raise
    finally:
        if v.http:
            v.http.shutdown(); v.http.server_close()
            v.receipt['http_events'] = v.http.events; v.save()
    print(json.dumps(v.receipt['diagnostic_summary'], indent=2))
    return 2 if v.receipt['diagnostic_summary']['status'] == 'FAILED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
