# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Wave 6 tool functions (specs/wiki and specs/mixar_docs contracts the captain released as Wave 6). Plain functions: ``api.py`` wraps every name in
``TOOLS`` with its ``@tool`` envelope, so they join the one door (``api.call``) with the same refusal shape. Each docstring is the agent-facing
description; the server's Def (agent/wave6_tools.py) carries the same text."""

from . import settings as S

TOOLS = ("modular_character",)


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
