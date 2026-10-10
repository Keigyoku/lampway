# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure controls for the native human-only browser admission action; no app or browser launch."""
import ast
import inspect
import gc
import weakref
from types import SimpleNamespace

import pytest
from mixar.modules.lampway_tools import human_gate, studio_client
from mixar.modules.lampway_tools.ui import agent_pill_pref as UI, launch_notice


@pytest.fixture(autouse=True)
def clear_error(monkeypatch):
    monkeypatch.setattr(UI, "_VISION_ERROR", "")


def operator():
    tree = ast.parse(inspect.getsource(UI))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LAMPWAY_OT_chatgpt_vision_open')
    node.bases = [ast.Name(id='object', ctx=ast.Load())]
    space = dict(UI.__dict__)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), UI.__file__, 'exec'), space)
    op = space[node.name]()
    op.errors = []
    op.report = lambda levels, text: op.errors.append((levels, text))
    return op


@pytest.mark.parametrize('method', ['invoke', 'execute'])
def test_script_cannot_prepare_admission_or_open_browser(monkeypatch, method):
    monkeypatch.setattr(studio_client, 'StudioClient', lambda: pytest.fail('Script reached authenticated transport'))
    monkeypatch.setattr(launch_notice, '_background', lambda *args: pytest.fail('Script scheduled request'))
    op = operator()
    with human_gate.scripting():
        result = op.invoke(None, None) if method == 'invoke' else op.execute(None)
    assert result == {'CANCELLED'}


def test_human_click_only_schedules_authenticated_request_then_opens_fixed_local_page(monkeypatch):
    queued, calls, opened = [], [], []
    client = SimpleNamespace(chatgpt_vision_ticket=lambda: calls.append('ticket') or {'path': '/app/chatgpt/vision?ticket=' + 'x' * 32},
                             base=lambda: 'http://127.0.0.1:8787')
    monkeypatch.setattr(studio_client, 'StudioClient', lambda: client)
    monkeypatch.setattr(launch_notice, '_background', lambda call, done: queued.append((call, done)))
    import webbrowser
    monkeypatch.setattr(webbrowser, 'open', lambda url: opened.append(url) or True)
    op = operator()
    assert op.invoke(None, None) == {'FINISHED'}
    assert calls == opened == [] and len(queued) == 1
    reference = weakref.ref(op)
    del op
    gc.collect()
    assert reference() is None, 'Async publication must not retain finished operator RNA'
    call, done = queued[0]
    done(call(), None)  # worker result publication; production queue delivers this on the main thread
    assert calls == ['ticket'] and opened == ['http://127.0.0.1:8787/app/chatgpt/vision?ticket=' + 'x' * 32]
    assert not UI._VISION_ERROR


@pytest.mark.parametrize('path', ['https://outside.invalid/', '/app/chatgpt/vision?ticket=x&provider=outside', '//outside.invalid/', None])
def test_malformed_ticket_response_cannot_open_a_browser(monkeypatch, path):
    import webbrowser
    monkeypatch.setattr(webbrowser, 'open', lambda url: pytest.fail('Malformed response opened URL'))
    client = SimpleNamespace(chatgpt_vision_ticket=lambda: {'path': path}, base=lambda: 'http://127.0.0.1:8787')
    monkeypatch.setattr(studio_client, 'StudioClient', lambda: client)
    monkeypatch.setattr(launch_notice, '_background', lambda call, done: done(call(), None))
    op = operator()
    assert op.execute(None) == {'FINISHED'}
    assert UI._VISION_ERROR


def test_transport_uses_only_fixed_ticket_endpoint(monkeypatch):
    client = studio_client.StudioClient(base_url='http://127.0.0.1:8787', token_getter=lambda: 'synthetic-user-token')
    calls = []
    monkeypatch.setattr(client, '_call', lambda *args: calls.append(args) or {'path': '/fixed'})
    assert client.chatgpt_vision_ticket() == {'path': '/fixed'}
    assert calls == [('POST', '/app/chatgpt/vision/ticket', {})]


@pytest.mark.parametrize('failure', ['false', 'exception', 'script-publication', 'transport'])
def test_browser_failure_is_visible_and_never_retries(monkeypatch, failure):
    import webbrowser
    calls = []
    def browser(url):
        calls.append(url)
        if failure == 'exception':
            raise RuntimeError('owned synthetic browser error')
        return False
    monkeypatch.setattr(webbrowser, 'open', browser)
    client = SimpleNamespace(chatgpt_vision_ticket=lambda: {'path': '/app/chatgpt/vision?ticket=' + 'x' * 32}, base=lambda: 'http://127.0.0.1:8787')
    monkeypatch.setattr(studio_client, 'StudioClient', lambda: client)
    queued = []
    monkeypatch.setattr(launch_notice, '_background', lambda call, done: queued.append((call, done)))
    assert operator().execute(None) == {'FINISHED'}
    call, done = queued[0]
    if failure == 'script-publication':
        with human_gate.scripting():
            done(call(), None)
    elif failure == 'transport':
        done(None, 'account notice error must not become Q1 error')
    else:
        done(call(), None)
    assert UI._VISION_ERROR == 'The vision check could not open; try again from Agent preferences.' and len(queued) == 1
    assert len(calls) == (0 if failure in ('script-publication', 'transport') else 1)
