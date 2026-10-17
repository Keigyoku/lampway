# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The generic engine boundary uses PR1's shared codec, not its three-tool schema."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from lampway_server.compute.toon_out import SPEC_VERSION, decode, encode
from lampway_server.engine.mcp_endpoint import format_result


def test_pinned_hermes_receives_one_lossless_representation(tmp_path):
    engine = Path(os.environ.get("LAMPWAY_HERMES_ENGINE", "/nonexistent"))
    python = engine / "env/bin/python"
    if not python.is_file():
        pytest.skip("requires the pinned Hermes engine renderer")
    value = {"success": True, "rows": [{"name": "quoted, colon: 雪", "count": 42}]}
    result = format_result(json.dumps(value, ensure_ascii=False), False)
    code = """
import json, sys
from types import SimpleNamespace
from tools.mcp_tool_handlers import _render_call_tool_result
data = json.loads(sys.stdin.read())
data['content'] = [SimpleNamespace(**block) for block in data['content']]
print(_render_call_tool_result(SimpleNamespace(**data), 'lampway'))
"""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "HERMES_HOME": str(tmp_path / "hermes")}
    run = subprocess.run([str(python), "-c", code], input=json.dumps(result), text=True,
                         capture_output=True, env=env, timeout=30, check=True)
    rendered = json.loads(run.stdout)
    assert set(rendered) == {"result"}, "Hermes must not append a second JSON copy beside TOON"
    assert decode(rendered["result"]) == value


@pytest.mark.parametrize("value,is_error", [
    ({"success": True, "objects": [{"name": "true", "type": "MESH"}, {"name": "42", "type": "CURVE"}]}, False),
    ({"success": False, "error": "refused: capability is off", "help": ["lampway_capabilities action=list"]}, True),
    ({"nested": {"rows": [{"a": [1, 2], "b": "x: y"}]}, "empty": [], "big": 10**40}, False),
    (["true", "42", "#not a comment", "line\nbreak", None], False),
])
def test_engine_json_results_are_lossless_toon_without_wrapper_schema(value, is_error):
    result = format_result(json.dumps(value), is_error)
    rendered = result["content"][0]["text"]
    assert rendered == encode(value), "the engine must use the shared codec at its result seam"
    assert decode(rendered) == value
    assert result["isError"] is is_error
    assert "structuredContent" not in result


@pytest.mark.parametrize("text", ["pong", "refused: capability is off", "ordinary words\nwith another line", "{not JSON}"])
def test_plain_tool_text_is_a_toon_string_and_keeps_the_error_flag(text):
    result = format_result(text, True)
    assert decode(result["content"][0]["text"]) == text
    assert result["isError"] is True
    assert "structuredContent" not in result


def test_engine_codec_dependency_is_exactly_pr1s_byte_identical_pair():
    root = Path(__file__).resolve().parents[2]
    assert SPEC_VERSION == "4.3"
    assert (root / "server/lampway_server/compute/toon_out.py").read_bytes() == (
        root / "src/scripts/mixar/modules/common/toon/codec.py").read_bytes()
