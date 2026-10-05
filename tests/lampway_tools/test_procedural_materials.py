# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The local procedural-material library that replaces the withheld upstream package.

Contract (what the paint UI, the layer helpers and the agent tools read):
* a registry of ``ProceduralMaterial`` (material_id, name, category, script, script_path, node_group_name);
* ``is_custom_material(x)`` is True only for a registered material id (layer-type strings stay layer types);
* ``get_node_group`` returns an existing node group, builds one from the material's script, or None;
* the user's own materials persist in the user data dir and load back; there is no hosted catalogue, and
  asking for AI generation says so instead of pretending.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/paint/procedural_materials"


def _load(name):
    """Load a submodule by path: importing the real paint package needs Blender."""
    parent = "mixar.modules.paint.procedural_materials"
    for p in ("mixar", "mixar.modules", "mixar.modules.paint", parent):
        if p not in sys.modules:
            mod = types.ModuleType(p)
            mod.__path__ = []
            sys.modules[p] = mod
    sys.modules[parent].__path__ = [str(PKG)]
    full = f"{parent}.{name}"
    spec = importlib.util.spec_from_file_location(full, PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _fresh_modules():
    """Each test loads the package afresh: the import system caches submodules as parent attributes."""
    for key in [k for k in sys.modules if k.startswith("mixar.modules.paint.procedural_materials")]:
        del sys.modules[key]
    yield


@pytest.fixture
def reg():
    mod = _load("material_registry")
    mod.get_registry().clear()
    return mod


def _mat(reg, **kw):
    base = dict(material_id="oak", name="Oak", category="wood", script="")
    base.update(kw)
    return reg.ProceduralMaterial(**base)


def test_register_and_look_up(reg):
    reg.register_material(_mat(reg))
    assert reg.get_material("oak").name == "Oak"
    assert reg.get_material("nope") is None
    assert [m.material_id for m in reg.get_all_materials()] == ["oak"]


def test_categories_and_filter(reg):
    reg.register_material(_mat(reg))
    reg.register_material(_mat(reg, material_id="steel", name="Steel", category="metal"))
    assert reg.get_categories() == ["metal", "wood"]
    assert [m.material_id for m in reg.get_materials_by_category("metal")] == ["steel"]
    assert reg.get_materials_by_category("none") == []


def test_node_group_name_defaults_to_the_name(reg):
    assert _mat(reg).node_group_name == "Oak"
    assert _mat(reg, node_group_name="G").node_group_name == "G"


def test_is_custom_material_means_registered_id(reg):
    reg.register_material(_mat(reg))
    assert reg.is_custom_material("oak") is True
    assert reg.is_custom_material("NOISE") is False        # a built-in layer type
    assert reg.is_custom_material("") is False


def test_registering_again_overwrites(reg):
    reg.register_material(_mat(reg))
    reg.register_material(_mat(reg, name="Oak v2"))
    assert reg.get_material("oak").name == "Oak v2"
    assert len(reg.get_all_materials()) == 1


def test_unload_all_clears(reg):
    reg.register_material(_mat(reg))
    reg.unload_all_materials()
    assert reg.get_all_materials() == []


def test_load_server_catalog_is_a_documented_no_op(reg):
    assert reg.load_server_catalog() == 0
    assert reg.get_all_materials() == []


def test_get_node_group_none_for_unknown_id(reg):
    assert reg.get_node_group("unknown") is None


def test_get_node_group_runs_the_script_and_returns_the_group(reg):
    made = {}
    fake_bpy = reg.bpy
    groups = {}
    fake_bpy.data = types.SimpleNamespace(node_groups=types.SimpleNamespace(get=groups.get))

    def build(node_group_name):
        groups[node_group_name] = object()
        made["name"] = node_group_name

    reg._run_script = lambda script, material: build(material.node_group_name)
    reg.register_material(_mat(reg, script="make()"))
    assert reg.get_node_group("oak") is groups["Oak"]
    assert made == {"name": "Oak"}
    made.clear()
    assert reg.get_node_group("oak") is groups["Oak"]       # now cached in bpy.data: the script does not run twice
    assert made == {}


def test_persistence_round_trip(tmp_path, monkeypatch):
    per = _load("matgen_persistence")
    reg = _load("material_registry")
    monkeypatch.setattr(per, "_get_matgen_paths", lambda: (str(tmp_path / "matgen"), str(tmp_path / "catalog.json")))
    m = reg.ProceduralMaterial(material_id="g1", name="Generated", category="ai_generated", script="# s\n", node_group_name="G")
    saved = per.save_material(m)
    assert Path(saved.script_path).read_text() == "# s\n"
    assert json.loads((tmp_path / "catalog.json").read_text())["materials"][0]["material_id"] == "g1"
    loaded = per.load_materials()
    assert [(x.material_id, x.node_group_name, x.script_path) for x in loaded] == [("g1", "G", saved.script_path)]


def test_load_matgen_materials_registers_the_persisted_ones(tmp_path, monkeypatch):
    per = _load("matgen_persistence")
    reg = _load("material_registry")
    reg.get_registry().clear()
    monkeypatch.setattr(per, "_get_matgen_paths", lambda: (str(tmp_path / "m"), str(tmp_path / "c.json")))
    per.save_material(reg.ProceduralMaterial(material_id="g1", name="Generated", category="ai_generated", script="x=1"))
    assert reg.load_matgen_materials() == 1
    assert reg.get_material("g1").category == "ai_generated"


def test_missing_catalog_loads_nothing(tmp_path, monkeypatch):
    per = _load("matgen_persistence")
    monkeypatch.setattr(per, "_get_matgen_paths", lambda: (str(tmp_path / "m"), str(tmp_path / "none.json")))
    assert per.load_materials() == []


def test_generation_is_honestly_unavailable():
    q = _load("matgen_queue")
    with pytest.raises(q.MatgenUnavailable) as exc:
        q.enqueue_matgen_job(prompt="oak wood")
    assert "no generation backend" in str(exc.value)
