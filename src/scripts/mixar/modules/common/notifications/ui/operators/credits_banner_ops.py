# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Out-of-Credits Banner — button actions

The native banner (``MIXAR_OT_credits_banner``) reports every outcome here
exactly once, dismissal included, so destinations and telemetry live in one
Python place:

* ``UPGRADE`` — the manage-subscription page, via ``mixar.open_credit_upgrade``
  (the same signed-in handoff the chat's Upgrade CTA uses);
* ``REFER`` and ``CREATOR`` — Mixar's referral and Creator Program pages: Lampway has neither, so they only record the choice;
* ``DISMISS`` — ✕, Esc or a backdrop click.
"""

import bpy
from bpy.props import StringProperty

from mixar.config.logging_config import get_logger

logger = get_logger(__name__)

BANNER_ACTIONS = ("UPGRADE", "REFER", "CREATOR", "DISMISS")


def _open_upgrade() -> None:
    try:
        bpy.ops.mixar.open_credit_upgrade()
    except Exception as exc:  # noqa: BLE001
        logger.error("Credits banner: upgrade failed to open: %s", exc)


# Module-level so the QA replay can stand in for the browser.
DESTINATIONS = {
    "UPGRADE": _open_upgrade,
}


class MIXAR_OT_credits_banner_action(bpy.types.Operator):
    """Act on the out-of-credits banner choice"""

    bl_idname = "mixar.credits_banner_action"
    bl_label = "Out of Credits"
    bl_options = {"INTERNAL"}

    action: StringProperty(
        name="Action",
        description="UPGRADE, REFER, CREATOR or DISMISS",
        default="DISMISS",
        options={"SKIP_SAVE"},
    )

    def execute(self, context):
        from ...credits_banner import note_banner_closed

        action = self.action if self.action in BANNER_ACTIONS else "DISMISS"
        note_banner_closed()

        destination = DESTINATIONS.get(action)
        if destination is not None:
            destination()

        try:
            from mixar.modules.common.analytics.credits_events import (
                capture_credits_banner_action,
            )

            capture_credits_banner_action(action, context=context)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Credits banner telemetry skipped: %s", exc)
        return {"FINISHED"}


class MIXAR_OT_show_credits_banner(bpy.types.Operator):
    """Show the out-of-credits banner (support and QA)"""

    bl_idname = "mixar.show_credits_banner"
    bl_label = "Show Out-of-Credits Banner"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        from ...credits_banner import request_credits_banner, reset_state

        reset_state()  # an explicit request is never swallowed by the cooldown
        request_credits_banner("manual")
        return {"FINISHED"}


classes = (
    MIXAR_OT_credits_banner_action,
    MIXAR_OT_show_credits_banner,
)
