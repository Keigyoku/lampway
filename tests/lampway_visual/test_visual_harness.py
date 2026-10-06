# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 15: captures that can fail.

The real build runs windowed on a throwaway virtual display (never a live session), a state script puts the UI in a
named state, the window is captured, and the harness fails when a named surface is not the token it should be, or a
region differs from its approved golden capture. The harness's own falsifiers come first: a wrong token and a moved
region must fail, and a missing display must skip loudly.
"""

import json

import pytest

import harness


def test_harness_skips_loudly_without_display(monkeypatch):
    monkeypatch.delenv("LAMPWAY_XVFB", raising=False)
    monkeypatch.setenv("PATH", "/nonexistent")
    assert harness.display_runner() is None
    with pytest.raises(pytest.skip.Exception, match="no virtual display: run inside the build box"):
        harness.require_display()


def test_harness_fails_on_a_wrong_token(tmp_path):
    """Falsifier for the sampler: plant an off-token colour on the outliner's active row; the verdict names the
    surface and the token it should have been."""
    report = harness.run_state("night_startup", tmp_path, plant={"outliner.active": "#123456"})
    failures = harness.token_failures(report)
    assert [f.split(":")[0] for f in failures] == ["outliner_active_row"], failures
    assert "accent_bed_hi" in failures[0] and "#123456" in failures[0], failures


def test_night_startup_samples_the_tokens(tmp_path):
    """T9 (contract 01): a new profile in Lampway Night; the outliner's active row is `accent_bed_hi` and its back is
    `surface`, each within 2/255."""
    report = harness.run_state("night_startup", tmp_path)
    assert harness.token_failures(report) == [], json.dumps(report["surfaces"], indent=1)
    assert set(report["surfaces"]) == {"outliner_active_row", "outliner_back"}


def test_harness_fails_on_a_moved_region(tmp_path):
    """Falsifier for the diff: the same capture with the outliner shifted 20 px differs beyond the 1 percent
    tolerance; unshifted, it does not differ at all."""
    report = harness.run_state("night_startup", tmp_path)
    capture = tmp_path / report["capture"]
    moved = tmp_path / "moved.png"
    rect = report["regions"]["outliner"]
    harness.shift_region(capture, moved, rect, dx=20)
    assert harness.region_diff(capture, capture, rect) == 0.0
    assert harness.region_diff(capture, moved, rect) > harness.DIFF_TOLERANCE


def test_a_state_without_an_approved_golden_fails_with_its_name(tmp_path):
    capture = tmp_path / "frame.png"
    harness.blank_png(capture, 40, 30)
    failures = harness.golden_failures("no_such_state", capture, {"all": [0, 0, 40, 30]}, golden_dir=tmp_path)
    assert failures == ["no approved golden for no_such_state: capture and approve it"]


def test_approving_a_golden_needs_a_person(tmp_path, monkeypatch):
    capture = tmp_path / "frame.png"
    harness.blank_png(capture, 40, 30)
    monkeypatch.delenv("LAMPWAY_VISUAL_APPROVE", raising=False)
    with pytest.raises(PermissionError, match="LAMPWAY_VISUAL_APPROVE=1"):
        harness.approve("some_state", capture, golden_dir=tmp_path, who="a test")
    assert not (tmp_path / "some_state.png").exists()
