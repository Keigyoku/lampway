# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
from mixar.modules.lampway_tools.inspect.relations import classify


def test_cube_on_table_and_inverse_under():
    cube=[[0,0,1],[1,1,2]]
    table=[[-1,-1,0],[2,2,1]]
    assert classify(cube,table)['relation']=='on_top_of'
    assert classify(table,cube)['relation']=='under'


def test_cup_inside_box_and_definite_one_metre_gap():
    assert classify([[0,0,0],[1,1,1]],[[-1,-1,-1],[2,2,2]])['relation']=='inside'
    result=classify([[0,0,0],[1,1,1]],[[2,0,0],[3,1,1]])
    assert result['relation']=='apart'
    assert result['gap_m']==1


def test_degenerate_bounds_have_no_invented_ratios():
    result=classify([[0,0,0],[0,0,0]],[[2,0,0],[2,0,0]])
    assert result['size_ratio'] is None
    assert result['height_ratio'] is None
    assert result['gap_m']==2
