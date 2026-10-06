"""The Asset Vault's data model (specs/asset_library/asset_schema.md): closed kinds, relation types and facets, plus the numbered migrations.

A new kind is a migration, not a string: ``KINDS`` is the registry the store validates against and the tool reports."""
from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).with_name("migrations")

KINDS = {
    "mesh": {"subtypes": ["model", "part", "lod", "collision", "proxy"], "stats_table": "mesh_stats", "file_roles": ["main", "lod:N", "preview", "turntable"]},
    "image": {"subtypes": ["plate", "reference", "render", "concept", "screenshot", "turnaround", "mask", "strip"], "stats_table": "image_stats", "file_roles": ["main", "thumb"]},
    "material": {"subtypes": ["procedural", "pbr_set", "layer_stack", "soft_material"], "stats_table": "material_stats", "file_roles": ["script", "blend", "ball:N"]},
    "texture_set": {"subtypes": [], "stats_table": "texset_stats", "file_roles": []},
    "map": {"subtypes": ["basecolor", "orm", "normal_gl", "normal_dx", "height", "ao", "roughness", "metallic", "mask", "material_id", "curvature", "emission"],
            "stats_table": "map_channel", "file_roles": ["main"]},
    "uv_layout": {"subtypes": ["smart_uv", "atlas", "udim"], "stats_table": "uv_set", "file_roles": ["main", "overlay"]},
    "rig": {"subtypes": ["skeleton", "bind", "weights"], "stats_table": "rig_stats", "file_roles": ["main"]},
    "animation": {"subtypes": ["clip", "loop", "pose", "retargeted"], "stats_table": "anim_stats", "file_roles": ["main", "preview"]},
    "video": {"subtypes": ["generated", "reference", "split", "render", "capture"], "stats_table": "video_stats", "file_roles": ["main", "proxy", "strip", "overlay:N"]},
    "hdri": {"subtypes": ["sky", "studio"], "stats_table": "image_stats", "file_roles": ["main", "thumb"]},
    "prompt": {"subtypes": ["template", "filled", "negative"], "stats_table": "prompt_stats", "file_roles": ["main"]},
    "receipt": {"subtypes": ["gate", "qa", "fit", "track", "audit", "ruling"], "stats_table": None, "file_roles": ["main"]},
    "collection": {"subtypes": ["board", "smart"], "stats_table": None, "file_roles": []},
}
for _k in KINDS.values():
    _k["required_provenance"] = []

RELATION_TYPES = ["derived_from", "variant_of", "part_of", "textured_by", "fits_body", "rigged_to", "generated_from", "drives", "uses", "frame_of", "supersedes",
                  "normalized_from"]
# Kinds whose versions are canonical (a validated lampway.canonical-asset/1 document) or raw (migration 0004; specs/canon/normalization)
CANONICAL_KINDS = ("mesh", "rig", "animation", "map", "texture_set", "material")
FACETS = ["piece_type", "material_role", "era_style", "faction", "motion_type", "camera_template", "view", "pipeline_stage", "studio",
          # named by asset_ingest section 6.7 rules but missing from the contract's facet list: added so those rules can be written
          "topology", "authority", "lod", "license", "state"]
SECTIONS = ("kinds", "relations", "taxonomy", "ddl", "all")


def migration_files() -> list:
    return sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def latest_version() -> int:
    return int(migration_files()[-1].name[:4])


def ddl() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in migration_files())


def stats_columns(table: str, db) -> list:
    if not re.fullmatch(r"[a-z_]+", table):
        raise ValueError("bad table")
    return [r[1] for r in db.execute(f"PRAGMA table_info({table})")]


def describe(section: str = "all") -> dict:
    if section not in SECTIONS:
        raise ValueError("unknown section %r; sections: kinds|relations|taxonomy|ddl|all" % section)
    out = {"schema_version": latest_version()}
    if section in ("kinds", "all"):
        out["kinds"] = [{"kind": k, **v} for k, v in KINDS.items()]
    if section in ("relations", "all"):
        out["relation_types"] = list(RELATION_TYPES)
    if section in ("taxonomy", "all"):
        out["facets"] = list(FACETS)
    if section in ("ddl", "all"):
        out["ddl"] = ddl()
    return out
