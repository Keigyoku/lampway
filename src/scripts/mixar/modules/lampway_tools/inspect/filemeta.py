# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender Lab summaries, with every external path reduced before disclosure."""
from pathlib import Path
import bpy
from ._vendor import datablocks, missing_files, of_linked_libraries, path_info, usage_guess


def hint(value, root, *, basename=False):
    path = Path(bpy.path.abspath(value)).resolve()
    if not basename:
        try:
            return path.relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            pass
    return path.name


def measure(root):
    path = path_info.main(None)
    libraries = of_linked_libraries.main(None)
    missing = missing_files.main(None)
    usage = usage_guess.main(None)
    return {'path': hint(path.filepath, root) if path.filepath else None,
            'unsaved': bool(path.is_dirty or not path.is_saved), 'saved_age_s': path.age_seconds,
            'backups': [{**row, 'path': hint(row['path'], root)} for row in path.backups or []],
            'datablocks': datablocks.main(None).datablock_counts,
            'missing_files': [{'kind': row['id_type'], 'name': row['id_name'],
                              'path': hint(row['path'], root, basename=True)} for row in missing.missing_files],
            'libraries': [{'name': Path(row['name']).name, 'path': hint(row['filepath'], root), 'indirect': indirect}
                          for indirect, rows in ((False, libraries.direct_libraries), (True, libraries.indirect_libraries)) for row in rows],
            'usage_guess': [{'use': use, 'score': scores['score']} for use, scores in usage.usage_guesses.items()]}
