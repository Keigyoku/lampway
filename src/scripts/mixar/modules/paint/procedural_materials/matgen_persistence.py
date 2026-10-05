# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The user's own procedural materials, kept in the user data directory:
``<user data>/mixar/matgen/<material_id>.py`` plus one ``matgen_catalog.json`` listing them."""

import json
import os
import re

import bpy

from .material_registry import ProceduralMaterial


def _get_matgen_paths():
    """(directory of material scripts, catalog json path)."""
    base = bpy.utils.user_resource("DATAFILES", path="lampway", create=True)
    return os.path.join(base, "matgen"), os.path.join(base, "matgen_catalog.json")


def _safe_filename(material_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", material_id) or "material"


def _read_catalog(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return list(json.load(fh).get("materials", []))


def save_material(material: ProceduralMaterial) -> ProceduralMaterial:
    """Write the script to disk, upsert the catalog row, and return the material pointing at the script file."""
    directory, catalog_path = _get_matgen_paths()
    os.makedirs(directory, exist_ok=True)
    script_path = os.path.join(directory, _safe_filename(material.material_id) + ".py")
    with open(script_path, "w", encoding="utf-8") as fh:
        fh.write(material.script)
    material.script_path = script_path
    rows = [r for r in _read_catalog(catalog_path) if r.get("material_id") != material.material_id]
    rows.append({"material_id": material.material_id, "name": material.name, "category": material.category,
                 "node_group_name": material.node_group_name, "description": material.description,
                 "script_path": script_path})
    with open(catalog_path, "w", encoding="utf-8") as fh:
        json.dump({"materials": rows}, fh, indent=1)
    return material


def load_materials() -> list:
    """The persisted materials, as registry entries (scripts are read on demand from ``script_path``)."""
    _, catalog_path = _get_matgen_paths()
    return [ProceduralMaterial(material_id=r["material_id"], name=r.get("name", r["material_id"]),
                               category=r.get("category", "ai_generated"), script_path=r.get("script_path", ""),
                               node_group_name=r.get("node_group_name", ""), description=r.get("description", ""))
            for r in _read_catalog(catalog_path)]
