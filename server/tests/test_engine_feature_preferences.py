# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Hermes helper layering is an independent, default-off user choice."""

import pytest

from lampway_server import capabilities as CAP
from lampway_server.engine import hermes_config as HC
from lampway_server.engine.wiring import WorkerBoard


def render(board):
    return HC.render(board, None, "http://127.0.0.1:8799/engine/v1", "fixture-token", "fixture-model")


@pytest.mark.parametrize("other", ["memory", "skills.write"])
def test_memory_and_skill_writes_do_not_opt_into_native_background_agents(tmp_path, other):
    board = CAP.Store(tmp_path)
    board.set(other, enabled=True)
    cfg = render(board)
    assert cfg["auxiliary"]["background_review"]["enabled"] is False
    assert cfg["curator"]["enabled"] is False


def test_all_three_native_features_default_off_and_have_independent_opt_ins(tmp_path):
    board = CAP.Store(tmp_path)
    assert render(board)["lampway_features"] == dict(subagents=False, schedule=False, background=False)
    for feature in ("subagents", "schedule", "background"):
        board.set(feature, enabled=True)
        flags = render(board)["lampway_features"]
        assert flags == {key: key == feature for key in flags}
        board.set(feature, enabled=False)


def test_explicit_background_choice_gates_both_auxiliary_review_and_curator(tmp_path):
    board = CAP.Store(tmp_path)
    board.set("memory", enabled=True)
    board.set("skills.write", enabled=True)
    board.set("background", enabled=True)
    cfg = render(board)
    assert cfg["auxiliary"]["background_review"]["enabled"] is True
    assert cfg["curator"]["enabled"] is True
    board.set("background", enabled=False)
    assert render(board)["auxiliary"]["background_review"]["enabled"] is False
    assert render(board)["curator"]["enabled"] is False


def test_main_agent_opt_ins_never_enable_native_helpers_for_swarm_workers(tmp_path):
    board = CAP.Store(tmp_path)
    for feature in ("subagents", "schedule", "background"):
        board.set(feature, enabled=True)
    assert render(WorkerBoard(board))["lampway_features"] == dict(
        subagents=False, schedule=False, background=False)
