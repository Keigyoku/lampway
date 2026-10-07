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
