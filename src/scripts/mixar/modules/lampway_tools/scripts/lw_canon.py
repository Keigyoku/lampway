# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shelf's batch tools import ``lw_canon`` from the directory above their own, as they import ``axi_out``: Lampway's canon_io
(../canon_io.py, the ONLY module that calls Blender's importers) loaded by path, so a tool runs under any Blender, with or without
the ``mixar`` package importable. ``lw_canon.io.import_raw(path)`` replaces every direct importer call."""
import importlib.util as _u
import os as _os

_spec = _u.spec_from_file_location("_lampway_canon_io", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "canon_io.py"))
io = _u.module_from_spec(_spec)
_spec.loader.exec_module(io)
