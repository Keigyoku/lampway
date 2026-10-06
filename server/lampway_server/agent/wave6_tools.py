"""The Wave 6 Lampway tool definitions that run in Blender (one api.call each, the same door as lampway_tools.DEFS). Kept apart from lampway_tools.py so
that file stays reviewable; lampway_tools appends these to DEFS, so BY_NAME, SPECS and the MCP offer see them like any other Def."""

from .lampway_tools import Def, P

_PATHS = " Paths are relative to the project root; a path outside it is refused."
_OBJ = {"type": "object"}

DEFS = [
    Def("lampway_modular_character", "A character's interchangeable parts as one typed record. manifest {character_id, parts: [{object, role: head|body|hands|hair|"
        "garment|accessory, fixed_or_deforming, wearer_side: left|right|center|paired, bone (required for a fixed part)}], armature, allowed_outfits: [[part ids]], "
        "poses: rest | wiki8 | [poses]} writes <root>/<character_id>/manifest.json with the template fields. validate: one shared armature (two armatures are "
        "refused), the rest pose unchanged since the manifest, equal scales, each part's measured side against its declared one (the figure faces -Y, its left is "
        "+X), and weight_audit on every deforming part. outfit_matrix: per allowed outfit (in each pose) the body faces it leaves uncovered of the region any outfit "
        "covers and the body vertices poking through it; pass = both zero. hidden_body makes `<body>_hidden`, a copy without the faces every outfit covers, and is "
        "refused before a passing matrix or after anything changed since it. export_parts writes one FBX per part with the same armature under "
        "out_dir/<character_id>/. The full body is never deleted." + _PATHS,
        [P("action", desc="manifest | validate | outfit_matrix | hidden_body | export_parts", required=True), P("character_id", required=True),
         P("parts", "array", "manifest: [{object, role, fixed_or_deforming, wearer_side, bone}]", items=_OBJ), P("armature"),
         P("allowed_outfits", "array", "[[part ids]]", items={"type": "array", "items": {"type": "string"}}),
         P("poses", "string", "rest | wiki8 (default: the manifest's)"), P("out_dir")], api="modular_character"),
]
