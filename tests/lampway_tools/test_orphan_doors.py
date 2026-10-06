# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every orphan-lane tool declares what it consumes (specs/canon/normalization DOOR.md §2) before the door exists: each exported tool has a row,
each row names only the tool's own parameters, and every need is in canonical_asset's vocabulary (SCHEMA.md §3-4)."""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import orphan_doors as D  # noqa: E402

LT = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools"
KINDS = {"mesh", "rigged_mesh", "skeleton", "animation_clip", "texture", "material", "part", "set"}
SCALES = {"real", "generator_normalised", "unknown"}
ROLES = {"basecolor", "normal", "roughness", "metallic", "ao", "orm", "height", "displacement", "emission", "opacity", "mask", "material_id",
         "curvature", "hdri", "reference"}


def _tools(path):
    out = {}
    for n in ast.parse(path.read_text()).body:
        if isinstance(n, ast.FunctionDef) and any(getattr(d.func if isinstance(d, ast.Call) else d, "id", "") == "tool" for d in n.decorator_list):   # @tool or @tool(consumes=...)
            out[n.name] = {a.arg for a in n.args.args + n.args.kwonlyargs}
    return out


def test_every_orphan_tool_declares_what_it_consumes_in_its_own_parameters():
    tools = _tools(LT / "orphans_api.py")
    assert set(tools) == set(D.CONSUMES), set(tools) ^ set(D.CONSUMES)
    api = _tools(LT / "api.py")
    for table, params in ((D.CONSUMES, tools), (D.EXTENDED, api)):
        for name, row in table.items():
            if "none" in row:
                assert isinstance(row["none"], str) and len(row["none"]) > 10, name
                continue
            assert row and set(row) <= params[name], (name, set(row) - params[name])
            for arg, n in row.items():
                assert set(n["kind"]) <= KINDS and n["kind"], (name, arg)
                assert set(n["scale"]) <= SCALES and n["scale"], (name, arg)
                assert set(n["roles"]) <= ROLES and (not n["roles"] or n["kind"] == ("texture",)), (name, arg)
                assert n["convention"] in (None, "blender", "ue_axes") and n["welded"] in (None, True), (name, arg)


def test_every_ported_runner_tool_of_this_lane_declares_too():
    import re
    runner = set(re.findall(r'_t\("([a-z_]+)"', (LT / "runner.py").read_text()))
    assert set(D.RUNNER) <= runner
    for name in ("export_parts", "verify_set", "render_final", "judge_pack", "gen_parts_table", "libwiki"):
        assert name in D.RUNNER, name


def test_tools_with_absolute_thresholds_accept_only_real_scale():
    for name, arg in (("mesh_local_edit", "object"), ("mesh_join_boolean", "objects"), ("uv_check", "object"), ("edit_locality_check", "before"),
                      ("multi_piece_material", "pieces")):
        assert D.CONSUMES[name][arg]["scale"] == ("real",), name
