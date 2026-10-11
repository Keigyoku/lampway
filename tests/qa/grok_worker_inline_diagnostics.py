#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent user-authored inline-profile diagnostic, never worker acceptance.

Run the original default-profile validator separately and retain its RED receipt.
This synthetic fixture adds no native-user configuration or selected-agent argv
replacement. It reuses the original restricted ACP and native pane assertions.
"""
import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import traceback

from grok_worker_transport_diagnostics import admission_gate, check_checkout

QA_SHA256 = 'f4907583260d28cb226466b471e81a7b2d27fc5b23d1cf98b3413dce253c756b'


def load_qa(repo):
    import hashlib
    path = repo / 'tests/qa/grok_worker_validation.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != QA_SHA256:
        raise ValueError('original validator changed; review diagnostic against exact original')
    spec = importlib.util.spec_from_file_location('original_grok_worker_qa', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def author_inline_profile(persona, connector):
    """Finish an owned synthetic fixture before its preservation baseline exists."""
    original = persona.read_text()
    opening, frontmatter, body = original.split('---\n', 2)
    if opening or 'mcpServers:' in frontmatter or not body.strip():
        raise ValueError('unexpected original synthetic profile')
    entry = {'lampway_pane': {'command': connector['command'], 'args': connector['args']}}
    persona.write_text('---\n' + frontmatter + 'mcpServers: ' + json.dumps([entry]) + '\n---\n' + body)
    return {'original_frontmatter': frontmatter, 'original_body': body, 'inline': entry}


def validator_type(qa):
    class InlineValidator(qa.Validator):
        def make_fixture(self):
            path, env, cwd, config = super().make_fixture()
            persona = Path(env['GROK_HOME']) / 'original-agent.md'
            authored = author_inline_profile(persona, config['connector'])
            self.receipt['inline_profile'] = {
                'path': str(persona), 'state': qa.file_state(persona),
                'auth_state': qa.file_state(Path(env['GROK_AUTH_PATH'])),
                'construction': authored,
                'selection': 'original native [agent] definition; no argv override',
                'scope': 'user-authored owned synthetic fixture only; not runtime config migration'}
            self.receipt['synthetic_inputs'][str(persona)] = qa.file_state(persona)
            self.receipt['acceptance'] = False
            self.receipt['acceptance_scope'] = 'independent inline subset diagnostic; original default-profile acceptance remains separate'
            self.save()
            return path, env, cwd, config

        def diagnose(self):
            from lampway_server import grok_worker as G
            self.check('exact native artifact', qa.digest(self.options.grok) == qa.GROK_SHA256)
            self.check('unprivileged runner', os.getuid() != 0)
            self.check('loopback-only namespace', {name for _, name in socket.if_nameindex()} == {'lo'})
            probe = socket.socket(); probe.settimeout(1)
            try:
                probe.connect(('198.18.0.1', 9)); self.check('external route refused', False)
            except OSError:
                self.check('external route refused', True)
            finally:
                probe.close()
            self.http = qa.ThreadingHTTPServer(('127.0.0.1', 0), qa.HTTPFixture)
            self.http.events = []; self.http.binding = 'swarm:owned:one'; self.http.hold_model = False
            threading.Thread(target=self.http.serve_forever, daemon=True).start()
            path, env, cwd, config = self.make_fixture()
            qa.enroll_compatibility_fixture(config)
            native = [str(self.options.grok), 'agent', '--no-leader', 'stdio']
            self.receipt['protected_artifacts'] = {str(p): qa.file_state(p) for p in [
                self.options.grok.resolve(), self.options.bwrap.resolve(), Path(config['connector']['command']),
                Path(qa.__file__), Path(G.__file__)]}
            self.receipt['versions'] = {
                'grok': self.run([str(self.options.grok), '--version'], env=env, cwd=cwd),
                'bwrap': self.run([str(self.options.bwrap), '--version'], env=env, cwd=cwd)}
            # An inline overlay defeats the original baseline's deliberate env
            # rebinding attack. Do not alter that assertion or call this warmup
            # the original baseline. Its independent default run stays required.
            self.receipt['stages'] = {'selected_inline_warmup': 'RUNNING', 'restricted_acp': 'NOT RUN',
                                      'native_panes': 'NOT RUN', 'native_policy_intersection': 'NOT RUN'}
            self.save()
            asyncio.run(self.acp(native, env, cwd, 'selected-inline-warmup'))
            self.receipt['stages']['selected_inline_warmup'] = 'PASS'
            for source in ['user', 'compat', 'plugin', 'cursor']:
                self.check('selected inline native foreign ' + source + ' positive control',
                    any(e.get('method') == 'initialize' for e in qa.read_events(self.output / ('foreign-' + source + '.jsonl'))))
            warmed = {p: qa.file_state(p) for p in self.receipt['synthetic_inputs']}
            untouched = [Path(env['GROK_AUTH_PATH']), Path(env['GROK_HOME']) / 'original-agent.md']
            self.check('selected native warmup preserves constructed auth and persona',
                all(warmed[str(p)] == self.receipt['synthetic_inputs'][str(p)] for p in untouched))
            self.receipt['native_baseline_side_effects'] = {p: {'initial': initial, 'warmed': warmed[p]}
                for p, initial in self.receipt['synthetic_inputs'].items() if initial != warmed[p]}
            for log in self.output.glob('foreign-*.jsonl'):
                log.rename(log.with_suffix('.baseline.jsonl'))
            with qa.fixture_environment(env):
                plan = G.build_plan(path)
                self.check('exact explicit compatibility environment',
                    qa.compatibility_environment(plan, selected=True) == {'GROK_CURSOR_MCPS_ENABLED': 'false'})
                view = qa.compatibility_view(config, env, plan)
                self.check('consented compatibility view exists', view is not None)
                G.prepare(plan)
            self.receipt['production_plan'] = {'argv': plan['argv'], 'policy': plan['policy'],
                                               'policy_path': plan['policy_path'], 'compat_view': view}
            self.check('exact read-only attribution sentinel',
                qa.file_state(Path(view['sentinel_path'])) == {'sha256': view['sentinel_sha256'], 'mode': 0o400})
            split = plan['argv'].index('--'); boundary = plan['argv'][:split + 1]
            policy = Path(plan['policy_path'])
            protected_probe = ('import os,errno; p=' + repr(str(policy)) + '\n'
                'try: os.chmod(p, 0o600)\n'
                'except OSError as e: assert e.errno in (errno.EROFS,errno.EPERM,errno.EACCES)\n'
                'else: raise AssertionError("alternate policy source became writable")\n')
            self.run(boundary + [sys.executable, '-I', '-c', protected_probe], env=env, cwd=cwd)
            self.check('alternate policy source remains immutable', policy.read_text() == plan['policy'])
            restricted = boundary + [config['native'], 'agent', '--no-leader', 'stdio']
            self.receipt['stages']['restricted_acp'] = 'RUNNING'; self.save()
            # Exactly the original function, label, assertions and deadlines.
            asyncio.run(self.acp(restricted, env, cwd, 'restricted'))
            self.receipt['stages']['restricted_acp'] = 'PASS'
            for source in ['user', 'compat', 'plugin', 'cursor']:
                self.check('restricted foreign ' + source + ' not initialized',
                    not qa.read_events(self.output / ('foreign-' + source + '.jsonl')))
            self.check('restricted preserves warmed inputs', warmed == {p: qa.file_state(p) for p in warmed})
            self.receipt['stages']['native_panes'] = 'RUNNING'; self.save()
            # Original method uses instance-only candidate admission. Global and
            # published adapter/readiness state are never changed by this driver.
            self.native_panes(path, env, cwd, config)
            self.receipt['stages']['native_panes'] = 'PASS'
            self.check('native pane chain preserves warmed inputs', warmed == {p: qa.file_state(p) for p in warmed})
            self.receipt['stages']['native_policy_intersection'] = 'RUNNING'; self.save()
            native_config = Path(env['GROK_HOME']) / 'config.toml'; original_config = native_config.read_bytes()
            denied = '[[denied_mcp_servers]]\nserver_command = ' + json.dumps([config['connector']['command']]) + '\n'
            native_config.write_bytes(denied.encode() + original_config)
            before_negative = qa.file_state(native_config); offset = len(self.http.events)
            try:
                asyncio.run(self.acp(native, env, cwd, 'original-denial-baseline', expect_owned=False))
                asyncio.run(self.acp(restricted, env, cwd, 'original-denial-restricted', expect_owned=False))
                self.check('original native deny intersection unchanged', before_negative == qa.file_state(native_config))
                self.check('original deny prevents helper initialization', not any(
                    e.get('path') == '/api/v1/mcp/pane' for e in self.http.events[offset:]))
            finally:
                native_config.write_bytes(original_config)
            self.receipt['stages']['native_policy_intersection'] = 'PASS'
            self.check('final warmed native state preserved', warmed == {p: qa.file_state(p) for p in warmed})
            self.receipt['completed'] = True
            self.check('native and production artifacts unchanged', self.receipt['protected_artifacts'] ==
                {p: qa.file_state(Path(p)) for p in self.receipt['protected_artifacts']})
            self.receipt['worker_ready'] = False
            self.receipt['limitations'] = ['Not original default-profile acceptance',
                'No active-agent CLI attestation established', 'No live profile switch/load/SDK/rebuild qualification',
                'Project MCP trust-positive control remains the original validator obligation']
            self.save()
    return InlineValidator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True); parser.add_argument('--head', required=True)
    parser.add_argument('--grok', type=Path, required=True); parser.add_argument('--bwrap', type=Path, required=True)
    parser.add_argument('--herdr', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args(); options.repo = options.repo.resolve()
    admission_gate(options.head)
    options.repo = check_checkout(options.repo, options.head)
    actual = options.head
    options.phase = 'loopback'; options.compatibility_layer = True; options.cursor_fixture = 'present'
    qa = load_qa(options.repo)
    sys.path.insert(0, str(options.repo / 'server'))
    validator = validator_type(qa)(options)
    validator.receipt['head'] = actual; validator.receipt['original_qa_sha256'] = QA_SHA256
    validator.receipt['diagnostic_driver_sha256'] = qa.digest(Path(__file__))
    try:
        qa.enable_owned_reaping(); validator.diagnose()
    except Exception:
        validator.receipt['failure'] = traceback.format_exc(); validator.save(); raise
    finally:
        if validator.http:
            validator.http.shutdown(); validator.http.server_close()
            validator.receipt['http_events'] = validator.http.events
        validator.receipt['worker_ready'] = False
        validator.receipt['acceptance'] = False
        if 'protected_artifacts' in validator.receipt:
            validator.receipt['protected_artifacts_after'] = {p: qa.file_state(Path(p))
                for p in validator.receipt['protected_artifacts']}
        validator.receipt['source_head_after'] = subprocess.check_output(['git', '-C', str(options.repo), 'rev-parse', 'HEAD'], text=True).strip()
        validator.receipt['source_status_after'] = subprocess.check_output(['git', '-C', str(options.repo), 'status', '--porcelain'], text=True)
        validator.save()
        check_checkout(options.repo, options.head)
        if qa.digest(options.grok) != qa.GROK_SHA256 or qa.digest(Path(qa.__file__)) != QA_SHA256:
            validator.receipt['final_guard_failure'] = 'native or original QA fingerprint changed'
            validator.save()
            raise ValueError(validator.receipt['final_guard_failure'])


if __name__ == '__main__':
    main()
