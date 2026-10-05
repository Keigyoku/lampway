# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every ported tool, run for real through the runner with no arguments, shows AXI's home view (bin + description)
and exits 0: content first, never a usage dump, never a crash. Blender tools run under the Lampway binary; the
scipy/OpenCV tools under a science python (skipped when none is configured on this machine)."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from blender_run import lampway_bin  # noqa: E402
from mixar.modules.lampway_tools import runner as R  # noqa: E402
from mixar.modules.lampway_tools import settings as S  # noqa: E402

SCI = Path(os.environ.get("LAMPWAY_PYTHON_SCIENCE") or "/nonexistent")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))
    s = S.load()
    s.project_root = tmp_path / "proj"
    s.blender = lampway_bin()
    s.python_science = SCI if SCI.exists() else None
    return s


@pytest.mark.parametrize("name", sorted(R.TOOLS))
def test_a_tool_with_no_arguments_shows_its_home_view(name, cfg, tmp_path):
    tool = R.TOOLS[name]
    if tool.kind == "blender" and not lampway_bin().exists():
        pytest.skip("no Lampway binary")
    if tool.kind == "science" and cfg.python_science is None:
        pytest.skip("no science python (numpy + scipy + OpenCV) configured")
    if tool.kind == "blender":
        subprocess_sync = Path(__file__).resolve().parents[2] / "scripts/lampway/sync_python.sh"
        import subprocess
        subprocess.run([str(subprocess_sync), "--bin-dir", str(lampway_bin().parent)], check=True, capture_output=True)
    res = R.run(name, [], cfg, timeout=120, env_extra={"XDG_CONFIG_HOME": str(tmp_path / "xdg")})
    assert res.rc == 0, res.stdout[-1500:]
    assert "bin: " in res.stdout and "description: " in res.stdout, res.stdout[-800:]
