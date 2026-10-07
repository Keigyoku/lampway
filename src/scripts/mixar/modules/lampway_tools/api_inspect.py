# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""T1 API entry, registered by api.py through the OBSERVE door."""
from .inspect import run


def inspect(**kwargs):
    return run(**kwargs)
