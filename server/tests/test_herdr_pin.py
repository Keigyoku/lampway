# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway runs ITS pinned herdr (``third_party/herdr``, built by scripts/lampway/herdr_env.py into ``<builds>/<tag>/``), the way
it builds its pinned Blender: ahead of any herdr on PATH. ``LAMPWAY_HERDR_BIN`` still overrides; a build without its
``herdr.json`` is unfinished and never used."""
import json
import os

import pytest

from lampway_server.herdr import launcher as L


def exe(path, text="herdr"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\necho {text}\n")
    path.chmod(0o755)
    return path


def pinned(builds, tag="v0.9.3", finished=True):
    binary = exe(builds / tag / "herdr", f"herdr {tag}")
    if finished:
        (builds / tag / "herdr.json").write_text(json.dumps({"tool": "herdr", "tag": tag, "commit": "7b116c05", "binary": "herdr"}))
    return binary


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("LAMPWAY_HERDR_BIN", raising=False)
    monkeypatch.setenv("LAMPWAY_HERDR_BUILDS", str(tmp_path / "builds"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    path_herdr = exe(tmp_path / "pathbin" / "herdr", "someone else's herdr")
    monkeypatch.setenv("PATH", f"{path_herdr.parent}{os.pathsep}/usr/bin{os.pathsep}/bin")
    return tmp_path, path_herdr


def test_the_pinned_build_wins_over_a_herdr_on_path(env):
    tmp, _ = env
    built = pinned(tmp / "builds")
    assert L.bin_path() == str(built)


def test_lampway_herdr_bin_still_overrides_the_pin(env, monkeypatch):
    tmp, _ = env
    pinned(tmp / "builds")
    mine = exe(tmp / "mine" / "herdr")
    monkeypatch.setenv("LAMPWAY_HERDR_BIN", str(mine))
    assert L.bin_path() == str(mine)


def test_an_unfinished_build_is_never_used(env):
    tmp, path_herdr = env
    pinned(tmp / "builds", finished=False)
    assert L.bin_path() == str(path_herdr), "no herdr.json: an unfinished build; the next candidate is used"


def test_without_any_herdr_the_refusal_names_the_pinned_build(env, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    with pytest.raises(L.HerdrError) as refused:
        L.bin_path()
    assert "scripts/lampway/herdr_env.py" in str(refused.value)
