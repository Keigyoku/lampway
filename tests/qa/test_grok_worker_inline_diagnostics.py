# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure construction controls; never a substitute for native receipts."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).with_name('grok_worker_inline_diagnostics.py')
SPEC = importlib.util.spec_from_file_location('inline_diagnostic', PATH)
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


@pytest.fixture
def repo():
    return Path(os.environ.get('LAMPWAY_INLINE_DIAGNOSTIC_TEST_REPO', str(Path(__file__).resolve().parents[2])))


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('pure inline controls cannot start processes, socket or signal')
    monkeypatch.setattr(D.subprocess, 'run', refuse)
    monkeypatch.setattr(D.subprocess, 'check_output', refuse)
    monkeypatch.setattr(D.asyncio, 'create_subprocess_exec', refuse)
    monkeypatch.setattr(D.socket, 'socket', refuse)
    monkeypatch.setattr(D.os, 'kill', refuse)


@pytest.fixture
def qa(repo):
    return D.load_qa(repo)


@pytest.fixture
def validator(tmp_path, qa):
    options = SimpleNamespace(output=tmp_path/'owned-fixture', phase='stdio',
        grok=Path('/owned/native'), bwrap=Path('/bin/true'), herdr=Path('/owned/herdr'),
        compatibility_layer=True, cursor_fixture='present')
    return D.validator_type(qa)(options)


def test_constructed_profile_retains_original_persona_body(validator, qa):
    _, env, _, _ = validator.make_fixture()
    persona = Path(env['GROK_HOME'])/'original-agent.md'
    body = persona.read_text().split('---\n', 2)[2]
    assert body == qa.PERSONA+'\n'
    assert validator.receipt['inline_profile']['construction']['original_body'] == body
    assert validator.receipt['synthetic_inputs'][str(persona)] == qa.file_state(persona)


def test_constructed_profile_has_exact_canonical_inline_transport_only(validator):
    _, _, _, config = validator.make_fixture()
    inline = validator.receipt['inline_profile']['construction']['inline']
    assert inline == {'lampway_pane': {'command': config['connector']['command'], 'args': config['connector']['args']}}
    assert list(inline) == ['lampway_pane']
    assert set(inline['lampway_pane']) == {'command', 'args'}


def test_preservation_baseline_is_after_authored_construction(validator, qa):
    _, env, _, _ = validator.make_fixture()
    profile = validator.receipt['inline_profile']
    assert profile['state'] == qa.file_state(Path(profile['path']))
    assert profile['auth_state'] == qa.file_state(Path(env['GROK_AUTH_PATH']))
    assert Path(env['GROK_AUTH_PATH']).read_text() == '{}\n'
    assert validator.receipt['worker_ready'] is False


def test_native_selected_definition_is_not_replaced_by_argv_or_config(validator):
    _, env, _, _ = validator.make_fixture()
    import tomllib
    config = tomllib.loads((Path(env['GROK_HOME'])/'config.toml').read_text())
    assert config['agent'] == {'definition': str(Path(env['GROK_HOME'])/'original-agent.md')}
    assert config['models'] == {'default': 'fixture'}
    assert config['model']['fixture']['api_key'] == 'synthetic-offline-only'


def test_original_native_acp_and_panes_functions_are_inherited_unmodified(qa):
    cls = D.validator_type(qa)
    assert cls.acp is qa.Validator.acp
    assert cls.native_panes is qa.Validator.native_panes
    assert cls.check is qa.Validator.check
    assert cls.run is qa.Validator.run


def test_compatibility_selection_is_explicit_synthetic_only(validator):
    _, _, _, config = validator.make_fixture()
    assert config['compat_view']['version'] == 1
    assert validator.receipt['compatibility_layer']['selected'] is True
    assert validator.receipt['inline_profile']['selection'] == 'original native [agent] definition; no argv override'


@pytest.mark.parametrize('text', ['body only\n', '---\nmcpServers: []\n---\nbody\n', '---\nname: fixture\n---\n'])
def test_reject_unexpected_synthetic_profile_before_edit(tmp_path, text):
    persona = tmp_path/'persona.md'; persona.write_text(text)
    with pytest.raises(ValueError):
        D.author_inline_profile(persona, {'command': '/owned/canonical', 'args': []})
    assert persona.read_text() == text


def test_profile_roundtrips_exact_owned_argv_and_preserves_unicode(tmp_path):
    persona = tmp_path/'persona.md'; original='---\nname: owned\npromptMode: full\n---\nFixture π body\n'
    persona.write_text(original)
    expected={'command': '/owned/path with spaces/canonical', 'args': ['--literal', 'value with spaces']}
    authored=D.author_inline_profile(persona, expected)
    frontmatter=persona.read_text().split('---\n',2)[1]
    encoded=frontmatter.split('mcpServers: ',1)[1].strip()
    assert json.loads(encoded) == [{'lampway_pane': expected}]
    assert authored['original_body'] == 'Fixture π body\n'
    assert persona.read_text().endswith('---\nFixture π body\n')


def test_changed_original_validator_hash_is_refused_before_import(tmp_path):
    path=tmp_path/'tests/qa';path.mkdir(parents=True)
    (path/'grok_worker_validation.py').write_text('raise AssertionError("must not import changed QA")\n')
    with pytest.raises(ValueError, match='original validator changed'):
        D.load_qa(tmp_path)


def test_original_transport_admission_guards_reexported_unmodified():
    import grok_worker_transport_diagnostics as T
    assert D.admission_gate is T.admission_gate
    assert D.check_checkout is T.check_checkout


def test_main_checks_admission_and_clean_checkout_before_qa_or_fixture():
    import ast
    tree=ast.parse(PATH.read_text())
    main=next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='main')
    calls=[n.func.id for stmt in main.body for n in ast.walk(stmt)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert calls.index('admission_gate') < calls.index('check_checkout') < calls.index('load_qa') < calls.index('validator_type')
    assert calls.count('check_checkout') == 2


def test_original_admission_refuses_missing_slot_before_any_execution(monkeypatch):
    monkeypatch.delenv('LAMPWAY_GROK_DIAGNOSTIC_SLOT_AUTHORIZED', raising=False)
    with pytest.raises(ValueError, match='slot grant'):
        D.admission_gate('a'*40)


@pytest.mark.parametrize('permanent,code,expected', [
    (False, 503, 503), (True, 503, 400),
    (False, 200, 200), (True, 200, 200),
    (False, 403, 403), (True, 403, 403),
    (False, 418, 418), (True, 418, 418),
])
def test_only_opted_in_local_retryable_refusal_changes(qa, monkeypatch, permanent, code, expected):
    import http.server
    observed = []
    monkeypatch.setattr(http.server.BaseHTTPRequestHandler, 'send_response',
        lambda self, status, message=None: observed.append((status, message)))
    handler = object.__new__(D.http_fixture_type(qa, permanent=permanent))
    handler.send_response(code, 'Exact original response message')
    assert observed == [(expected, 'Exact original response message')]


def test_default_retains_exact_original_http_handler(qa):
    assert D.http_fixture_type(qa) is qa.HTTPFixture
    assert D.http_fixture_type(qa, permanent=False) is qa.HTTPFixture


def test_permanent_refusal_inherits_body_hold_and_mcp_handlers(qa):
    cls = D.http_fixture_type(qa, permanent=True)
    assert issubclass(cls, qa.HTTPFixture)
    assert cls.do_POST is qa.HTTPFixture.do_POST
    assert cls.do_GET is qa.HTTPFixture.do_GET
    assert cls.log_message is qa.HTTPFixture.log_message
    assert cls.__dict__.keys() - {'__module__', '__doc__', '__qualname__'} == {'send_response'}


@pytest.mark.parametrize('permanent', [False, True])
def test_refusal_receipt_records_exact_selected_handler(qa, permanent):
    handler, record = D.model_refusal_fixture(qa, permanent=permanent)
    assert record['permanent_model_refusal'] is permanent
    assert record['unheld_model_status'] == (400 if permanent else 503)
    assert record['handler'] == handler.__module__ + '.' + handler.__qualname__
    assert record['original_handler'] == qa.HTTPFixture.__module__ + '.' + qa.HTTPFixture.__qualname__


def test_permanent_refusal_option_is_explicit_default_false():
    import ast
    tree = ast.parse(PATH.read_text())
    option = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and
        isinstance(n.func, ast.Attribute) and n.func.attr == 'add_argument' and
        n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == '--permanent-model-refusal')
    assert {k.arg: ast.literal_eval(k.value) for k in option.keywords}['action'] == 'store_true'
    assert not any(k.arg == 'default' for k in option.keywords)
