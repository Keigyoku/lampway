# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The clip table's cache (specs/mrmak/08 section 6): the panel draws these rows and never measures; Classify fills them, Apply names reads the proposed labels back."""

ROWS = []


def fill(result: dict) -> None:
    ROWS[:] = [{"action": c["action"], "primary": c["classification"]["primary"], "labels": c["classification"]["labels"], "speed": c["features"]["speed"], "loop": c["loop"]["loop"],
                "inferred": c["name"]["inferred"], "label": c["name"]["label"], "measured": c["name"]["measured"], "scales_joints": c["features"]["scales_joints"]} for c in result["clips"]]


def line(row: dict) -> str:
    loop = {True: "loop", False: "one-shot", None: "loop ?"}[row["loop"]]
    return f"{row['primary'] or 'no class'}  {row['speed']:.2f} H/s  {loop}" + ("  (inferred)" if row["inferred"] else "")
