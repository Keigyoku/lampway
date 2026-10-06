# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The coordinator's build rule: the agent contract files of the repository (AGENTS.md, CLAUDE.md, skills: the rail's
SKILL.md and .agents / .claude folders) instruct agents working on the source; they never ship in the installed app. This
walks the installed tree of the build under test, so it measures the install, not the rule that should produce it."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import lampway_bin  # noqa: E402

NAMES = {"AGENTS.md", "CLAUDE.md", "SKILL.md"}
DIRS = {".agents", ".claude", "skills"}


def test_the_installed_app_carries_no_agent_contract():
    binary = lampway_bin()
    if not binary.exists():
        pytest.skip(f"no Lampway binary at {binary}")
    roots = [p for p in binary.parent.iterdir() if p.is_dir() and (p / "scripts").is_dir()]
    assert roots, f"no installed scripts beside {binary}"
    found = []
    for root in roots:
        for path in root.rglob("*"):
            if path.name in NAMES or (path.is_dir() and path.name in DIRS):
                found.append(str(path.relative_to(binary.parent)))
    assert found == [], found
