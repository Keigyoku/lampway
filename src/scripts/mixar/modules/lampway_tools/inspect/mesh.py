# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read topology using the defect-scan engine's existing shells/loops/descriptor."""
import bmesh
from ..features import defect_scan as DS


def measure(ob, scale=1, deep=False):
    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        bm.transform(ob.matrix_world)
        for vertex in bm.verts:
            vertex.co *= scale
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.normal_update()
        shells = sorted(DS._shells(bm), key=lambda group: min(face.index for face in group))
        shell_rows = [{'id': i, 'faces': len(group),
                       'closed': all(len(edge.link_faces) == 2 for face in group for edge in face.edges),
                       'area_m2': round(sum(face.calc_area() for face in group), 6)} for i, group in enumerate(shells)]
        hole_rows = []
        for edges, faces in DS._open_loops(bm):
            descriptor = DS._descriptor(faces)
            rim_vertices = {vertex for edge in edges for vertex in edge.verts}
            rim_center = [sum(vertex.co[axis] for vertex in rim_vertices) / len(rim_vertices) for axis in range(3)]
            hole_rows.append({'edges': len(edges), 'rim_length_m': round(sum(edge.calc_length() for edge in edges), 4),
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
                              'flipped_shells': None},
                  'skipped': [{'object': ob.name, 'section': 'flipped_shells',
                               'reason': 'The orientation engine needs a metric-bmesh measurement interface'}]}
    finally:
        bm.free()
    if not result['shells']:
        result['defects']['flipped_shells'] = 0
        result['skipped'] = []
        if deep:
            result['intersections'], result['thin_regions'] = [], []
        return result
    if deep and (scale != 1 or getattr(ob, 'is_evaluated', False)):
        result['skipped'].extend({'object': ob.name, 'section': section,
                                  'reason': 'The deep scan engine cannot yet consume the evaluated mesh in scene metres'}
                                 for section in ('intersections', 'thin_regions'))
    elif deep and len(ob.data.polygons):
        scanned = DS.run(ob.name, kinds=['intersection', 'thin', 'flipped_shell'], max_candidates=500)
        result['intersections'] = [candidate for candidate in scanned['candidates'] if candidate['kind'] == 'intersection']
        result['thin_regions'] = [candidate for candidate in scanned['candidates'] if candidate['kind'] == 'thin']
        result['defects']['flipped_shells'] = scanned['counts'].get('flipped_shell', 0)
        result['skipped'] = []
    elif deep:
        result['intersections'], result['thin_regions'] = [], []
        result['defects']['flipped_shells'] = 0
        result['skipped'] = []
    return result
