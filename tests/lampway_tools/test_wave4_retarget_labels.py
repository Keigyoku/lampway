# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bone-name labels for animation_retarget: 36 names from Mixamo, Rigify, UE Manny and 3ds Bip01 read to one vocabulary."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import anim_labels as L  # noqa: E402

TABLE = [
    ("mixamorig:LeftForeArm", ("lowerarm", "l")), ("mixamorig:RightUpLeg", ("thigh", "r")), ("mixamorig:Hips", ("pelvis", None)), ("mixamorig:LeftShoulder", ("clavicle", "l")),
    ("mixamorig:LeftArm", ("upperarm", "l")), ("mixamorig:LeftLeg", ("calf", "l")), ("mixamorig:LeftToeBase", ("ball", "l")), ("mixamorig:Spine2", ("spine", None)),
    ("mixamorig:LeftHand", ("hand", "l")), ("mixamorig:Neck", ("neck", None)), ("mixamorig:Head", ("head", None)), ("mixamorig:RightFoot", ("foot", "r")),
    ("Bip01_L_Thigh", ("thigh", "l")), ("Bip01 L Calf", ("calf", "l")), ("Bip01 R Foot", ("foot", "r")), ("Bip01 L UpperArm", ("upperarm", "l")), ("Bip01 L Forearm", ("lowerarm", "l")),
    ("Bip01 L Clavicle", ("clavicle", "l")), ("Bip01 Pelvis", ("pelvis", None)), ("Bip01 Neck", ("neck", None)), ("Bip01 Head", ("head", None)),
    ("forearm.L", ("lowerarm", "l")), ("upper_arm.L", ("upperarm", "l")), ("thigh.R", ("thigh", "r")), ("shin.L", ("calf", "l")), ("foot.R", ("foot", "r")), ("toe.L", ("ball", "l")),
    ("shoulder.L", ("clavicle", "l")), ("spine.001", ("spine", None)), ("hand.R", ("hand", "r")),
    ("lowerarm_l", ("lowerarm", "l")), ("calf_l", ("calf", "l")), ("thigh_r", ("thigh", "r")), ("upperarm_l", ("upperarm", "l")), ("clavicle_r", ("clavicle", "r")),
    ("ball_l", ("ball", "l")), ("pelvis", ("pelvis", None)), ("neck_01", ("neck", None)), ("spine_03", ("spine", None)), ("root", ("root", None)),
]


@pytest.mark.parametrize("name,expected", TABLE)
def test_a_bone_name_reads_to_its_canonical_label_and_side(name, expected):
    got = L.label(name)
    assert got is not None and (got[0], got[1]) == expected, (name, got)


def test_numbers_and_fingers_are_kept_and_helper_bones_are_not_guessed():
    assert L.label("spine_03")[2] == 3 and L.label("mixamorig:Spine2")[2] == 2 and L.label("neck_01")[2] == 1
    assert L.label("index_01_l") == ("finger_index", "l", 1) and L.label("mixamorig:LeftHandPinky3") == ("finger_pinky", "l", 3)
    for helper in ("ik_foot_l", "upperarm_twist_01_l", "thigh_correctiveRoot_l", "mixamorig:LeftHand_end", "weird_bone"):
        assert L.label(helper) is None, helper


def test_left_and_right_are_never_confused_for_the_same_bone():
    assert L.label("Bip01 L Thigh")[1] == "l" and L.label("mixamorig:RightArm")[1] == "r" and L.label("hand.R")[1] == "r" and L.label("head")[1] is None
