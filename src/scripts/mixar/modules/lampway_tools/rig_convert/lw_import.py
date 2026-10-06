# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rig_convert recipes run in a headless Blender that loads them by path; their FBX imports go through Lampway's canon_io (the ONLY
module that calls Blender's importers, DOOR.md 1), loaded by path the same way, so every datablock an import makes is stamped lw_raw."""
import importlib.util as _u
import os as _os

_spec = _u.spec_from_file_location("_lampway_canon_io", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "canon_io.py"))
io = _u.module_from_spec(_spec)
_spec.loader.exec_module(io)


def import_raw(path, **settings):
    """canon_io.import_raw: the import's record (what it made, the file's sha256, the settings)."""
    return io.import_raw(path, **settings)
