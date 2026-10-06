# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Approve one staged add-on patch: the USER's click. human_gate refuses it while any script runs (the agent's, a worker's or the bridge's), so the agent
that staged a patch cannot approve it; addon_commit commits only an approved proposal (features/addon_tools.py)."""

from bpy.props import StringProperty
from bpy.types import Operator

from mixar.modules.lampway_tools import human_gate
from mixar.modules.lampway_tools.features import addon_tools


class LAMPWAY_OT_addon_approve(Operator):
    """Approve this staged add-on patch so the agent may commit it. Your click only"""
    bl_idname = "lampway.addon_approve"
    bl_label = "Approve patch"
    bl_options = {"REGISTER"}
    project_id: StringProperty()
    proposal_id: StringProperty()

    def execute(self, context):
        if human_gate.script_running():
            self.report({"ERROR"}, "this is the user's click: a script (the agent's, a worker's or the bridge's) cannot press it")
            return {"CANCELLED"}
        addon_tools.approve(self.project_id, self.proposal_id)
        self.report({"INFO"}, f"patch {self.proposal_id} approved: the agent may commit it")
        return {"FINISHED"}


classes = [LAMPWAY_OT_addon_approve]
