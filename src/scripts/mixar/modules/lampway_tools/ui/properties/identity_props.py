# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The account card's one switch (facelift contract 03): the card reads "Local account" and shows no address until the user asks."""

import bpy
from bpy.props import BoolProperty


def register():
    bpy.types.WindowManager.lampway_show_identity = BoolProperty(
        name="Show account details", default=False, options={'SKIP_SAVE'},
        description="Show the signed-in name and address on the account card; off, it reads Local account")


def unregister():
    if hasattr(bpy.types.WindowManager, "lampway_show_identity"):
        del bpy.types.WindowManager.lampway_show_identity
