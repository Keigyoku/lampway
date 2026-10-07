# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 08 in the real build: the island's Image tab in its three policy states. Under the click-above-$0.25
policy a $0.067 estimate is a lamplit Generate carrying the number; a $0.40 one turns it into Spend; with OpenRouter
off Generate is disabled, the fix is said, and the estimate is never asked for."""

import pytest

import harness


def _run(state, tmp_path):
    report = harness.run_state(state, tmp_path)
    assert report["facts"]["island"], report["facts"]
    return report, report["facts"]


def test_no_click_needed(tmp_path):
    report, facts = _run("gen_generate", tmp_path)
    assert facts["face"]["estimate"] == "≈ $0.067 est." and facts["face"]["route"] == "openrouter.ai", facts
    assert [g["text"] for g in facts["generate"]] == ["Generate, ≈ $0.07"], facts
    assert facts["face"]["last_run"] == "3 images, $0.20 billed against a $0.21 estimate, rated 4", "the results row's line reaches the column"
    assert harness.token_failures(report) == [], report["surfaces"]


def test_click_needed(tmp_path):
    report, facts = _run("gen_spend", tmp_path)
    assert [g["text"] for g in facts["generate"]] == ["Spend $0.40"], facts
    assert facts["generate"][0]["mixar_variant"] == "ACCENT", facts
    assert harness.token_failures(report) == [], report["surfaces"]


def test_refused(tmp_path):
    report, facts = _run("gen_refused", tmp_path)
    assert facts["face"]["button_kind"] == "refused", facts
    assert facts["face"]["refusal"] == "openrouter is off: switch it on in Privacy to let data leave", facts
    assert facts["estimate_calls"] == 0, "a route that is off asks nothing"
    assert facts["generate"] and all(g.get("enabled") is False for g in facts["generate"]), facts
    assert facts["generate"][0]["tip"] == facts["face"]["refusal"], "the hover says why"
