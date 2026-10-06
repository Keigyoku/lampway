# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The captain's moodboard prompts as the reference-to-asset chain (O24 over workflow_graph): the graph, as data.

P1 anatomy sheet (the MetaHuman turnarounds) -> P2 armor adaptation (Image A the anatomy sheet, Image B the armor design) -> P3 fit-check (A anatomy,
B adaptation) -> P4 modular breakdown (A anatomy, B fit-check) -> P7 cutout sheet (A anatomy, B fit-check), then per piece: P5 multiview (A anatomy,
B breakdown), P6 the matched four single views (A anatomy, B that piece's multiview) and P8 the 3x2 turnaround (the piece's multiview as its reference).
Every node is a generation, so every node is a spend node (``studio_action: image_gen``): workflow_graph plans them and never runs them; one confirm
generates one image. The templates are the server's built-in moodboard-* prompts (tests/test_moodboard_parity.py proves nothing of the originals
was lost). Pure python."""

import re

VIEWS = ("FRONT (from directly in front of the wearer, looking at their chest)", "LEFT (from the wearer's own left side)",
         "BACK (from directly behind the wearer)", "RIGHT (from the wearer's own right side)")
TOOL, ACTION = "prompt_image", "image_gen"


def slug(piece: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(piece).lower()).strip("_")
    if not s:
        raise ValueError(f"a piece needs a name with letters or digits: {piece!r}")
    return s[:40]


def _node(nid, template, references, after, name, variables=None):
    return {"id": nid, "tool": TOOL, "after": list(after), "spend": True, "studio_action": ACTION,
            "args": {"template": template, "variables": dict(variables or {}), "references": references, "out_dir": f"moodboard/{name}/{nid}", "live": True}}


def graph(pieces, name="moodboard", example_sheet=False) -> dict:
    """The chain for these pieces. Inputs it needs: {{body_refs}} (the MetaHuman turnaround images) and {{armor_design}} (the concept armor);
    with example_sheet, {{example_sheet}} (a turnaround sheet to follow for layout, e.g. the Sandal sheet) rides every P8 node."""
    pieces = list(pieces or [])
    if not pieces:
        raise ValueError("name the pieces to carry through (helmet, chest armor, left greave ...)")
    if len({slug(p) for p in pieces}) != len(pieces):
        raise ValueError("two pieces share a name")
    A = "@anatomy.image"
    nodes = [_node("anatomy", "moodboard-anatomy-sheet", {"image_references": "{{body_refs}}"}, [], name),
             _node("adaptation", "moodboard-armor-adaptation", {"character_body": A, "design_plate": "{{armor_design}}"}, ["anatomy"], name),
             _node("fit_check", "moodboard-fit-check", {"character_body": A, "design_plate": "@adaptation.image"}, ["adaptation"], name),
             _node("breakdown", "moodboard-armor-breakdown", {"character_body": A, "design_plate": "@fit_check.image"}, ["fit_check"], name),
             _node("cutout", "moodboard-cutout-sheet", {"character_body": A, "design_plate": "@fit_check.image"}, ["breakdown", "fit_check"], name)]
    outputs = []
    for p in pieces:
        h = slug(p)
        mv = f"multiview_{h}"
        nodes.append(_node(mv, "moodboard-asset-multiview", {"character_body": A, "design_plate": "@breakdown.image"}, ["cutout", "breakdown"], name,
                           {"asset_name": p}))
        for v in VIEWS:
            nodes.append(_node(f"view_{h}_{v.split()[0].lower()}", "moodboard-asset-view", {"character_body": A, "design_plate": f"@{mv}.image"}, [mv], name,
                               {"asset_name": p, "view": v}))
        refs = {"reference_image": f"@{mv}.image"}
        if example_sheet:
            refs["image_references"] = "{{example_sheet}}"
        nodes.append(_node(f"turnaround_{h}", "moodboard-turnaround-3x2", refs, [mv], name, {"asset_name": p}))
        outputs.append(f"turnaround_{h}")
    return {"nodes": nodes, "outputs": outputs}
