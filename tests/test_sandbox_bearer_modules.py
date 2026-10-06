# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Connections audit F2, held to the source: every first-party module that mentions the client's bearer (get_access_token, an Authorization header,
'Bearer') is refused to sandboxed scripts by ``sandbox_modules.is_denied_module``. A new module that starts carrying the bearer fails here until it is
added, so the deny list cannot silently fall behind the code."""
import re
from pathlib import Path

from mixar.modules.space_mixie_chat.core import sandbox_modules as SM

SRC = Path(__file__).resolve().parents[1] / "src" / "scripts"
MARKER = re.compile(r"get_access_token|[\"']Authorization[\"']|[\"']Bearer ")


def _bearer_modules():
    out = []
    for p in (SRC / "mixar").rglob("*.py"):
        if "tests" in p.parts or "__pycache__" in p.parts:
            continue
        if MARKER.search(p.read_text(encoding="utf-8", errors="replace")):
            mod = ".".join(p.relative_to(SRC).with_suffix("").parts)
            out.append(mod[: -len(".__init__")] if mod.endswith(".__init__") else mod)
    return sorted(out)


def test_every_module_that_carries_the_bearer_is_refused_to_scripts():
    mods = _bearer_modules()
    assert len(mods) > 10
    missing = [m for m in mods if not SM.is_denied_module(m)]
    assert not missing, "modules that hold or send the client's bearer but are reachable from a sandboxed script:\n  " + "\n  ".join(missing)


def test_the_tool_entry_points_scripts_use_stay_importable():
    for ok in ("mixar.modules.lampway_tools.api", "mixar.modules.common.agent_execution", "mixar.modules.paint.core.layer.mappings"):
        assert not SM.is_denied_module(ok), ok
