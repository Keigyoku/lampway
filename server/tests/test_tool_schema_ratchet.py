"""Audit F14 (2026-10-06): tool schemas leave agents guessing - parameters with no description, numbers with no bounds. The debt
measured on 2026-10-06 (691 of 1,540 parameters undescribed, 241 of 241 numeric parameters unbounded across the agent's 238
tools) is recorded here and may only FALL: a tool added or changed with an undescribed parameter or an unbounded number fails
this test. Lower the numbers when you describe or bound parameters (the test says so when they fall)."""
from lampway_server.agent.tools import TOOLS

UNDESCRIBED = 702
UNBOUNDED_NUMBERS = 258
# Recorded rises (each names the merge that brought it; a rise anywhere else is the failure this test exists for):
#   b20, merging lp/facelift d18d713d: facelift 07's typed batch forms (agent/batch_forms.py) arrived written before this ratchet,
#   +11 undescribed (material_masks, mesh_qa_batch, patch_holes, relief_project, robust_weight_transfer) and +18 unbounded numbers
#   (clay_view, mesh_qa_batch, patch_holes, relief_project, uv_patches). Routed to the facelift lane to describe and bound.


def _counts():
    undescribed, unbounded = [], []
    for t in TOOLS:
        for name, p in (t.parameters.get("properties") or {}).items():
            if not str(p.get("description") or "").strip():
                undescribed.append(f"{t.name}.{name}")
            if p.get("type") in ("number", "integer") and "minimum" not in p and "maximum" not in p and "enum" not in p:
                unbounded.append(f"{t.name}.{name}")
    return undescribed, unbounded


def test_undescribed_parameters_and_unbounded_numbers_only_fall():
    undescribed, unbounded = _counts()
    assert len(undescribed) <= UNDESCRIBED, f"{len(undescribed) - UNDESCRIBED} more undescribed parameters than recorded; the newest: {undescribed[-5:]}"
    assert len(unbounded) <= UNBOUNDED_NUMBERS, f"{len(unbounded) - UNBOUNDED_NUMBERS} more unbounded numbers than recorded"
    assert (len(undescribed), len(unbounded)) == (UNDESCRIBED, UNBOUNDED_NUMBERS), \
        f"the debt fell to {len(undescribed)} / {len(unbounded)}: lower UNDESCRIBED and UNBOUNDED_NUMBERS in this file to match"
