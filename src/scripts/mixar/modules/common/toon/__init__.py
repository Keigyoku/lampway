# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The shared, dependency-free Lampway TOON codec."""
from .codec import encode, decode, normalize, SPEC_VERSION

__all__ = ['encode', 'decode', 'normalize', 'SPEC_VERSION']
