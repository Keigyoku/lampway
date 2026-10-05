# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh QA in the live scene: candidates computed on an object, drawn where the captain reviews them, his tags read back.

Ported from the shelf's qa_marks_live.py (draw) and qa_read_marks.py (read), reworked onto the tag layers. The live
object is the rebuilt, textured mesh standing on the floor; candidates are kept in the mesh's OWN frame (what the
rebuild's patch_holes.py expects with its turn) and the live frame is that plus ``offset`` (his LIFT).

One config per scene, saved as JSON on the scene (``scene['lampway_qa']``), so the operators, the panel and the agent
tools all work on the same piece.
"""

import json
import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

import bpy
from mathutils import Matrix, Vector

from . import candidates as C
from . import decisions as D
from . import marks as M
from .rulings import Rulings

_MAX_SEGMENTS = 20000                      # bounded: at most this many segments drawn per loop
SCENE_KEY = "lampway_qa"


@dataclass
class QAConfig:
    object: str
    recipe: str
    owner: str = ""                        # .npy of one part index per polygon; "" = the mesh's int face attribute 'part'
    rulings_dir: str = ""
    piece: str = "piece"
    session: str = "session"
    offset: tuple = (0.0, 0.0, 0.0)        # live frame = mesh frame + offset
    orig_poly: str = ""                    # .npy: source polygon id per live polygon (-1 = a patch); "" = identity
    turn: float = 0.0                      # the turn the rebuild applies (patch_holes --turn)
    min_perimeter: float = 0.15
    max_shell_tris: int = 400
    float_mm: float = 3.0
    skip_strokes: dict = field(default_factory=lambda: {"delete": 0, "mislabel": 0, "hole": 0})

    @property
    def candidates_path(self) -> Path:
        return Path(self.rulings_dir) / f"{self.piece}_candidates.json"

    @property
    def decisions_path(self) -> Path:
        return Path(self.rulings_dir) / "decisions.jsonl"


def save_config(scene, cfg: QAConfig) -> None:
    scene[SCENE_KEY] = json.dumps(asdict(cfg))


def load_config(scene) -> QAConfig:
    raw = scene.get(SCENE_KEY)
    if not raw:
        raise LookupError("no Mesh QA configuration on this scene: set the piece up first (lampway.qa_setup)")
    data = json.loads(raw)
    data["offset"] = tuple(data.get("offset", (0, 0, 0)))
    return QAConfig(**data)


def _object(cfg):
    ob = bpy.data.objects.get(cfg.object)
    if ob is None or ob.type != "MESH":
        raise LookupError(f"no mesh object named {cfg.object!r}")
    return ob


def _owner(cfg, me) -> np.ndarray:
    if cfg.owner:
        return np.load(cfg.owner)
    attr = me.attributes.get("part")
    if attr is None:
        raise LookupError("no owner map: set the .npy path, or the mesh needs an int face attribute named 'part'")
    arr = np.zeros(len(me.polygons), dtype=np.int32)
    attr.data.foreach_get("value", arr)
    return arr


def _orig_poly(cfg, n) -> np.ndarray:
    return np.load(cfg.orig_poly) if cfg.orig_poly else np.arange(n)


def compute_candidates(cfg: QAConfig) -> dict:
    """Open loops and floating shells on the live object, written to ``<rulings_dir>/<piece>_candidates.json``."""
    ob = _object(cfg)
    me = ob.data
    rec = json.load(open(cfg.recipe))
    owner = _owner(cfg, me)
    rulings = Rulings(cfg.rulings_dir, cfg.piece)
    dele_path = rulings.path("deletions")
    delete_polys = []
    if not cfg.orig_poly and dele_path.exists():             # a source mesh: earlier ruled deletions apply first
        delete_polys = json.load(open(dele_path)).get("polys", [])
    matrix = Matrix.Translation(-Vector(cfg.offset)) @ ob.matrix_world
    prep = C.prepare(me, matrix, owner, delete_polys=delete_polys)
    cands = C.analyse(prep, rec, C.Params(cfg.min_perimeter, cfg.max_shell_tris, cfg.float_mm))
    prep.bm.free()
    out = {"mesh": f"<live object {cfg.object}>", "owner": cfg.owner or "<attribute part>", "recipe": cfg.recipe,
           "turn": cfg.turn, "deleted_before": str(dele_path) if delete_polys else None,
           "frame": "-y front, +x the body left, in the mesh's own frame (live frame minus offset)",
           "offset": list(cfg.offset), "candidates": cands}
    cfg.candidates_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.candidates_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return {"path": str(cfg.candidates_path), "candidates": len(cands),
            "open_loops": sum(c["kind"] == "open_loop" for c in cands),
            "loose_shells": sum(c["kind"] == "loose_shell" for c in cands)}


def _load_candidates(cfg) -> dict:
    if not cfg.candidates_path.exists():
        raise FileNotFoundError(f"{cfg.candidates_path} does not exist: compute the candidates first")
    return json.loads(cfg.candidates_path.read_text(encoding="utf-8"))


def draw_candidates(cfg: QAConfig, collection="QA_candidates", prefix="") -> dict:
    """Draw the candidates into one collection: an open loop a yellow tube along its edges, a loose shell a yellow
    ring around it, each with its id as a small label beside it. A second run replaces the collection; nothing outside
    it is touched (hide it to see the piece clean)."""
    cand = _load_candidates(cfg)
    off = Vector(cfg.offset)
    old = bpy.data.collections.get(collection)
    if old:
        for o in list(old.objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(old)
    col = bpy.data.collections.new(collection)
    bpy.context.scene.collection.children.link(col)
    mat = bpy.data.materials.get("QA_mark") or bpy.data.materials.new("QA_mark")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (1, 0.85, 0, 1)
    b.inputs["Emission Color"].default_value = (1, 0.85, 0, 1)
    b.inputs["Emission Strength"].default_value = 3.0
    made = 0
    for c in cand["candidates"]:
        cu = bpy.data.curves.new(prefix + c["id"], "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.0015
        cu.bevel_resolution = 1
        if c["kind"] == "open_loop":
            for p0, p1 in c["segments_m"][:_MAX_SEGMENTS]:
                sp = cu.splines.new("POLY")
                sp.points.add(1)
                sp.points[0].co = (*(Vector(p0) + off), 1)
                sp.points[1].co = (*(Vector(p1) + off), 1)
        else:
            r = max(c["extent_m"]) / 2 + 0.006
            n = Vector(c["facing"])
            ctr = Vector(c["centroid_m"]) + off
            q = n.to_track_quat("Z", "Y")
            sp = cu.splines.new("POLY")
            sp.points.add(31)
            sp.use_cyclic_u = True
            for i in range(32):
                t = 2 * math.pi * i / 32
                sp.points[i].co = (*(ctr + q @ Vector((r * math.cos(t), r * math.sin(t), 0))), 1)
        o = bpy.data.objects.new(prefix + c["id"], cu)
        o.data.materials.append(mat)
        col.objects.link(o)
        tc = bpy.data.curves.new(prefix + c["id"] + "_label", "FONT")
        tc.body = c["id"]
        tc.size = 0.014
        tc.align_x = "CENTER"
        t = bpy.data.objects.new(prefix + c["id"] + "_label", tc)
        t.data.materials.append(mat)
        col.objects.link(t)
        n = Vector(c["facing"])
        t.location = Vector(c["centroid_m"]) + off + n * 0.02
        t.rotation_euler = n.to_track_quat("Z", "Y").to_euler()
        made += 1
    return {"drawn": made, "collection": col.name}


def _shift(c, off):
    c = dict(c)
    c["centroid_m"] = [x + o for x, o in zip(c["centroid_m"], off)]
    if "segments_m" in c:
        c["segments_m"] = [[[x + o for x, o in zip(p, off)] for p in seg] for seg in c["segments_m"]]
    return c


def read_tags(cfg: QAConfig, apply=True, close_round=False, mislabel_to=None) -> dict:
    """Read the tag layers: faces, islands, loops; with ``apply`` write the decision rows and the rulings.

    ``cfg.skip_strokes`` ({tag: n}) leaves the first n strokes of a tag alone (earlier marks, already ruled).
    ``mislabel_to`` ({stroke index: part}) turns green strokes into relabels; without a target they come back in
    ``relabels_needing_a_target`` - the target is a decision, never guessed. ``close_round`` answers every candidate
    nobody named 'keep' ("everything else looks intentional")."""
    cand = _load_candidates(cfg)
    ob = _object(cfg)
    n = len(ob.data.polygons)
    orig = _orig_poly(cfg, n)
    tags = M.read_tags()
    for tag, skip in cfg.skip_strokes.items():
        tags[tag] = tags[tag][skip:]
    off = cfg.offset
    shifted = [_shift(c, off) for c in cand["candidates"]]
    tagged = M.interpret(tags, ob, candidates=shifted)
    for row in tagged["delete"]:
        row["orig_faces"] = [int(orig[f]) for f in row["faces"] if orig[f] >= 0]
    report = {"strokes": {t: len(v) for t, v in tags.items()},
              "faces": {t: sorted({f for r in rows for f in r["faces"]}) for t, rows in tagged.items() if t != "hole"},
              "islands": {t: sorted({i for r in rows for i in r["islands"]}) for t, rows in tagged.items()},
              "hole_loops": sorted({cid for r in tagged["hole"] for cid in r["loops"]}),
              "orphans": [r["stroke"] for r in tagged["hole"] if r["orphan"]],
              "deleted": 0, "shells": [], "relabelled": 0, "relabels_needing_a_target": [], "decisions": 0}
    if apply:
        parts = list(json.load(open(cfg.recipe))["parts"])
        rulings = Rulings(cfg.rulings_dir, cfg.piece, parts=parts)
        rows = D.rows_from_tags(tagged, cand["candidates"], cfg.session, str(cfg.candidates_path), close_round=close_round)
        fresh = D.new_rows(D.read_rows(cfg.decisions_path), rows)
        report["decisions"] = D.append_rows(cfg.decisions_path, fresh)
        applied = rulings.apply_tags(tagged, cand["candidates"], orig, mislabel_to=mislabel_to)
        for k in ("deleted", "shells", "relabelled", "relabels_needing_a_target"):
            report[k] = applied[k]
    return report
