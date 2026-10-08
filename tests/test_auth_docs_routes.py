# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The native profile's public actions use the running installation's backend.

Execute the two production action classes in isolation: standalone Blender
stubs do not need to import or exercise the unrelated sign-in implementation.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/scripts/mixar/modules/space_mixie_chat/ui/operators/auth_ops.py'
ACTIONS = {'MIXIE_CHAT_OT_open_docs': ('mixie_chat.open_docs', '/app/docs'),
           'MIXIE_CHAT_OT_report_bug': ('mixie_chat.report_bug', '/app/bug-report')}


def public_actions():
    tree = ast.parse(SOURCE.read_text())
    registration = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'classes' for t in n.targets))
    registered = [n.id for n in registration.elts]
    assert set(ACTIONS) <= set(registered), 'native profile Docs/Report operators are not registered'
    assert all(registered.count(name) == 1 for name in ACTIONS)
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ACTIONS]
    assert len(nodes) == 2, 'both registered public actions need real implementations'
    calls = []
    namespace = {'Operator': object, 'bpy': SimpleNamespace(ops=SimpleNamespace(
        wm=SimpleNamespace(url_open=lambda **args: calls.append(args))))}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace, calls, registered


def test_native_profile_actions_register_once_and_keep_existing_auth_actions():
    _, _, registered = public_actions()
    assert {'MIXIE_CHAT_OT_login', 'MIXIE_CHAT_OT_logout', 'MIXIE_CHAT_OT_open_dashboard',
            'MIXIE_CHAT_OT_refresh_credits'} <= set(registered)


@pytest.mark.parametrize('class_name', ACTIONS)
@pytest.mark.parametrize('backend', ['http://127.0.0.1:19343/', 'http://localhost:19521/local/',
                                   'http://[::1]:19417/'])
def test_profile_actions_use_runtime_backend_including_port_and_path(monkeypatch, class_name, backend):
    monkeypatch.setenv('LAMPWAY_BACKEND_URL', backend)
    actions, opened, _ = public_actions()
    operator = actions[class_name]()
    identifier, route = ACTIONS[class_name]
    assert operator.bl_idname == identifier
    assert operator.execute(None) == {'FINISHED'}
    assert opened == [{'url': backend.rstrip('/') + route}]


@pytest.mark.parametrize('class_name', ACTIONS)
def test_profile_actions_use_bundled_backend_when_runtime_override_absent(monkeypatch, class_name):
    from mixar.config import config
    monkeypatch.delenv('LAMPWAY_BACKEND_URL', raising=False)
    backend = 'http://127.0.0.1:19347/'
    monkeypatch.setattr(config, 'get_config', lambda: {'backend_url': backend})
    actions, opened, _ = public_actions()
    assert actions[class_name]().execute(None) == {'FINISHED'}
    assert opened == [{'url': backend.rstrip('/') + ACTIONS[class_name][1]}]


@pytest.mark.parametrize('class_name', ACTIONS)
def test_profile_actions_use_brand_backend_default_without_saved_configuration(monkeypatch, class_name):
    from mixar.config import brand, config
    monkeypatch.delenv('LAMPWAY_BACKEND_URL', raising=False)
    monkeypatch.setattr(config, 'get_config', lambda: {})
    actions, opened, _ = public_actions()
    assert actions[class_name]().execute(None) == {'FINISHED'}
    assert opened == [{'url': brand.DEFAULT_BACKEND_URL.rstrip('/') + ACTIONS[class_name][1]}]
