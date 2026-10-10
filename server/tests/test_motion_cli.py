# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The motion-graphics AXI CLI (`python -m lampway_server.motion`, bug 4 of the PR #3 dogfood log): a thin layer over the agent tool with the
same checks and Vault filing; a live no-args view with explicit empties, TOON summaries with minimal default fields and --full, help[] after
every output, structured errors on stdout with exit 1, exit 2 for usage. Synthetic frames (FakeCapture); no browser."""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

from lampway_server.agent import motion_tools as MT
from lampway_server.motion import cli as CLI
from lampway_server.motion import frames as F

from .fake_motion import FakeCapture

SMALL = ["--width", "320", "--height", "180", "--fps", "10", "--duration", "0.2"]


def a_vault(tmp_path):
    from lampway_server.library.store import AssetLibrary
    from lampway_server.library.vault import Vault
    return Vault(tmp_path / "state", library=AssetLibrary(tmp_path / "state" / "library"))


def project(tmp_path):
    p = tmp_path / "proj"
    (p / "motion" / "scenes" / "teaser").mkdir(parents=True, exist_ok=True)
    (p / "motion" / "scenes" / "teaser" / "index.html").write_text("<!doctype html>")
    return p


def run(argv, tmp_path, capture=FakeCapture, vault=None):
    out = io.StringIO()
    ctx = CLI.Context(root=project(tmp_path), state=tmp_path / "state", capture=capture, vault_factory=(lambda: vault) if vault else None)
    rc = CLI.main(argv, ctx=ctx, out=out)
    return rc, out.getvalue()


def test_no_arguments_is_a_live_view_with_explicit_empties(tmp_path):
    (tmp_path / "empty").mkdir()
    out = io.StringIO()
    rc = CLI.main([], ctx=CLI.Context(root=tmp_path / "empty", state=tmp_path / "state"), out=out)
    text = out.getvalue()
    assert rc == 0 and "usage:" not in text
    assert text.startswith("bin: ") and "-m lampway_server.motion\ndescription: " in text and f"project: {tmp_path / 'empty'}" in text
    assert "scenes: 0 scenes" in text and "runs: 0 runs" in text and text.rstrip().splitlines()[-1].startswith("help[")


def test_render_prints_a_minimal_toon_summary_and_files_in_the_vault(tmp_path):
    vault = a_vault(tmp_path)
    rc, out = run(["render", "--scene", "motion/scenes/teaser", *SMALL], tmp_path, vault=vault)
    assert rc == 0, out
    assert "ok: true" in out and "frames: 2" in out and "vault: filed" in out
    assert "files[4]{kind,path}:" in out and "inputs[4]{name,value,source}:" in out and "  width,320,explicit" in out
    assert "findings: 0 findings" in out or "findings[" in out and "{frame,check,severity}:" in out
    assert "severity,detail}" not in out and "code_sha256" not in out                                     # minimal by default
    assert "verify --receipt motion/out/" in out and "--full:" in out and out.rstrip().splitlines()[-1].startswith("help[")


def test_full_adds_detail_hashes_outputs_and_timings(tmp_path):
    rc, out = run(["render", "--scene", "motion/scenes/teaser", *SMALL, "--no-vault", "--full"], tmp_path)
    assert rc == 0, out
    assert "findings[1]{frame,check,severity,detail}:" in out and "code_sha256: " in out and "outputs[2]{format,sha256,bytes}:" in out and "timing_s:" in out and "vault: not filed" in out


def test_the_scene_default_size_and_its_source(tmp_path):
    class Vertical(FakeCapture):
        def scene(self):
            return {"duration_s": 0.2, "width": 180, "height": 320}
    rc, out = run(["render", "--scene", "motion/scenes/teaser", "--fps", "10", "--no-vault"], tmp_path, capture=Vertical)
    assert rc == 0, out
    assert "  width,180,scene\n  height,320,scene\n  fps,10,explicit\n  duration_s,0.2,scene" in out


def test_template_vars_and_defaults_reach_the_render(tmp_path):
    rc, out = run(["render", "--scene", "motion/scenes/teaser", "--fps", "2", "--duration", "0.5", "--no-vault", "--template", "mg-social-clip@1.0.0",
                   "--var", "copy_source=motion/scenes/teaser/index.html", "--var", "focus=a launch"], tmp_path)
    assert rc == 0, out
    assert "  width,1080,template\n  height,1920,template" in out
    assert "warnings[2]{warning}:" in out and "logo_dir=assets does not exist under the project" in out
    assert '"--var logo_dir=<project-relative path> naming the real logo the scene was built from"' in out and "pass variables" not in out


def test_no_arguments_after_a_render_lists_the_scene_and_the_run(tmp_path):
    run(["render", "--scene", "motion/scenes/teaser", *SMALL, "--no-vault"], tmp_path)
    rc, out = run([], tmp_path)
    assert rc == 0 and "scenes[1]{name}:\n  teaser" in out and "runs[1]{run_id,ok,warn}:\n  mg-teaser-" in out and ",true," in out
    assert "verify --receipt motion/out/teaser-" in out


def test_verify_reproduces_a_render(tmp_path):
    run(["render", "--scene", "motion/scenes/teaser", *SMALL, "--no-vault"], tmp_path)
    out_dir = next((tmp_path / "proj" / "motion" / "out").iterdir())
    rc, out = run(["verify", "--receipt", f"motion/out/{out_dir.name}/receipt.json"], tmp_path)
    assert rc == 0, out
    assert "reproduced: true" in out and "integrity_matches: true" in out and "frames_differing: 0" in out and "help[" in out
    assert "integrity:" not in out                                                                # the detail is --full only


def test_an_unknown_flag_or_missing_argument_is_a_usage_error_exit_2(tmp_path):
    for argv in (["render", "--scene", "x", "--bogus"], ["render"], ["frobnicate"], ["render", "--scene", "x", "--width", "wide"]):
        rc, out = run(argv, tmp_path)
        assert rc == 2 and out.startswith("error: ") and "help[" in out, (argv, out)


def test_a_refusal_is_an_error_with_help_on_stdout_exit_1(tmp_path):
    rc, out = run(["render", "--scene", "motion/scenes/teaser", "--width", "4096", "--height", "2160"], tmp_path)
    assert rc == 1 and out.startswith('error: "size 4096x2160') and "long edge 16..3840, short edge 16..2160" in out.splitlines()[-1]
    rc, out = run(["verify", "--receipt", "motion/out/none/receipt.json"], tmp_path)
    assert rc == 1 and out.startswith("error: ") and "help[" in out


def test_no_browser_points_at_the_build_guide(tmp_path, monkeypatch):
    def missing():
        raise F.ChromiumMissing(F.NO_CHROMIUM)
    monkeypatch.setattr(MT.F, "chromium_binary", missing)
    rc, out = run(["render", "--scene", "motion/scenes/teaser", "--no-vault"], tmp_path, capture=None)
    assert rc == 1 and out.startswith("error: ") and "BUILD-LAMPWAY.md section 8" in out


def test_python_dash_m_runs_without_prompting(tmp_path):
    env = {**os.environ, "LAMPWAY_PROJECT_ROOT": str(tmp_path), "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    p = subprocess.run([sys.executable, "-m", "lampway_server.motion"], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and "runs: 0 runs" in p.stdout and p.stderr == ""
    p = subprocess.run([sys.executable, "-m", "lampway_server.motion", "--nope"], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and p.stdout.startswith("error: ")
