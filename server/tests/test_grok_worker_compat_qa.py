# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""In-process QA switch controls; no native process/socket/signal/account."""
import copy
import hashlib
import json
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace
import pytest

SOURCE = Path(__file__).resolve().parents[2] / 'tests/qa/grok_worker_validation.py'
spec = importlib.util.spec_from_file_location('consented_grok_qa_control', SOURCE)
QA = importlib.util.module_from_spec(spec)
spec.loader.exec_module(QA)

@pytest.fixture(autouse=True)
def no_effects(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('native/account/process/socket/signal forbidden')
    for name in ['Popen', 'run']:
        monkeypatch.setattr(subprocess, name, refuse)
    monkeypatch.setattr(socket, 'socket', refuse)
    for name in ['execve', 'execv', 'system', 'kill', 'killpg']:
        monkeypatch.setattr(os, name, refuse)
    monkeypatch.setattr(QA.asyncio, 'create_subprocess_exec', refuse)

@pytest.fixture
def options(tmp_path):
    native = tmp_path / 'grok'; native.write_bytes(b'synthetic native')
    boundary = tmp_path / 'bwrap'; boundary.write_bytes(b'synthetic namespace')
    return SimpleNamespace(output=tmp_path/'out', phase='stdio', grok=native,
                           bwrap=boundary, compatibility_layer=True)

def test_explicit_on_qa_records_precise_compatibility_view(options):
    validator = QA.Validator(options)
    _, env, _, config = validator.make_fixture()
    assert config.get('compat_view') == {'version': 1, 'home': env['HOME'],
                                                'project_root': config['cwd'], 'state_dir': config['root']}
    # Original unrestricted baseline is never silently changed.
    assert 'GROK_CURSOR_MCPS_ENABLED' not in env

def test_default_off_qa_does_not_add_compatibility_authority(options):
    del options.compatibility_layer
    validator = QA.Validator(options)
    _, env, _, config = validator.make_fixture()
    assert 'compat_view' not in config
    assert 'GROK_CURSOR_MCPS_ENABLED' not in env


def test_selected_temporary_cursor_override_is_exact_and_nonmutating():
    argv = ['bwrap', '--setenv', 'GROK_CURSOR_MCPS_ENABLED', 'false', '--', 'native']
    original = list(argv)
    assert QA.compatibility_environment({'argv': argv}, selected=True) == {'GROK_CURSOR_MCPS_ENABLED': 'false'}
    assert argv == original
    assert QA.compatibility_environment({'argv': ['bwrap', '--', 'native']}, selected=False) == {}

@pytest.mark.parametrize('selected,flags', [
    (True, []),
    (True, ['--setenv','GROK_CURSOR_MCPS_ENABLED','true']),
    (True, ['--setenv','GROK_CURSOR_MCPS_ENABLED','false','--setenv','GROK_CURSOR_MCPS_ENABLED','false']),
    (True, ['--setenv','GROK_CURSOR_MCPS_ENABLED','false','--setenv','GROK_CLAUDE_MCPS_ENABLED','false']),
    (False, ['--setenv','GROK_CURSOR_MCPS_ENABLED','false']),
    (True, ['--setenv','GROK_CURSOR_MCPS_ENABLED']),
])
def test_undeclared_missing_or_extra_override_fails(selected, flags):
    with pytest.raises(ValueError, match='compatibility environment'):
        QA.compatibility_environment({'argv': ['bwrap', *flags, '--','native']}, selected=selected)


@pytest.fixture
def view_plan(options):
    validator = QA.Validator(options)
    _, env, _, config = validator.make_fixture()
    home = Path(env['HOME']); work = Path(config['root'])/'panes/one/grok-worker-boundary'
    skeleton = work/'home-view'
    sources = {'home': {'path': str(home)}, 'children': [
        {'path': str(home/'.grok'), 'kind': 'directory'},
        {'path': str(home/'.claude.json'), 'kind': 'file'},
        {'path': str(home/'preserved-link'), 'kind': 'symlink', 'target': '.grok'}],
        'cursor_children': [{'path':str(home/'.cursor/mcp.json'), 'kind':'file'},
                            {'path':str(home/'.cursor/native-settings'), 'kind':'file'}]}
    entries = [{**row, 'relative': Path(row['path']).name} for row in sources['children']]
    entries += [{**sources['cursor_children'][1], 'relative': '.cursor/native-settings'}]
    mounts = ['--ro-bind',str(skeleton),str(home)]
    for row in entries:
        if row['kind'] != 'symlink': mounts += ['--bind',row['path'],str(home/row['relative'])]
    mounts += ['--setenv','GROK_CURSOR_MCPS_ENABLED','false']
    sentinel = json.dumps({'mcpServers':{'lampway_pane':{'command':config['connector']['command'],
                                                      'args': [], 'enabled':True}}},sort_keys=True)+'\n'
    view = {'version':1,'enrollment':config['compat_view'],'sources':sources,'entries':entries,
            'skeleton':str(skeleton),'sentinel_path':str(skeleton/'.cursor/mcp.json'),
            'sentinel':sentinel,'sentinel_sha256':hashlib.sha256(sentinel.encode()).hexdigest(),
            'mounts':mounts,'manifest_sha256':hashlib.sha256(json.dumps({'sources':sources,'mounts':mounts,
            'sentinel':sentinel},sort_keys=True).encode()).hexdigest()}
    return config,env,{'work':str(work),'compat_view':view,'argv':['bwrap',*mounts,'--','native']}


def test_exact_private_view_preserves_backing_and_masks_only_cursor_mcp(view_plan):
    config,env,plan=view_plan; old=copy.deepcopy(plan)
    assert QA.compatibility_view(config,env,plan) == plan['compat_view']
    assert plan == old
    assert '.cursor/mcp.json' not in [row['relative'] for row in plan['compat_view']['entries']]
    assert QA.compatibility_view({},env,{'argv':['bwrap','--','native']}) is None


@pytest.mark.parametrize('change',['enrollment','boolean_version','skeleton','sentinel_path','name',
                                   'command','extra_server','sentinel_hash','entries','extra_mount',
                                   'manifest','argv','foreign_source'])
def test_foreign_or_undeclared_compatibility_effect_refuses(view_plan,change):
    config,env,plan=view_plan; view=plan['compat_view']
    if change=='enrollment':view['enrollment']={**view['enrollment'],'project_root':'/foreign'}
    elif change=='boolean_version':view['version']=True
    elif change=='skeleton':view['skeleton']='/foreign'
    elif change=='sentinel_path':view['sentinel_path']='/foreign/mcp.json'
    elif change in ['name','command','extra_server']:
        body=json.loads(view['sentinel']); entry=body['mcpServers']['lampway_pane']
        if change=='name':body['mcpServers']={'foreign':entry}
        elif change=='command':entry['command']='/foreign/helper'
        else:body['mcpServers']['foreign']=entry
        view['sentinel']=json.dumps(body);view['sentinel_sha256']=hashlib.sha256(view['sentinel'].encode()).hexdigest()
    elif change=='sentinel_hash':view['sentinel_sha256']='0'*64
    elif change=='entries':view['entries']=[]
    elif change=='extra_mount':view['mounts'] += ['--bind','/foreign','/foreign']
    elif change=='manifest':view['manifest_sha256']='0'*64
    elif change=='argv':plan['argv']=['bwrap','--','native']
    else:view['sources']['children'][0]['path']='/foreign/config'
    with pytest.raises(ValueError,match='compatibility'):
        QA.compatibility_view(config,env,plan)


def test_off_refuses_any_introduced_private_view(view_plan):
    _,env,plan=view_plan
    with pytest.raises(ValueError,match='OFF compatibility'):
        QA.compatibility_view({},env,plan)


def test_synthetic_enrollment_uses_current_project_and_explicit_user(options,monkeypatch):
    from lampway_server import capabilities as CAP
    validator=QA.Validator(options);_,_,_,config=validator.make_fixture();calls=[]
    class Store:
        def __init__(self,root):calls.append(('root',root))
        def set(self,*args,**kwargs):calls.append(('set',args,kwargs))
        def effective(self,*args):calls.append(('effective',args));return True,''
    monkeypatch.setattr(CAP,'Store',Store)
    monkeypatch.setattr(CAP,'grok_compat_disclosure',lambda: {'effects_sha256': 'a'*64}, raising=False)
    assert isinstance(QA.enroll_compatibility_fixture(config),Store)
    assert calls == [('root',config['root']),('set',('grok.worker_compat',),
         {'enabled':True,'options':{'consent_version':1,'effects_sha256':'a'*64},'project':config['cwd'],'by':'user'}),
         ('effective',('grok.worker_compat',config['cwd']))]


def test_refused_synthetic_enrollment_does_not_admit_candidate(options,monkeypatch):
    from lampway_server import capabilities as CAP
    validator=QA.Validator(options);_,_,_,config=validator.make_fixture()
    class Store:
        def __init__(self,root):pass
        def set(self,*args,**kwargs):pass
        def effective(self,*args):return False,'no current versioned consent'
    monkeypatch.setattr(CAP,'Store',Store)
    monkeypatch.setattr(CAP,'grok_compat_disclosure',lambda: {'effects_sha256': 'a'*64}, raising=False)
    with pytest.raises(ValueError,match='enrollment was refused'):
        QA.enroll_compatibility_fixture(config)


@pytest.mark.parametrize('layout',['absent','present'])
def test_cursor_fixture_layout_keeps_original_content_and_no_override(options,layout):
    options.cursor_fixture=layout
    validator=QA.Validator(options);_,env,_,_=validator.make_fixture()
    path=Path(env['HOME'])/'.cursor/mcp.json'
    assert path.is_file() == (layout=='present')
    assert 'GROK_CURSOR_MCPS_ENABLED' not in env
    if layout=='present':
        assert list(json.loads(path.read_text())['mcpServers']) == ['foreign_cursor']
        assert validator.receipt['synthetic_inputs'][str(path)] == QA.file_state(path)
        assert path.stat().st_mode & 0o777 == 0o600
    else:
        assert not path.parent.exists()


@pytest.mark.parametrize('destination',['.', '.cursor', '.cursor/mcp.json'])
def test_extra_home_mask_cannot_hide_approved_view(view_plan,destination):
    config,env,plan=view_plan
    index=plan['argv'].index('--')
    plan['argv'][index:index]=['--bind','/foreign',str(Path(env['HOME'])/destination)]
    with pytest.raises(ValueError,match='compatibility'):
        QA.compatibility_view(config,env,plan)

@pytest.mark.parametrize('failure', [None, 'build', 'prepare'])
def test_fixture_planning_uses_production_consent_scope_and_restores_environment(options, monkeypatch, failure):
    from lampway_server import capabilities as CAP
    runtime_path = Path(__file__).resolve().parents[1] / 'lampway_server/grok_worker.py'
    runtime_spec = importlib.util.spec_from_file_location('lampway_server.qa_compat_runtime', runtime_path)
    runtime = importlib.util.module_from_spec(runtime_spec)
    runtime_spec.loader.exec_module(runtime)
    validator = QA.Validator(options)
    _, env, _, config = validator.make_fixture()
    monkeypatch.setenv('HOME', str(options.output.parent / 'outer-home'))
    monkeypatch.setenv('QA_OUTER_ONLY', 'must restore')
    original = dict(os.environ)
    observed = []
    def consent(project, *, state_dir):
        observed.append((os.environ['HOME'], project, state_dir))
        assert project == config['compat_view']['project_root']
        assert state_dir == config['compat_view']['state_dir']
        return None
    monkeypatch.setattr(CAP, 'grok_worker_problem', consent, raising=False)
    def stage(name):
        assert runtime._compat_consent(config['compat_view'], Path(config['cwd'])) == Path(env['HOME'])
        assert dict(os.environ) == env
        os.environ['QA_STAGE_MUTATION'] = name
        if name == failure:
            raise RuntimeError('synthetic ' + name + ' failure')
        os.environ.pop('QA_STAGE_MUTATION')
    try:
        context = QA.fixture_environment
        if failure:
            with pytest.raises(RuntimeError, match='synthetic ' + failure):
                with context(env):
                    stage('build'); stage('prepare')
        else:
            with context(env):
                stage('build'); stage('prepare')
    finally:
        assert dict(os.environ) == original
    assert len(observed) == (1 if failure == 'build' else 2)


def test_validator_build_and_prepare_are_inside_fixture_environment():
    import ast
    tree = ast.parse(SOURCE.read_text())
    scopes = [node for node in ast.walk(tree) if isinstance(node, ast.With)
              and any(isinstance(item.context_expr, ast.Call)
                      and isinstance(item.context_expr.func, ast.Name)
                      and item.context_expr.func.id == 'fixture_environment'
                      for item in node.items)]
    calls = [node.func.attr for scope in scopes for node in ast.walk(scope)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name) and node.func.value.id == 'G']
    assert calls == ['build_plan', 'prepare']


def test_stdio_removes_every_exact_shim_mount_from_actual_runtime_plan(tmp_path, monkeypatch):
    from lampway_server import grok_worker as G
    from lampway_server import capabilities as CAP
    fixture_spec = importlib.util.spec_from_file_location('qa_owned_runtime_fixture', Path(__file__).with_name('test_grok_worker.py'))
    fixture_module = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(fixture_module)
    path, config, etc = fixture_module.fixture(tmp_path)
    home = tmp_path / 'owned-home'; home.mkdir(mode=0o700)
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr(CAP, 'grok_worker_problem', lambda project, *, state_dir: '', raising=False)
    config['compat_view'] = {'version':1, 'home':str(home), 'project_root':config['cwd'], 'state_dir':str(tmp_path/'state')}
    path.write_text(json.dumps(config))
    plan = G.build_plan(path, etc=etc)
    original = copy.deepcopy(plan)
    boundary = plan['argv'][:plan['argv'].index('--')+1]
    triple = ['--ro-bind', plan['shim'], str(Path(plan['connector']).resolve())]
    indices = [i for i in range(len(boundary)-2) if boundary[i:i+3] == triple]
    assert len(indices) == 2, 'control must exercise actual repeated production shim mounts'
    expected = list(boundary)
    for i in reversed(indices): del expected[i:i+3]
    actual = QA.stdio_diagnostic_boundary(plan)
    assert actual == expected
    assert plan == original
    assert '--setenv' in actual and '--ro-bind' in actual


@pytest.mark.parametrize('boundary', [
    ['bwrap', '--ro-bind', '/unrelated', '/preserved', '--'],
    ['bwrap', '--ro-bind', '/owned/shim', '--'],
    ['bwrap', '--bind', '/owned/shim', '/connector', '--'],
    ['bwrap', '--ro-bind', '/owned/shim', '/different', '--'],
])
def test_stdio_refuses_missing_or_malformed_exact_shim_mount(boundary):
    plan = {'argv':boundary+['native'], 'shim':'/owned/shim', 'connector':'/connector'}
    original = copy.deepcopy(plan)
    with pytest.raises(ValueError, match='shim'):
        QA.stdio_diagnostic_boundary(plan)
    assert plan == original


def test_stdio_driver_uses_exact_shim_removal_only_in_stdio_branch():
    import ast
    tree = ast.parse(SOURCE.read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.If)
             and ast.unparse(node.test) == "self.options.phase == 'stdio'"
             and any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                     and child.func.id == 'stdio_diagnostic_boundary' for child in ast.walk(node))]
    assert len(calls) == 1
