# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 04 in the real build: the answered question is one line with its expander row."""

import harness


def test_the_answered_question_is_one_line(tmp_path):
    f = harness.run_state("chat_answered", tmp_path)["facts"]
    assert f["island"] and f["content"] == "Which glass? Clear, you answered 14:30" and f["actions"] == ["2 other choices"], f
