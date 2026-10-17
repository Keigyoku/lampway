# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Context adoption and competing config writers preserve the same session."""
from types import SimpleNamespace
import threading
import os
from pathlib import Path


def test_context_and_refresh_share_a_reentrant_config_writer_lock():
    from lampway_server.engine import hermes_config as HC
    lock = getattr(HC, 'CONFIG_WRITER_LOCK', None)
    assert lock is not None, 'Context and Capabilities refresh currently have no common writer lock'
    acquired = threading.Event()
    def contender():
        with lock:
            acquired.set()
    with lock:
        with lock:  # nested rerender -> write_config -> HC.write is supported
            thread = threading.Thread(target=contender)
            thread.start()
            assert not acquired.wait(.05)
    thread.join(1)
    assert acquired.is_set()


def test_observed_native_window_comes_from_matching_live_link_only():
    from lampway_server.engine.context_settings import observed_window
    front = SimpleNamespace(links={'unit': SimpleNamespace(live_id='native-sid', context_max=262144)})
    app = SimpleNamespace(state=SimpleNamespace(engine_wiring=SimpleNamespace(front=front)))
    assert observed_window(app, [{'unit': 'unit'}]) == 262144
    assert observed_window(app, [{'unit': 'other'}]) is None
    front.links['unit'].live_id = ''
    assert observed_window(app, [{'unit': 'unit'}]) is None


def test_actual_pinned_compression_sync_adopts_saved_values_and_reset_without_rebuilding(tmp_path, monkeypatch):
    import ast
    import contextlib
    import logging
    import sys
    from pathlib import Path
    from lampway_server.engine import context_settings as CS, hermes_config as HC
    source = Path(os.environ.get('LAMPWAY_HERMES_SOURCE') or Path(__file__).resolve().parents[2] / 'third_party/hermes-agent')
    if not (source / 'tui_gateway/session_compression.py').exists():
        import pytest
        pytest.skip('Read-only pinned Hermes source unavailable')
    module = ast.parse((source / 'tui_gateway/session_compression.py').read_text())
    names = {'_compressor_ctor_default', '_default_threshold_tokens_cap', '_derived_default_threshold_percent',
             '_apply_live_compression_config', '_sync_agent_compression_with_config'}
    nodes = [n for n in module.body if isinstance(n, ast.FunctionDef) and n.name in names or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_COMPRESSION_INT_KEYS' for t in n.targets)]
    ctor = next(n for n in ast.walk(ast.parse((source / 'agent/context_compressor.py').read_text()))
                if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    defaults = dict(zip([a.arg for a in ctor.args.args][-len(ctor.args.defaults):],
                        [ast.literal_eval(d) for d in ctor.args.defaults]))
    def constructor(self, protect_last_n=20, threshold_percent=.5):
        pass
    assert defaults['protect_last_n'] == 20 and defaults['threshold_percent'] == .5
    compressor_module = SimpleNamespace(ContextCompressor=type('ContextCompressor', (), {'__init__': constructor}),
                                        resolve_model_threshold=lambda model, thresholds, pct, provider: pct)
    monkeypatch.setitem(sys.modules, 'agent.context_compressor', compressor_module)
    monkeypatch.setitem(sys.modules, 'agent.agent_init', SimpleNamespace(
        config_context_length_for_runtime=lambda agent, cfg: None, set_config_context_length=lambda *args: None))
    monkeypatch.setitem(sys.modules, 'hermes_cli.config_defaults', SimpleNamespace(DEFAULT_CONFIG={'compression': {'threshold_tokens': 256000}}))
    home = tmp_path / 'home'; home.mkdir()
    HC._write_private(home, 'config.yaml', HC.to_yaml({'model': {'default': 'lampway', 'api_key': 'owned-token'}}))
    store, project = CS.Store(tmp_path / 'state'), str(tmp_path / 'project')
    cc = SimpleNamespace(context_length=262144, _config_context_length=None,
                         _effective_threshold_percent=lambda window, base: max(.75, base),
                         _coerce_threshold_tokens_cap=lambda cap: cap)
    agent = SimpleNamespace(context_compressor=cc, model='lampway', provider='custom')
    history = [{'role': 'user', 'content': 'preserve me'}]
    session = {'agent': agent, 'history': history}
    scope = {'contextlib': contextlib, 'logger': logging.getLogger(__name__), 'is_truthy_value': bool,
             '_load_cfg': lambda: HC.read(home),
             '_tui_compression_config_signature': lambda cfg: tuple(sorted((cfg.get('compression') or {}).items()))}
    code = 'from __future__ import annotations\n' + '\n'.join(ast.unparse(n) for n in nodes)
    exec(compile(code, str(source / 'tui_gateway/session_compression.py'), 'exec'), scope)
    store.apply(project, {'compression_threshold': .9, 'protected_recent_turns': 7}, [], None, [{'home': str(home)}])
    scope['_sync_agent_compression_with_config']('same-native-sid', session)
    assert cc.threshold_percent == .9 and cc.protect_last_n == 7
    assert session['agent'] is agent and session['history'] is history
    store.apply(project, {}, ['compression_threshold', 'protected_recent_turns'], None, [{'home': str(home)}])
    scope['_sync_agent_compression_with_config']('same-native-sid', session)
    assert cc.threshold_percent == .75 and cc.protect_last_n == 20
    assert cc.threshold_tokens_cap == 256000
    assert HC.read(home)['model']['api_key'] == 'owned-token'


def test_native_status_snapshot_refuses_working_waiting_starting_and_closes_client(monkeypatch):
    import asyncio
    from lampway_server.engine import context_settings as CS, units as U
    calls, closed = [], []
    status = ['idle']
    class Client:
        async def call(self, method, params, timeout):
            calls.append((method, params))
            return {'sessions': [{'status': status[0]}]}
        async def close(self):
            closed.append(True)
    async def connect(info, **kw):
        assert kw == {'timeout': 2, 'server_requests': False}
        return Client()
    monkeypatch.setattr(U, 'connect_when_up', connect)
    app = SimpleNamespace(state=SimpleNamespace(engine_wiring=SimpleNamespace(units=SimpleNamespace(info=lambda rec: object()))))
    for value in ('idle', 'working', 'waiting', 'starting'):
        status[0] = value
        assert asyncio.run(CS.panes_busy(app, [{}])) is (value != 'idle')
    assert len(closed) == 4 and all(method == 'session.active_list' for method, _ in calls)


def test_context_read_replace_and_capabilities_rerender_cannot_interleave(tmp_path, monkeypatch):
    from lampway_server.engine import context_settings as CS, hermes_config as HC, units as U
    home = tmp_path / 'home'; home.mkdir()
    HC._write_private(home, 'config.yaml', HC.to_yaml({'model': {'api_key': 'keep', 'default': 'lampway'}}))
    store = CS.Store(tmp_path / 'state')
    project = str(tmp_path / 'project')
    entered, release, refreshed = threading.Event(), threading.Event(), threading.Event()
    original = HC._write_private
    def held_write(home, name, text):
        if threading.current_thread().name == 'context-save':
            entered.set()
            assert release.wait(2)
        return original(home, name, text)
    monkeypatch.setattr(HC, '_write_private', held_write)
    seen = []
    def render(home, *args, **kwargs):
        seen.append(store.config(project))
        refreshed.set()
    units = SimpleNamespace(write_config=render, gateway_url='loopback', model_id='lampway')
    rec = {'home': str(home), 'project_root': project}
    save = threading.Thread(name='context-save', target=lambda: store.apply(project, {'compression_threshold': .9}, [], None, [rec]))
    save.start(); assert entered.wait(1)
    refresh = threading.Thread(target=lambda: U.Mode1Units.rerender(units, rec))
    refresh.start()
    assert not refreshed.wait(.05), 'refresh must not read/write the config during Context replacement'
    release.set(); save.join(2); refresh.join(2)
    assert seen == [{'compression': {'threshold': .9}}]
    assert HC.read(home)['model']['api_key'] == 'keep'


def test_front_observes_native_window_without_account_usage_rpc():
    import asyncio
    from lampway_server.engine.front import HermesFront, Link
    front = HermesFront(SimpleNamespace(), SimpleNamespace())
    link = front.links['unit'] = Link('unit', live_id='same-native-sid')
    asyncio.run(front._on_event(link, {'type': 'session.info', 'session_id': 'other', 'payload': {'usage': {'context_max': 123}}}))
    assert link.context_max is None
    asyncio.run(front._on_event(link, {'type': 'session.info', 'session_id': 'same-native-sid', 'payload': {'usage': {'context_max': 262144}}}))
    assert link.context_max == 262144


def test_actual_pinned_auxiliary_config_read_adopts_named_summary_each_call(tmp_path, monkeypatch):
    import ast
    import sys
    from pathlib import Path
    from lampway_server.engine import context_settings as CS, hermes_config as HC
    source = Path(os.environ.get('LAMPWAY_HERMES_SOURCE') or Path(__file__).resolve().parents[2] / 'third_party/hermes-agent') / 'agent/auxiliary_client.py'
    if not source.exists():
        import pytest
        pytest.skip('Read-only pinned Hermes source unavailable')
    node = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == '_get_auxiliary_task_config')
    home = tmp_path / 'home'; home.mkdir()
    HC._write_private(home, 'config.yaml', HC.to_yaml({'model': {'default': 'lampway'}}))
    monkeypatch.setitem(sys.modules, 'hermes_cli.config', SimpleNamespace(load_config_readonly=lambda: HC.read(home)))
    monkeypatch.setitem(sys.modules, 'hermes_cli.plugins', SimpleNamespace(get_plugin_auxiliary_tasks=lambda: []))
    scope = {}
    exec(compile('from __future__ import annotations\n' + ast.unparse(node), str(source), 'exec'), scope)
    read = scope['_get_auxiliary_task_config']
    assert read('compression') == {}
    store = CS.Store(tmp_path / 'state'); project = str(tmp_path / 'project')
    selected = 'chatgpt_plan:gpt-6.1-sol'
    store.apply(project, {'summarizing_model': selected}, [], {'provider': 'chatgpt_plan', 'endpoint': ''}, [{'home': str(home)}])
    assert read('compression')['model'] == CS.summary_alias(selected)
    store.apply(project, {}, ['summarizing_model'], None, [{'home': str(home)}])
    assert read('compression') == {}
