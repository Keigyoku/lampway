# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Segment labels without executing segment_mesh's split or hide steps."""
import bmesh
from ..features import segment as S, defect_scan as DS


def measure(ob, scale=1, method='shells', angle=40):
    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        bm.faces.ensure_lookup_table()
        uv_layer = bm.loops.layers.uv.active
        if method == 'uv_islands' and uv_layer is None:
            raise ValueError('No UV layer: call lampway_uv_unwrap or use method=shells')
        labels = ({face.index: face.material_index for face in bm.faces} if method == 'materials'
                  else S._labels(bm, method, angle, uv_layer))
        S._merge_small(bm, labels, 1)
        bm.transform(ob.matrix_world)
        for vertex in bm.verts:
            vertex.co *= scale
        groups = {}
        for face in bm.faces:
            groups.setdefault(labels[face.index], []).append(face)
        rows = []
        for i, faces in sorted(groups.items()):
            descriptor = DS._descriptor(faces)
            materials = sorted({face.material_index for face in faces})
            points = [vertex.co for face in faces for vertex in face.verts]
            lo = [min(point[axis] for point in points) for axis in range(3)]
            hi = [max(point[axis] for point in points) for axis in range(3)]
            rows.append({'id': i, 'faces': len(faces), 'area_m2': round(descriptor['area_m2'], 6),
                         'material': materials[0] if len(materials) == 1 else None,
                         'bounds': {'min': [round(v, 4) for v in lo], 'max': [round(v, 4) for v in hi]},
                         'centroid': [round((a + b) / 2, 4) for a, b in zip(lo, hi)]})
        return {'object': ob.name, 'method': method, 'parts': rows}
    finally:
        bm.free()
