# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Glove DOF schemas retain the joint grammar and refuse nonfinite JSON inputs."""
import jsonschema
import pytest
from lampway_server.agent import lampway_tools as LT


def arguments(axis='lateral'):
    return {'stage': 'pose', 'piece': 'glove', 'armature': 'body_rig', 'body_object': 'body',
            'dofs': [{'bone': 'hand_r', 'axis': axis, 'range': [-8, 8], 'step': 4,
                      'expect': {'joint': 'middle_03_r', 'along': 'forward', 'min_cm': 0}}]}


@pytest.mark.parametrize('axis', ['lateral', [0, 1, 0], {'line': ['hand_r', 'middle_03_r']},
                                  {'perp': ['hand_r', 'middle_03_r'], 'to': {'line': ['neck_01', 'head']}}])
def test_joint_grammar_forms_remain_accepted(axis):
    schema = LT.BY_NAME['lampway_fit_glove'].spec().parameters
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(arguments(axis), schema)


@pytest.mark.parametrize('field,value', [('step', 0), ('step', -1), ('step', float('inf')),
                                         ('step', float('nan')), ('range', [-8, float('inf')]),
                                         ('axis', [0, 1]), ('mirror', 'false'), ('bone', 12)])
def test_malformed_or_nonfinite_dof_refuses_before_a_script_is_built(field, value):
    args = arguments()
    args['dofs'][0][field] = value
    with pytest.raises(LT.BadArguments):
        LT.build_script(LT.BY_NAME['lampway_fit_glove'], args)


def test_axis_and_range_bounds_are_float_domain_not_physical_angle_limits():
    args = arguments([1e20, 1, 0])
    args['dofs'][0]['range'] = [720, 728]
    assert LT.build_script(LT.BY_NAME['lampway_fit_glove'], args)


@pytest.mark.parametrize('field', ['dofs', 'chain'])
def test_fit_pose_accepts_the_actual_structured_grammar_and_nullable_defaults(field):
    dof = arguments()['dofs'][0]
    payload = {'kind': 'helmet', field: [dof]}
    schema = LT.BY_NAME['lampway_fit_pose'].spec().parameters
    jsonschema.validate(payload, schema)
    jsonschema.validate({'kind': 'helmet', field: None}, schema)
    assert LT.build_script(LT.BY_NAME['lampway_fit_pose'], payload)


@pytest.mark.parametrize('value', [0, -1, float('nan')])
def test_fit_pose_refuses_invalid_structured_steps_before_execution(value):
    dof = arguments()['dofs'][0]
    dof['step'] = value
    with pytest.raises(LT.BadArguments):
        LT.build_script(LT.BY_NAME['lampway_fit_pose'], {'kind': 'helmet', 'dofs': [dof]})
