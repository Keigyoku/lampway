# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh QA: mesh defects as typed decisions (candidates, the captain's tags, rulings, a decision log).

  candidates  - open loops and floating shells with typed descriptors (the shelf's meshqa/mesh_qa.py)
  marks       - the three annotation tag layers (Red = Delete, Green = Mislabel, Yellow = Hole) read into faces,
                islands and loops (the shelf's captain_marks/ scripts)
  rulings     - the rulings files the rebuild reads (deletions, relabels, texel overrides, merged candidates)
  decisions   - the JSONL decision log, shaped like the project's fit_state tool's
"""
