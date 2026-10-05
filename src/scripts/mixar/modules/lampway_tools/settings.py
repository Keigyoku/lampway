# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lampway tool configuration: where things live. Pure Python (no bpy), so the command-line tools and the tests
read it the same way the add-on does.

Resolution order for every value: the environment variable, then ``<lampway home>/settings.json``, then the default.
"""

import json
import os
from pathlib import Path


def lampway_home(environ=None) -> Path:
    """The Lampway profile directory: ``$LAMPWAY_HOME``, else ``$XDG_DATA_HOME/lampway``, else ``~/.local/share/lampway``."""
    env = os.environ if environ is None else environ
    if env.get("LAMPWAY_HOME"):
        return Path(env["LAMPWAY_HOME"])
    base = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "lampway"
