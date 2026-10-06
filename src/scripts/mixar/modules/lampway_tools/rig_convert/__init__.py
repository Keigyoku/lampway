# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The external rig-conversion and normalization tool's core (STATUS O36, canon 22), ported from the TITAN project, same author:
``animation_canon`` (profile, align_reference, normalize, adapt, compare, retarget), ``canon`` (unrigged mesh normalize / adapt /
serialize) and ``skin_bind`` (capture, rebind, evaluate: WIP, canon pages 07 and 22 are DRAFT). Pure python, no numpy, no bpy; the
recipes under ``recipes/`` are the Blender read-backs. The wire schema ids (``titan.animation/1`` ...) are a stable contract shared
with TITAN: the game reads this tool's output, so they are never renamed."""
