# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read topology using the defect-scan engine's existing shells/loops/descriptor."""
import bmesh
from ..features import defect_scan as DS
from ..features import workflows as W


def measure(ob, scale=1, deep=False, budget=None):
    check = budget.check if budget else lambda: None
    check()
    if budget:
        budget.admit_geometry(ob.data)
    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        check()
        bm.transform(ob.matrix_world)
        for vertex in bm.verts:
            check()
            vertex.co *= scale
        # A reflected coordinate adapter must reverse traversal (canon 01 D.4).
        if ob.matrix_world.to_3x3().determinant() < 0:
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bm.faces.ensure_lookup_table()
        bm.faces.index_update()
        bm.edges.ensure_lookup_table()
        bm.normal_update()
        shells = sorted(DS._shells(bm, budget=budget), key=lambda group: min(face.index for face in group))
        shell_rows = [{'id': i, 'faces': len(group),
                       'closed': all(len(edge.link_faces) == 2 for face in group for edge in face.edges),
                       'area_m2': round(sum(face.calc_area() for face in group), 6)} for i, group in enumerate(shells)]
        hole_rows = []
        for edges, faces in DS._open_loops(bm, budget=budget):
            check()
            descriptor = DS._descriptor(faces, budget=budget)
            rim_vertices = {vertex for edge in edges for vertex in edge.verts}
            rim_center = [sum(vertex.co[axis] for vertex in rim_vertices) / len(rim_vertices) for axis in range(3)]
            hole_rows.append({'edges': len(edges), 'rim_length_m': DS._rim_length(edges, budget=budget),
                              'centroid': dict(zip('xyz', [round(float(v), 4) for v in rim_center])),
                              'normal': dict(zip('xyz', descriptor['normal']))})
        hole_rows.sort(key=lambda row: -row['rim_length_m'])
        hole_rows = [{'id': i, **row} for i, row in enumerate(hole_rows)]
        lengths = [len(face.verts) for face in bm.faces]
        result = {'object': ob.name, 'counts': {'verts': len(bm.verts), 'edges': len(bm.edges), 'faces': len(bm.faces),
                    'tris': sum(max(0, length - 2) for length in lengths), 'quads': lengths.count(4),
                    'ngons': sum(length > 4 for length in lengths), 'loose_verts': sum(not vertex.link_edges for vertex in bm.verts),
                    'loose_edges': sum(not edge.link_faces for edge in bm.edges)},
                  'manifold': {'non_manifold_edges': sum(not edge.is_manifold for edge in bm.edges),
                               'boundary_edges': sum(edge.is_boundary for edge in bm.edges)},
                  'shells': shell_rows, 'holes': hole_rows, 'holes_total': len(hole_rows),
                  'defects': {'degenerate': sum(face.calc_area() < 1e-10 for face in bm.faces),
                              'isolated_tri': sum(len(group) == 1 and len(group[0].verts) == 3 for group in shells),
                              'flipped_shells': 0}, 'skipped': []}
        if shells:
            check()
            result['defects']['flipped_shells'] = sum(
                row['outward_fraction'] < W.FLIPPED_BELOW
                for row in W.shell_orientation_bmesh(bm, eps=1e-4 * scale, budget=budget))
        if deep:
            scanned = DS.scan_bmesh(bm, piece=ob.name, kinds=['intersection', 'thin'], budget=budget)
            result['intersections'] = [row for row in scanned['candidates'] if row['kind'] == 'intersection']
            result['thin_regions'] = [row for row in scanned['candidates'] if row['kind'] == 'thin']
            result['intersections_total'] = scanned['counts'].get('intersection', 0)
            result['thin_regions_total'] = scanned['counts'].get('thin', 0)
        check()
    finally:
        bm.free()
    return result
