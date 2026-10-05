# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh QA in the live scene: candidates computed on an object, drawn where the captain reviews them, his tags read back.

Ported from the shelf's qa_marks_live.py (draw) and qa_read_marks.py (read), reworked onto the tag layers. The live
object is the rebuilt, textured mesh standing on the floor; candidates are kept in the mesh's OWN frame (what the
rebuild's patch_holes.py expects with its turn) and the live frame is that plus ``offset`` (his LIFT).

One config PER PIECE, saved as JSON on the scene (``scene['lampway_qa_pieces']``, keyed by piece name), so several pieces
can be reviewed in one scene and in separate swarm lanes. The most recently set-up piece is the active one: a tool called
without a ``piece`` works on it. Each piece draws into its own collection (``QA_<piece>``) with its own marker names
(``<piece>_L000``), so one piece's markers are never touched by another's.

Frames. Candidates are measured in the ANALYSIS frame: -y front, +x the body's left. ``turn`` is the rotation about Z that
brings the live object there (a Tripo FBX faces +x: turn -90), applied after the ``offset`` is removed; ``analysis_matrix``
is that map and ``live_matrix`` its inverse, which draw and read_tags use to put markers where the object really is. An
object that is already in the analysis frame (a loaded rebuild) has turn 0; the rebuild's own turn lives in its setup.
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
from . import proposals as P
from .rulings import Rulings

_MAX_SEGMENTS = 20000                      # bounded: at most this many segments drawn per loop
SCENE_KEY = "lampway_qa"                    # the old single-config key, still read
PIECES_KEY = "lampway_qa_pieces"
ACTIVE_KEY = "lampway_qa_active"
VERDICTS = ("delete", "hole", "mislabel", "keep")
VERDICT_COLOURS = {"delete": (0.9, 0.05, 0.05), "hole": (1.0, 0.85, 0.0), "mislabel": (0.1, 0.75, 0.15), "keep": (0.5, 0.5, 0.5),
                   None: (0.2, 0.55, 1.0)}                       # None = nobody has proposed anything for it yet


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
    turn: float = 0.0                      # about Z, degrees: brings the live object to the -y front (a Tripo FBX: -90)
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


def _pieces(scene) -> dict:
    raw = scene.get(PIECES_KEY)
    out = json.loads(raw) if raw else {}
    legacy = scene.get(SCENE_KEY)
    if legacy:                                                      # a scene saved before configs were per piece
        data = json.loads(legacy)
        out.setdefault(data.get("piece", "piece"), data)
    return out


def save_config(scene, cfg: QAConfig) -> None:
    pieces = _pieces(scene)
    pieces[cfg.piece] = asdict(cfg)
    scene[PIECES_KEY] = json.dumps(pieces)
    scene[ACTIVE_KEY] = cfg.piece


def piece_names(scene) -> list:
    return sorted(_pieces(scene))


def load_config(scene, piece=None) -> QAConfig:
    """The config of ``piece``, or of the active piece (the last one set up) when none is named."""
    pieces = _pieces(scene)
    if not pieces:
        raise LookupError("no Mesh QA configuration on this scene: set the piece up first (lampway.qa_setup)")
    name = piece or scene.get(ACTIVE_KEY) or (next(iter(pieces)) if len(pieces) == 1 else None)
    if name not in pieces:
        raise LookupError(f"no Mesh QA piece {name!r} on this scene; the pieces are: {sorted(pieces)}")
    data = dict(pieces[name])
    data["offset"] = tuple(data.get("offset", (0, 0, 0)))
    return QAConfig(**data)


def analysis_matrix(cfg: QAConfig) -> Matrix:
    """Live frame -> analysis frame: remove the offset, then turn about Z."""
    return Matrix.Rotation(math.radians(cfg.turn), 4, "Z") @ Matrix.Translation(-Vector(cfg.offset))


def live_matrix(cfg: QAConfig) -> Matrix:
    return analysis_matrix(cfg).inverted()


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
    matrix = analysis_matrix(cfg) @ ob.matrix_world
    prep = C.prepare(me, matrix, owner, delete_polys=delete_polys)
    cands = C.analyse(prep, rec, C.Params(cfg.min_perimeter, cfg.max_shell_tris, cfg.float_mm))
    prep.bm.free()
    out = {"mesh": f"<live object {cfg.object}>", "owner": cfg.owner or "<attribute part>", "recipe": cfg.recipe,
           "turn": cfg.turn, "deleted_before": str(dele_path) if delete_polys else None,
           "frame": "-y front, +x the body left: the live frame minus offset, then turned about Z by `turn`",
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


def _collection_name(cfg, collection):
    return collection or f"QA_{cfg.piece}"


def _prefix(cfg, prefix):
    return f"{cfg.piece}_" if prefix is None else prefix


def _verdict_material(verdict):
    name = f"QA_mark_{verdict or 'new'}"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    r, g, b_ = VERDICT_COLOURS[verdict]
    node = mat.node_tree.nodes["Principled BSDF"]
    node.inputs["Base Color"].default_value = (r, g, b_, 1)
    node.inputs["Emission Color"].default_value = (r, g, b_, 1)
    node.inputs["Emission Strength"].default_value = 3.0
    mat.diffuse_color = (r, g, b_, 1)
    return mat


def _label(cid, verdict):
    return f"{cid} {verdict.upper()}" if verdict else cid


def draw_candidates(cfg: QAConfig, collection=None, prefix=None) -> dict:
    """Draw the candidates into the piece's own collection (``QA_<piece>``, marker names ``<piece>_<id>``): an open loop a tube
    along its edges, a loose shell a ring around it, each with a label beside it. Colour and label follow the piece's proposals
    (delete red, hole yellow, mislabel green, keep grey, nothing proposed blue; ``<id> <VERDICT>``). A second run replaces THIS
    collection only; another piece's markers are never touched. Positions are the analysis-frame candidates carried back to
    the live frame (turn undone, offset added)."""
    cand = _load_candidates(cfg)
    name = _collection_name(cfg, collection)
    prefix = _prefix(cfg, prefix)
    live = live_matrix(cfg)
    rot = live.to_3x3()
    proposals = P.as_map(P.load_rows(cfg.rulings_dir, cfg.piece))
    old = bpy.data.collections.get(name)
    if old:
        for o in list(old.objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(old)
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    made = 0
    for c in cand["candidates"]:
        verdict = (proposals.get(c["id"]) or {}).get("verdict")
        mat = _verdict_material(verdict)
        cu = bpy.data.curves.new(prefix + c["id"], "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.0015
        cu.bevel_resolution = 1
        if c["kind"] == "open_loop":
            for p0, p1 in c["segments_m"][:_MAX_SEGMENTS]:
                sp = cu.splines.new("POLY")
                sp.points.add(1)
                sp.points[0].co = (*(live @ Vector(p0)), 1)
                sp.points[1].co = (*(live @ Vector(p1)), 1)
        else:
            r = max(c["extent_m"]) / 2 + 0.006
            n = rot @ Vector(c["facing"])
            ctr = live @ Vector(c["centroid_m"])
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
        o.hide_viewport = o.hide_render = (verdict == "keep")        # a KEEP marker is out of the way
        tc = bpy.data.curves.new(prefix + c["id"] + "_label", "FONT")
        tc.body = _label(c["id"], verdict)
        tc.size = 0.014
        tc.align_x = "CENTER"
        t = bpy.data.objects.new(prefix + c["id"] + "_label", tc)
        t.data.materials.append(mat)
        col.objects.link(t)
        t.hide_viewport = t.hide_render = (verdict == "keep")
        n = rot @ Vector(c["facing"])
        t.location = live @ Vector(c["centroid_m"]) + n * 0.02
        t.rotation_euler = n.to_track_quat("Z", "Y").to_euler()
        made += 1
    return {"drawn": made, "collection": col.name, "prefix": prefix}


def recolour(cfg: QAConfig, collection=None, prefix=None) -> dict:
    """Recolour and relabel the piece's existing markers from its proposals (no redraw; the geometry stays)."""
    cand = _load_candidates(cfg)
    prefix = _prefix(cfg, prefix)
    proposals = P.as_map(P.load_rows(cfg.rulings_dir, cfg.piece))
    changed = 0
    for c in cand["candidates"]:
        verdict = (proposals.get(c["id"]) or {}).get("verdict")
        mat = _verdict_material(verdict)
        for suffix, is_label in (("", False), ("_label", True)):
            o = bpy.data.objects.get(prefix + c["id"] + suffix)
            if o is None:
                continue
            o.data.materials.clear()
            o.data.materials.append(mat)
            o.hide_viewport = o.hide_render = (verdict == "keep")
            if is_label:
                o.data.body = _label(c["id"], verdict)
        changed += 1
    return {"recoloured": changed, "proposals": P.counts(list(proposals.values()))}


def _shift(c, live):
    """A candidate carried from the analysis frame to the live frame by the 4x4 ``live`` matrix."""
    c = dict(c)
    c["centroid_m"] = list(live @ Vector(c["centroid_m"]))
    if "segments_m" in c:
        c["segments_m"] = [[list(live @ Vector(p)) for p in seg] for seg in c["segments_m"]]
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
    live = live_matrix(cfg)
    shifted = [_shift(c, live) for c in cand["candidates"]]
    tagged = M.interpret(tags, ob, candidates=shifted)
    for row in tagged["delete"]:
        row["orig_faces"] = [int(orig[f]) for f in row["faces"] if orig[f] >= 0]
    report = {"strokes": {t: len(v) for t, v in tags.items()},
              "faces": {t: sorted({f for r in rows for f in r["faces"]}) for t, rows in tagged.items() if t != "hole"},
              "islands": {t: sorted({i for r in rows for i in r["islands"]}) for t, rows in tagged.items()},
              "hole_loops": sorted({cid for r in tagged["hole"] for cid in r["loops"]}),
              "orphans": [r["stroke"] for r in tagged["hole"] if r["orphan"]],
              "deleted": 0, "shells": [], "relabelled": 0, "relabels_needing_a_target": [], "decisions": 0}
    if not apply:                                                  # a dry run still says which green strokes need a target
        for r in tagged["mislabel"]:
            faces = sorted({int(orig[f]) for f in r["faces"] if orig[f] >= 0})
            if faces:
                report["relabels_needing_a_target"].append({"stroke": r["stroke"], "faces_orig": faces, "islands": r["islands"]})
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
