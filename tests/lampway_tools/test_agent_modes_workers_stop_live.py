# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual parent Stop interrupts two real worker panes and headless Blender jobs.

Only the loopback model responses are deterministic. No fake fleet, pane,
worker connection, task cancellation or commit implementation is substituted.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
import time

import pytest

from test_agent_modes_workers_live import (ROOT, BlenderClient, ENGINES, MISSING, NODE, TUI,
    Stack, free_port, create_app, Settings, EG, Cockpit, L, Text, lampway_bin, CH, CAP,
    EW, SwarmProvider, WorkerProvider, _called, binary_fingerprint)


class InterruptProvider(SwarmProvider):
    async def stream(self, request):
        users = self._user_texts(request)
        if request.tools and users and 'RECOVER' in users[-1]:
            self.requests.append(request)
            yield Text('Recovered after worker Stop.')
            return
        async for event in super().stream(request):
            yield event


class PausedWorkerProvider(WorkerProvider):
    def __init__(self, label, pause_before_first=False):
        super().__init__(label)
        self.pause_before_first = pause_before_first
        self.held = threading.Event()
        self.stream_closed = threading.Event()
        self.request_seq = 0
        self.active_requests = set()
        self.finished_requests = set()
        self.request_lifecycle = []

    async def stream(self, request):
        if request.tools and _called(request.messages, 'run_blender_python'):
            self.requests.append(request)
            # Every held call has its own identity: one closed call must never
            # hide another pending call or a retry admitted during Stop.
            self.request_seq += 1
            request_id = f'{self.worker_name}:{self.request_seq}'
            self.active_requests.add(request_id)
            self.request_lifecycle.append({'request': request_id, 'event': 'held', 'at': time.monotonic()})
            try:
                if not self.pause_before_first:
                    yield Text(self.worker_name + ' waiting for the fixture user Stop.')
                self.held.set()
                await asyncio.Event().wait()
            finally:
                self.active_requests.remove(request_id)
                self.finished_requests.add(request_id)
                self.request_lifecycle.append({'request': request_id, 'event': 'closed', 'at': time.monotonic()})
                self.stream_closed.set()
            return
        async for event in super().stream(request):
            yield event


def process_running(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'
    except FileNotFoundError:
        return False


def wait_for(predicate, timeout=90, failure='real worker cancellation did not settle before the deadline'):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.1)
    raise AssertionError(failure)


def pane_records(cockpit):
    return [{key: row.get(key) for key in ('id', 'pane_id', 'terminal_id', 'unit', 'role',
            'state', 'created_by', 'swarm_binding', 'end_reason')} for row in cockpit.list_sessions()]


@pytest.mark.timeout(1200)
@pytest.mark.parametrize('pause_before_first', [False, True], ids=['streamed', 'before-first-token'])
def test_actual_parent_stop_interrupts_both_worker_panes_without_commits(tmp_path, monkeypatch, pause_before_first):
    assert lampway_bin().exists(), f'No built Blender at {lampway_bin()}'
    if MISSING:
        pytest.fail(MISSING)
    xvfb = shutil.which('xvfb-run')
    assert xvfb, 'isolated cloud xvfb-run is required'
    root = Path(tempfile.mkdtemp(prefix='lw-s5-stop-', dir='/tmp'))
    project = tmp_path / 'project'; project.mkdir()
    for key, value in {'LAMPWAY_ENGINES_DIR': str(ENGINES), 'LAMPWAY_HERMES_TUI_DIR': str(TUI),
                       'LAMPWAY_NODE': NODE, 'LAMPWAY_PROJECT_ROOT': str(project),
                       'LAMPWAY_SECRETS_DIR': str(tmp_path / 'secrets')}.items():
        monkeypatch.setenv(key, value)
    settings = Settings(port=free_port(), jwt_secret='test-secret-not-for-production', user_password='correct-horse',
                        state_dir=tmp_path / 'server-state', provider='mock')
    strict = EG.Egress(tmp_path / 'strict-egress')
    cockpit = Cockpit(root, project_root=str(project))
    providers, gateway = {}, []
    model_enrollments, key_revocations = [], []
    main = InterruptProvider()

    def worker_factory(label, *, resolution=None):
        assert resolution is not None and resolution.option == 'mock', resolution
        providers[label] = PausedWorkerProvider(label, pause_before_first)
        return providers[label]

    original_getter = EW.provider_getter
    def observed_getter(agent):
        actual = original_getter(agent)
        def get(session_id=None):
            selected = actual(session_id)
            gateway.append({'session_id': session_id, 'provider': selected.name})
            return selected
        return get
    monkeypatch.setattr(EW, 'provider_getter', observed_getter)
    client_root = tmp_path / 'client'; client_root.mkdir()
    main.audit_path = client_root / 'main-tool-results.json'
    env = dict(os.environ)
    for key, sub in {'HOME': 'os-home', 'XDG_CONFIG_HOME': 'config', 'XDG_DATA_HOME': 'data',
                     'XDG_STATE_HOME': 'state', 'XDG_CACHE_HOME': 'cache', 'TMPDIR': 'tmp',
                     'LAMPWAY_HOME': 'profile', 'LAMPWAY_LEGACY_HOME': 'no-legacy'}.items():
        env[key] = str(client_root / sub); (client_root / sub).mkdir()
    env.update(LW_INTEGRATION_ROOT=str(client_root), LAMPWAY_TEST_ROOT=str(client_root),
               LAMPWAY_BRIDGE_PORT='0', LAMPWAY_BACKEND_URL=f'http://127.0.0.1:{settings.port}',
               PYTHON_KEYRING_BACKEND='mixar.modules.lampway_tools.keyring_file.FileKeyring')
    process = client = None
    proof = {'qualification': 'Real app/worker processes and pinned Hermes/herdr, deterministic local providers; no account proof',
             'binary_at_start': binary_fingerprint(),
             'stream_pause_phase': 'before-first-token' if pause_before_first else 'established-stream'}
    try:
        cockpit.ensure_server()
        app = create_app(settings, provider=main, swarm_provider_factory=worker_factory,
                         egress=strict, cockpit=cockpit)
        assert app.state.engine_wiring is not None
        tokens = app.state.engine_tokens
        watch_call, revoke_session = tokens.watch_call, tokens.revoke_session

        def observe_watch(token):
            future = watch_call(token)
            session = tokens.session_for(token)
            if not future.done() and session is not None:
                model_enrollments.append({'session': session, 'at': time.monotonic()})
            return future

        def observe_revoke(session):
            count = revoke_session(session)
            if count:
                key_revocations.append({'session': session, 'at': time.monotonic()})
            return count

        monkeypatch.setattr(tokens, 'watch_call', observe_watch)
        monkeypatch.setattr(tokens, 'revoke_session', observe_revoke)
        before = CAP.ACTIVE.setting('swarm')
        assert before['scope'] == 'default' and not before['enabled']
        refusal = CAP.check_tool('swarm_start', {'tasks': []}, origin='agent')
        assert refusal and 'swarm is off' in refusal
        proof['capability_fixture'] = {'before': before, 'default_off_refusal': refusal,
                                       'change': {'id': 'swarm', 'enabled': True, 'by': 'user'}}
        CH.active_store().set('agent.worker', 'global', None, {'preferred': 'mock'}, by='user')
        assert CH.resolve('agent.worker_mode').option == 'local:lampway_hermes'
        subprocess.run([str(ROOT / 'scripts/lampway/sync_python.sh'), '--bin-dir', str(lampway_bin().parent)],
                       check=True, capture_output=True)
        with Stack(app, settings), (client_root / 'app.log').open('w') as output:
            process = subprocess.Popen([xvfb, '-a', '-s', '-screen 0 1600x1000x24', 'nice', '-n', '15',
                str(lampway_bin()), '--python-exit-code', '1', '-P', str(ROOT / 'tests/qa/agent_modes_integrated_client.py')],
                env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            client = BlenderClient(client_root)
            ready = client.wait(lambda s: s.get('connected') and s.get('state') == 'IDLE')
            rid = client.command('enable_fixture_swarm')
            response = client.wait(lambda s: str(rid) in s.get('replies', {}))['replies'][str(rid)]
            assert response['enabled'], response
            proof['capability_fixture']['authenticated_user_route_response'] = response
            client.command('chat', text='Create the two fixture workers and collect both.')
            wait_for(lambda: len(providers) == 2 and all(p.held.is_set() for p in providers.values()), timeout=600)
            swarm = next(iter(app.state.agent.swarm.swarms.values()))
            assert len(swarm.workers) == 2 and all(w.status == 'running' for w in swarm.workers)
            assert all(w.calls and w.calls[0]['success'] for w in swarm.workers)
            held = client.wait(lambda s: s.get('state') == 'BUSY' and len(s.get('worker_processes', {})) == 2)
            pids = [held['worker_processes'][w.connection_id]['pid'] for w in swarm.workers]
            assert len(set(pids)) == 2 and all(process_running(pid) for pid in pids)
            sessions_before = pane_records(cockpit)
            workers_before = [r for r in sessions_before if r['swarm_binding'] in
                              {f'swarm:{swarm.id}:{w.id}' for w in swarm.workers}]
            mains = [r for r in sessions_before if r['unit'] == held['sid'] and r['role'] != 'worker' and r['state'] == 'live']
            assert len(workers_before) == 2 and all(r['state'] == 'live' for r in workers_before)
            assert len(mains) == 1, sessions_before
            proof.update({'held': held, 'workers_before': [w.detail() for w in swarm.workers],
                          'panes_before': sessions_before, 'worker_pids': pids})
            (client_root / 'worker-stop-proof.json').write_text(json.dumps(proof, indent=2, default=str))
            client.command('stop')
            app_idle = client.wait(lambda s: s.get('state') == 'IDLE' and not s.get('run_open'))
            proof['stop_returned_idle'] = app_idle
            wait_for(lambda: all(w.status == 'cancelled' and w.task.done() for w in swarm.workers))
            wait_for(lambda: all(not process_running(pid) for pid in pids))
            proof.update({'workers_after': [w.detail() for w in swarm.workers],
                          'panes_after': pane_records(cockpit),
                          'worker_processes_running_after_stop': {pid: process_running(pid) for pid in pids}})
            wait_for(lambda: all(p.stream_closed.is_set() and not p.active_requests for p in providers.values()), timeout=15,
                     failure='provider streams remain open after real Stop closed both worker panes and processes')
            after = client.status()
            sessions_after = pane_records(cockpit)
            ended = [r for r in sessions_after if r['id'] in {w['id'] for w in workers_before}]
            assert len(ended) == 2 and all(r['state'] == 'ended' and 'cancelled' in r['end_reason'] for r in ended), ended
            assert all(not app.state.agent.swarm.bindings.is_live(f'swarm:{swarm.id}:{w.id}') for w in swarm.workers)
            panes_after = cockpit.snapshot()['panes']
            pane_ids = {r['pane_id'] for r in panes_after}
            assert not ({r['pane_id'] for r in workers_before} & pane_ids), panes_after
            assert cockpit.pane_alive(mains[0]['id'])[0], 'Stop closed the main pane'
            # Collect terminalizes a cancelled swarm for its Retry card; only
            # staged workers can commit, and these both remain cancelled.
            assert swarm.collected and all(not w.receipt for w in swarm.workers)
            assert after['scene_objects'] == ready['scene_objects'], after
            assert 'Alpha' not in after['collections'] and 'Beta' not in after['collections'], after
            proof.update({'workers_after': [w.detail() for w in swarm.workers], 'panes_after': sessions_after,
                          'live_pane_ids_after': sorted(pane_ids), 'scene_after_stop': after})
            # After both worker tasks have settled, the same unit accepts a new
            # real island turn. Its completion is also the no-late-commit fence.
            client.command('chat', text='RECOVER after stopping the workers.')
            recovered = client.settled('Recovered after worker Stop.')
            assert recovered['sid'] == held['sid'] and not recovered['delivery_blocked'], recovered
            assert recovered['scene_objects'] == ready['scene_objects'], recovered
            assert swarm.collected and all(w.status == 'cancelled' and not w.receipt for w in swarm.workers)
            sessions = {r['session_id'] for r in gateway if str(r['session_id']).startswith('swarm:')}
            assert sessions == {f'swarm:{swarm.id}:worker-1', f'swarm:{swarm.id}:worker-2'}, gateway
            revoked_at = {r['session']: r['at'] for r in key_revocations if r['session'] in sessions}
            assert set(revoked_at) == sessions, key_revocations
            assert not [r for r in model_enrollments if r['session'] in revoked_at
                        and r['at'] > revoked_at[r['session']]], model_enrollments
            assert all(p.finished_requests == {f'{p.worker_name}:{n}' for n in range(1, p.request_seq + 1)}
                       and not p.active_requests for p in providers.values())
            assert not [r for r in strict.log() if r.get('event') == 'send'], strict.log()
            proof.update({'recovered': recovered, 'gateway': gateway, 'binary_at_end': binary_fingerprint()})
            assert proof['binary_at_start'] == proof['binary_at_end'], 'binary changed during the worker proof'
            client.command('quit'); process.wait(timeout=60)
            assert process.returncode == 0
    finally:
        proof.update({'gateway': gateway, 'model_enrollments': model_enrollments,
                      'key_revocations': key_revocations,
                      'provider_streams': {label: {'held': p.held.is_set(), 'closed': p.stream_closed.is_set(),
                      'active_requests': sorted(p.active_requests), 'finished_requests': sorted(p.finished_requests),
                      'request_lifecycle': p.request_lifecycle, 'tool_results': [part for request in p.requests
                       for m in request.messages for part in m.content if part.get('type') == 'tool_result']}
                      for label, p in providers.items()}})
        (client_root / 'worker-stop-proof.json').write_text(json.dumps(proof, indent=2, default=str))
        artifact_dir = os.environ.get('LAMPWAY_WORKER_STOP_ARTIFACTS')
        if artifact_dir:
            target = Path(artifact_dir); target.mkdir(parents=True, exist_ok=True)
            for path in [client_root / 'app.log', client_root / 'status.json', client_root / 'worker-stop-proof.json',
                         client_root / 'main-tool-results.json', *(client_root / 'tmp').glob('mixar_sandbox_*.log')]:
                if path.exists(): shutil.copy2(path, target / path.name)
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=15)
        status_path = client_root / 'status.json'
        if status_path.exists():
            saved = json.loads(status_path.read_text())
            for child in saved.get('worker_processes', {}).values():
                pid = child['pid']
                try:
                    own_env = f'LW_INTEGRATION_ROOT={client_root}'.encode()
                    environ = Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
                    if own_env in environ and os.getpgid(pid) == pid:
                        os.killpg(pid, signal.SIGTERM)
                except (ProcessLookupError, FileNotFoundError):
                    pass
        L.stop_server(root, confirmed=True)
        shutil.rmtree(root, ignore_errors=True)
