# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the model-compare window says (facelift contract 11 over specs/mrmak/05-model-compare.md). No bpy.

    strip(stats)          a view's strip: triangles visible; vertices, quad status and the largest texture on hover;
                          channels as words, a missing map in stop with a cross (the finding stays loud)
    overlay_texts(...)    what a view's overlay draws: while blind and not revealed, only the alias and "name hidden"
    pair_rows(numbers)    pair, worst-view outline IoU, interior difference (lit above 0.05); the lattice on hover
"""

MODES = (("1", "Wire"), ("2", "Clay"), ("3", "Normals"), ("4", "Textured"), ("5", "Base colour"), ("6", "Normal map"), ("7", "ORM"))
CHANNELS = (("base", "base", "base colour"), ("normal", "normal", "normal"), ("orm_packed", "ORM", "ORM"))
INTERIOR_LIT = 0.05
LATTICE = "192 x 192, 10 bands"


def _px(n) -> str:
    n = int(n or 0)
    return f"{n // 1024}K" if n >= 1024 and n % 1024 == 0 else f"{n} px"


def strip(stats: dict) -> dict:
    ch = stats.get("channels") or {}
    channels = []
    for key, word, long in CHANNELS:
        if ch.get(key):
            channels.append({"key": key, "text": word, "tone": "go", "glyph": ""})
        else:
            text = f"no {long} map baked" if key != "orm_packed" else "no ORM"
            channels.append({"key": key, "text": text, "tone": "stop", "glyph": "cross"})
    quads = "quads (ngon-encoded)" if stats.get("ngon_encoding") else "quads unknown: triangles only"
    if stats.get("ngon_encoding") and stats.get("polygons") is not None:
        quads = f"quads: {int(stats['polygons']):,} (ngon-encoded)"
    hover = f"{int(stats.get('vertices') or 0):,} verts; {quads}; largest texture {_px(stats.get('largest_texture_px'))}"
    return {"tris": f"{int(stats.get('triangles') or 0):,} tris", "hover": hover, "channels": channels}


def overlay_texts(view: dict, blind: bool, revealed: bool) -> list:
    if blind and not revealed:
        return [view["alias"], "name hidden"]
    return [view["alias"], view.get("label") or view["alias"]]


def pair_rows(numbers: dict, aliases: str = "ABCD") -> list:
    out = []
    for p in (numbers or {}).get("pairs") or []:
        cells = max((int(v.get("cells_compared") or 0) for v in p.get("views") or []), default=0)
        interior = float(p.get("worst_interior") or 0.0)
        out.append({"pair": f"{aliases[p['a']]} vs {aliases[p['b']]}", "iou": f"{float(p.get('worst_iou') or 0.0):.3f}",
                    "interior": f"{interior:.3f}", "interior_tone": "accent" if interior > INTERIOR_LIT else "text",
                    "tip": f"measured on {LATTICE}, {cells:,} cells" + (f"; {p['note']}" if p.get("note") else "")})
    return out
