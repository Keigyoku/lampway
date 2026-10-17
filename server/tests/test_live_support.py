# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Displayed terminal evidence must apply cursor-addressed redraws, not concatenate their bytes."""
import threading

from .live_support import PtyProcess


def terminal(raw, cols=40, rows=5):
    proc = PtyProcess.__new__(PtyProcess)
    proc.buf = bytearray(raw)
    proc.lock = threading.Lock()
    proc.cols, proc.rows = cols, rows
    return proc


def test_screen_reconstructs_a_prompt_completed_by_cursor_addressed_diffs():
    # Ink first draws the skeleton, then writes missing words into existing columns.
    raw = b"\x1b[2J\x1b[1;1Hwhat is       scene?\x1b[1;9Hin my"
    proc = terminal(raw)
    assert "what is in my scene?" in proc.screen_text()
    assert "what is in my scene?" not in proc.text(), "the legacy byte log remains useful for offset/slice marks"


def test_screen_does_not_claim_erased_text_is_still_displayed():
    proc = terminal(b"\x1b[1;1HThere is one cube.\r\x1b[2KNo cube remains.")
    displayed = proc.screen_text()
    assert "There is one cube." not in displayed
    assert "No cube remains." in displayed


def test_screen_uses_terminal_dimensions_and_utf8_split_across_reads():
    proc = terminal(b"\x1b[2;1H\xe2\x94", cols=20, rows=3)
    proc.buf.extend(b"\x82 There is one cube.")
    lines = proc.screen_text().splitlines()
    assert len(lines) == 3 and all(len(line) == 20 for line in lines)
    assert lines[1] == "\u2502 There is one cube."
