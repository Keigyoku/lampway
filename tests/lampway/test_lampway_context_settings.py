# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Context settings use Hermes's server values and never network from draw."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_existing_capabilities_surface_draws_context_section():
    path = ROOT / 'src/scripts/mixar/modules/lampway_tools/ui/capabilities.py'
    tree = ast.parse(path.read_text())
    draw = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'draw_capabilities')
    calls = [ast.unparse(n.func) for n in ast.walk(draw) if isinstance(n, ast.Call)]
    assert 'context_settings.draw_context' in calls, 'existing configuration surface is missing governing R3/Q3 Context section'

import importlib
import io
import json
import sys
import threading
import urllib.error
from types import SimpleNamespace

import pytest

from mixar.modules.lampway_tools import capabilities_state, context_state as S, human_gate, studio_client


def answer(**kw):
    defaults = {'context_engine': 'compressor', 'compression_threshold': 0.5,
                'protected_recent_turns': 20, 'summarizing_model': ''}
    out = {'project': '/work/p', 'defaults': defaults, 'effective': dict(defaults), 'overrides': {},
           'model_window': {'tokens': None, 'source': 'unknown'}, 'busy': False, 'live_reload_supported': False,
           'engine_choices': ['compressor'], 'summarizing_model_choices': ['lampway']}
    out.update(kw)
    return out


@pytest.fixture
def ui(monkeypatch):
    monkeypatch.setattr(sys.modules['bpy.types'], 'Operator', object, raising=False)
    name = 'mixar.modules.lampway_tools.ui.context_settings'
    monkeypatch.delitem(sys.modules, name, raising=False)
    mod = importlib.import_module(name)
    S.reset()
    capabilities_state.STATE['project'] = '/work/p'
    S.STATE.update(project='/work/p', answer=answer())
    monkeypatch.setattr(human_gate, 'script_running', lambda: False)
    yield mod
    S.reset()
    capabilities_state.reset()
    sys.modules.pop(name, None)


class Layout:
    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.enabled = True
    def row(self, **kw):
        return Layout(self.log)
    box = row
    def label(self, text='', **kw):
        self.log.append(('label', text))
    def operator(self, name, **kw):
        props = SimpleNamespace()
        self.log.append(('op', name, props))
        return props


def press(cls, **props):
    op = cls()
    if props.get('key') in {'context_engine', 'summarizing_model'} and 'value' in props:
        op.choice = props['value']
    if 'project' in getattr(cls, '__annotations__', {}):
        op.project = capabilities_state.STATE['project']
    for key, value in props.items():
        setattr(op, key, value)
    op.messages = []
    op.report = lambda kind, text: op.messages.append(text)
    return op, op.execute(SimpleNamespace())


def test_draw_shows_server_defaults_overrides_window_and_reset_without_requests(ui, monkeypatch):
    monkeypatch.setattr(ui, 'CLIENT_FACTORY', lambda: pytest.fail('draw touched transport'))
    monkeypatch.setattr(S, 'request', lambda *a, **kw: pytest.fail('draw started a request'))
    S.STATE['answer'] = answer(overrides={'compression_threshold': 0.7},
                              effective={**answer()['effective'], 'compression_threshold': 0.7},
                              model_window={'tokens': 12345, 'source': 'provider'})
    lay = Layout()
    ui.draw_context(lay)
    labels = [x[1] for x in lay.log if x[0] == 'label']
    assert 'Compression threshold: 0.7' in labels
    assert 'Hermes default: 0.5' in labels
    assert 'Project override' in labels
    assert 'Model window: 12345 tokens (source: provider)' in labels
    resets = [x[2].key for x in lay.log if x[0] == 'op' and x[1] == 'lampway.context_reset']
    assert resets == ['compression_threshold']
    assert 'Protected recent messages: 20' in labels


def test_worker_does_not_publish_until_main_thread_takes_and_save_contains_only_explicit_field():
    S.reset()
    queued, calls = [], []
    original = answer()
    class Door:
        def context(self, project):
            calls.append(('get', project))
            return original
        def set_context(self, project, values=None, reset=None):
            calls.append(('put', project, values, reset))
            return answer(overrides=values)
    assert S.request(Door, '/work/p', spawn=queued.append)
    assert not calls and S.STATE['answer'] is None
    queued.pop()()
    assert S.STATE['answer'] is None and S.STATE['inflight']
    assert S.take() and S.STATE['answer'] is original
    assert S.request(Door, '/work/p', values={'protected_recent_turns': 0}, spawn=queued.append)
    assert not S.request(Door, '/work/p', spawn=queued.append)
    queued.pop()()
    assert S.take()
    assert calls[-1] == ('put', '/work/p', {'protected_recent_turns': 0}, None)
    S.reset()


def test_async_real_worker_is_off_callers_thread_and_refusal_preserves_effective_values():
    S.reset()
    S.STATE.update(project='/work/p', answer=answer())
    original = S.STATE['answer']
    parent_thread, worker_threads = threading.get_ident(), []
    done = threading.Event()
    class Door:
        def set_context(self, project, values=None, reset=None):
            worker_threads.append(threading.get_ident())
            done.set()
            raise studio_client.StudioError('Agent busy: wait for this turn to finish')
    assert S.request(Door, '/work/p', reset_keys=['context_engine'])
    assert done.wait(2)
    # Joining this bounded worker proves inbox publication before take.
    for thread in threading.enumerate():
        if thread.name == 'lampway-context-settings':
            thread.join(2)
    assert S.take()
    assert S.STATE['answer'] is original and 'Agent busy' in S.STATE['error']
    assert worker_threads and worker_threads[0] != parent_thread
    S.reset()


@pytest.mark.parametrize('name,props', [('LAMPWAY_OT_context_edit', {'key':'compression_threshold','value':'0.8'}),
                                      ('LAMPWAY_OT_context_reset', {'key':'compression_threshold'})])
def test_script_cannot_save_or_reset(ui, monkeypatch, name, props):
    monkeypatch.setattr(human_gate, 'script_running', lambda: True)
    monkeypatch.setattr(ui, '_request', lambda **kw: pytest.fail('script wrote settings'))
    op, result = press(getattr(ui, name), **props)
    assert result == {'CANCELLED'} and "user's click" in op.messages[-1]


def test_edit_and_reset_queue_only_selected_key_and_busy_refuses(ui, monkeypatch):
    requests = []
    monkeypatch.setattr(ui, '_request', lambda **kw: requests.append(kw) or True)
    assert press(ui.LAMPWAY_OT_context_edit, key='protected_recent_turns', value='0')[1] == {'FINISHED'}
    assert press(ui.LAMPWAY_OT_context_reset, key='compression_threshold')[1] == {'FINISHED'}
    assert requests == [{'values': {'protected_recent_turns': 0}}, {'reset_keys': ['compression_threshold']}]
    S.STATE['answer']['busy'] = True
    op, result = press(ui.LAMPWAY_OT_context_edit, key='compression_threshold', value='0.8')
    assert result == {'CANCELLED'} and 'busy' in op.messages[-1] and len(requests) == 2


@pytest.mark.parametrize('key,value', [('compression_threshold','nan'), ('compression_threshold','0'),
                                     ('compression_threshold','1.1'), ('protected_recent_turns','-1'),
                                     ('protected_recent_turns','1.5'), ('context_engine','unknown'),
                                     ('summarizing_model','provider/model')])
def test_invalid_or_non_gateway_edits_are_refused(ui, monkeypatch, key, value):
    monkeypatch.setattr(ui, '_request', lambda **kw: pytest.fail('invalid value was written'))
    assert press(ui.LAMPWAY_OT_context_edit, key=key, value=value)[1] == {'CANCELLED'}


def test_client_builds_authenticated_bounded_project_get_put_and_preserves_refusal(monkeypatch):
    from mixar.modules.lampway_tools.context_client import ContextClient
    calls = []
    def wire(req, timeout):
        calls.append((req.get_method(),req.full_url,req.get_header('Authorization'),
                      json.loads(req.data) if req.data else None,timeout))
        if len(calls) == 4:
            raise urllib.error.HTTPError(req.full_url,409,'busy',{},io.BytesIO(b'{"detail":"agent busy: wait"}'))
        return io.BytesIO(json.dumps(answer()).encode())
    monkeypatch.setattr(studio_client.urllib.request, 'urlopen', wire)
    c = ContextClient(base_url='http://127.0.0.1:8787',token_getter=lambda:'tok')
    c.context('/work/My Project')
    c.set_context('/work/p', values={'protected_recent_turns':0})
    c.set_context('/work/p', reset=['compression_threshold'])
    assert calls == [('GET','http://127.0.0.1:8787/app/agent/context?project=%2Fwork%2FMy+Project','Bearer tok',None,5),
                     ('PUT','http://127.0.0.1:8787/app/agent/context','Bearer tok',{'project':'/work/p','values':{'protected_recent_turns':0}},5),
                     ('PUT','http://127.0.0.1:8787/app/agent/context','Bearer tok',{'project':'/work/p','reset':['compression_threshold']},5)]
    with pytest.raises(studio_client.StudioError, match='agent busy: wait'):
        c.set_context('/work/p',values={'compression_threshold':0.7})


def test_choices_has_context_entry_and_selects_it_without_purpose_network():
    path = ROOT / 'src/scripts/mixar/modules/lampway_tools/ui/choices.py'
    src = path.read_text()
    assert 'text="Context"' in src and '_context_page().draw_context(layout)' in src
    tree = ast.parse(src)
    select = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'select')
    first = select.body[2]
    assert 'CONTEXT' in ast.unparse(first.test)
    assert '_context_page().request_refresh()' in ast.unparse(first.body)


def test_open_edit_cannot_write_to_a_different_project_after_switch(ui, monkeypatch):
    op = ui.LAMPWAY_OT_context_edit()
    op.key = 'compression_threshold'
    messages = []
    op.report = lambda kind, text: messages.append(text)
    context = SimpleNamespace(window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {'RUNNING_MODAL'}))
    assert op.invoke(context, None) == {'RUNNING_MODAL'}
    capabilities_state.STATE['project'] = '/work/other'
    S.STATE.update(project='/work/other', answer=answer(project='/work/other'))
    monkeypatch.setattr(ui, '_request', lambda **kw: pytest.fail('old popup wrote to different project'))
    assert op.execute(context) == {'CANCELLED'}
    assert 'project changed' in messages[-1].lower()


def test_live_context_renders_server_adoption_note_without_cold_reopen_claim(ui):
    S.STATE['answer'] = answer(live_reload_supported=True, live_pane=True,
                              apply_note='Thresholds apply at the next native turn; summary choice applies at next compression.',
                              defaults_source='pinned Hermes config defaults',
                              summarizing_model_choices=['lampway', 'choices:agent.main:local-review'])
    lay = Layout()
    ui.draw_context(lay)
    labels = [x[1] for x in lay.log if x[0] == 'label']
    assert S.STATE['answer']['apply_note'] in ' '.join(labels)
    assert not any('closed' in label or 'reopen' in label for label in labels)
    assert 'Defaults source: pinned Hermes config defaults' in labels


def test_summary_edit_renders_selectable_server_choices_instead_of_raw_text(ui):
    S.STATE['answer']['summarizing_model_choices'] = ['lampway', 'choices:agent.main:local-review']
    op = ui.LAMPWAY_OT_context_edit()
    op.key = 'summarizing_model'
    op.report = lambda *a: None
    context = SimpleNamespace(window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {'RUNNING_MODAL'}))
    assert op.invoke(context, None) == {'RUNNING_MODAL'}
    props = []
    layout = Layout()
    layout.prop = lambda _op, prop: props.append(prop)
    op.layout = layout
    op.draw(context)
    assert props == ['choice'], 'models must use server-listed selection rather than raw alias entry'


def test_explicit_listed_cross_service_summary_is_selected_and_saved_without_other_settings(ui, monkeypatch):
    selected = 'choices:agent.main:local-review'
    S.STATE['answer']['summarizing_model_choices'] = ['lampway', selected]
    requests = []
    monkeypatch.setattr(ui, '_request', lambda **kw: requests.append(kw) or True)
    op = ui.LAMPWAY_OT_context_edit()
    op.key = 'summarizing_model'
    op.report = lambda *a: None
    context = SimpleNamespace(window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {'RUNNING_MODAL'}))
    assert op.invoke(context, None) == {'RUNNING_MODAL'}
    assert requests == [], 'opening/selecting never grants or writes defaults'
    assert {item[0] for item in ui._choice_items(op, context)} == {ui._DEFAULT_CHOICE, 'lampway', selected}
    op.choice = selected
    assert op.execute(context) == {'FINISHED'}
    assert requests == [{'values': {'summarizing_model': selected}}]
    op.choice = 'unlisted:remote-service'
    assert op.execute(context) == {'CANCELLED'}
    assert len(requests) == 1


def test_automatic_summary_choice_is_explicit_and_default_source_and_notes_are_server_data(ui, monkeypatch):
    requests = []
    monkeypatch.setattr(ui, '_request', lambda **kw: requests.append(kw) or True)
    S.STATE['answer'].update(summarizing_model_note='Recorded service guards apply before compression.',
                            threshold_note='Pinned native threshold calculation.', defaults_source='Pinned source')
    op = ui.LAMPWAY_OT_context_edit()
    op.key, op.project, op.choice = 'summarizing_model', '/work/p', ui._DEFAULT_CHOICE
    op.report = lambda *a: None
    assert op.execute(SimpleNamespace()) == {'FINISHED'}
    assert requests == [{'values': {'summarizing_model': ''}}]
    layout = Layout()
    ui.draw_context(layout)
    labels = [entry[1] for entry in layout.log if entry[0] == 'label']
    assert 'Recorded service guards apply before compression.' in labels
    assert 'Pinned native threshold calculation.' in labels
    assert 'Defaults source: Pinned source' in labels


def test_long_native_adoption_note_wraps_without_losing_information(ui):
    note = 'Hermes reads protected messages and compression threshold before the next ordinary turn. ' * 3
    S.STATE['answer']['apply_note'] = note
    layout = Layout()
    ui.draw_context(layout)
    labels = [entry[1] for entry in layout.log if entry[0] == 'label']
    pieces = labels[labels.index('Model window: Unknown (source: unknown)') + 1:]
    # Other rows follow the note; the complete note must appear in their joined text.
    assert note.strip() in ' '.join(pieces)
    assert all(len(piece) <= 64 for piece in pieces if piece.startswith(('Hermes reads', 'compression', 'ordinary', 'threshold', 'protected', 'messages', 'before', 'turn.')))
