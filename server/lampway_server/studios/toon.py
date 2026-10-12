# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Adapt shared TOON decoding to the Studio reader's existing Parsed shape.

Non-strict mode retains compatibility with legacy shelf driver output, including
legacy empty-array headers; the shared encoder always emits the current forms.
"""

import re
from dataclasses import dataclass, field
from ..compute.toon_out import decode


@dataclass
class Parsed:
    kv: dict = field(default_factory=dict)
    tables: dict = field(default_factory=dict)
    help: list = field(default_factory=list)
    error: str = None


def parse(text: str) -> Parsed:
    """Read current TOON and legacy driver output into the Studio's stable shape."""
    data = decode(text, strict=False)
    p = Parsed()
    if not isinstance(data, dict):
        raise ValueError('Studio driver output must be an object')
    for key, value in data.items():
        if key == 'help':
            p.help = [re.sub(r'^Run `|`$', '', str(item)) for item in value]
        elif key == 'error':
            p.error = value
        elif isinstance(value, list):
            p.tables[key] = value
        else:
            p.kv[key] = value
    return p
