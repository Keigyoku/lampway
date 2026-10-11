# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""F13/G19: refusal next calls resolve to real tools and usable argument names."""
import asyncio
import json
import re
from lampway_server.agent import choices_tools, vault_tools
from lampway_server.agent.tools import TOOLS
from lampway_server.mcp import McpServer, SERVER_TOOLS


def _check(text, expected):
    assert expected in text
    known = {t.name for t in [*TOOLS, *SERVER_TOOLS]}
    assert set(re.findall(r'\blampway_[a-z0-9_]+\b', text)) <= known


def test_choices_bad_action_names_a_callable_list():
    text, error = asyncio.run(choices_tools.call('lampway_choices', {'action': 'bogus'}))
    assert error
    _check(text, 'lampway_choices action=list')


def test_vault_similar_missing_vault_names_the_selection_shape():
    text, error = asyncio.run(vault_tools.call(None, 'lampway_vault_similar', {}))
    assert error
    _check(text, 'lampway_vault_similar text=<query>')


def test_missing_call_status_names_the_retry_shape():
    server = McpServer(None, None)
    result = server._call_status(1, 'absent')['result']
    assert result['isError']
    _check(result['content'][0]['text'], 'lampway_call_status call_id=<call_id>')


def test_client_help_names_and_argument_templates_resolve_to_registry():
    import ast
    from pathlib import Path
    from lampway_server.agent.lampway_tools import DEFS
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / 'src/scripts/mixar/modules/lampway_tools/api.py').read_text())
    known = {t.name: t.parameters for t in [*TOOLS, *SERVER_TOOLS]}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'_HELP', '_SPECIFIC_CALLS'} for t in node.targets):
            for value in ast.walk(node.value):
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    for match in re.finditer(r'\b(lampway_[a-z0-9_]+)\b([^`]*?)(?=lampway_|$)', value.value):
                        name, arguments = match.groups()
                        assert name in known, value.value
                        for key in re.findall(r'\b([a-z_]+)=', arguments):
                            assert key in known[name].get('properties', {}), value.value
    data = json.loads((root / 'src/scripts/mixar/modules/lampway_tools/tool_specs.json').read_text())
    expected = {d.api: d for d in DEFS if d.api and not d.batch}
    assert set(data['api_calls']) == set(expected)
    for api, call in data['api_calls'].items():
        assert call['name'] == expected[api].name
        assert call['required'] == [p.name for p in expected[api].params if p.required]


def test_normalization_refusals_do_not_invent_tool_names():
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / 'src/scripts/mixar/modules/lampway_tools/canon_door.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'refusal')
    namespace = {'_skinned': lambda _: False}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(root), 'exec'), namespace)
    for kind in ('mesh', 'rigged_mesh', 'skeleton', 'texture', 'material', 'animation'):
        answer = namespace['refusal']('input', 'sample', ['scale is unresolved'], SimpleNamespace(kind=(kind,)))
        known = {t.name: t.parameters for t in [*TOOLS, *SERVER_TOOLS]}
        for line in answer['help']:
            for match in re.finditer(r'\b(lampway_[a-z0-9_]+)\b([^`]*?)(?=lampway_|$)', line):
                name, arguments = match.groups()
                assert name in known, line
                for key in re.findall(r'\b([a-z_]+)=', arguments):
                    assert key in known[name].get('properties', {}), line


def test_proportion_next_steps_use_callable_tools_not_old_shelf_paths():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    known = {t.name for t in [*TOOLS, *SERVER_TOOLS]}
    for filename in ('piece_ratios.py', 'proportion_ratios.py'):
        tree = ast.parse((root / 'src/scripts/mixar/modules/lampway_tools/scripts/proportion' / filename).read_text())
        for call in ast.walk(tree):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in ('helps', 'refuse'):
                for node in ast.walk(call):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        assert 'tools/studios/' not in node.value and 'scripts/studios/' not in node.value, node.value
                        assert set(re.findall(r'\blampway_[a-z0-9_]+\b', node.value)) <= known, node.value


def test_every_literal_tool_in_help_lines_exists_in_the_whole_registry():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    known = {t.name for t in [*TOOLS, *SERVER_TOOLS]}
    bases = (root / 'src/scripts/mixar/modules/lampway_tools', root / 'server/lampway_server/agent')
    for base in bases:
        for path in base.rglob('*.py'):
            tree = ast.parse(path.read_text())
            help_nodes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in ('helps', 'refuse'):
                        help_nodes.append(node)
                    elif node.func.attr in ('append', 'extend') and isinstance(node.func.value, ast.Name) and 'help' in node.func.value.id.lower():
                        help_nodes.append(node)
                elif isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and 'help' in target.id.lower() for target in node.targets):
                    help_nodes.append(node.value)
                elif isinstance(node, ast.Dict):
                    help_nodes.extend(value for key, value in zip(node.keys, node.values) if isinstance(key, ast.Constant) and key.value in ('help', 'helps', 'next_step'))
            for node in help_nodes:
                for value in ast.walk(node):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        names = set(re.findall(r'\blampway_[a-z0-9_]+\b', value.value))
                        assert names <= known, f'{path.relative_to(root)}:{value.lineno}: {names - known}'


def test_registry_help_gate_rejects_a_planted_nonexistent_tool(monkeypatch):
    from pathlib import Path
    import pytest
    original = Path.read_text

    def planted(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        if path.name == 'api.py':
            text += '\nplanted = {"help": ["lampway_not_a_real_tool input=<input>"]}\n'
        return text

    monkeypatch.setattr(Path, 'read_text', planted)
    with pytest.raises(AssertionError, match='lampway_not_a_real_tool'):
        test_every_literal_tool_in_help_lines_exists_in_the_whole_registry()


def _runtime_help_lines(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('help', 'helps', 'next_step'):
                yield from ([child] if isinstance(child, str) else child or [])
            yield from _runtime_help_lines(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _runtime_help_lines(child)
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            for marker in ('Next call:', 'Call it as:'):
                if marker in value:
                    yield value.split(marker, 1)[1]
        else:
            if isinstance(decoded, (dict, list)):
                yield from _runtime_help_lines(decoded)


def _assert_runtime_help(value):
    known = {t.name for t in [*TOOLS, *SERVER_TOOLS]}
    lines = list(_runtime_help_lines(value))
    assert lines, value
    for line in lines:
        assert isinstance(line, str), line
        assert set(re.findall(r'\blampway_[a-z0-9_]+\b', line)) <= known, line
        assert not re.search(r'\b(?:api\.[a-z_]+\(|mixar_[a-z0-9_]+)', line), line


def test_actual_server_refusal_branches_have_registry_checked_next_calls(tmp_path):
    from lampway_server.library.vault import Vault
    root = tmp_path / 'project'; root.mkdir()
    vault = Vault.open(tmp_path / 'vault', project_root=root)
    replies = []
    for arguments in ({}, {'action':'bogus'}, {'action':'view','purpose':'unknown'}, {'action':'view','project':'wrong'}):
        text, error = asyncio.run(choices_tools.call('lampway_choices', arguments))
        assert error
        replies.append(text)
    for instance, arguments in ((None, {}), (vault, {'unexpected':True}), (vault, {'text':'greave','k':'wrong'}),
                                (vault, {'image':'../outside.png'}), (vault, {'asset_ids':1})):
        text, error = asyncio.run(vault_tools.call(instance, 'lampway_vault_similar', arguments))
        assert error
        replies.append(text)
    replies.append(McpServer(None, None)._call_status(1, 'absent'))
    for reply in replies:
        _assert_runtime_help(reply)


def test_runtime_registry_gate_rejects_generated_nested_help():
    import pytest
    with pytest.raises(AssertionError, match='lampway_dynamically_unknown_tool'):
        _assert_runtime_help({'rows':[{'details':{'help':['lampway_' + 'dynamically_unknown_tool']}}]})


def test_generated_batch_call_templates_are_exact_live_registry_mappings():
    from pathlib import Path
    from lampway_server.agent.lampway_tools import DEFS
    data = json.loads((Path(__file__).resolve().parents[2] / 'src/scripts/mixar/modules/lampway_tools/tool_specs.json').read_text())
    expected = {d.batch: {'name': d.name, 'required': [p.name for p in d.params if p.required]} for d in DEFS if d.batch}
    assert data['batch_calls'] == expected
