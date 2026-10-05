# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The procedural-material registry: what paint's layer stack, library popup and agent tools read.

A material is a node-group-building Blender script (``script`` inline, or ``script_path`` on disk) that
creates the node group ``node_group_name``. ``get_node_group`` returns the group if Blender already has it,
otherwise runs the script through the agent sandbox's AST guard and restricted builtins and returns what it made.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import bpy

logger = logging.getLogger(__name__)


@dataclass
class ProceduralMaterial:
    material_id: str
    name: str
    category: str = "custom"
    script: str = ""
    script_path: str = ""
    node_group_name: str = ""
    description: str = ""

    def __post_init__(self):
        if not self.node_group_name:
            self.node_group_name = self.name


class MaterialRegistry:
    def __init__(self):
        self._materials: Dict[str, ProceduralMaterial] = {}

    def register_material(self, material: ProceduralMaterial) -> None:
        self._materials[material.material_id] = material

    def get_material(self, material_id: str) -> Optional[ProceduralMaterial]:
        return self._materials.get(material_id)

    def get_all_materials(self) -> List[ProceduralMaterial]:
        return list(self._materials.values())

    def get_categories(self) -> List[str]:
        return sorted({m.category for m in self._materials.values()})

    def get_materials_by_category(self, category: str) -> List[ProceduralMaterial]:
        return [m for m in self._materials.values() if m.category == category]

    def clear(self) -> None:
        self._materials.clear()


_registry = MaterialRegistry()


def get_registry() -> MaterialRegistry:
    return _registry


def register_material(material: ProceduralMaterial) -> None:
    _registry.register_material(material)


def get_material(material_id: str) -> Optional[ProceduralMaterial]:
    return _registry.get_material(material_id)


def get_all_materials() -> List[ProceduralMaterial]:
    return _registry.get_all_materials()


def get_categories() -> List[str]:
    return _registry.get_categories()


def get_materials_by_category(category: str) -> List[ProceduralMaterial]:
    return _registry.get_materials_by_category(category)


def is_custom_material(layer_type) -> bool:
    """True when ``layer_type`` is a registered material id (built-in layer types are not)."""
    return bool(layer_type) and _registry.get_material(layer_type) is not None


def unload_all_materials() -> None:
    _registry.clear()


def load_matgen_materials() -> int:
    """Register the user's own persisted materials; returns how many were loaded."""
    from . import matgen_persistence

    loaded = matgen_persistence.load_materials()
    for material in loaded:
        _registry.register_material(material)
    return len(loaded)


def load_server_catalog() -> int:
    """There is no hosted catalogue: the library is local. Loads the user's own materials instead and
    returns the number of catalogue entries fetched (always 0)."""
    try:
        load_matgen_materials()
    except Exception:
        logger.warning("Failed to load the user's generated materials", exc_info=True)
    return 0


def _run_script(script: str, material: ProceduralMaterial) -> None:
    """Run a material script under the agent sandbox's guard: AST validation, restricted builtins."""
    import math

    import mathutils

    from mixar.modules.space_mixie_chat.core.sandbox_builtins import get_safe_builtins
    from mixar.modules.space_mixie_chat.core.sandbox_validator import validate_script_ast

    error = validate_script_ast(script)
    if error:
        raise RuntimeError(f"Material '{material.material_id}' script blocked: {error}")
    namespace = {"__builtins__": get_safe_builtins(), "__name__": "__material__",
                 "bpy": bpy, "mathutils": mathutils, "math": math}
    exec(compile(script, f"<material:{material.material_id}>", "exec"), namespace)  # noqa: S102


def _script_text(material: ProceduralMaterial) -> str:
    if material.script:
        return material.script
    if material.script_path:
        with open(material.script_path, encoding="utf-8") as fh:
            return fh.read()
    return ""


def get_node_group(material_id: str):
    """The material's node group: already in Blender, or built from its script; None if neither."""
    material = _registry.get_material(material_id)
    if material is None:
        return None
    existing = bpy.data.node_groups.get(material.node_group_name)
    if existing is not None:
        return existing
    script = _script_text(material)
    if not script:
        return None
    _run_script(script, material)
    return bpy.data.node_groups.get(material.node_group_name)


def get_node_group_blocking(material_id: str):
    """Same as ``get_node_group``: there is no download to wait for."""
    return get_node_group(material_id)
