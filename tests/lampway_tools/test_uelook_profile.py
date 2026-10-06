# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE profile (lampway.ue-profile/1, specs/ue_parity/contracts/ue_look.md §4): one file describes the UE scene a piece is
judged in. Every field is required (no defaults inside the tool); the captain's open choices are NAMED fields whose shipped
values are documented defaults, never constants in code."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.ue import profile as PR  # noqa: E402

OPEN_CHOICES = {"light_units.k": 683, "judgement_surface": "capture", "project.cvars.r.Material.EnergyConservation": 0,
                "preview.texture_compression": "source", "export.precision": "standard"}


def _get(d, dotted):
    if dotted.startswith("project.cvars."):
        return d["project"]["cvars"][dotted[len("project.cvars."):]]
    for k in dotted.split("."):
        d = d[k]
    return d


def test_the_shipped_default_carries_every_open_choice_as_a_named_field():
    p = PR.load(PR.DEFAULT_PROFILE)
    assert p["schema"] == "lampway.ue-profile/1" and p["source"] == "engine-defaults"
    for field, value in OPEN_CHOICES.items():
        assert _get(p, field) == value, field
    assert set(PR.OPEN_CHOICES) == set(OPEN_CHOICES)                                 # the code names the same five


def test_the_hash_is_of_the_canonical_content_not_the_file_bytes(tmp_path):
    p = PR.load(PR.DEFAULT_PROFILE)
    q = tmp_path / "p.json"
    q.write_text(json.dumps(p, indent=4, sort_keys=False))
    assert PR.sha256(PR.load(q)) == PR.sha256(p) and len(PR.sha256(p)) == 64
    p2 = copy.deepcopy(p)
    p2["light_units"]["k"] = 1
    assert PR.sha256(p2) != PR.sha256(p)


@pytest.mark.parametrize("path, value, message", [
    (("light_units",), None, "light_units is required"),
    (("light_units", "k"), 0, "light_units.k must be a positive number"),
    (("judgement_surface",), "monitor", "judgement_surface is capture, viewport or map:<name>"),
    (("preview", "texture_compression"), "bc7", "preview.texture_compression is source or bc_decoded"),
    (("export", "precision"), "max", "export.precision is standard or hero"),
    (("schema",), "lampway.ue-profile/0", "schema must be lampway.ue-profile/1"),
])
def test_a_bad_or_missing_field_is_refused_by_name(tmp_path, path, value, message):
    p = PR.load(PR.DEFAULT_PROFILE)
    node = p
    for k in path[:-1]:
        node = node[k]
    if value is None:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    q = tmp_path / "bad.json"
    q.write_text(json.dumps(p))
    with pytest.raises(PR.ProfileError, match=message.replace(".", r"\.").replace("(", r"\(").replace(")", r"\)")):
        PR.load(q)


def test_exposure_formula():
    """T-EXP-00: k = 683, defaults -> +0.509 stops; k = 1 -> -8.907 (COL-08)."""
    p = PR.load(PR.DEFAULT_PROFILE)
    assert round(PR.exposure_stops(p), 3) == 0.509
    p["light_units"]["k"] = 1
    assert round(PR.exposure_stops(p), 3) == -8.907
