# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shelf's tools import ``axi_out`` from the directory above their own. This is that module: Lampway's AXI
implementation (../axi.py, a standalone file) loaded by path, so a tool runs under any interpreter, with or
without Blender, and with or without the ``mixar`` package importable."""
import importlib.util as _u
import os as _os

_spec = _u.spec_from_file_location("_lampway_axi", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "axi.py"))
_mod = _u.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
