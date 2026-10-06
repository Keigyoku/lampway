"""Audit F13 (2026-10-06): a required-argument refusal carries a call template - the tool's required arguments with what each one
is - so the agent's next call can be right. 153 server-side refusals said only "<tool> needs <arg>"."""
import asyncio
import json

import pytest

from lampway_server.agent import lampway_tools as LT
from lampway_server.agent import server_tools as ST
from lampway_server.agent import vault_tools as VT


def _template(text, name):
    assert "Call it as: " + name in text, text
    return json.loads(text.split("Call it as: " + name, 1)[1].strip())


def test_every_def_with_required_arguments_answers_an_empty_call_with_a_template():
    defs = [d for d in LT.DEFS if any(p.required for p in d.params)]
    assert len(defs) > 50
    for d in defs:
        with pytest.raises(LT.BadArguments) as exc:
            LT.build_script(d, {})
        template = _template(str(exc.value), d.name)
        assert set(template) == {p.name for p in d.params if p.required}, (d.name, template)


def test_server_run_tools_answer_an_empty_call_with_a_template():
    tools = [d for d in ST.BY_NAME.values() if any(a.required for a in d.args)]
    assert tools
    for d in tools:
        with pytest.raises(ST.BadToolCall) as exc:
            ST.command(d.name, {})
        assert set(_template(str(exc.value), d.name)) == {a.name for a in d.args if a.required}


def test_vault_tools_answer_an_empty_call_with_a_template():
    name = next(n for n, t in VT.BY_NAME.items() if t.parameters.get("required"))
    text, is_error = asyncio.run(VT.call(object(), name, {}, {"origin": "agent", "agent_id": "main"}))     # refused before the Vault is touched
    assert is_error and set(_template(text, name)) == set(VT.BY_NAME[name].parameters["required"])
