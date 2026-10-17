# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import os
import socket
import subprocess
from pathlib import Path

import pytest
import yaml
from lampway_server import capabilities as CAP
from lampway_server.engine import context_settings as CS, hermes_config as HC, units as U


@pytest.fixture(autouse=True)
def no_native(monkeypatch, tmp_path):
    def refuse(*a, **kw):
        raise AssertionError('No process, socket or signal in YAML controls')
    for name in ('Popen', 'run', 'call', 'check_output', 'check_call'):
        monkeypatch.setattr(subprocess, name, refuse)
    for name in ('connect', 'connect_ex', 'bind', 'listen'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(os, 'kill', refuse)
    monkeypatch.setattr(os, 'system', refuse)
    monkeypatch.setenv('HOME', str(tmp_path / 'synthetic-home'))


def native_config():
    return {'model': {'provider': 'custom', 'base_url': 'http://127.0.0.1:8799/engine/v1',
                     'api_key': 'synthetic-token', 'default': 'fixture-model'},
            'mcp_servers': {'lampway': {'url': 'http://127.0.0.1:8799/engine/mcp/unit',
                                      'headers': {'Authorization': 'Bearer synthetic-binding'}}},
            'display': {'personality': 'concise', 'show_thinking': False},
            'personalities': {'custom': {'prompt': 'First line\nSecond line\n', 'tags': ['brief', 'safe']}},
            'compression': {'threshold': .82, 'protect_last_n': 4},
            'lampway_features': {'subagents': False, 'schedule': False, 'background': False}}


def native_home(tmp_path):
    home = tmp_path / 'owned'; home.mkdir()
    # Native-compatible block lists and bare scalars, plus a literal multiline scalar.
    text = yaml.safe_dump(native_config(), sort_keys=False)
    text += 'native_note: |\n  First line\n  Second line\n'
    (home / 'config.yaml').write_text(text)
    return home


def test_native_yaml_readback(tmp_path):
    cfg = HC.read(native_home(tmp_path))
    assert cfg['display']['personality'] == 'concise'
    assert cfg['personalities']['custom']['tags'] == ['brief', 'safe']
    assert cfg['native_note'] == 'First line\nSecond line\n'
    assert cfg['model']['api_key'] == 'synthetic-token'


def test_context_save_and_reset_keep_native_config(tmp_path):
    home = native_home(tmp_path); project = str(tmp_path / 'project')
    store = CS.Store(tmp_path / 'state')
    for values, reset in [({'compression_threshold': .9, 'protected_recent_turns': 6}, []),
                          ({}, ['compression_threshold', 'protected_recent_turns'])]:
        store.apply(project, values, reset, None, [{'home': str(home)}])
        cfg = HC.read(home)
        assert cfg['display'] == native_config()['display']
        assert cfg['personalities'] == native_config()['personalities']
        assert cfg['model'] == native_config()['model']
        assert cfg['mcp_servers'] == native_config()['mcp_servers']
    assert 'compression' not in cfg


def test_capability_rerender_retains_native_selection_without_authority(tmp_path):
    home = native_home(tmp_path); board = CAP.Store(tmp_path / 'board')
    # Make the source baseline parseable so preservation failure is independent of the parser.
    HC._write_private(home, 'config.yaml', HC.to_yaml(native_config()))
    def writer(home, base, token, model, rendered, **kw):
        kw.pop('worker', None)
        return HC.write(home, board, kw.pop('project'), base, token, model, rendered=rendered, **kw)
    units = object.__new__(U.Mode1Units)
    units.write_config = writer; units.base = 'http://127.0.0.1:8799'; units.model_id = 'fixture-model'
    assert units.rerender({'home': str(home), 'project_root': str(tmp_path / 'project'), 'id': 'owned'})
    cfg = HC.read(home)
    assert cfg['display'] == native_config()['display']
    assert cfg['personalities'] == native_config()['personalities']
    assert cfg['model']['api_key'] == 'synthetic-token'
    assert cfg['mcp_servers'] == native_config()['mcp_servers']
    assert cfg['lampway_features'] == dict(subagents=False, schedule=False, background=False)
    assert 'terminal' in cfg['agent']['disabled_toolsets']
    assert 'compression' not in cfg  # stale overrides do not return on reset/rerender


@pytest.mark.parametrize('text', ['[]', 'null', 'bare', '!!python/object/apply:os.system [echo forbidden]',
    'lampway_features: {subagents: 1}', 'lampway_features: {unknown: false}',
    'lampway_features: []', 'root: &root {self: *root}', 'date: 2026-10-10', '1: value'])
def test_invalid_retained_yaml_refuses_before_context_writes(tmp_path, text):
    home = tmp_path / 'owned'; home.mkdir(); path = home / 'config.yaml'; path.write_text(text)
    store = CS.Store(tmp_path / 'state')
    with pytest.raises(ValueError):
        store.apply(str(tmp_path / 'project'), {'compression_threshold': .9}, [], None, [{'home': str(home)}])
    assert path.read_text() == text and not store.path.exists()


def test_existing_json_subset_roundtrip():
    cfg = {'a': {}, 'b': [], 'c': [{'x': [1, 2.5, None]}], 'd': -1.5e-07, 'e': 'on'}
    assert HC.from_yaml(HC.to_yaml(cfg)) == cfg



@pytest.mark.parametrize('bad', [{'lampway_features': {'background': 1}}, {'display': []}])
def test_rebuild_refuses_malformed_retained_policy_without_overwrite(tmp_path, bad):
    home = tmp_path / 'owned'; home.mkdir()
    original = HC.to_yaml({**native_config(), **bad})
    (home / 'config.yaml').write_text(original)
    board = CAP.Store(tmp_path / 'board')
    with pytest.raises(ValueError):
        HC.write(home, board, str(tmp_path / 'project'), 'http://127.0.0.1:8799/engine/v1', 'new-token', 'new-model')
    assert (home / 'config.yaml').read_text() == original
    assert not (home / '.env').exists()


@pytest.mark.parametrize('via', ['write', 'rerender'])
def test_selected_custom_personality_retains_later_agent_definition(tmp_path, via):
    home = native_home(tmp_path)
    original = native_config()
    original['display']['personality'] = 'custom'
    original['personalities'] = {'custom': 'root definition'}
    original['agent'] = {'personalities': {'custom': 'later agent definition'},
                         'disabled_toolsets': [], 'system_prompt': 'stale controlled prompt'}
    HC._write_private(home, 'config.yaml', HC.to_yaml(original))
    board = CAP.Store(tmp_path / 'board')
    def writer(home, base, token, model, rendered=None, **kw):
        kw.pop('worker', None)
        return HC.write(home, board, kw.pop('project'), base, token, model, rendered=rendered, **kw)
    if via == 'write':
        writer(home, 'http://127.0.0.1:8799/engine/v1', 'synthetic-token', 'fixture-model',
               project=str(tmp_path / 'project'))
    else:
        units = object.__new__(U.Mode1Units)
        units.write_config = writer; units.base = 'http://127.0.0.1:8799'; units.model_id = 'fixture-model'
        assert units.rerender({'home': str(home), 'project_root': str(tmp_path / 'project'), 'id': 'owned'})
    cfg = HC.read(home)
    assert cfg['display']['personality'] == 'custom'
    assert cfg['personalities'] == {'custom': 'root definition'}
    assert cfg['agent']['personalities'] == {'custom': 'later agent definition'}
    # The native merger applies the agent definitions last; neither definition is replaced.
    definitions = {**cfg['personalities'], **cfg['agent']['personalities']}
    assert definitions[cfg['display']['personality']] == 'later agent definition'
    assert 'terminal' in cfg['agent']['disabled_toolsets']
    assert 'system_prompt' not in cfg['agent']


@pytest.mark.parametrize('value', [[], 'not a mapping'])
def test_invalid_agent_personalities_refuses_before_rebuild(tmp_path, value):
    home = native_home(tmp_path)
    original = HC.to_yaml({**native_config(), 'agent': {'personalities': value}})
    (home / 'config.yaml').write_text(original)
    board = CAP.Store(tmp_path / 'board')
    with pytest.raises(ValueError):
        HC.write(home, board, str(tmp_path / 'project'), 'http://127.0.0.1:8799/engine/v1', 'new-token', 'new-model')
    assert (home / 'config.yaml').read_text() == original
    assert not (home / '.env').exists()
