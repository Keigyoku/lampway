# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Wave 6 tool functions (specs/wiki and specs/mixar_docs contracts the captain released as Wave 6). Plain functions: ``api.py`` wraps every name in
``TOOLS`` with its ``@tool`` envelope, so they join the one door (``api.call``) with the same refusal shape. Each docstring is the agent-facing
description; the server's Def (agent/wave6_tools.py) carries the same text."""

from . import settings as S

TOOLS = ("modular_character", "character_pipeline")


def _root() -> str:
    return str(S.load().project_root)


def _p(path) -> str:
    return "" if path in (None, "") else str(S.resolve_in_root(path, _root()))


def modular_character(action="validate", character_id="", parts=None, armature=None, allowed_outfits=None, poses=None, out_dir="export_parts"):
    """A character's interchangeable parts as one typed record. manifest {character_id, parts: [{object, role: head|body|hands|hair|garment|accessory,
    fixed_or_deforming, wearer_side: left|right|center|paired, bone (required for a fixed part)}], armature, allowed_outfits: [[part ids]], poses: rest |
    wiki8 | [poses]} writes <root>/<character_id>/manifest.json with the template fields. validate: one shared armature (two armatures are refused), the
    rest pose unchanged since the manifest, equal scales, each part's measured side against its declared one (the figure faces -Y, its left is +X), and
    weight_audit on every deforming part. outfit_matrix: per allowed outfit (in each pose) the body faces it leaves uncovered of the region any outfit
    covers (a ray from each face along its normal) and the body vertices poking through it; pass = both zero. hidden_body makes `<body>_hidden`, a copy
    without the faces every outfit covers, and is refused before a passing matrix or after anything changed since it. export_parts writes one FBX per
    part with the same armature under out_dir/<character_id>/. The full body is never deleted."""
    from .features import modular_character as M
    return M.run(_root(), action, character_id, parts, armature, allowed_outfits, poses, out_dir, resolve=_p)


def character_pipeline(character_id, parts, mode="plan", target="unreal_mannequin", from_stage=1, to_stage=13, stage=None, gate=None, evidence="", stage_calls=None):
    """The character route as thirteen gated stages: 1 reference pack, 2 generate parts (tripo.mesh, a spend), 3 prep and segment, 4 assemble (fit),
    5 retopology to the part budgets, 6 UV, 7 bake, 8 projection texture (a spend), 9 auto rig, 10 weights, 11 secondary chains, 12 skeleton check and
    export, 13 retarget test. parts: [{name, budget (triangles), rigid_bone}]. mode plan lists the stages with their tools (missing_tools = not built
    yet), spend flags, credits and state. mode record {stage, gate: pass|fail, evidence} appends a gate; a stage needs the stage before it passed, and
    rigging (9-11) needs the assembly (4) passed: "fit before rigging". mode run executes stage_calls {"<n>": [{tool, args}]} for from_stage..to_stage,
    each a tool of that stage, and stops at the first failed gate, the first spend stage (needs_approval: the user's click confirms spends, never this
    tool) and a stage whose tools are not built. target metahuman adds the MetaHuman conform as a needs_decision UE leg. Run record:
    <root>/<character_id>/pipeline/run.json."""
    from .pipeline import character_pipeline as CP
    from . import api
    door = list(api.TOOL_FUNCS)
    if mode == "plan":
        return CP.plan(_root(), character_id, parts, target, from_stage, to_stage, tools=door)
    if mode == "record":
        return CP.record(_root(), character_id, stage, gate, evidence, by="agent", tools=door)
    if mode == "run":
        import json as _json
        return CP.run(_root(), character_id, parts, from_stage, to_stage, stage_calls, executor=lambda t, a: api.call(t, _json.dumps(a)), target=target, tools=door)
    raise ValueError(f"unknown mode {mode!r}; plan | record | run")
