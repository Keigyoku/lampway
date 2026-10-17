# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded local UI protocol; shared by MCP and the development harness."""

CAPABILITY = "mixar_ui_v1"
MAX_PENDING = 32
MAX_TARGETS = 200
MAX_IMAGE_BYTES = 4 * 1024 * 1024
ACTION_TIMEOUT = 10.0
# A claimed action (its input already being delivered) runs on past the caller's response deadline to this
# ceiling from submission, so its receipt can record the real outcome (F16). The protocol's existing 30 s
# bound: the longest mixar_ui_wait a caller may ask for (schema.py). The pump serves one request at a time, so
# requests queued behind such an action wait for it and may themselves answer outcome_unknown at their deadline.
# Scene tools run in one step and are never resumed this way.
LATE_OUTCOME_LIMIT = 30.0
CONTEXT_TTL = 30.0
MAX_CONTEXTS = 32
MAX_SCENES = 32  # scene tabs in one document, counting the user's own


class UIError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

    def result(self):
        result = {"error_type": self.code, "error": str(self)}
        if self.code == "modal_active":
            result["next_step"] = (
                "Use lampway_ui_observe, then lampway_ui_act(action=press, key=ESC, context=<observed context>, target=<observed popup control or editor region>) to cancel the popup or modal; "
                "observe again and retry the scene tool after it closes.")
        return result
