# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Segment labels without executing segment_mesh's split or hide steps."""
import bmesh
from ..features import segment as S, defect_scan as DS


def measure(ob, scale=1, method='shells', angle=40, budget=None):
    check = budget.check if budget else lambda: None
    if budget:
        budget.admit_geometry(ob.data)
    bm = bmesh.new()
    try:
        check()
        bm.from_mesh(ob.data)
        check()
        bm.faces.ensure_lookup_table()
        uv_layer = bm.loops.layers.uv.active
        if method == 'uv_islands' and uv_layer is None:
            raise ValueError('No UV layer: call lampway_uv_unwrap or use method=shells')
        if method == 'materials':
            labels = {}
            for face in bm.faces:
                check()
                labels[face.index] = face.material_index
        else:
            labels = S._labels(bm, method, angle, uv_layer, budget=budget)
        # min_faces=1 cannot merge any nonempty region.
        bm.transform(ob.matrix_world)
        for vertex in bm.verts:
            check()
            vertex.co *= scale
        groups = {}
        for face in bm.faces:
            check()
            groups.setdefault(labels[face.index], []).append(face)
        rows = []
        for i, faces in sorted(groups.items()):
            check()
            descriptor = DS._descriptor(faces, budget=budget)
            materials = sorted({face.material_index for face in faces})
            points = []
            for face in faces:
                check()
                points.extend(vertex.co for vertex in face.verts)
            lo = [min(point[axis] for point in points) for axis in range(3)]
            hi = [max(point[axis] for point in points) for axis in range(3)]
            rows.append({'id': i, 'faces': len(faces), 'area_m2': round(descriptor['area_m2'], 6),
                         'material': materials[0] if len(materials) == 1 else None,
                         'bounds': {'min': [round(v, 4) for v in lo], 'max': [round(v, 4) for v in hi]},
                         'centroid': [round((a + b) / 2, 4) for a, b in zip(lo, hi)]})
        check()
        return {'object': ob.name, 'method': method, 'parts': rows}
    finally:
        bm.free()
