# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The validation poses of canon 05 (B, "Pose sources: authored"), vendored from Titan tools/recipes/armour-poses.json
(titan.armour-poses/1) with its numbers unchanged. Axes are named from the body's own joints (canon_geom.resolve_axis) so a
pose means the same on every MetaHuman; each pose's ``expect`` is checked on the posed JOINTS before anything is measured
(minimums in centimetres). The curl axis runs index_01 -> pinky_01: the opposite line bent the fingers BACK (measured
2026-09-30 on the engine's rest skeleton of NewMetaHumanCharacter_FullBody). The thumb is not posed (its axis is unmeasured);
MetaHuman correctives follow their parents here (only a captured pose carries the post-process graph state)."""

SCHEMA = 'titan.armour-poses/1'

POSES = {'rest': {'bones': []},
 'wrist_r_plus30': {'bones': [{'bone': 'hand_r',
                               'axis': {'line': ['pinky_metacarpal_r', 'index_metacarpal_r']},
                               'deg': 30}]},
 'wrist_r_minus30': {'bones': [{'bone': 'hand_r',
                                'axis': {'line': ['pinky_metacarpal_r', 'index_metacarpal_r']},
                                'deg': -30}]},
 'elbow_r_70': {'bones': [{'bone': 'lowerarm_r',
                           'axis': {'perp': ['lowerarm_r', 'hand_r'], 'to': 'forward'},
                           'deg': 70}],
                'expect': {'joint': 'hand_r', 'along': 'forward', 'min_cm': 5.0}},
 'curl_r_third': {'curl': {'side': 'r', 'fraction': 0.3333},
                  'expect': {'joint': 'middle_03_r', 'closer_to': 'thigh_r', 'min_cm': 0.3}},
 'curl_r_partial': {'curl': {'side': 'r', 'fraction': 0.5},
                    'expect': {'joint': 'middle_03_r', 'closer_to': 'thigh_r', 'min_cm': 0.5}},
 'curl_r_two_thirds': {'curl': {'side': 'r', 'fraction': 0.6667},
                       'expect': {'joint': 'middle_03_r', 'closer_to': 'thigh_r', 'min_cm': 0.8}},
 'curl_r_full': {'curl': {'side': 'r', 'fraction': 1.0},
                 'expect': {'joint': 'middle_03_r', 'closer_to': 'thigh_r', 'min_cm': 1.0}}}

CURL = {'fingers': ['index', 'middle', 'ring', 'pinky'],
 'deg': {'01': 80, '02': 95, '03': 60},
 'axis': {'line': ['index_01_{s}', 'pinky_01_{s}']}}
