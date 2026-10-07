# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One declared facing handoff: raw arrays turn once; canonical arrays already face -Y."""
import json
import numpy as np


def load_piece(path, turn):
    with np.load(path, allow_pickle=False) as data:
        vertices = data['V'].astype(float)
        triangles = data['T'].copy()
        canon = json.loads(str(data['canon'])) if 'canon' in data.files else None
    if canon is not None:
        if float(turn) != 0:
            raise ValueError('canonical piece already has its declared -Y frame: use turn_deg 0 (do not apply its source turn twice)')
        return vertices, triangles
    angle = np.radians(float(turn))
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0],
                         [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    return vertices @ rotation.T, triangles
