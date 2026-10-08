# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""S5: real two-worker headless Blender swarm, pinned Hermes/herdr, local deterministic providers.

Only model responses are scripted. Worker processes, sockets, task fences,
staging artifacts and both parent commits are production implementations.
"""
import json
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import uuid

import pytest

from test_agent_modes_integrated_live import (ROOT, BlenderClient, ENGINES, MISSING, NODE, TUI,
    LiveProvider, Stack, free_port, create_app, Settings, EG, Cockpit, L, Text, ToolCall, lampway_bin)
from lampway_server import choices as CH
from lampway_server import capabilities as CAP
from lampway_server.agent.providers.mock import _called
from lampway_server.engine import wiring as EW
from lampway_server.compute.toon_out import decode as decode_toon


def call_tool(request, name, args):
    full = 'mcp__lampway__' + name
    direct = full in {t.name for t in request.tools}
    return ToolCall(id='call_' + uuid.uuid4().hex[:8], name=full if direct else 'tool_call',
                    arguments=args if direct else {'calls': [{'name': full, 'arguments': args}]})


def find_swarm_id(value):
    if isinstance(value, str):
        if value.startswith('<untrusted_tool_result '):
            # Hermes wraps MCP structuredContent in its data-only envelope.
            start = value.index('{')
            decoded, _ = json.JSONDecoder().raw_decode(value[start:])
            return find_swarm_id(decoded)
        try:
            return find_swarm_id(json.loads(value))
        except (ValueError, TypeError):
            try:
                decoded = decode_toon(value)
                return find_swarm_id(decoded) if not isinstance(decoded, str) else None
            except ValueError:
                return None
    if isinstance(value, dict):
        if value.get('swarm_id'):
            return value['swarm_id']
        values = value.values()
    elif isinstance(value, list):
        values = value
    else:
        return None
    return next((found for item in values if (found := find_swarm_id(item))), None)


def binary_fingerprint():
    binary = lampway_bin()
    with binary.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(binary.resolve()), 'sha256': digest, 'bytes': binary.stat().st_size}


class SwarmProvider(LiveProvider):
    async def stream(self, request):
        self.requests.append(request)
        if getattr(self, 'audit_path', None):
            self.audit_path.write_text(json.dumps([p for m in request.messages for p in m.content
                if p.get('type') == 'tool_result'], indent=2, default=str))
        if not request.tools:
            yield Text('Two fixture workers')
        elif not _called(request.messages, 'swarm_start'):
            yield call_tool(request, 'swarm_start', {'tasks': [
                {'name': 'Alpha', 'prompt': 'Create Alpha_object, one synthetic mesh.'},
                {'name': 'Beta', 'prompt': 'Create Beta_object, one synthetic mesh.'}]})
        elif not _called(request.messages, 'swarm_collect'):
            swarm_id = find_swarm_id([m.content for m in request.messages])
            assert swarm_id, 'the real swarm_start result did not contain a swarm_id'
            yield call_tool(request, 'swarm_collect', {'swarm_id': swarm_id})
        else:
            yield Text('Collected both fixture workers.')


class WorkerProvider(LiveProvider):
    def __init__(self, label):
        super().__init__()
        self.name = 'deterministic-fixture-' + label
        self.worker_name = {'worker-1': 'Alpha', 'worker-2': 'Beta'}[label]

    async def stream(self, request):
        self.requests.append(request)
        if not request.tools:
            yield Text(self.worker_name + ' fixture worker')
        elif not _called(request.messages, 'run_blender_python'):
            name = self.worker_name
            script = ('import bpy\n'
                f'mesh = bpy.data.meshes.new("{name}_mesh")\n'
                'mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])\n'
                f'obj = bpy.data.objects.new("{name}_object", mesh)\n'
                'bpy.context.scene.collection.objects.link(obj)\n'
                '__RESULT__ = {"worker_objects": sorted(o.name for o in bpy.context.scene.objects)}')
            yield call_tool(request, 'run_blender_python', {'script': script})
        elif not _called(request.messages, 'lampway_worker_done'):
            yield call_tool(request, 'lampway_worker_done', {'summary': self.worker_name + ' created its synthetic mesh.'})
        else:
            yield Text(self.worker_name + ' finished.')


@pytest.mark.timeout(1200)
def test_two_real_mode1_workers_collect_into_real_parent_blender(tmp_path, monkeypatch):
    assert lampway_bin().exists(), f'No built Blender at {lampway_bin()}'
    if MISSING:
        pytest.fail(MISSING)
    xvfb = shutil.which('xvfb-run')
    assert xvfb, 'isolated cloud xvfb-run is required'
    root = Path(tempfile.mkdtemp(prefix='lw-s5-', dir='/tmp'))
    project = tmp_path / 'project'; project.mkdir()
    for key, value in {'LAMPWAY_ENGINES_DIR': str(ENGINES), 'LAMPWAY_HERMES_TUI_DIR': str(TUI),
                       'LAMPWAY_NODE': NODE, 'LAMPWAY_PROJECT_ROOT': str(project),
                       'LAMPWAY_SECRETS_DIR': str(tmp_path / 'secrets')}.items():
        monkeypatch.setenv(key, value)
    settings = Settings(port=free_port(), jwt_secret='test-secret-not-for-production', user_password='correct-horse',
                        state_dir=tmp_path / 'server-state', provider='mock')
    strict = EG.Egress(tmp_path / 'strict-egress')
    cockpit = Cockpit(root, project_root=str(project))
    providers, factories, gateway = {}, [], []
    main = SwarmProvider()

    def worker_factory(label, *, resolution=None):
        assert resolution is not None and resolution.option == 'mock', resolution
        factories.append({'worker': label, 'selection': resolution.record()})
        providers[label] = WorkerProvider(label)
        return providers[label]

    original_getter = EW.provider_getter
    def observed_getter(agent, *, settings=None, chatgpt_auth=None):
        actual = original_getter(agent, settings=settings, chatgpt_auth=chatgpt_auth)
        def get(session_id=None, requested_model=None):
            selected = actual(session_id, requested_model)
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
    proof = {'qualification': 'Actual app + two real headless Blender workers + pinned Hermes/herdr; deterministic local provider, no account/native-chip proof'}
    proof['binary_at_start'] = binary_fingerprint()
    try:
        cockpit.ensure_server()
        app = create_app(settings, provider=main, swarm_provider_factory=worker_factory,
                         egress=strict, cockpit=cockpit)
        assert app.state.engine_wiring is not None
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
            client.wait(lambda s: s.get('connected') and s.get('state') == 'IDLE')
            rid = client.command('enable_fixture_swarm')
            reply = client.wait(lambda s: str(rid) in s.get('replies', {}))['replies'][str(rid)]
            proof['capability_fixture']['authenticated_user_route_response'] = reply
            assert reply['enabled'] and CAP.ACTIVE.setting('swarm')['enabled'], reply
            client.command('chat', text='Create the two fixture workers and collect both.')
            final = client.settled('Collected both fixture workers.', timeout=600)
            swarm = next(iter(app.state.agent.swarm.swarms.values()))
            proof.update({'swarm_id': swarm.id, 'workers': [w.detail() for w in swarm.workers],
                'worker_processes': final['worker_processes'], 'gateway': gateway, 'factories': factories,
                'scene_objects': final['scene_objects'], 'collections': final['collections'],
                'collection_children': final['collection_children'],
                'worker_model_results': {label: [part for req in provider.requests for m in req.messages
                    for part in m.content if part.get('type') == 'tool_result'] for label, provider in providers.items()}})
            (client_root / 'worker-proof.json').write_text(json.dumps(proof, indent=2, default=str))
            assert swarm.collected and len(swarm.workers) == 2
            assert all(w.status == 'done' and w.receipt and w.calls[0]['success'] for w in swarm.workers), proof
            assert len({w.connection_id for w in swarm.workers}) == 2
            assert len({final['worker_processes'][w.connection_id]['pid'] for w in swarm.workers}) == 2
            assert set(final['collection_children']['Lampway Agent']) == {'Alpha', 'Beta'}, final
            assert final['collections']['Alpha'] == ['Alpha_object'], final
            assert final['collections']['Beta'] == ['Beta_object'], final
            assert {'Alpha_object', 'Beta_object'} <= set(final['scene_objects']), final
            assert len(factories) == 2 and {r['selection']['option'] for r in factories} == {'mock'}
            sessions = {r['session_id'] for r in gateway if str(r['session_id']).startswith('swarm:')}
            assert sessions == {f'swarm:{swarm.id}:worker-1', f'swarm:{swarm.id}:worker-2'}, proof
            for worker in swarm.workers:
                results = proof['worker_model_results'][worker.id]
                assert results and worker.name + '_object' in json.dumps(results), results
                other = 'Beta' if worker.name == 'Alpha' else 'Alpha'
                assert other + '_object' not in json.dumps(results), results
            assert not [r for r in strict.log() if r.get('event') == 'send'], strict.log()
            proof['binary_at_end'] = binary_fingerprint()
            assert proof['binary_at_start'] == proof['binary_at_end'], 'binary changed during the worker proof'
            client.command('quit'); process.wait(timeout=60)
            assert process.returncode == 0
    except Exception:
        print((client_root / 'app.log').read_text()[-12000:] if (client_root / 'app.log').exists() else 'no app log')
        raise
    finally:
        proof.update({'gateway': gateway, 'factories': factories,
            'main_tool_results': [p for request in main.requests for m in request.messages
                                 for p in m.content if p.get('type') == 'tool_result']})
        (client_root / 'worker-proof.json').write_text(json.dumps(proof, indent=2, default=str))
        artifact_dir = os.environ.get('LAMPWAY_WORKER_ARTIFACTS')
        if artifact_dir:
            target = Path(artifact_dir); target.mkdir(parents=True, exist_ok=True)
            for path in [client_root / 'app.log', client_root / 'status.json', client_root / 'worker-proof.json',
                         client_root / 'main-tool-results.json',
                         *(client_root / 'tmp').glob('mixar_sandbox_*.log')]:
                if path.exists(): shutil.copy2(path, target / path.name)
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=15)
        # A failed parent turn can leave its setsid worker children alive. Only
        # stop PIDs recorded by this fixture's real sandbox supervisor.
        if client is not None and (client_root / 'status.json').exists():
            saved = json.loads((client_root / 'status.json').read_text())
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
