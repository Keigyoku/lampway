# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared by the brand gates (G2-G8): the one allow-list, ``brand_allowlist.toml``.

An entry ``{path, text, reason, category}`` exempts the lines of ``path`` that contain ``text``. ``category`` is one of ``CATEGORIES``; ``reason`` is a
sentence that names the line that looks the string up or the decision that blocks renaming it. G9 (test_brand_allowlist.py) keeps the list honest: every
field present, every entry still matching a line (no stale exemptions), and the count may only fall (``brand_allowlist.ratchet``).
"""

import pathlib
import tomllib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CATEGORIES = ("native-lookup", "upstream-provenance", "blocked-on-decision", "protocol-token", "legacy-read")


def load():
    with open(HERE / "brand_allowlist.toml", "rb") as fh:
        return tomllib.load(fh).get("allow", [])


def is_allowed(entries, path, line):
    path = str(path)
    return any(e["path"] == path and e["text"] in line for e in entries)
