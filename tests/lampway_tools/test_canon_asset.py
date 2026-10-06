# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""N0 (specs/canon/normalization contracts/canon_asset.md): the schema module `canon_asset`, `lampway.canonical-asset/1`.

The schema's own self-test cases (canonical-asset.examples.json: 3 valid, 7 invalid) run through the vendored validator Blender's
python can use, and - where the jsonschema package is importable - through jsonschema too, with a randomized mutation run showing
the two agree. Then the (code) invariants JSON Schema cannot express, `satisfies`, and the refusals of contract section 8."""

import copy
import json
import os
import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from mixar.modules.lampway_tools import canon_asset as CA  # noqa: E402

EX = json.loads((Path(__file__).resolve().parents[2] / "docs/canon/normalization/canonical-asset.examples.json").read_text())
for extra in filter(None, os.environ.get("LAMPWAY_TEST_PYDEPS", "").split(os.pathsep)):
    sys.path.append(extra)
try:
    import jsonschema
except ImportError:                                                          # the cross-validator is optional; its test says so
    jsonschema = None


def merge(base, patch):
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def docs():
    valid = []
    for case in EX["valid"]:
        valid.append(case["doc"] if "doc" in case else merge(valid[0], case["patch"]))
    invalid = [(c["name"], merge(valid[c["base"]], c["patch"])) for c in EX["invalid"]]
    return valid, invalid


def test_the_schema_ships_beside_the_module_and_is_its_version():
    s = CA.load_schema()
    assert s["$id"] == CA.SCHEMA_ID == "lampway.canonical-asset/1" and set(CA.KINDS) == set(s["properties"]["kind"]["enum"])


def test_the_selftest_cases_through_the_vendored_validator():
    valid, invalid = docs()
    for d in valid:
        assert CA.schema_errors(d) == [], CA.schema_errors(d)
    for name, d in invalid:
        assert CA.schema_errors(d), name


@pytest.mark.skipif(jsonschema is None, reason="jsonschema is not importable here (set LAMPWAY_TEST_PYDEPS to a dir holding it)")
def test_the_vendored_validator_agrees_with_jsonschema_on_200_mutations():
    schema = CA.load_schema()
    ref = jsonschema.Draft202012Validator(schema)
    valid, invalid = docs()
    rng = random.Random(7)
    pool = valid + [d for _n, d in invalid]
    leaves = []

    def paths(x, p=()):
        if isinstance(x, dict):
            for k, v in x.items():
                yield from paths(v, p + (k,))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                yield from paths(v, p + (i,))
        yield p
    for _ in range(200):
        d = copy.deepcopy(rng.choice(pool))
        ps = [p for p in paths(d) if p]
        p = rng.choice(ps)
        parent = d
        for k in p[:-1]:
            parent = parent[k]
        op = rng.choice(["drop", "str", "num", "neg", "bool", "null", "list"])
        if op == "drop" and isinstance(parent, dict):
            parent.pop(p[-1])
        else:
            parent[p[-1]] = {"str": "x", "num": 3.5, "neg": -1, "bool": True, "null": None, "list": [], "drop": "y"}[op]
        leaves.append((bool(list(ref.iter_errors(d))), bool(CA.schema_errors(d)), p, op))
    disagree = [x for x in leaves if x[0] != x[1]]
    assert not disagree, disagree[:5]


def _skeleton_doc():
    valid, _ = docs()
    d = copy.deepcopy(valid[0])
    d["kind"] = "skeleton"
    d.pop("pivot", None)
    eye = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
    d["body"] = {"reference_skeleton": {"id": "custom", "sha256": "a" * 64}, "convention": "blender",
                 "rest_pose": {"name": "rest", "sha256": "b" * 64}, "naming": {"family": "custom", "map_sha256": "c" * 64, "unmapped": []},
                 "roster": {"complete": True, "missing": []}, "root": {"name": "root", "at_origin": True}, "non_uniform_bone_scale": False,
                 "bones": [{"name": "root", "canonical_name": "root", "parent": None, "head_m": [0, 0, 0], "along": [0, 0, 1.0], "along_source": "child_head",
                            "frame": eye, "length_m": 0.5, "deform": True},
                           {"name": "spine", "canonical_name": "spine_01", "parent": "root", "head_m": [0, 0, 0.5], "along": [0, 0, 1.0],
                            "along_source": "leaf_parent_line", "frame": eye, "length_m": 0.4, "deform": True}]}
    return d


def test_a_well_formed_skeleton_has_no_code_errors():
    d = _skeleton_doc()
    assert CA.schema_errors(d) == [] and CA.validate(d) == []


def test_code_invariants_refuse_a_left_handed_frame_a_non_unit_along_and_a_child_before_its_parent():
    d = _skeleton_doc()
    d["body"]["bones"][1]["frame"] = [[-1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
    assert any("spine" in e and "det" in e for e in CA.validate(d))
    d = _skeleton_doc()
    d["body"]["bones"][1]["along"] = [0, 0, 2.0]
    assert any("spine" in e and "unit" in e for e in CA.validate(d))
    d = _skeleton_doc()
    d["body"]["bones"].reverse()
    assert any("before its parent" in e for e in CA.validate(d))


def test_the_axis_map_must_have_the_determinant_it_declares():
    valid, _ = docs()
    d = copy.deepcopy(valid[0])
    d["conventions"]["axis_map"] = [[1, 0, 0], [0, 1, 0], [0, 0, -1]]
    assert any("axis_map" in e for e in CA.validate(d))


def test_a_newer_version_or_an_interchange_frame_is_refused_by_name():
    valid, _ = docs()
    d = copy.deepcopy(valid[0])
    d["schema_version"] = 2
    assert any("newer than this Lampway" in e for e in CA.validate(d))
    d = copy.deepcopy(valid[0])
    d["conventions"]["frame"] = "titan.canonical-mesh/1"
    assert any("not a working-canonical document" in e for e in CA.validate(d))


def test_satisfies_names_each_unmet_need():
    valid, _ = docs()
    seed, placed = valid[0], valid[1]
    assert CA.satisfies(seed, CA.Need(kind=("mesh",), scale=("real", "generator_normalised"))) == []
    unmet = CA.satisfies(seed, CA.Need(kind=("mesh",), scale=("real",)))
    assert len(unmet) == 1 and "scale" in unmet[0] and "generator_normalised" in unmet[0]
    assert CA.satisfies(placed, CA.Need(kind=("mesh",), scale=("real",))) == []
    assert any("kind" in e for e in CA.satisfies(seed, CA.Need(kind=("skeleton",))))
    tex = valid[2]
    assert CA.satisfies(tex, CA.Need(kind=("texture",), scale=CA.ANY_SCALE, roles=("normal",))) == []
    assert any("role" in e for e in CA.satisfies(tex, CA.Need(kind=("texture",), scale=CA.ANY_SCALE, roles=("basecolor",))))


def test_check_compares_the_document_with_the_measured_facts():
    valid, _ = docs()
    d = valid[0]
    b = d["body"]
    facts = {"object_matrix": np.eye(4).tolist(), "scene_scale_length": 1.0, "bbox_min_m": b["bbox_min_m"], "bbox_max_m": b["bbox_max_m"],
             "geometry_sha256": b["geometry_sha256"]}
    assert CA.check(d, facts) == []
    assert any("geometry_sha256" in e for e in CA.check(d, dict(facts, geometry_sha256="0" * 64)))
    assert any("matrix" in e for e in CA.check(d, dict(facts, object_matrix=(2 * np.eye(4)).tolist())))
    assert any("scale_length" in e for e in CA.check(d, dict(facts, scene_scale_length=0.01)))
    assert any("bbox" in e for e in CA.check(d, dict(facts, bbox_max_m=[9, 9, 9])))


def test_the_settings_are_named_and_only_d4_is_still_owed():
    assert CA.SETTINGS["weld_m"]["value"] == 1e-5 and CA.SETTINGS["weld_guard_fraction"]["value"] == 0.05
    assert CA.SETTINGS["pivot_rule"]["value"] == "bbox_bottom_centre"
    owed = {k for k, v in CA.SETTINGS.items() if v.get("needs_decision")}
    assert owed == {"pair_scale_group", "facing_margin"}, owed
    assert CA.SETTINGS["facing_margin"]["value"] is None                    # D6's number was never given: no default is invented


def test_digest_is_sha256_hex():
    assert CA.digest(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_the_shipped_schema_is_the_canons_byte_for_byte():
    """The runtime ships its own copy (Blender's scripts tree has no docs/); it must be the canon's normalization schema exactly."""
    root = Path(__file__).resolve().parents[2]
    shipped = root / "src/scripts/mixar/modules/lampway_tools/canon/canonical-asset.schema.json"
    assert shipped.read_bytes() == (root / "docs/canon/normalization/canonical-asset.schema.json").read_bytes()
