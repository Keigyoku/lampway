# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The hub's refusals: each text names the fix."""

from typing import Optional

AGENT_WRITE = "only your click in Connections can change a credential"


class Refused(Exception):
    def __init__(self, text: str, status: int = 400):
        super().__init__(text)
        self.status = status


class NotConnected(Refused):
    def __init__(self, text: str, needs_connection: Optional[str] = None):
        super().__init__(text, 409)
        self.needs_connection = needs_connection
