"""Audit F14 (2026-10-06): tool schemas leave agents guessing - parameters with no description, numbers with no bounds. The debt
is recorded by parameter identity across the whole registry, including nested properties, numeric array items and schema
alternatives. Debt may only FALL: paying down one old entry cannot license an unrelated new defect. Remove repaired entries
from tool_schema_debt.json when this test reports them. The original top-level counts were 691 / 240."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from lampway_server.agent.providers.base import ToolSpec
from lampway_server.agent.tools import TOOLS

UNDESCRIBED = 691
UNBOUNDED_NUMBERS = 240
# Recorded rises (each names the merge that brought it; a rise anywhere else is the failure this test exists for):
#   b20, merging lp/facelift d18d713d: facelift 07's typed batch forms (agent/batch_forms.py) arrived written before this ratchet,
#   +11 undescribed (material_masks, mesh_qa_batch, patch_holes, relief_project, robust_weight_transfer) and +18 unbounded numbers
#   (clay_view, mesh_qa_batch, patch_holes, relief_project, uv_patches). Routed to the facelift lane to describe and bound:
#   paid back by the facelift lane (702 -> 691, 258 -> 240): every batch form parameter described and every number bounded.


def _counts(tools=None):
    undescribed, unbounded = [], []

    def visit(schema, path, parameter=False):
        if parameter and not str(schema.get("description") or "").strip():
            undescribed.append(path)
        types = schema.get("type", [])
        types = [types] if isinstance(types, str) else types
        if any(kind in types for kind in ("number", "integer")) and not any(k in schema for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "enum")):
            unbounded.append(path)
        for name, child in (schema.get("properties") or {}).items():
            visit(child, f"{path}.{name}", True)
        if isinstance(schema.get("items"), dict):
            visit(schema["items"], path + "[]")
        for name, child in (schema.get("$defs") or {}).items():
            visit(child, f"{path}.$defs.{name}")
        for keyword in ("oneOf", "anyOf", "allOf"):
            for index, child in enumerate(schema.get(keyword) or []):
                visit(child, f"{path}.{keyword}[{index}]")

    for tool in TOOLS if tools is None else tools:
        visit(tool.parameters, tool.name)
    return sorted(undescribed), sorted(unbounded)


def _assert_debt(tools=None):
    undescribed, unbounded = _counts(tools)
    baseline = json.loads(Path(__file__).with_name("tool_schema_debt.json").read_text())
    for kind, actual in (("undescribed", undescribed), ("unbounded", unbounded)):
        recorded = set(baseline[kind])
        introduced = set(actual) - recorded
        assert not introduced, f"new {kind} schema debt: {sorted(introduced)}"
        assert set(actual) == recorded, f"{kind} debt fell: remove repaired entries from tool_schema_debt.json: {sorted(recorded - set(actual))}"


def test_undescribed_parameters_and_unbounded_numbers_only_fall():
    _assert_debt()


@pytest.mark.parametrize("kind", ["description", "bounds"])
def test_new_debt_cannot_hide_behind_a_paid_down_legacy_parameter(kind):
    tools = deepcopy(TOOLS)
    for tool in tools:
        paid = False
        for parameter in tool.parameters.get("properties", {}).values():
            if kind == "description" and not parameter.get("description"):
                parameter["description"] = "Paid down legacy debt."
                paid = True
            elif kind == "bounds" and parameter.get("type") in ("number", "integer") and not any(k in parameter for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "enum")):
                parameter["minimum"] = 0
                paid = True
            if paid:
                break
        if paid:
            break
    parameter = {"type": "string"} if kind == "description" else {"type": "number", "description": "New number without a bound."}
    tools.append(ToolSpec("lampway_planted_new_tool", "Ratchet falsifier", {"type": "object", "properties": {"new_parameter": parameter}}))
    with pytest.raises(AssertionError, match="lampway_planted_new_tool"):
        _assert_debt(tools)


@pytest.mark.parametrize("parameter", [
    {"type": "object", "description": "Nested payload.", "properties": {"hidden": {"type": "string"}}},
    {"type": "array", "description": "Numeric list.", "items": {"type": "number"}},
])
def test_nested_schema_debt_cannot_enter_the_whole_registry(parameter):
    planted = [*TOOLS, ToolSpec("lampway_planted_new_tool", "Nested ratchet falsifier", {"type": "object", "properties": {"payload": parameter}})]
    with pytest.raises(AssertionError, match="lampway_planted_new_tool"):
        _assert_debt(planted)


@pytest.mark.parametrize('keyword,value', [('exclusiveMinimum', 0), ('exclusiveMaximum', 100)])
def test_exclusive_numeric_bounds_are_real_bounds_and_removal_introduces_debt(keyword, value):
    from jsonschema import Draft202012Validator
    parameter = {'type': 'number', 'description': 'Explicit exclusive numeric bound.', keyword: value}
    tool = ToolSpec('lampway_planted_new_tool', 'Exclusive bound falsifier', {'type': 'object', 'properties': {'value': parameter}})
    Draft202012Validator.check_schema(tool.parameters)
    assert _counts([tool]) == ([], [])
    del parameter[keyword]
    with pytest.raises(AssertionError, match='lampway_planted_new_tool'):
        _assert_debt([*TOOLS, tool])
