# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""G8: a Lampway run leaves no trace of the upstream identity on the machine (rebrand finding 5).

With HOME an empty temp directory and the launcher's LAMPWAY_HOME set, start the real binary headless, load the add-on, touch the modules that keep
per-user data and quit. No path under HOME may carry the upstream name (a ``.mixar`` folder, a ``mixar`` config dir), and everything the run wrote
under HOME is inside LAMPWAY_HOME or the XDG config folder (which is named ``lampway`` now).
"""

import os
from pathlib import Path

from blender_run import run_script

TOUCH = r'''
import json, os
import bpy
from mixar.config import paths
home = paths.app_home()
home.mkdir(parents=True, exist_ok=True)
# modules that resolve a per-user data folder: ask them where it is (they create it on first use)
import importlib
resolved = {}
for mod, fn in (("mixar.modules.space_mixie_chat.core.chat_history", "history_dir"), ("mixar.modules.space_mixie_chat.core.checkpoint_store", "checkpoints_root"),
                ("mixar.modules.common.agent_history.core.store", "root"), ("mixar.modules.common.scenes_log", "dossier_root"),
                ("mixar.modules.local_models.core.paths", "base_dir"), ("mixar.bootstrap.generation_catalog.storage", "_data_dir"),
                ("mixar.modules.onboarding.core.persistence", "_data_dir"), ("mixar.modules.virtual_camera.core.tls_utils", "_cache_dir")):
    try:
        m = importlib.import_module(mod)
        resolved[mod] = str(getattr(m, fn)())
    except Exception as exc:
        resolved[mod] = "ERR " + type(exc).__name__
print("RESULT " + json.dumps({"app_home": str(home), "resolved": resolved, "home": os.environ["HOME"]}))
'''


def _walk(root: Path):
    for p in root.rglob("*"):
        yield p


def test_a_lampway_session_creates_nothing_named_mixar_under_home(tmp_path):
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    lampway_home = home / ".local/share/lampway"
    run = run_script(TOUCH, env={"HOME": str(home), "LAMPWAY_HOME": str(lampway_home), "XDG_CONFIG_HOME": str(home / ".config"),
                                 "XDG_CACHE_HOME": str(home / ".cache"), "XDG_DATA_HOME": str(home / ".local/share")})
    assert run.rc == 0, run.out[-1500:]
    result = run.results[-1]
    assert Path(result["app_home"]) == lampway_home / "app"
    for mod, where in result["resolved"].items():
        assert not where.startswith("ERR"), (mod, where)
        assert str(lampway_home) in where or str(home / ".config") in where or str(home / ".cache") in where, (mod, where)
    leaked = [str(p.relative_to(home)) for p in _walk(home) if "mixar" in p.name.lower()]
    assert leaked == [], leaked


def test_the_leak_check_sees_a_planted_dot_mixar(tmp_path):
    home = tmp_path / "home"
    (home / ".mixar").mkdir(parents=True)
    leaked = [str(p.relative_to(home)) for p in _walk(home) if "mixar" in p.name.lower()]
    assert leaked == [".mixar"]
