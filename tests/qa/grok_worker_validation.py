#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cloud-only owned-fixture validator, never a worker-readiness grant.

Public downloads happen in CI setup. Native execution is either under inherited
INET/INET6 denial, or in a separate network namespace with loopback only. No
accounts, provider endpoints, real homes or host security changes are involved.
Receipts survive every failure; absent proof fails rather than becoming a skip.
"""
import argparse
import asyncio
import ctypes
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback

GROK_SHA256 = '41626a53292324140b92556b9d42ff5542e3dcd04aff85eafb8689dd4adb44fc'
PERSONA = 'SYNTHETIC_ORIGINAL_PERSONA_MUST_REMAIN'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_state(path):
    path = Path(path)
    return {'sha256': digest(path), 'mode': path.stat().st_mode & 0o777} if path.is_file() else {'absent': True}


def deny_inet():
    """The prior approved guard: no socket(AF_INET/AF_INET6), including loopback."""
    lib = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]; lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]; lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    class Cmp(ctypes.Structure):
        _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_int), ('a', ctypes.c_uint64), ('b', ctypes.c_uint64)]
    lib.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(Cmp)]
    lib.seccomp_rule_add_array.restype = ctypes.c_int
    lib.seccomp_load.argtypes = [ctypes.c_void_p]; lib.seccomp_load.restype = ctypes.c_int
    context = lib.seccomp_init(0x7fff0000)
    assert context
    for family in (socket.AF_INET, socket.AF_INET6):
        assert lib.seccomp_rule_add_array(context, 0x50000 | 13, lib.seccomp_syscall_resolve_name(b'socket'), 1,
                                          ctypes.byref(Cmp(0, 4, family, 0))) == 0
    assert lib.seccomp_load(context) == 0


def fake_mcp(log):
    log = Path(log)
    with log.open('a') as stream:
        stream.write(json.dumps({'pid': os.getpid(), 'event': 'started', 'cwd': os.getcwd()}) + '\n')
    for line in sys.stdin:
        request = json.loads(line)
        with log.open('a') as stream:
            stream.write(json.dumps({'event': 'request', 'method': request.get('method')}) + '\n')
        if 'id' not in request:
            continue
        result = {}
        if request['method'] == 'initialize':
            result = {'protocolVersion': request['params']['protocolVersion'], 'capabilities': {'tools': {}},
                      'serverInfo': {'name': 'owned-offline', 'version': '1'}}
        elif request['method'] == 'tools/list':
            result = {'tools': [{'name': 'scene_summary', 'description': 'Read-only owned fixture',
                                  'inputSchema': {'type': 'object', 'properties': {}}}]}
        elif request['method'] == 'tools/call':
            result = {'content': [{'type': 'text', 'text': 'owned fixture result'}]}
        print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
    return 0


def read_events(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def process_rows():
    """Only stat identity/ancestry; command lines are read later for owned descendants."""
    rows = {}
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            try:
                text = (path / 'stat').read_text(); fields = text[text.rfind(')') + 2:].split()
                rows[int(path.name)] = {'pid': int(path.name), 'state': fields[0], 'parent': int(fields[1]), 'group': int(fields[2]),
                    'session': int(fields[3]), 'start': fields[19]}
            except (OSError, ValueError, IndexError):
                pass
    return rows


def descendants(root, rows):
    result = {root}
    changed = True
    while changed:
        changed = False
        for pid, row in rows.items():
            if row['parent'] in result and pid not in result:
                result.add(pid); changed = True
    return result


def owned_snapshot(root, start=None):
    rows = process_rows(); result = []
    if start is not None and root in rows and rows[root]['start'] != start:
        return []                         # the recorded session leader PID was reused
    pids = descendants(root, rows)
    if start is not None:
        # start_new_session creates this private session/group. A surviving
        # member keeps the kernel session ID allocated after leader exit, so
        # orphaned children remain attributable without a broad group signal.
        pids.update(pid for pid, row in rows.items() if row['session'] == root)
    for pid in pids:
        if pid not in rows:
            continue
        path = Path('/proc') / str(pid)
        try:
            result.append({**rows[pid], 'argv': (path / 'cmdline').read_bytes().decode(errors='replace').split('\0'),
                           'pid_namespace': os.readlink(path / 'ns/pid')})
        except OSError:
            pass
    return result


def enable_owned_reaping():
    """This standalone fixture adopts orphaned children; no host setting changes."""
    lib = ctypes.CDLL(None, use_errno=True)
    if lib.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER, this process only
        raise OSError(ctypes.get_errno(), 'owned fixture subreaper refused')


def reap_owned(owned, *, exclude):
    """Never consume asyncio's direct child or an unowned/reused/live PID."""
    rows = process_rows()
    for recorded in owned.values():
        pid = recorded['pid']; current = rows.get(pid)
        if (pid == exclude or not current or current['start'] != recorded['start'] or
                current.get('state') != 'Z' or current['parent'] != os.getpid()):
            continue
        try: os.waitpid(pid, os.WNOHANG)
        except ChildProcessError: pass


async def cleanup_acp(process, start, owned):
    """Reap the ACP parent and signal only live, identity-checked owned PIDs."""
    for sig, duration in [(signal.SIGTERM, 2), (signal.SIGKILL, 3)]:
        deadline = time.monotonic() + duration
        sent = set()
        while True:
            for row in owned_snapshot(process.pid, start):
                owned[(row['pid'], row['start'])] = row
            reap_owned(owned, exclude=process.pid)
            live = [row for row in owned.values() if still_alive(row)]
            for row in live:
                identity = (row['pid'], row['start'])
                if identity not in sent and still_alive(row):
                    try: os.kill(row['pid'], sig)
                    except ProcessLookupError: pass
                    sent.add(identity)
            if not live or time.monotonic() >= deadline:
                break
            await asyncio.sleep(0.02)
        if not any(still_alive(row) for row in owned.values()):
            break
    await asyncio.wait_for(process.wait(), 3)
    reap_owned(owned, exclude=process.pid)


def still_alive(row):
    current = process_rows().get(row['pid'])
    return current is not None and current['start'] == row['start']


class HTTPFixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
        if self.path == '/api/v1/mcp/pane':
            session = self.headers.get('X-Mixar-Session-Id')
            self.server.events.append({'path': self.path, 'binding': session, 'method': request.get('method')})
            if session != self.server.binding or self.headers.get('Authorization') != 'Bearer fixture-only':
                body = b'{"error":"owned fixture refuses foreign binding"}'
                self.send_response(403); self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            result = {}
            if request.get('method') == 'initialize':
                result = {'protocolVersion': request['params']['protocolVersion'], 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'owned-worker', 'version': '1'}}
            elif request.get('method') == 'tools/list':
                result = {'tools': [{'name': 'scene_summary', 'description': 'Owned scene',
                                      'inputSchema': {'type': 'object', 'properties': {}}}]}
            elif request.get('method') == 'tools/call':
                result = {'content': [{'type': 'text', 'text': session}]}
            response = {'jsonrpc': '2.0', 'id': request.get('id'), 'result': result}
            code = 200
        else:
            # A local rejecting model stand-in, never an account or provider endpoint.
            self.server.events.append({'path': self.path, 'persona_present': PERSONA in json.dumps(request)})
            if self.server.hold_model:
                self.server.events.append({'path': self.path, 'model_pending': True})
                end = time.monotonic() + 15
                while self.server.hold_model and time.monotonic() < end:
                    try:
                        if self.connection.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) == b'':
                            self.server.events.append({'path': self.path, 'model_cancelled': True})
                            return
                    except BlockingIOError:
                        pass
                    except ConnectionResetError:
                        self.server.events.append({'path': self.path, 'model_cancelled': True})
                        return
                    time.sleep(0.05)
            response = {'error': {'message': 'Owned fixture refuses model execution'}}; code = 503
        body = json.dumps(response).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)


class Validator:
    def __init__(self, options):
        self.options = options; self.output = options.output.resolve()
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.receipt = {'phase': options.phase, 'cases': [], 'commands': [], 'worker_ready': False,
                        'scope': 'Owned synthetic homes, offline fixture only; no accounts/model service or native user files.'}
        self.http = None

    def check(self, name, value, evidence=None):
        self.receipt['cases'].append({'name': name, 'passed': bool(value), 'evidence': evidence})
        self.save()
        assert value, name

    def save(self):
        (self.output / 'receipt.json').write_text(json.dumps(self.receipt, indent=2) + '\n')

    def run(self, argv, env=None, cwd=None, timeout=15):
        result = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        self.receipt['commands'].append({'argv': list(map(str, argv)), 'returncode': result.returncode,
                                        'stdout': result.stdout, 'stderr': result.stderr})
        self.save(); assert result.returncode == 0, result.stderr
        return result.stdout

    def make_fixture(self):
        home = self.output / 'home'; gh = home / '.grok'; gh.mkdir(parents=True)
        cwd = self.output / 'project'; cwd.mkdir()
        root = self.output / 'state'; pane = root / 'panes' / 'one'; pane.mkdir(parents=True, mode=0o700)
        auth = gh / 'auth.json'; auth.write_text('{}\n'); auth.chmod(0o600)
        persona = gh / 'original-agent.md'; persona.write_text(
            '---\nname: original-user-agent\ndescription: Owned persona fixture\npromptMode: full\n---\n' + PERSONA + '\n')
        connector = self.output / 'lampway-pane-mcp'
        if self.options.phase == 'loopback':
            connector = Path(sys.executable).with_name('lampway-pane-mcp')
            self.check('installed public pane helper', connector.is_file() and os.access(connector, os.X_OK))
        else:
            connector.write_text('#!' + sys.executable + '\nimport os\nos.execv(' + repr(sys.executable) + ', [' +
                                 repr(sys.executable) + ',' + repr(str(Path(__file__).resolve())) + ',"--fake-mcp",' +
                                 repr(str(self.output / 'owned-connector.jsonl')) + '])\n')
        if self.options.phase == 'stdio':
            connector.chmod(0o755)
        self.connector = connector
        port = self.http.server_port if self.http else 9
        native_config = ('[agent]\ndefinition=' + json.dumps(str(persona)) + '\n[models]\ndefault="fixture"\n'
                         '[model.fixture]\nname="Offline fixture"\nmodel="fixture"\nbase_url="http://127.0.0.1:' + str(port) +
                         '/v1"\napi_key="synthetic-offline-only"\n')
        # A pre-existing enabled toy user plugin: native discovery separates
        # user-scope trust from activation. Baseline must prove initialization.
        native_config += '\n[plugins]\nenabled=["owned-sentinel"]\n'
        for name in ['foreign_user', 'lampway_pane', 'foreign_same_command']:
            command = str(connector) if name != 'foreign_user' else sys.executable
            args = [] if name != 'foreign_user' else [str(Path(__file__).resolve()), '--fake-mcp', str(self.output / 'foreign-user.jsonl')]
            native_config += '\n[mcp_servers.' + name + ']\ncommand=' + json.dumps(command) + '\nargs=' + json.dumps(args) + '\nenabled=true\n'
        (gh / 'config.toml').write_text(native_config); (gh / 'config.toml').chmod(0o600)
        for name in ['requirements.toml', 'managed_config.toml']:
            policy = gh / name
            policy.write_text('# Original synthetic native policy cache; no grants.\n'); policy.chmod(0o600)
        # A compat sentinel is a native source, never silently disabled through env.
        (home / '.claude.json').write_text(json.dumps({'mcpServers': {'foreign_compat': {
            'command': sys.executable, 'args': [str(Path(__file__).resolve()), '--fake-mcp', str(self.output / 'foreign-compat.jsonl')]}}}))
        # User-scope trust is native; activation is the explicit synthetic
        # preference above. No trust command, grant or marketplace is used.
        plugin = gh / 'plugins' / 'owned-sentinel'
        (plugin / '.grok-plugin').mkdir(parents=True)
        (plugin / '.grok-plugin' / 'plugin.json').write_text(json.dumps({'name': 'owned-sentinel'}))
        (plugin / '.mcp.json').write_text(json.dumps({'mcpServers': {'foreign_plugin': {
            'command': sys.executable, 'args': [str(Path(__file__).resolve()), '--fake-mcp', str(self.output / 'foreign-plugin.jsonl')]}}}))
        env = {key: value for key, value in os.environ.items() if key in ['PATH', 'LANG', 'LD_LIBRARY_PATH', 'PYTHONPATH']}
        env.update(HOME=str(home), GROK_HOME=str(gh), GROK_AUTH_PATH=str(auth), TERM='xterm-256color',
                   LAMPWAY_HERMES_CONNECTOR_CONFIG=str(pane / 'mcp.json'), LAMPWAY_HERMES_CONNECTOR_ROOT=str(root))
        binding = 'swarm:owned:one'
        direct = {'url': 'http://127.0.0.1:' + str(port) + '/api/v1/mcp/pane',
                  'headers': {'Authorization': 'Bearer fixture-only', 'X-Mixar-Session-Id': binding}}
        (pane / 'mcp.json').write_text(json.dumps({'version': 1, 'binding': binding, 'desktop': None, 'direct': [direct]}))
        (pane / 'mcp.json').chmod(0o600)
        attack_root = self.output / 'foreign-state'
        attack_pane = attack_root / 'panes' / 'other'; attack_pane.mkdir(parents=True, mode=0o700)
        attack_binding = 'swarm:foreign:other'
        attack_direct = {**direct, 'headers': {**direct['headers'], 'X-Mixar-Session-Id': attack_binding}}
        attack_config = attack_pane / 'mcp.json'
        attack_config.write_text(json.dumps({'version': 1, 'binding': attack_binding, 'desktop': None, 'direct': [attack_direct]}))
        attack_config.chmod(0o600)
        self.attack_env = [{'name': 'LAMPWAY_HERMES_CONNECTOR_CONFIG', 'value': str(attack_config)},
                           {'name': 'LAMPWAY_HERMES_CONNECTOR_ROOT', 'value': str(attack_root)}]
        config = {'version': 1, 'root': str(root), 'cwd': str(cwd), 'native': str(self.options.grok.resolve()),
                  'native_sha256': GROK_SHA256, 'bwrap': str(self.options.bwrap.resolve()),
                  'bwrap_sha256': digest(self.options.bwrap), 'connector': {'command': str(connector), 'args': [], 'sha256': digest(connector)},
                  'inner_socket': str(pane / 'inner.sock'), 'outer_socket': str(pane / 'outer.sock'),
                  'task': 'synthetic_no_data_probe'}
        path = pane / 'grok-worker.json'; path.write_text(json.dumps(config)); path.chmod(0o600)
        self.receipt['synthetic_inputs'] = {str(p): file_state(p) for p in
            [auth, persona, gh / 'config.toml', gh / 'requirements.toml', gh / 'managed_config.toml',
             home / '.claude.json', plugin / '.mcp.json', plugin / '.grok-plugin' / 'plugin.json', connector,
             gh / 'trusted_folders.toml', gh / 'trusted-plugins']}
        return path, env, cwd, config

    async def acp(self, argv, env, cwd, label, *, expect_owned=True):
        stderr = (self.output / (label + '-stderr.log')).open('wb')
        process = await asyncio.create_subprocess_exec(*argv, env=env, cwd=cwd, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=stderr, start_new_session=True)
        self.receipt['commands'].append({'argv': argv, 'label': label, 'pid': process.pid}); self.save()
        sequence = 0; traffic = []; owned = {}
        start = process_rows().get(process.pid, {}).get('start')
        if start is None:
            # This can happen for an immediate native exit. Session membership
            # remains exact; a live leader is still required to validate reuse.
            start = 'exited-before-first-snapshot'
        def capture():
            for row in owned_snapshot(process.pid, start):
                owned[(row['pid'], row['start'])] = row
        async def monitor():
            while True:
                capture()
                await asyncio.sleep(0.01)
        capture()
        watcher = asyncio.create_task(monitor())
        async def read_frame(deadline):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError("native ACP original twenty-second deadline expired")
            line = await asyncio.wait_for(process.stdout.readline(), remaining)
            if not line:
                raise RuntimeError("native ACP ended before reply")
            capture()
            value = json.loads(line); traffic.append(value)
            return value

        async def request(method, params, *, deadline=None):
            nonlocal sequence
            if deadline is None:
                deadline = asyncio.get_running_loop().time() + 20
            sequence += 1; rid = sequence
            capture()
            if deadline <= asyncio.get_running_loop().time():
                raise asyncio.TimeoutError("native ACP original twenty-second deadline expired before write")
            process.stdin.write((json.dumps({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params}) + '\n').encode())
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError("native ACP original twenty-second deadline expired before drain")
            await asyncio.wait_for(process.stdin.drain(), remaining)
            while True:
                value = await read_frame(deadline)
                if value.get('id') == rid: return value
        try:
            await request('initialize', {'protocolVersion': 1, 'clientCapabilities': {},
                                        'clientInfo': {'name': 'owned-offline-fixture', 'version': '1'}})
            session = await request('session/new', {'cwd': str(cwd), 'mcpServers': []})
            sid = session['result']['sessionId']
            # Native session startup initializes the pool asynchronously. Discovery
            # alone is not readiness. Completion and the first call share the
            # original twenty-second call deadline; no sleep/retry/fallback.
            owned_deadline = asyncio.get_running_loop().time() + 20
            def completion():
                return next((frame for frame in traffic if
                    frame.get('method') == '_x.ai/mcp_initialized' and
                    isinstance(frame.get('params'), dict) and frame['params'].get('sessionId') == sid and
                    type(frame['params'].get('mcpToolCount')) is int and frame['params']['mcpToolCount'] >= 0), None)
            while completion() is None:
                await read_frame(owned_deadline)
            self.receipt.setdefault('native_mcp_readiness', []).append({
                'label': label, 'sessionId': sid, 'completion': completion(),
                'deadline_seconds': 20, 'remaining_seconds': max(0, owned_deadline - asyncio.get_running_loop().time()),
                'same_session_server_status': [frame for frame in traffic if
                    frame.get('method') == '_x.ai/mcp/server_status' and
                    isinstance(frame.get('params'), dict) and frame['params'].get('sessionId') == sid]})
            self.save()
            # Unknown/failed canonical servers still fail the original call;
            # completion is not an assertion that its handshake succeeded.
            result = await request('_x.ai/mcp/call', {'sessionId': sid, 'server': 'lampway_pane',
                                                   'tool': 'scene_summary', 'arguments': {}}, deadline=owned_deadline)
            if not expect_owned:
                self.check(label + ' original native policy denies owned connector', 'error' in result, result)
                return
            self.check(label + ' owned native MCP call', 'error' not in result, result)
            if label in ['baseline', 'restricted']:
                alias = await request('_x.ai/mcp/call', {'sessionId': sid, 'server': 'foreign_same_command',
                    'tool': 'scene_summary', 'arguments': {}})
                self.check(label + ' correct argv wrong name ' + ('positive control' if label == 'baseline' else 'refused'),
                           ('error' not in alias) if label == 'baseline' else ('error' in alias), alias)
            if self.http and label in ['baseline', 'restricted']:
                connector = self.connector
                update = await request('_x.ai/session/update_mcp_servers', {'sessionId': sid, 'mcpServers': [{
                    'name': 'lampway_pane', 'command': str(connector), 'args': [], 'env': self.attack_env}]})
                self.check(label + ' same-command native env override accepted for test', 'error' not in update, update)
                attack_offset = len(self.http.events)
                changed = await request('_x.ai/mcp/call', {'sessionId': sid, 'server': 'lampway_pane',
                    'tool': 'scene_summary', 'arguments': {}})
                events = self.http.events[attack_offset:]
                if label == 'baseline':
                    self.check('baseline same-command env really reaches foreign binding',
                        any(e.get('binding') == 'swarm:foreign:other' for e in events), events)
                else:
                    self.check('private executable bind defeats same-command env rebinding',
                        'error' not in changed and 'swarm:owned:one' in json.dumps(changed) and
                        not any(e.get('binding') == 'swarm:foreign:other' for e in events), changed)
            if label == 'restricted' and self.http:
                self.check('full helper worker binding', 'swarm:owned:one' in json.dumps(result))
                config_path = Path(env['LAMPWAY_HERMES_CONNECTOR_CONFIG'])
                binding = json.loads(config_path.read_text())
                binding['binding'] = 'swarm:owned:two'
                binding['direct'][0]['headers']['X-Mixar-Session-Id'] = binding['binding']
                self.http.binding = binding['binding']
                config_path.write_text(json.dumps(binding))
                changed = await request('_x.ai/mcp/call', {'sessionId': sid, 'server': 'lampway_pane',
                    'tool': 'scene_summary', 'arguments': {}})
                self.check('native call follows live worker rebind', 'error' not in changed and 'swarm:owned:two' in json.dumps(changed), changed)
                binding['binding'] = ''
                config_path.write_text(json.dumps(binding))
                unbound = await request('_x.ai/mcp/call', {'sessionId': sid, 'server': 'lampway_pane',
                    'tool': 'scene_summary', 'arguments': {}})
                self.check('native call refuses unbound helper', 'error' in unbound or 'isError": true' in json.dumps(unbound), unbound)
                binding['binding'] = 'swarm:owned:one'
                binding['direct'][0]['headers']['X-Mixar-Session-Id'] = binding['binding']
                self.http.binding = binding['binding']; config_path.write_text(json.dumps(binding))
            if label == 'restricted':
                before = await request('_x.ai/mcp/list', {'sessionId': sid, 'cache': False})
                self.check('exactly one canonical worker MCP server',
                    [row.get('name') for row in before.get('result', {}).get('servers', [])] == ['lampway_pane'], before)
                self.check('catalogue excludes inherited foreign servers', 'error' not in before and
                    not any(name in json.dumps(before) for name in ['foreign_user', 'foreign_compat', 'foreign_plugin']), before)
                injected = [{'name': name, 'command': sys.executable, 'args': [str(Path(__file__).resolve()),
                    '--fake-mcp', str(self.output / ('foreign-' + name + '.jsonl'))], 'env': []}
                    for name in ['dynamic', 'lampway_pane']]
                updated = await request('_x.ai/session/update_mcp_servers', {'sessionId': sid, 'mcpServers': injected})
                self.check('native hot reload replied', 'error' not in updated, updated)
                # Force lazy initialization after the swap; a rejected route alone
                # is not proof that the foreign subprocess was never started.
                after = await request('_x.ai/mcp/list', {'sessionId': sid, 'cache': False})
                self.check('hot reload excludes new foreign identity', 'error' not in after and 'dynamic' not in json.dumps(after), after)
                self.check('hot reload retains exactly one canonical MCP server',
                    [row.get('name') for row in after.get('result', {}).get('servers', [])] == ['lampway_pane'], after)
                self.check('same-name foreign argv blocked before initialization',
                    not read_events(self.output / 'foreign-lampway_pane.jsonl'))
                self.check('hot reload foreign subprocess blocked before initialization',
                    not read_events(self.output / 'foreign-dynamic.jsonl'))
            capture()
        finally:
            watcher.cancel()
            try: await watcher
            except asyncio.CancelledError: pass
            try:
                capture()
                await cleanup_acp(process, start, owned)
            finally:
                stderr.close()
            (self.output / (label + '-traffic.json')).write_text(json.dumps(traffic, indent=2) + '\n')
            deadline = time.monotonic() + 5
            while any(still_alive(row) for row in owned.values()) and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            self.check(label + ' owned ACP cleanup', not any(still_alive(row) for row in owned.values()), list(owned.values()))

    def validate(self):
        from lampway_server import grok_worker as G
        self.check('exact native artifact', digest(self.options.grok) == GROK_SHA256)
        self.receipt['runner'] = {'uid': os.getuid(), 'gid': os.getgid(), 'uname': list(os.uname()),
                                  'image': os.getenv('ImageVersion'), 'bwrap_sha256': digest(self.options.bwrap)}
        self.check('unprivileged runner', os.getuid() != 0)
        self.run([str(self.options.bwrap), '--unshare-user', '--uid', str(os.getuid()), '--gid', str(os.getgid()),
                  '--cap-drop', 'ALL', '--bind', '/', '/', '--dev', '/dev', '--die-with-parent', '--', '/bin/true'])
        if self.options.phase == 'stdio':
            deny_inet()
            try:
                socket.socket(socket.AF_INET)
                self.check('INET denied', False)
            except PermissionError: self.check('INET denied', True)
        else:
            self.check('network namespace has only loopback', {name for _, name in socket.if_nameindex()} == {'lo'})
            probe = socket.socket(); probe.settimeout(1)
            try:
                probe.connect(('198.18.0.1', 9)); self.check('external route refused', False)
            except OSError: self.check('external route refused', True)
            finally: probe.close()
            self.http = ThreadingHTTPServer(('127.0.0.1', 0), HTTPFixture)
            self.http.events = []; self.http.binding = 'swarm:owned:one'; self.http.hold_model = False
            threading.Thread(target=self.http.serve_forever, daemon=True).start()
        path, env, cwd, config = self.make_fixture()
        self.receipt['versions'] = {'grok': self.run([str(self.options.grok), '--version'], env=env, cwd=cwd),
                                   'bwrap': self.run([str(self.options.bwrap), '--version'], env=env, cwd=cwd)}
        repo = Path(__file__).resolve().parents[2]
        self.receipt['head'] = self.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], env=env, cwd=cwd).strip()
        self.receipt['sources'] = {str(p.relative_to(repo)): digest(p) for p in [
            repo / 'server/lampway_server/grok_worker.py', repo / 'server/lampway_server/pane_mcp.py',
            repo / 'server/lampway_server/herdr/harnesses/grok.py',
            repo / 'server/lampway_server/native_worker_readiness.py',
            repo / 'server/lampway_server/herdr/host.py', Path(__file__).resolve()]}
        self.receipt['source_research_qualification'] = 'Native 1.0.46 artifact is hash-pinned; earlier read-only 1.0.45 source research is not native proof.'
        baseline = [str(self.options.grok), 'agent', '--no-leader', 'stdio']
        asyncio.run(self.acp(baseline, env, cwd, 'baseline'))
        for source in ['user', 'compat', 'plugin']:
            self.check('baseline foreign ' + source + ' source really initialized',
                       any(e.get('method') == 'initialize' for e in read_events(self.output / ('foreign-' + source + '.jsonl'))))
        # Warmed vendor configuration, auth and persona are the comparison baseline.
        warmed = {p: file_state(p) for p in self.receipt['synthetic_inputs']}
        untouched = [Path(env['GROK_AUTH_PATH']), Path(env['GROK_HOME']) / 'original-agent.md']
        self.check('native baseline preserves original auth and persona',
                   all(warmed[str(p)] == self.receipt['synthetic_inputs'][str(p)] for p in untouched))
        self.receipt['native_baseline_side_effects'] = {p: {'initial': initial, 'warmed': warmed[p]}
            for p, initial in self.receipt['synthetic_inputs'].items() if initial != warmed[p]}
        self.receipt['preservation_qualification'] = 'Compare warmed native baseline; vendor first-start cache changes are separately recorded.'
        self.save()
        for log in self.output.glob('foreign-*.jsonl'): log.rename(log.with_suffix('.baseline.jsonl'))
        plan = G.build_plan(path); G.prepare(plan)
        split = plan['argv'].index('--')
        policy = Path(plan['policy_path'])
        # A writable alternate pathname would defeat a read-only /etc bind.
        # Both the source directory and private /proc are therefore bounded.
        protected_probe = ('import os,errno; p=' + repr(str(policy)) + '\n'
                           'try: os.chmod(p, 0o600)\n'
                           'except OSError as e: assert e.errno in (errno.EROFS,errno.EPERM,errno.EACCES)\n'
                           'else: raise AssertionError("alternate policy source became writable")\n')
        self.run(plan['argv'][:split + 1] + [sys.executable, '-I', '-c', protected_probe], env=env, cwd=cwd)
        self.check('alternate policy path cannot become writable', policy.read_text() == plan['policy'])
        boundary = plan['argv'][:split + 1]
        if self.options.phase == 'stdio':
            # This phase proves native policy against a stdio stand-in only.
            # The production shim invokes the HTTP helper and cannot operate
            # under all-INET denial. It is executed unchanged in loopback phase.
            shim_index = boundary.index(plan['shim'])
            del boundary[shim_index - 1:shim_index + 2]
            self.receipt['stdio_qualification'] = 'Policy-only ACP probe; fake stdio connector, no production shim/helper claim.'
        restricted = boundary + [config['native'], 'agent', '--no-leader', 'stdio']
        asyncio.run(self.acp(restricted, env, cwd, 'restricted'))
        self.check('foreign user blocked before initialization', not read_events(self.output / 'foreign-user.jsonl'))
        self.check('foreign compat blocked before initialization', not read_events(self.output / 'foreign-compat.jsonl'))
        self.check('trusted user plugin blocked before initialization', not read_events(self.output / 'foreign-plugin.jsonl'))
        self.check('warmed original persona/auth/config/policy preserved', warmed == {p: file_state(p) for p in warmed})
        if self.options.phase == 'loopback':
            self.native_panes(path, env, cwd, config)
            self.check('warmed native settings/policy unchanged by wrap chain', warmed == {p: file_state(p) for p in warmed})
        # Project MCP must have a positive native control. A folder-trust refusal
        # is reported as failed proof; this validator never grants native trust.
        project_config = cwd / '.mcp.json'
        project_config.write_text(json.dumps({'mcpServers': {'foreign_project': {
            'command': sys.executable, 'args': [str(Path(__file__).resolve()), '--fake-mcp',
                                             str(self.output / 'foreign-project.jsonl')]}}}))
        asyncio.run(self.acp(baseline, env, cwd, 'project-baseline'))
        self.check('project source positive native control (no trust workaround)',
            any(e.get('method') == 'initialize' for e in read_events(self.output / 'foreign-project.jsonl')))
        (self.output / 'foreign-project.jsonl').rename(self.output / 'foreign-project.baseline.jsonl')
        asyncio.run(self.acp(restricted, env, cwd, 'project-restricted'))
        self.check('project foreign source blocked before initialization', not read_events(self.output / 'foreign-project.jsonl'))
        # Original native config is itself a policy layer. It must still be able
        # to deny our otherwise-admitted connector; the added requirement grants
        # nothing beyond that original intersection. Only this owned fixture is
        # changed, and its original bytes are restored afterward.
        native_config = Path(env['GROK_HOME']) / 'config.toml'
        original_config = native_config.read_bytes()
        denied = '[[denied_mcp_servers]]\nserver_command = ' + json.dumps([config['connector']['command']]) + '\n'
        native_config.write_bytes(denied.encode() + original_config)
        before_negative = file_state(native_config)
        offset = len(self.http.events) if self.http else 0
        log = self.output / 'owned-connector.jsonl'
        if log.exists(): log.rename(self.output / 'owned-connector.before-negative.jsonl')
        try:
            asyncio.run(self.acp(baseline, env, cwd, 'original-denial-baseline', expect_owned=False))
            asyncio.run(self.acp(restricted, env, cwd, 'original-denial-restricted', expect_owned=False))
            self.check('original native deny intersection unchanged', before_negative == file_state(native_config))
            self.check('original deny prevents owned connector initialization',
                not read_events(log) and (not self.http or
                    not any(e.get('path') == '/api/v1/mcp/pane' for e in self.http.events[offset:])))
        finally:
            native_config.write_bytes(original_config)
        self.receipt['acceptance_scope'] = ('Native ACP policy controls only' if self.options.phase == 'stdio'
                                          else 'Native policy, helper, herdr wrap/leader and owned lifecycle fixture')
        self.receipt['completed'] = True
        self.save()

    def native_panes(self, path, env, cwd, config):
        """Real pinned herdr; the production wrapper argv, never an executable override.

        A namespace/provenance/detection failure is a failed case. Only this
        fixture instance admits the candidate; published readiness remains false.
        """
        from lampway_server.herdr import launcher as L, layout
        from lampway_server.herdr.harnesses.grok import Grok
        from lampway_server.herdr.harnesses.base import PaneSpec, DirectServer
        from lampway_server import grok_worker as G
        self.check('pinned herdr supplied', self.options.herdr is not None)
        self.receipt['versions']['herdr'] = self.run([str(self.options.herdr), '--version'])
        herdr_root = self.output / 'herdr'
        tools = self.output / 'native-bin'; tools.mkdir()
        (tools / 'grok').symlink_to(self.options.grok.resolve())
        (tools / 'bwrap').symlink_to(self.options.bwrap.resolve())
        old_env = dict(os.environ)
        os.environ.update(env)
        os.environ['PATH'] = str(tools) + os.pathsep + env['PATH']
        os.environ['LAMPWAY_HERDR_BIN'] = str(self.options.herdr.resolve())
        owned = {}
        def command(args):
            result = L.run(herdr_root, args, timeout=25)
            self.receipt['commands'].append({'herdr': args, 'result': result}); self.save()
            return result
        def snapshot():
            for row in owned_snapshot(L.server_info(herdr_root)['pid']):
                owned[row['pid']] = row
            return list(owned.values())
        def gone(rows, timeout=8):
            end = time.monotonic() + timeout
            while any(still_alive(r) for r in rows) and time.monotonic() < end:
                time.sleep(0.05)
            return not any(still_alive(r) for r in rows)
        panes = []
        try:
            candidate = G.candidate_paths(str(self.options.grok.resolve()))
            self.receipt['candidate_paths'] = candidate; self.save()
            self.check('production lookup pins native artifact',
                Path(candidate['native']).resolve() == self.options.grok.resolve() and
                digest(Path(candidate['native'])) == GROK_SHA256)
            self.check('production lookup pins ordinary namespace executable',
                Path(candidate['bwrap']).resolve() == self.options.bwrap.resolve() and
                digest(Path(candidate['bwrap'])) == config['bwrap_sha256'])
            self.check('production lookup pins installed helper',
                Path(candidate['connector']).resolve() == Path(config['connector']['command']).resolve() and
                digest(Path(candidate['connector'])) == config['connector']['sha256'])
            L.start_server(herdr_root, method='setsid')
            server_pid = L.server_info(herdr_root)['pid']
            self.receipt['herdr_identity'] = process_rows()[server_pid]; self.save()
            flags = [value for k, v in env.items() for value in ['--env', k + '=' + v]]
            flags += ['--env', 'PATH=' + os.environ['PATH']]
            for index, action in enumerate(['ctrl-c', 'hup-term', 'hard-close']):
                pane = layout.created_pane(command(layout.workspace_create(str(cwd), flags)))['pane_id']
                panes.append(pane)
                pane_dir = Path(config['root']) / 'panes' / pane
                pane_dir.mkdir(mode=0o700)
                original = json.loads(path.with_name('mcp.json').read_text())
                entry = original['direct'][0]
                spec = PaneSpec(cwd=str(cwd), desktop=False, scene_session_id=original['binding'],
                    mcp_config_path=str(pane_dir / 'mcp.json'), direct=(DirectServer('lampway', entry['url'],
                        entry['headers'], '', 'fixture-only'),))
                adapter = Grok()
                # This instance admits the candidate solely for acceptance testing.
                # Native list, strict preflight and the namespace probe remain real.
                adapter.worker_ok = True
                adapter.locate = lambda: str(self.options.grok.resolve())
                wiring = adapter.lampway_tools(spec)
                launch = adapter.launch(spec, 'synthetic_no_data_probe')
                for name, body in wiring.files.items():
                    target = Path(name); target.write_text(body); target.chmod(0o600)
                metadata = pane_dir / 'grok-worker.json'
                current = json.loads(metadata.read_text())
                native_args = launch[1:]
                self.check(action + ' production adapter launch consumed', launch[0] == 'grok' and
                    native_args == [*wiring.argv, '--task=synthetic_no_data_probe'] and
                    native_args[:4] == ['--leader-socket', current['outer_socket'], 'wrap', '--'],
                    {'argv': launch, 'candidate_instance_only': True, 'native_readiness_probe': 'real'})
                offset = len(self.http.events)
                self.http.hold_model = action == 'ctrl-c'
                command(['agent', 'start', 'owned-' + str(index), '--kind', 'grok', '--pane', pane,
                         '--timeout', '10000', '--', *native_args])
                end = time.monotonic() + 25
                observed = []
                while time.monotonic() < end:
                    observed = snapshot()
                    if (any(current['inner_socket'] in ' '.join(r['argv']) for r in observed)
                            and any(e.get('persona_present') for e in self.http.events[offset:])):
                        break
                    time.sleep(0.1)
                inner = [r for r in observed if r['argv'][0] and
                    Path(r['argv'][0]).resolve() == self.options.grok.resolve() and
                    current['inner_socket'] in ' '.join(r['argv'])]
                outer = [r for r in observed if str(metadata) in ' '.join(r['argv']) and 'wrap' in r['argv']]
                self.check(action + ' exact native wrap route observed', bool(outer), outer)
                self.check(action + ' separate inner leader namespace origin', bool(inner) and bool(outer) and
                    all(i['pid_namespace'] != o['pid_namespace'] for i in inner for o in outer), inner)
                self.check(action + ' original TUI persona and model route',
                    any(e.get('persona_present') for e in self.http.events[offset:]), self.http.events[offset:])
                self.check(action + ' actual native helper discovery',
                    any(e.get('method') == 'tools/list' for e in self.http.events[offset:]))
                info = json.loads(command(['pane', 'process-info', '--pane', pane]))['result']['process_info']
                agent = json.loads(command(['agent', 'get', 'owned-' + str(index)]))
                detected = agent.get('result', {}).get('agent', {})
                self.check(action + ' herdr detects native worker', detected.get('agent') == 'grok' and
                           detected.get('agent_status') in ['idle', 'working', 'blocked', 'done'], agent)
                self.receipt.setdefault('pane_witnesses', []).append({'action': action, 'pane': pane,
                    'process_info': info, 'inventory': observed, 'screen': command(['pane', 'read', pane]),
                    'agent': agent})
                self.save()
                inner_namespaces = {r['pid_namespace'] for r in inner}
                workers = [r for r in observed if r['pid_namespace'] in inner_namespaces or r in outer]
                if action == 'ctrl-c':
                    self.check('foreground interrupt has a pending owned request',
                        any(e.get('model_pending') for e in self.http.events[offset:]))
                    command(['pane', 'send-keys', pane, 'ctrl+c'])
                    end = time.monotonic() + 8
                    while time.monotonic() < end and not any(e.get('model_cancelled') for e in self.http.events[offset:]):
                        time.sleep(0.05)
                    self.check('CtrlC closes pending owned fixture request before pane close',
                        any(e.get('model_cancelled') for e in self.http.events[offset:]), self.http.events[offset:])
                    self.check('CtrlC retains native frontend after cancelling request', all(still_alive(row) for row in outer))
                    self.http.hold_model = False
                    self.check('foreground interrupt retains owned herdr server', still_alive(self.receipt['herdr_identity']))
                elif action == 'hup-term':
                    # Exact known outer native frontend identities only; no
                    # process-group signal can reach a different pane/server.
                    for sig in [signal.SIGHUP, signal.SIGTERM, signal.SIGTERM]:
                        for row in outer:
                            if still_alive(row):
                                try: os.kill(row['pid'], sig)
                                except ProcessLookupError: pass
                    self.check('HUP TERM alone cleans worker descendants before pane close', gone(workers), workers)
                command(['pane', 'close', pane]); panes.remove(pane)
                self.check(action + ' all owned worker descendants absent', gone(workers), workers)
                self.check(action + ' herdr survives worker cleanup', still_alive(self.receipt['herdr_identity']))
                for source in ['user', 'compat', 'plugin', 'dynamic', 'lampway_pane']:
                    self.check(action + ' no foreign ' + source + ' initialization',
                        not read_events(self.output / ('foreign-' + source + '.jsonl')))
        finally:
            for pane in panes:
                try: command(['pane', 'close', pane])
                except Exception as exc:
                    self.receipt.setdefault('cleanup_errors', []).append(str(exc))
            try:
                if L.server_info(herdr_root):
                    snapshot()
                    try: L.stop_server(herdr_root, confirmed=True)
                    finally:
                        self.check('owned herdr and descendants absent', gone(list(owned.values())), list(owned.values()))
            finally:
                os.environ.clear(); os.environ.update(old_env)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--fake-mcp':
        return fake_mcp(sys.argv[2])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grok', type=Path, required=True); parser.add_argument('--bwrap', type=Path, required=True)
    parser.add_argument('--herdr', type=Path)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--phase', choices=['stdio', 'loopback'], required=True)
    options = parser.parse_args(); validator = Validator(options)
    try:
        enable_owned_reaping()
        validator.validate()
    except Exception:
        validator.receipt['failure'] = traceback.format_exc(); validator.save()
        raise
    finally:
        if validator.http:
            validator.http.shutdown(); validator.http.server_close()
            validator.receipt['http_events'] = validator.http.events; validator.save()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
