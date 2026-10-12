# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real Blender refusals use registry-backed external tool templates."""
import json
from isolated_binary import run


def test_refusal_templates_use_public_tool_names(tmp_path):
    result = run(tmp_path, """
from mixar.modules.lampway_tools import api
out = api.call("model_compare", json.dumps({"action": "stats", "set": "absent.glb"}))
print("RESULT", json.dumps(out))
""")
    assert result.rc == 0, result.out[-2500:]
    refusal = result.results[0]
    assert refusal["ok"] is False
    assert any("lampway_model_compare" in h for h in refusal["help"])
    assert not any("api." in h for h in refusal["help"])


def test_normalization_help_in_real_blender_uses_registered_next_calls(tmp_path):
    result = run(tmp_path, '''
from mixar.modules.lampway_tools import canon_door
from types import SimpleNamespace
answers = [canon_door.refusal("input", "sample", ["scale is unresolved"], SimpleNamespace(kind=(kind,)))
           for kind in ("mesh", "rigged_mesh", "skeleton", "texture", "material", "animation")]
print("RESULT", json.dumps(answers))
''')
    assert result.rc == 0, result.out[-2500:]
    for answer in result.results[0]:
        assert answer['ok'] is False
        assert 'lampway_fit stage=place' in answer['help'][-1]
        assert 'lampway_fit_place' not in json.dumps(answer)


def test_invalid_model_set_refusal_gives_an_actionable_public_shape(tmp_path):
    result = run(tmp_path, '''
from mixar.modules.lampway_tools import api
print("RESULT", json.dumps(api.call("model_compare", json.dumps({"action":"stats", "set":"invalid"}))))
''')
    assert result.rc == 0, result.out[-2500:]
    text = '\n'.join(result.results[0]['help'])
    assert 'lampway_model_compare action=stats set=' in text
    assert 'models' in text and 'file' in text
    assert 'Fix the argument named in the error' not in text


def test_jailed_batch_refusal_names_the_actual_registered_batch(tmp_path):
    result = run(tmp_path, '''
from mixar.modules.lampway_tools import api
print("RESULT", json.dumps(api.call("run_tool", json.dumps({"name":"proportion_ratios", "args":["../outside.npz"]}))))
''')
    assert result.rc == 0, result.out[-2500:]
    answer = result.results[0]
    assert answer['ok'] is False
    assert any('lampway_proportion_ratios out=<out> body=<body> pieces=<pieces>' in line for line in answer['help'])


def _assert_runtime_help_registry(value, known, path='result'):
    import re
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('help', 'helps', 'next_step'):
                lines = [item] if isinstance(item, str) else item or []
                for line in lines:
                    assert isinstance(line, str), (path, line)
                    assert set(re.findall(r'\blampway_[a-z0-9_]+\b', line)) <= known, (path, line)
                    assert not re.search(r'\b(?:api\.[a-z_]+\(|mixar_[a-z0-9_]+)', line), (path, line)
                    assert 'Fix the argument named in the error' not in line
            _assert_runtime_help_registry(item, known, path + '.' + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_runtime_help_registry(item, known, f'{path}[{index}]')


def test_real_api_refusal_corpus_checks_generated_and_nested_help(tmp_path):
    result = run(tmp_path, '''
import inspect
from mixar.modules.lampway_tools import api
outputs = {}
for name in api.TOOL_FUNCS:
    outputs[name + ":json"] = api.call(name, "[]")
    fn = getattr(api, name)
    try:
        inspect.signature(fn).bind_partial(__audit_unknown_argument__=True)
    except TypeError:
        outputs[name + ":arguments"] = api.call(name, json.dumps({"__audit_unknown_argument__":True}))
# Read/validation paths exercising actual engines before any mutation.
for name, args in [
    ("model_compare", {"action":"stats", "set":"invalid"}),
    ("model_compare", {"action":"stats", "set":{"models":[{"file":"absent-a.glb"},{"file":"absent-b.glb"}]}}),
    ("model_compare", {"action":"unknown", "set":{}}),
    ("qa_candidates", {}),
    ("job_status", {"job":"absent"}),
    ("run_tool", {"name":"proportion_ratios", "args":["../outside.npz"]}),
    ("run_tool", {"name":[]}),
    ("run_tool", {"name":{}}),
    ("run_tool", {"name":None}),
    ("run_tool", {"name":"unknown"}),
    ("anim_multiview_fit", {}),
    ("edit_locality_check", {"before":{},"after":{},"region":{}}),
]:
    outputs[name + ":case:" + str(len(outputs))] = api.call(name, json.dumps(args))
print("RESULT", json.dumps(outputs))
''')
    assert result.rc == 0, result.out[-3500:]
    outputs = result.results[0]
    from pathlib import Path
    metadata = json.loads((Path(__file__).resolve().parents[2] / 'src/scripts/mixar/modules/lampway_tools/tool_specs.json').read_text())
    known = {record['name'] for record in [*metadata['api_calls'].values(), *metadata['batch_calls'].values()]}
    assert len(outputs) > 250
    for case, output in outputs.items():
        assert output['ok'] is False, (case, output)
        assert output.get('help'), (case, output)
    _assert_runtime_help_registry(outputs, known)


def test_runtime_help_gate_rejects_a_dynamically_nested_nonexistent_tool():
    import pytest
    with pytest.raises(AssertionError, match='lampway_generated_unknown_tool'):
        _assert_runtime_help_registry({'items':[{'details':{'help':['lampway_' + 'generated_unknown_tool input=<x>']}}]}, {'lampway_status'})


def test_direct_batch_api_invalid_name_remains_a_structured_refusal(tmp_path):
    result = run(tmp_path, '''
from mixar.modules.lampway_tools import api
print("RESULT", json.dumps(api.run_tool(name=[])))
''')
    assert result.rc == 0, result.out[-3000:]
    assert result.results[0]['ok'] is False
    assert result.results[0]['help']
