# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""String literals of a C/C++ source file with comments removed (a small state machine, not a regex: ``"//"`` inside a string is not a comment and an apostrophe
inside a comment does not open a character literal)."""


def spans(text):
    """Yield ``(line_number, start, end)`` (offsets of the literal's inside, quotes excluded) for every string literal."""
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += text.count("\n", i, j)
            i = j
        elif c == "'":
            i += 1
            while i < n and text[i] != "'" and text[i] != "\n":
                i += 2 if text[i] == "\\" else 1
            i += 1
        elif c == '"':
            start, start_line = i + 1, line
            i += 1
            while i < n and text[i] != '"' and text[i] != "\n":
                i += 2 if text[i] == "\\" else 1
            yield start_line, start, i
            i += 1
        else:
            i += 1


def literals(text):
    """Yield ``(line_number, literal_text)`` for every string literal (escapes kept verbatim)."""
    for line, a, b in spans(text):
        yield line, text[a:b]
