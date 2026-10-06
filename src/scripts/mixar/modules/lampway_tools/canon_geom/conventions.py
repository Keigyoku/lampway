# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 01: the frames, units and bone conventions every canon tool states in its receipt.

Body frame (every fit tool): +Z up, the body faces -Y, the wearer's left is +X, metres, right-handed. A Tripo/Hi3D glTF
after Blender's import is +Z up, +X front, +Y wearer's left: a turn of -90 deg about Z maps it to the body frame. A tool
never assumes a piece's turn; it takes ``turn_deg`` and records it (canon 01 B)."""

BODY_FRAME = {"name": "body", "up": (0.0, 0.0, 1.0), "front": (0.0, -1.0, 0.0), "left": (1.0, 0.0, 0.0), "units": "m", "handed": "right"}
BONE_DIRECTION = "head->child head"
BONE_AXIS_EXPORT = "Z/X"
FIELDS = ("frame", "units", "turn_deg", "bone_direction", "bone_axis_export", "weld_m", "source_frame")


def conventions_block(*, turn_deg, weld_m, source_frame, frame="body", units="m", bone_direction=BONE_DIRECTION,
                      bone_axis_export=BONE_AXIS_EXPORT):
    """The receipt's ``conventions`` block (canon 01 F). A field a tool cannot fill is passed as None and refused by name;
    a field that does not apply is passed as the string "n/a"."""
    block = {"frame": frame, "units": units, "turn_deg": turn_deg, "bone_direction": bone_direction,
             "bone_axis_export": bone_axis_export, "weld_m": weld_m, "source_frame": source_frame}
    missing = [k for k in FIELDS if block[k] is None]
    if missing:
        raise ValueError(f"the conventions block cannot be filled: {', '.join(missing)} (canon 01 F)")
    return block
