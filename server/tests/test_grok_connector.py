# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grok MAIN adds only owned connector authority; native settings remain native."""
import json

import pytest

from lampway_server.herdr.harnesses.base import DirectServer, PaneSpec
from lampway_server.herdr.harnesses.grok import Grok
from lampway_server.pane_mcp import CONFIG_ENV, ROOT_ENV


def test_main_connector_binding_and_rebind_do_not_select_a_native_agent(tmp_path):
    path = tmp_path / 'panes' / 'one' / 'mcp.json'
    adapter = Grok()
    direct = DirectServer('swarm', 'http://127.0.0.1:8787/api/v1/mcp/pane', {}, '', 'synthetic-secret')
    pane = PaneSpec(cwd='/synthetic/project', scene_session_id='scene-one',
                    mcp_config_path=str(path), launcher=('/opt/lampway/lampway-mcp',), direct=(direct,))
    wiring = adapter.lampway_tools(pane)
    assert adapter.tools_reachable and adapter.always_pane_config and adapter.direct_ok
    assert wiring.kind == 'symbolic_stdio' and wiring.argv == ()
    assert wiring.env == {CONFIG_ENV: str(path), ROOT_ENV: str(tmp_path)}
    body = json.loads(wiring.files[str(path)])
    assert body['binding'] == 'scene-one'
    assert body['desktop'] == {'command': '/opt/lampway/lampway-mcp', 'args': [],
                               'env': {'LAMPWAY_BOUND_SESSION': 'scene-one'}}
    assert body['direct'][0]['headers']['Authorization'] == 'Bearer synthetic-secret'
    for argv in (adapter.launch(pane), adapter.resume('native-id', pane)):
        assert '--agent' not in argv and '--always-approve' not in argv
        assert 'synthetic-secret' not in ' '.join(argv)
    assert not ({'HOME', 'GROK_HOME', 'GROK_AUTH_PATH', 'GROK_AGENT', 'GROK_CONFIG'} & wiring.env.keys())
    unbound = adapter.lampway_tools(PaneSpec(cwd=pane.cwd, mcp_config_path=str(path), launcher=pane.launcher))
    assert json.loads(unbound.files[str(path)]) == {'version': 1, 'binding': '', 'desktop': None, 'direct': []}
    assert not path.exists()  # Adapter describes files; only the host writes them.


def test_worker_is_refused_even_without_binding_or_config():
    adapter = Grok()
    pane = PaneSpec(cwd='/synthetic/project', desktop=False)
    for action in (lambda: adapter.lampway_tools(pane), lambda: adapter.launch(pane, 'work'),
                   lambda: adapter.resume('native-id', pane)):
        with pytest.raises(ValueError, match='worker'):
            action()
