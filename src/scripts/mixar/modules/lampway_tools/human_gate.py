# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The human gate: a spend is confirmed by the user's own click, never by a script.

Anything that runs Python on the user's behalf - the agent's ``blender.execute_script`` (the GUI executor and a headless worker's) and the
live bridge - runs inside ``scripting()``. The Studio confirm operator refuses while one is on the stack, so no agent script, no swarm
worker and no bridge-driven tool can confirm; a click on the Client's own button reaches the operator with nothing running. It is a
depth counter on the main thread (scripts run one at a time there)."""

import contextlib

_depth = 0


@contextlib.contextmanager
def scripting():
    global _depth
    _depth += 1
    try:
        yield
    finally:
        _depth -= 1


def script_running() -> bool:
    return _depth > 0
