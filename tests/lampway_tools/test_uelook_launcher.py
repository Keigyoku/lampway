# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scripts/lampway/lampway and UE Look: the launcher exports OCIO to the generated config ONLY while UE Look is enabled (its
state file exists) and the cube still validates (the config is there and the cube's sha256 is the one recorded at enable).
Otherwise OCIO is left exactly as it was. Tested with the fake binary of test_launcher.py and a SYNTHETIC cube."""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uelook_support as U  # noqa: E402
from test_launcher import env, lampway, tree  # noqa: E402,F401  (the fixtures)


def _state(home, cube, config, sha=None):
    d = home / "ue_look"
    d.mkdir(parents=True, exist_ok=True)
    (d / "launch.state").write_text(f"config={config}\ncube={cube}\ncube_sha256={sha or hashlib.sha256(cube.read_bytes()).hexdigest()}\n"
                                    "view=UE 5.8 Filmic 0000abcd\n")


def _app_env(tmp_path):
    return dict(l.split("=", 1) for l in (tmp_path / "app.txt").read_text().splitlines()[1:] if "=" in l)


def _setup(tmp_path):
    cube, config = tmp_path / "ue.cube", tmp_path / "ue_ocio" / "config.ocio"
    U.write_cube(cube)
    config.parent.mkdir()
    config.write_text("ocio_profile_version: 2.5\n")
    return cube, config


def test_enabled_with_a_valid_cube_exports_ocio_to_the_generated_config(tree, env, tmp_path):
    e, _ = env
    cube, config = _setup(tmp_path)
    _state(tmp_path / "home", cube, config)
    r = lampway(tree, {**e, "OCIO": "/elsewhere/user.ocio"}, "--env", "Prod", "--no-server")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _app_env(tmp_path)["OCIO"] == str(config) and f"UE Look: OCIO={config}" in r.stdout
    plan = lampway(tree, e, "--plan", "--env", "Prod")
    assert f"ue_look: on (OCIO={config})" in plan.stdout


def test_not_enabled_leaves_ocio_untouched(tree, env, tmp_path):
    e, _ = env
    r = lampway(tree, {**e, "OCIO": "/elsewhere/user.ocio"}, "--env", "Prod", "--no-server")
    assert r.returncode == 0 and _app_env(tmp_path)["OCIO"] == "/elsewhere/user.ocio"
    r = lampway(tree, e, "--env", "Prod", "--no-server")
    assert "OCIO" not in _app_env(tmp_path) and "UE Look" not in r.stdout
    assert "ue_look: off" in lampway(tree, e, "--plan", "--env", "Prod").stdout


def test_a_cube_that_no_longer_validates_leaves_ocio_untouched_and_says_why(tree, env, tmp_path):
    e, _ = env
    cube, config = _setup(tmp_path)
    for case in ("changed", "no_cube", "no_config"):
        if case == "no_config":
            (tmp_path / "moved.cube").rename(cube)
        _state(tmp_path / "home", cube, config, sha="0" * 64 if case == "changed" else None)
        if case == "no_cube":
            cube.rename(tmp_path / "moved.cube")
        if case == "no_config":
            config.unlink()
        r = lampway(tree, {**e, "OCIO": "/elsewhere/user.ocio"}, "--env", "Prod", "--no-server")
        assert r.returncode == 0, (case, r.stdout + r.stderr)
        assert _app_env(tmp_path)["OCIO"] == "/elsewhere/user.ocio", case
        assert "UE Look is on but its cube does not validate" in r.stdout and "OCIO left as it was" in r.stdout, (case, r.stdout)
    assert "ue_look: invalid" in lampway(tree, e, "--plan", "--env", "Prod").stdout
