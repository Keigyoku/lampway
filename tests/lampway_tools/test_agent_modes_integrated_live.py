# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real Blender + Lampway server + pinned herdr/Hermes, deterministic loopback model, no new grants.

The fixture uses a real isolated Xvfb window and real socket/executor/slots. Vendor/account paths are not covered.
"""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import pytest

from blender_run import ROOT, lampway_bin

sys.path.insert(0, str(ROOT / 'server'))
# Name the server's support package explicitly; root's client tests also use the name "tests".
PACKAGE = 'lampway_live_support'
spec = importlib.util.spec_from_file_location(PACKAGE, ROOT / 'server/tests/__init__.py',
    submodule_search_locations=[str(ROOT / 'server/tests')])
package = importlib.util.module_from_spec(spec)
sys.modules[PACKAGE] = package
spec.loader.exec_module(package)
from lampway_live_support.test_engine_pane_live import LiveProvider, ENGINES, MISSING, NODE, TUI
from lampway_live_support.serve_support import Stack, free_port
from lampway_server.app import create_app
from lampway_server.config import Settings
from lampway_server import egress as EG
from lampway_server.herdr.host import Cockpit
from lampway_server.herdr import launcher as L
from lampway_server.agent.providers.base import Text, ToolCall
from lampway_server.engine.serve_client import ServeClient


class SceneProvider(LiveProvider):
    """Only the model response is scripted; the named tool really runs in Blender."""
    def __init__(self):
        super().__init__()
        self.holding = threading.Event()

    async def stream(self, request):
        users = self._user_texts(request)
        if not request.tools or not users or 'MUTATE' not in users[-1]:
            if request.tools and any('HOLD' in text for text in users[-2:]) and any(
                p.get('type') == 'tool_result' for m in request.messages for p in m.content):
                self.holding.set()
            async for item in super().stream(request):
                yield item
            return
        self.requests.append(request)
        idx = max(i for i, m in enumerate(request.messages) if m.role == 'user' and m.text())
        results = [p for m in request.messages[idx + 1:] for p in m.content if p.get('type') == 'tool_result']
        if results:
            yield Text('Mutation complete.')
            return
        name = 'mcp__lampway__run_blender_python'
        args = {'script': 'import bpy\nbpy.context.scene["fixture_mutation"] = 7\n__RESULT__ = {"mutated": 7}'}
        direct = name in {t.name for t in request.tools}
        yield ToolCall(id='call_' + uuid.uuid4().hex[:8], name=name if direct else 'tool_call',
                       arguments=args if direct else {'calls': [{'name': name, 'arguments': args}]})


class BlenderClient:
    def __init__(self, root):
        self.root, self.serial = root, 0

    def status(self):
        try:
            value = json.loads((self.root / 'status.json').read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        assert not value.get('error'), value.get('error')
        return value

    def wait(self, predicate, timeout=300):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = self.status()
            if predicate(value):
                return value
            time.sleep(.1)
        raise AssertionError(f'Blender timed out: {self.status()}')

    def command(self, action, **extra):
        self.serial += 1
        tmp = self.root / 'command.tmp'
        tmp.write_text(json.dumps({'id': self.serial, 'action': action, **extra}))
        tmp.replace(self.root / 'command.json')
        self.wait(lambda s: s.get('command', 0) >= self.serial)
        return self.serial

    def settled(self, text, timeout=300):
        return self.wait(lambda s: s.get('state') == 'IDLE' and any(
            m.get('content') == text for m in s.get('messages', [])), timeout)

    def chat_complete(self, text):
        previous = set(self.status().get('turns', {}))
        self.command('chat', text=text)
        return self.wait(lambda s: s.get('state') == 'IDLE' and any(
            k not in previous and turn['complete'] for k, turn in s.get('turns', {}).items()))

    def rpc(self, method, **payload):
        rid = self.command('rpc', method=method, payload=payload)
        result = self.wait(lambda s: str(rid) in s.get('replies', {}))['replies'][str(rid)]
        while isinstance(result, dict) and 'result' in result:
            result = result['result']
        return result


def native_sessions(record):
    """Read the surviving real serve, even while the Lampway server is absent."""
    async def read():
        client = ServeClient(record['port'], Path(record['token_file']).read_text().strip(), server_requests=False)
        try:
            await client.connect()
            return (await client.call('session.active_list', {}, timeout=10)).get('sessions') or []
        finally:
            await client.close()
    return asyncio.run(read())


def serve_identity(record):
    pid = int((Path(record['home']) / 'serve.pid').read_text())
    stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    assert stat[0] != 'Z', (pid, stat[0])
    return {'pid': pid, 'startticks': int(stat[19])}


@pytest.mark.timeout(1200)
def test_real_blender_roundtrip_through_real_hermes_and_herdr(tmp_path, monkeypatch):
    assert lampway_bin().exists(), f'No built Blender at {lampway_bin()}'
    if MISSING:
        pytest.fail(MISSING)
    xvfb = shutil.which('xvfb-run')
    if not xvfb:
        pytest.fail('isolated cloud xvfb-run is required')
    root = Path(tempfile.mkdtemp(prefix='lw-real-', dir='/tmp'))
    project = tmp_path / 'project'; project.mkdir()
    for key, value in {'LAMPWAY_ENGINES_DIR': str(ENGINES), 'LAMPWAY_HERMES_TUI_DIR': str(TUI),
                       'LAMPWAY_NODE': NODE, 'LAMPWAY_PROJECT_ROOT': str(project),
                       'LAMPWAY_SECRETS_DIR': str(tmp_path / 'secrets')}.items():
        monkeypatch.setenv(key, value)
    settings = Settings(port=free_port(), jwt_secret='test-secret-not-for-production', user_password='correct-horse',
                        state_dir=tmp_path / 'server-state', provider='mock')
    strict = EG.Egress(tmp_path / 'strict-egress')
    cockpit = Cockpit(root, project_root=str(project))
    provider = SceneProvider()
    env = dict(os.environ)
    client_root = tmp_path / 'client'; client_root.mkdir()
    for key, sub in {'HOME': 'os-home', 'XDG_CONFIG_HOME': 'config', 'XDG_DATA_HOME': 'data',
                     'XDG_STATE_HOME': 'state', 'XDG_CACHE_HOME': 'cache', 'TMPDIR': 'tmp',
                     'LAMPWAY_HOME': 'profile', 'LAMPWAY_LEGACY_HOME': 'no-legacy'}.items():
        env[key] = str(client_root / sub); (client_root / sub).mkdir()
    env.update(LW_INTEGRATION_ROOT=str(client_root), LAMPWAY_TEST_ROOT=str(client_root),
               LAMPWAY_BRIDGE_PORT='0', LAMPWAY_BACKEND_URL=f'http://127.0.0.1:{settings.port}',
               PYTHON_KEYRING_BACKEND='mixar.modules.lampway_tools.keyring_file.FileKeyring')
    process = None
    try:
        cockpit.ensure_server()
        app = create_app(settings, provider=provider, egress=strict, cockpit=cockpit)
        assert app.state.engine_wiring is not None
        subprocess.run([str(ROOT / 'scripts/lampway/sync_python.sh'), '--bin-dir', str(lampway_bin().parent)],
                       check=True, capture_output=True)
        with Stack(app, settings) as stack:
            front = app.state.engine_wiring.front
            events = []
            original_event = front._on_event

            async def record_event(link, frame):
                def state():
                    sink = link.sink
                    return {'running': link.running, 'island_prompts': link.island_prompts, 'absorb': link.absorb,
                            'sink_pending': sink.pending if sink else None,
                            'sink_turn': sink.turn.turn_id if sink and sink.turn else None}
                row = {'type': frame.get('type'), 'seq': frame.get('seq'), 'before': state(),
                       'status': (frame.get('payload') or {}).get('status')}
                await original_event(link, frame)
                row['after'] = state()
                events.append(row)
                (client_root / 'engine-events.json').write_text(json.dumps(events))

            monkeypatch.setattr(front, '_on_event', record_event)
            with (client_root / 'app.log').open('w') as output:
                process = subprocess.Popen([xvfb, '-a', '-s', '-screen 0 1600x1000x24', 'nice', '-n', '15',
                    str(lampway_bin()), '--python-exit-code', '1', '-P', str(ROOT / 'tests/qa/agent_modes_integrated_client.py')],
                    env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                client = BlenderClient(client_root)
                ready = client.wait(lambda s: s.get('connected') and s.get('state') == 'IDLE')
                client.command('chat', text='SCENE: what is in my scene?')
                settled = client.settled('There is one cube.')
                sid = settled['sid']; assert sid
                client.command('unknown_script_gate')
                assert any(m['steps'] for m in settled['messages']), settled
                rec = next(r for r in cockpit.list_sessions() if r.get('unit') == sid)
                assert rec['agent'] == 'lampway_hermes' and rec['stored_session_id']
                end = time.monotonic() + 60
                while 'There is one cube.' not in cockpit.read_screen(rec['id'], 120):
                    assert time.monotonic() < end
                    time.sleep(.2)
                # Type into the real TUI while both app and pane are idle.
                old_turns = set(client.status()['turns'])
                cockpit.send_input(rec['id'], 'SCENE typed in the pane', submit=True, by='user')
                pane = client.wait(lambda s: any(k not in old_turns and turn['pane'] and turn['complete']
                    for k, turn in s.get('turns', {}).items()))
                assert any('SCENE typed in the pane' in m['text'] for m in pane['messages']), pane
                assert pane['state'] == 'IDLE' and not pane['run_open']
                # A real chat while the tool turn is in flight uses the active turn's steer path.
                provider.release.clear()
                provider.holding.clear()
                client.command('chat', text='HOLD: make a chair')
                held = client.wait(lambda s: s.get('state') == 'BUSY' and any(
                    not turn['complete'] for turn in s.get('turns', {}).values()))
                assert provider.holding.wait(90), 'Hermes did not reach the held tool result'
                client.command('chat', text='make it red')
                time.sleep(1.0)  # the socket's steer must arrive before the model response is released
                provider.release.set()
                client.settled('Red it is.')
                assert any('make it red' in m['text'] for m in client.status()['messages'])
                # Stop goes through the registered UI operator and the actual socket.
                provider.release.clear()
                provider.holding.clear()
                client.command('chat', text='HOLD: stop this turn')
                client.wait(lambda s: s.get('state') == 'BUSY' and any(
                    not turn['complete'] for turn in s.get('turns', {}).values()))
                client.command('stop')
                provider.release.set()
                client.wait(lambda s: s.get('state') == 'IDLE' and not s.get('run_open') and
                    all(turn['complete'] for turn in s.get('turns', {}).values()))
                link = front.links[sid]
                (client_root / 'stop-settlement.json').write_text(json.dumps({
                    'app': client.status(), 'engine_running': link.running, 'island_prompts': link.island_prompts,
                    'sink_pending': link.sink.pending if link.sink else None, 'absorb': link.absorb}))
                # No engine-idle wait: the user starts a fresh pane turn as soon as Stop returns IDLE.
                previous_turns = set(client.status()['turns'])
                cockpit.send_input(rec['id'], 'SCENE immediately after Stop', submit=True, by='user')
                try:
                    after_stop = client.wait(lambda s: any(k not in previous_turns and turn['pane'] and turn['complete']
                        for k, turn in s.get('turns', {}).items()), timeout=120)
                    assert not after_stop['delivery_blocked']
                    assert any('SCENE immediately after Stop' in m['text'] for m in after_stop['messages'])
                    (client_root / 'post-stop-island.json').write_text(json.dumps(after_stop))
                finally:
                    (client_root / 'post-stop-tui-screen.txt').write_text(cockpit.read_screen(rec['id'], 120))
                client.wait(lambda s: not link.running and link.sink is None)
                # The SAME island controls must steer/Stop a turn whose origin
                # is the actual TUI, not merely a turn submitted by the island.
                pane_control = {}
                steer_receipts = []
                serve = front.links[sid].client
                original_call = serve.call

                async def record_call(method, params=None, **kwargs):
                    result = await original_call(method, params, **kwargs)
                    if method == 'session.steer':
                        steer_receipts.append({'params': params, 'result': result})
                    return result

                monkeypatch.setattr(serve, 'call', record_call)
                for control in ('steer', 'stop'):
                    previous = set(client.status()['turns'])
                    old_bubbles = {m['bubble_id'] for m in client.status()['messages']}
                    provider.release.clear(); provider.holding.clear()
                    text = f'HOLD pane-origin {control} acceptance'
                    cockpit.send_input(rec['id'], text, submit=True, by='user')
                    held_pane = client.wait(lambda s: s.get('state') == 'BUSY' and any(
                        k not in previous and t['pane'] and not t['complete']
                        for k, t in s.get('turns', {}).items()))
                    turn_id = next(k for k, t in held_pane['turns'].items()
                                   if k not in previous and t['pane'] and not t['complete'])
                    assert any(text in m['text'] for m in held_pane['messages']), held_pane
                    assert provider.holding.wait(90), f'pane {control} did not reach the held real tool result'
                    if control == 'steer':
                        client.command('chat', text='make it red for pane-origin steer')
                        # Observe the real serve ACK before releasing the held
                        # response. The wrapper delegates every request unchanged.
                        client.wait(lambda s: any('make it red for pane-origin steer' in m['text']
                                                 for m in s.get('messages', [])))
                        client.wait(lambda s: any(r['params'].get('text') == 'make it red for pane-origin steer'
                                                 for r in steer_receipts), timeout=60)
                        ack = next(r['result'] for r in steer_receipts
                                   if r['params'].get('text') == 'make it red for pane-origin steer')
                        assert ack.get('status') == 'queued', ack
                        provider.release.set()
                        client.settled('Red it is.')
                    else:
                        client.command('stop')
                        provider.release.set()
                    completed = client.wait(lambda s: s.get('state') == 'IDLE' and not s.get('run_open') and
                        s.get('turns', {}).get(turn_id, {}).get('complete'))
                    assert completed['turns'][turn_id]['pane'], completed
                    if control == 'steer':
                        assert any(m['bubble_id'] not in old_bubbles and m['content'] == 'Red it is.'
                                   for m in completed['messages']), completed
                    link = front.links[sid]
                    client.wait(lambda s: not link.running and link.sink is None)
                    pane_control[control] = {'held': held_pane, 'completed': completed,
                                             'engine_running': link.running, 'sink_absent': link.sink is None,
                                             'steer_receipts': list(steer_receipts)}
                    (client_root / 'pane-origin-control.json').write_text(json.dumps(pane_control))
                # A synthetic scene ID property exercises the normal tool's undo boundary.
                client.command('chat', text='MUTATE the disposable fixture scene')
                changed = client.settled('Mutation complete.')
                assert changed['mutation'] == 7, changed
                client.command('undo')
                client.wait(lambda s: s.get('mutation') is None)
                previous = set(client.status()['turns'])
                gate_count = len(client.status()['script_gates'])
                cockpit.send_input(rec['id'], 'MUTATE from the actual pane', submit=True, by='user')
                pane_mutated = client.wait(lambda s: s.get('mutation') == 7 and s.get('state') == 'IDLE' and any(
                    k not in previous and t['pane'] and t['complete'] for k, t in s.get('turns', {}).items()))
                assert any('MUTATE from the actual pane' in m['text'] for m in pane_mutated['messages'])
                assert any(g['known_before'] and not g['refusal'] for g in pane_mutated['script_gates'][gate_count:]), pane_mutated
                client.command('undo')
                pane_undone = client.wait(lambda s: s.get('mutation') is None)
                (client_root / 'pane-origin-undo.json').write_text(json.dumps({'changed': pane_mutated, 'undone': pane_undone}))
                client.command('seed_media_checkpoint')
                previous_conversation = client.status()['conversation']
                cockpit.send_input(rec['id'], '/new fixture reset', submit=True, by='user')
                end = time.monotonic() + 60
                while True:
                    screen = cockpit.read_screen(rec['id'], 120)
                    if 'Start a new session?' in screen:
                        cockpit.send_input(rec['id'], 'y', submit=False, by='user')
                        break
                    if client.status()['conversation'] != previous_conversation:
                        break
                    assert time.monotonic() < end, screen
                    time.sleep(.2)
                fresh = client.wait(lambda s: s.get('conversation') and s['conversation'] != previous_conversation)
                assert fresh['sid'] == sid and not any(m['sender'] == 'USER' for m in fresh['messages']), fresh
                rid = client.command('archive_status')
                records = client.wait(lambda s: str(rid) in s.get('replies', {}))['replies'][str(rid)]
                filed = next(r for r in records if r['sid'] != sid and r['media'])
                assert filed['media_exists'] and filed['checkpoints'], filed
                assert all(filed['sid'] in path for path in filed['media']), filed
                client.chat_complete('Hello first retained turn')
                second = client.chat_complete('Hello second removed turn')
                second_id = next(m['bubble_id'] for m in second['messages'] if m['text'] == 'Hello second removed turn')
                assert client.rpc('checkpoint.mark', session_id=sid, request_id='fixture-tip')['ok']
                back = client.rpc('checkpoint.rewind', session_id=sid, request_id=second_id)
                assert back == {'ok': True, 'has_conversation': True, 'removed_turns': 1}, back
                before = len(provider.requests)
                client.chat_complete('Hello third after rewind')
                words = '\n'.join(m.text() for request in provider.requests[before:] if request.tools for m in request.messages)
                assert 'Hello first retained turn' in words and 'Hello third after rewind' in words
                assert 'Hello second removed turn' not in words
                forward = client.rpc('checkpoint.rewind', session_id=sid, request_id='fixture-tip')
                assert forward['ok'] is False and forward['code'] == 'rewind_forward', forward
                stored = cockpit._get(rec['id'])['stored_session_id']
                cockpit.close_session(rec['id'], confirmed=True)
                client.chat_complete('Hello after the ended pane reopens')
                reopened = [r for r in cockpit.list_sessions() if r.get('unit') == sid and r['state'] == 'live']
                assert len(reopened) == 1 and reopened[0]['id'] != rec['id'], reopened
                assert reopened[0]['stored_session_id'] == stored, reopened
                assert not [r for r in strict.log() if r.get('event') == 'send'], strict.log()
                # Save BEFORE /new. Both application and server will be absent
                # when the user starts the next conversation in the real pane.
                client.chat_complete('Hello saved before disconnected native new')
                client.command('seed_media_checkpoint')
                before_away = client.status()
                save_id = client.command('save_before_new')
                saved = client.wait(lambda s: str(save_id) in s.get('replies', {}))['replies'][str(save_id)]
                saved_path = Path(saved['file'])
                assert saved['sid'] == sid and saved['conversation'] == before_away['conversation']
                saved_hash = hashlib.sha256(saved_path.read_bytes()).hexdigest()
                away_rec = cockpit._get(reopened[0]['id'])
                backend_before = serve_identity(away_rec)
                client.command('quit')
                process.wait(timeout=60)
                assert process.returncode == 0, (client_root / 'app.log').read_text()[-8000:]
                shutil.copy2(client_root / 'status.json', client_root / 'before-away-status.json')
                shutil.copy2(client_root / 'loaded-before-connect.json', client_root / 'initial-loaded-before-connect.json')
                stack.__exit__(None, None, None)
                assert not stack.thread.is_alive(), 'owned server did not stop'
                with socket.socket() as probe:
                    probe.settimeout(1)
                    assert probe.connect_ex(('127.0.0.1', settings.port)) != 0, 'server still accepts connections'
                assert serve_identity(away_rec) == backend_before
                assert any(r.get('session_key') == saved['conversation'] for r in native_sessions(away_rec))
                cockpit.send_input(away_rec['id'], '/new disconnected saved-file acceptance', submit=True, by='user')
                end = time.monotonic() + 60
                confirmed = False
                while True:
                    screen = cockpit.read_screen(away_rec['id'], 120)
                    if not confirmed and 'Start a new session?' in screen:
                        cockpit.send_input(away_rec['id'], 'y', submit=False, by='user')
                        confirmed = True
                    active = [r for r in native_sessions(away_rec) if r.get('session_key')]
                    if active and saved['conversation'] not in {r['session_key'] for r in active}:
                        new_conversation = str(max(active, key=lambda r: float(r.get('started_at') or 0))['session_key'])
                        break
                    assert time.monotonic() < end, {'screen': screen, 'active': active}
                    time.sleep(.2)
                assert serve_identity(away_rec) == backend_before
                # Fresh server/cockpit objects read the persisted registry; no
                # old front link, synthetic event, or rewritten session record.
                cockpit = Cockpit(root, project_root=str(project))
                restarted_app = create_app(settings, provider=provider, egress=strict, cockpit=cockpit)
                with Stack(restarted_app, settings):
                    front = restarted_app.state.engine_wiring.front
                    original_event = front._on_event
                    monkeypatch.setattr(front, '_on_event', record_event)
                    (client_root / 'command.json').rename(client_root / 'before-away-command.json')
                    (client_root / 'status.json').unlink()
                    # Retain the actual file/profile/History, but mint a fresh
                    # synthetic login instead of letting the old keyring auto-
                    # connect before the loaded-file observation is recorded.
                    reopened_env = dict(env)
                    reopened_state = client_root / 'reopened-state'
                    reopened_state.mkdir()
                    reopened_env['XDG_STATE_HOME'] = str(reopened_state)
                    with (client_root / 'reopened-app.log').open('w') as reopened_output:
                        process = subprocess.Popen([xvfb, '-a', '-s', '-screen 0 1600x1000x24', 'nice', '-n', '15',
                            str(lampway_bin()), str(saved_path), '--python-exit-code', '1', '-P',
                            str(ROOT / 'tests/qa/agent_modes_integrated_client.py')],
                            env=reopened_env, stdout=reopened_output, stderr=subprocess.STDOUT, start_new_session=True)
                        client = BlenderClient(client_root)
                        followed = client.wait(lambda s: s.get('connected') and s.get('state') == 'IDLE' and
                            s.get('conversation') == new_conversation)
                        loaded = json.loads((client_root / 'loaded-before-connect.json').read_text())
                        assert loaded['sid'] == sid and loaded['conversation'] == saved['conversation'], loaded
                        assert not loaded['connected'], loaded
                        assert any(m['text'] == 'Hello saved before disconnected native new' for m in loaded['messages'])
                        assert followed['sid'] == sid and not any(m['sender'] == 'USER' for m in followed['messages']), followed
                        assert hashlib.sha256(saved_path.read_bytes()).hexdigest() == saved_hash
                        live = [r for r in cockpit.list_sessions() if r.get('unit') == sid and r['state'] == 'live']
                        assert len(live) == 1 and live[0]['id'] == away_rec['id'], live
                        assert live[0]['stored_session_id'] == new_conversation, live
                        assert serve_identity(live[0]) == backend_before
                        rid = client.command('archive_status')
                        archives = client.wait(lambda s: str(rid) in s.get('replies', {}))['replies'][str(rid)]
                        old_chat = next(r for r in archives if r['sid'] != sid and any(
                            m.get('text') == 'Hello saved before disconnected native new' for m in r['messages']))
                        assert old_chat['media'] and old_chat['media_exists'] and old_chat['checkpoints'], old_chat
                        assert all(old_chat['sid'] in p for p in old_chat['media']), old_chat
                        rid = client.command('open_history', session_id=old_chat['sid'])
                        opened = client.wait(lambda s: str(rid) in s.get('replies', {}))['replies'][str(rid)]
                        assert opened['sid'] == old_chat['sid'] and old_chat['sid'] in opened['entries'], opened
                        expected = [{k: m.get(k, '') for k in ('sender', 'text', 'content', 'bubble_id')}
                                    for m in old_chat['messages']]
                        assert opened['messages'] == expected, {'opened': opened, 'expected': expected}
                        assert opened['media'] == old_chat['media'] and all(Path(p).is_file() for p in opened['media'])
                        assert not client.status()['run_open']
                        (client_root / 'disconnected-history-proof.json').write_text(json.dumps({
                            'saved': saved, 'saved_sha256': saved_hash, 'backend_before': backend_before,
                            'new_conversation': new_conversation, 'native_active_while_away': active,
                            'loaded_before_connect': loaded, 'followed': followed, 'archive': old_chat, 'opened': opened}))
                        assert not [r for r in strict.log() if r.get('event') == 'send'], strict.log()
                        client.command('quit')
                        process.wait(timeout=60)
                        assert process.returncode == 0, (client_root / 'reopened-app.log').read_text()[-8000:]
    except Exception:
        print((client_root / 'app.log').read_text()[-12000:] if (client_root / 'app.log').exists() else 'no app log')
        raise
    finally:
        artifact_dir = os.environ.get('LAMPWAY_INTEGRATION_ARTIFACTS')
        if artifact_dir:
            target = Path(artifact_dir); target.mkdir(parents=True, exist_ok=True)
            for name in ('app.log', 'status.json', 'engine-events.json', 'stop-settlement.json',
                         'post-stop-island.json', 'post-stop-tui-screen.txt', 'pane-origin-control.json',
                         'pane-origin-undo.json', 'before-away-status.json', 'loaded-before-connect.json',
                         'initial-loaded-before-connect.json', 'reopened-app.log', 'disconnected-history-proof.json'):
                if (client_root / name).exists():
                    shutil.copy2(client_root / name, target / name)
        provider.release.set()
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=15)
        L.stop_server(root, confirmed=True)
        shutil.rmtree(root, ignore_errors=True)
