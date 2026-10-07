# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read UV metrics with canon 13's island, signed-area, seam and per-tile raster engines."""
import bmesh
import numpy as np
from ..features import uv_islands as UI, uv_check as UC


def measure(ob, scale=1, texture_size=2048):
    layers = [{'name': layer.name, 'active': layer == ob.data.uv_layers.active} for layer in ob.data.uv_layers]
    result = {'object': ob.name, 'layers': layers, 'islands': [], 'islands_total': 0,
              'utilization': 0.0, 'overlap_fraction': 0.0, 'flipped_faces': 0, 'seam_length_m': 0.0,
              'density': {'mean_px_m': None, 'cv': None}, 'tiles': [], 'crossing_tiles': 0}
    if not layers:
        return result
    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        bm.faces.ensure_lookup_table()
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None or not bm.faces:
            return result
        labels = UI.island_ids(bm, uv_layer)
        groups = {}
        for face in bm.faces:
            groups.setdefault(int(labels[face.index]), []).append(face)
        rows = UC._island_rows(groups, uv_layer, ob.matrix_world, texture_size)
        islands = [{'id': row['index'], 'faces': row['faces'], 'uv_area': row['area_uv'],
                    'density_px_m': round(row['density_px_m'] / scale, 4) if row['density_px_m'] is not None else None,
                    'bounds': row['bbox'], 'tiles': row['tiles']} for row in rows]
        islands.sort(key=lambda row: -row['uv_area'])
        overlap, rasters = UC._overlaps(groups, uv_layer, 1024)
        # Utilization is coverage of tile 1001; overlap is measured across all used tiles.
        masks = [tiles[1001] for tiles in rasters.values() if 1001 in tiles]
        utilization = float(np.logical_or.reduce(masks).mean()) if masks else 0.0
        signs = np.array([np.sign(UC._signed_area([face], uv_layer)) for face in bm.faces])
        majority = 1 if np.count_nonzero(signs > 0) >= np.count_nonzero(signs < 0) else -1
        flipped = int(np.count_nonzero(signs == -majority))
        densities = np.array([row['density_px_m'] for row in islands if row['density_px_m'] is not None])
        # Measure seams before rounding, in world coordinates; the legacy score row rounds to centimetres.
        bm.transform(ob.matrix_world)
        seam = UI._seam_length(bm, uv_layer) * scale
        result.update(islands=islands, islands_total=len(islands), utilization=round(utilization, 4),
                      overlap_fraction=round(overlap['fraction'], 4), flipped_faces=flipped, seam_length_m=round(seam, 4),
                      density={'mean_px_m': round(float(densities.mean()), 4) if len(densities) else None,
                               'cv': round(float(densities.std() / densities.mean()), 4) if len(densities) and densities.mean() else None},
                      tiles=sorted({tile for row in islands for tile in row['tiles']}),
                      crossing_tiles=sum(len(row['tiles']) > 1 for row in islands))
        return result
    finally:
        bm.free()
