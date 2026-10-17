# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit worker-only view enrollment, without native calls or real home reads."""
import json
from pathlib import Path

import pytest
from lampway_server import grok_worker as G
from tests.test_grok_worker import fixture


def enrolled(tmp_path, monkeypatch):
    path, config, etc = fixture(tmp_path)
    home = tmp_path / 'native-home'; home.mkdir(mode=0o700)
    native = home / '.grok'; native.mkdir(mode=0o700)
    (native / 'auth.json').write_text('synthetic-auth-untouched')
    (native / 'config.toml').write_text('synthetic-persona-and-budget-untouched')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('GROK_HOME', str(native))
    monkeypatch.setenv('GROK_AUTH_PATH', str(native / 'auth.json'))
    from lampway_server import capabilities as CAP
    monkeypatch.setattr(CAP, 'grok_worker_problem', lambda project, *, state_dir: '', raising=False)
    config['compat_view'] = {'version': 1, 'home': str(home), 'project_root': config['cwd'], 'state_dir': str(tmp_path / 'capability-state')}
    path.write_text(json.dumps(config))
    return path, config, etc, home


def test_off_has_no_compatibility_env_or_home_view(tmp_path):
    path, config, etc = fixture(tmp_path)
    plan = G.build_plan(path, etc=etc)
    assert '--setenv' not in plan['argv']
    assert 'compat_view' not in plan


def test_enrolled_view_sets_only_worker_cursor_mcp_override(tmp_path, monkeypatch):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    plan = G.build_plan(path, etc=etc)
    assert '--setenv' in plan['argv'], 'explicit enrollment was ignored'
    i = plan['argv'].index('--setenv')
    assert plan['argv'][i:i+3] == ['--setenv', 'GROK_CURSOR_MCPS_ENABLED', 'false']
    assert plan['argv'].count('--setenv') == 1
    assert '--agent' not in plan['argv'] and '--always-approve' not in plan['argv']
    assert not (home / '.cursor').exists(), 'planning must not create host mount targets'


@pytest.mark.parametrize('version', [True, 0, 2, '1'])
def test_invalid_enrollment_version_refuses_before_owned_writes(tmp_path, monkeypatch, version):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    config['compat_view']['version'] = version
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='compat'):
        G.build_plan(path, etc=etc)
    assert not (path.parent / 'grok-worker-boundary').exists()
    assert not (home / '.cursor').exists()


def test_enrollment_cannot_select_another_home(tmp_path, monkeypatch):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    foreign = tmp_path / 'other-home'; foreign.mkdir()
    config['compat_view']['home'] = str(foreign)
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='HOME'):
        G.build_plan(path, etc=etc)


@pytest.mark.parametrize('existing_cursor', [False, True])
def test_prepare_creates_only_owned_view_and_preserves_native_files(tmp_path, monkeypatch, existing_cursor):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    cursor = home / '.cursor'
    if existing_cursor:
        cursor.mkdir(mode=0o700)
        (cursor / 'mcp.json').write_text('original native Cursor MCP configuration')
        (cursor / 'rules').mkdir()
        (cursor / 'settings.json').write_text('original native Cursor settings')
    originals = {p: p.read_bytes() for p in home.rglob('*') if p.is_file()}
    plan = G.build_plan(path, etc=etc)
    view = plan['compat_view']
    G.prepare(plan)
    assert {p: p.read_bytes() for p in originals} == originals
    assert cursor.exists() is existing_cursor
    sentinel = json.loads(Path(view['sentinel_path']).read_text())
    assert sentinel == {'mcpServers': {'lampway_pane': {'command': config['connector']['command'], 'args': [], 'enabled': True}}}
    assert Path(view['sentinel_path']).stat().st_mode & 0o777 == 0o400
    assert view['mounts'][:3] == ['--ro-bind', view['skeleton'], str(home)]
    assert ['--bind', str(home / '.grok'), str(home / '.grok')] == view['mounts'][3:6]
    assert '--dir' not in view['mounts'] and '--tmpfs' not in view['mounts']
    if existing_cursor:
        assert str(cursor / 'settings.json') in view['mounts']
        assert str(cursor / 'rules') in view['mounts']
        assert str(cursor / 'mcp.json') not in view['mounts']
    G._validate_compat(plan, prepared=True)


@pytest.mark.parametrize('change', ['membership', 'replacement', 'permissions'])
def test_native_metadata_changes_refuse_before_preparation(tmp_path, monkeypatch, change):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    plan = G.build_plan(path, etc=etc)
    if change == 'membership':
        (home / 'new-name').write_text('synthetic new entry')
    elif change == 'replacement':
        native = home / '.grok'; native.rename(home / 'old-native'); native.mkdir()
    else:
        home.chmod(0o755)
    with pytest.raises(ValueError, match='changed'):
        G.prepare(plan)
    assert not Path(plan['work']).exists()


@pytest.mark.parametrize('change', ['sentinel', 'mode', 'extra', 'symlink'])
def test_owned_view_tampering_refuses_before_exec(tmp_path, monkeypatch, change):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    plan = G.build_plan(path, etc=etc)
    G.prepare(plan)
    view = plan['compat_view']; sentinel = Path(view['sentinel_path'])
    if change == 'sentinel':
        sentinel.chmod(0o600); sentinel.write_text('{}'); sentinel.chmod(0o400)
    elif change == 'mode': sentinel.chmod(0o600)
    elif change == 'extra': (Path(view['skeleton']) / 'unlisted').touch()
    else:
        sentinel.unlink(); sentinel.symlink_to(home / '.grok' / 'auth.json')
    with pytest.raises(ValueError, match='integrity|identities'):
        G._validate_compat(plan, prepared=True)


def test_revoked_consent_refuses_before_directory_inspection(tmp_path, monkeypatch):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    from lampway_server import capabilities as CAP
    monkeypatch.setattr(CAP, 'grok_worker_problem', lambda *args, **kwargs: 'off')
    def refuse(*args): raise AssertionError('native HOME metadata must not be inspected without consent')
    monkeypatch.setattr(G, '_compat_sources', refuse)
    with pytest.raises(ValueError, match='consent refused'):
        G.build_plan(path, etc=etc)
    assert not (path.parent / 'grok-worker-boundary').exists()


def test_consent_revocation_between_plan_and_prepare_writes_nothing(tmp_path, monkeypatch):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    plan = G.build_plan(path, etc=etc)
    from lampway_server import capabilities as CAP
    monkeypatch.setattr(CAP, 'grok_worker_problem', lambda *args, **kwargs: 'renewed consent required')
    with pytest.raises(ValueError, match='consent refused'):
        G.prepare(plan)
    assert not Path(plan['work']).exists()


@pytest.mark.parametrize('kind', ['symlink', 'file'])
def test_redirected_cursor_parent_refuses_without_native_changes(tmp_path, monkeypatch, kind):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    cursor = home / '.cursor'
    if kind == 'symlink': cursor.symlink_to(home / '.grok', target_is_directory=True)
    else: cursor.write_text('synthetic original file')
    with pytest.raises(ValueError, match='.cursor'):
        G.build_plan(path, etc=etc)
    assert not (path.parent / 'grok-worker-boundary').exists()


def test_disclosure_digest_is_shared_canonical_json():
    import hashlib
    assert G.COMPAT_EFFECTS_SHA256 == hashlib.sha256(json.dumps({'version': G.COMPAT_VERSION, 'effects': list(G.COMPAT_EFFECTS)}, sort_keys=True).encode()).hexdigest()


def test_readonly_work_and_binding_shim_are_reapplied_after_home_mount(tmp_path, monkeypatch):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    plan = G.build_plan(path, etc=etc)
    argv = plan['argv']; view = plan['compat_view']
    last_env = argv.index('--setenv')
    assert argv[last_env+3:last_env+9] == ['--ro-bind', plan['work'], plan['work'], '--ro-bind', plan['shim'], str(Path(config['connector']['command']).resolve())]
    assert argv.index(view['skeleton']) < last_env


def test_worker_project_cannot_reclassify_global_sentinel_as_project_source(tmp_path, monkeypatch):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    config['cwd'] = str(home); config['compat_view']['project_root'] = str(home)
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='project discovery'):
        G.build_plan(path, etc=etc)


def test_native_symlinks_preserve_literal_targets_without_content_copy(tmp_path, monkeypatch):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    (home / 'native-link').symlink_to('.grok/auth.json')
    plan = G.build_plan(path, etc=etc); G.prepare(plan)
    shadow = Path(plan['compat_view']['skeleton']) / 'native-link'
    assert shadow.is_symlink() and shadow.readlink() == Path('.grok/auth.json')
    assert str(home / 'native-link') not in plan['compat_view']['mounts']



def test_public_preflight_checks_layout_without_owned_staging(tmp_path, monkeypatch):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    checked = G.compat_preflight(config['compat_view'], config['cwd'])
    assert checked['home'] == str(home)
    assert checked['sources']['children'][0]['path'] == str(home / '.grok')
    assert not (path.parent / 'grok-worker-boundary').exists()
    assert not (home / '.cursor').exists()
    (home / '.cursor').symlink_to(home / '.grok', target_is_directory=True)
    with pytest.raises(ValueError, match='.cursor'):
        G.compat_preflight(config['compat_view'], config['cwd'])
    assert not (path.parent / 'grok-worker-boundary').exists()


def test_public_preflight_refuses_native_config_home_collision(tmp_path, monkeypatch):
    path, config, etc, home = enrolled(tmp_path, monkeypatch)
    monkeypatch.setenv('GROK_HOME', str(home))
    with pytest.raises(ValueError, match='GROK_HOME'):
        G.compat_preflight(config['compat_view'], config['cwd'])
    assert not (path.parent / 'grok-worker-boundary').exists()
