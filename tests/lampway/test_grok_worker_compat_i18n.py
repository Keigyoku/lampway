# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Consent messages reach the actual extractor and translate before wrapping."""
import ast
import os, sys, textwrap
import pytest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from test_grok_worker_compat_ui import consent, modal, compat_row

ROOT = Path(__file__).resolve().parents[2]

def _bind_production_translation(module, monkeypatch):
    """Bind the actual helper body to this test's bpy, independent of prior imports."""
    path = ROOT / 'src/scripts/mixar/modules/lampway_tools/ui/onboarding.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'iface_')
    namespace = {'bpy': module.bpy}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(path), 'exec'), namespace)
    monkeypatch.setattr(module, 'iface_', namespace['iface_'])


@pytest.fixture
def production_translation(consent, monkeypatch):
    module, _ = consent
    _bind_production_translation(module, monkeypatch)


def test_production_consent_messages_reach_existing_ast_extractor():
    sys.path.insert(0, str(ROOT / 'scripts/i18n'))
    import extract_python
    source = Path(os.environ.get('LW_GROK_I18N_SOURCE', str(ROOT / 'src/scripts/mixar/modules/lampway_tools/ui/grok_worker_compat.py')))
    found = {message.msgid for message in extract_python.extract_file(source, str(source))}
    assert {
        'Grok MAIN uses its normal native configuration. This switch changes only Grok swarm workers.',
        'This does not enable a network route, transfer a login, or qualify worker execution.',
        'Continue selects native MAIN without enabling worker compatibility.',
        'Enable applies to this project only.', 'Enable applies to every project.',
        'Enable worker compatibility', 'Continue with native MAIN',
        'Grok worker execution is unavailable until qualification',
        'The project or scene changed: review Grok again',
        'Refresh Agent preferences: this server cannot describe Grok worker compatibility safely',
    } <= found


def test_static_note_translates_whole_sentence_before_wrap_once(consent, monkeypatch, production_translation):
    module,_ = consent
    source = 'Continue selects native MAIN without enabling worker compatibility.'
    translated = 'Translated whole sentence ' * 9
    calls=[];labels=[]
    monkeypatch.setattr(module.bpy.app.translations, 'pgettext_iface', lambda text: calls.append(text) or translated)
    layout=SimpleNamespace(label=lambda **kw: labels.append(kw))
    module._note(layout, source, 'INFO')
    assert calls == [source]
    assert [row['text'] for row in labels] == textwrap.wrap(translated, width=70)
    assert all(row['translate'] is False for row in labels)
    assert labels[0]['icon'] == 'INFO' and all(row['icon'] == 'NONE' for row in labels[1:])


def test_server_disclosure_display_and_digest_are_not_translated_or_mutated(consent, monkeypatch, production_translation):
    module,_ = consent
    descriptor=deepcopy(compat_row()['worker_compat']);before=deepcopy(descriptor)
    monkeypatch.setattr(module.bpy.app.translations, 'pgettext_iface', lambda text: 'WRONG TRANSLATED ' + text)
    labels=[]
    module.draw_status(SimpleNamespace(label=lambda **kw: labels.append(kw)), {'worker_compat': descriptor})
    text=' '.join(row['text'] for row in labels)
    for exact in [descriptor['warning'], *descriptor['effects'], descriptor['qualification'], descriptor['reason']]:
        assert exact in text
    assert all(row['translate'] is False for row in labels)
    assert descriptor == before


def test_modal_confirmation_translates_literal_client_action(consent, monkeypatch, production_translation):
    module,_=consent
    monkeypatch.setattr(module.bpy.app.translations, 'pgettext_iface', lambda text: 'Translated ' + text)
    for kind,expected in [('enable','Enable worker compatibility'),('main','Continue with native MAIN')]:
        module._PENDING.clear()
        if kind=='enable': module.review_enable()
        else: module.review_main(lambda: None, lambda: True)
        op=modal(module);captured=[]
        wm=SimpleNamespace(invoke_props_dialog=lambda *a,**kw: captured.append(kw) or {'RUNNING_MODAL'})
        assert op.invoke(SimpleNamespace(window_manager=wm),None)=={'RUNNING_MODAL'}
        assert captured[0]['confirm_text']=='Translated '+expected


@pytest.mark.parametrize('prior_helper', ['identity_stub', 'foreign_bpy'])
def test_translation_controls_survive_cached_helper_from_earlier_test(consent, monkeypatch, prior_helper):
    module, _ = consent
    if prior_helper == 'identity_stub':
        monkeypatch.setattr(module, 'iface_', lambda text: text)
    else:
        # The production function can retain an earlier module's bpy globals.
        foreign = SimpleNamespace(app=SimpleNamespace(translations=SimpleNamespace(pgettext_iface=lambda text: text)))
        path = ROOT / 'src/scripts/mixar/modules/lampway_tools/ui/onboarding.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'iface_')
        namespace = {'bpy': foreign}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(path), 'exec'), namespace)
        monkeypatch.setattr(module, 'iface_', namespace['iface_'])
    _bind_production_translation(module, monkeypatch)
    test_static_note_translates_whole_sentence_before_wrap_once(consent, monkeypatch, None)
    test_modal_confirmation_translates_literal_client_action(consent, monkeypatch, None)
