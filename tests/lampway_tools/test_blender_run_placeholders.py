# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""run_script's env placeholders: @RUN_TMP@ expands to the run's own temp dir; anything still shaped like a placeholder after expansion is refused
before the binary starts (an unexpanded one once became a relative path inside the repository)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import blender_run as B  # noqa: E402


def test_run_tmp_expands_and_an_unknown_placeholder_is_refused(tmp_path):
    assert B.expand_env({"LAMPWAY_HOME": "@RUN_TMP@/home", "X": "1"}, tmp_path) == {"LAMPWAY_HOME": f"{tmp_path}/home", "X": "1"}
    with pytest.raises(ValueError, match="unexpanded placeholder"):
        B.expand_env({"LAMPWAY_HOME": "@RUN_TMPX@/home"}, tmp_path)


def test_a_relative_home_shaped_value_is_refused(tmp_path):
    with pytest.raises(ValueError, match="relative"):
        B.expand_env({"LAMPWAY_HOME": "home"}, tmp_path)
