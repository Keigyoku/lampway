# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The live motion ToolSpec teaches concrete reports accepted by the renderer."""
from lampway_server.agent.motion_tools import SPEC
from lampway_server.motion import check as C
from .test_motion_brief_contract import example, ready


def test_tool_description_examples_pass_actual_runtime_contract(tmp_path):
    setup = example(SPEC.description, 'Setup return example:')
    audit = example(SPEC.description, 'Audit return example:')
    ready(setup, tmp_path)
    assert setup['fonts'] and setup['images']
    assert audit['text'] and audit['marks']
    assert set(audit['marks'][0]) == {'sel', 'box'}, 'marks teach their own minimal schema'
    assert C.validate_audit(audit) == audit
    ready(example(SPEC.description, 'Empty-resource setup:'), tmp_path)
    assert C.validate_audit(example(SPEC.description, 'Empty audit:')) == {'text': [], 'marks': []}
