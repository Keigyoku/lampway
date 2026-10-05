# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The studio guard: nothing that changes a studio account runs unless the owner armed it for this run.

A generation can cost credits and a retry/apply/discard changes a seed that cannot always be recovered. The drivers verify
their settings before they click; this is the other half: they do not click at all unless ``LAMPWAY_STUDIO_ARMED`` is exactly
``1`` in the environment of the process the owner started. Read-only commands (home views, fetch, harvest) never need it.
"""

import os

from . import axi


def armed() -> bool:
    return os.environ.get("LAMPWAY_STUDIO_ARMED") == "1"


def require_armed(what: str) -> None:
    if not armed():
        axi.refuse(f"{what} changes a studio account and the studio guard is not armed",
                   ["LAMPWAY_STUDIO_ARMED=1 <the same command>   (set it yourself, for this run only; it can spend credits)"])
