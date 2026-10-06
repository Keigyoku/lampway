# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Re-stamp a canonical mesh a tool changed in place (DOOR.md 2, produces=Inherit): the tool read a canonical object, changed its geometry
or scale on purpose, and the result is canonical again in the same frame. The previous document's generator and weld are kept; the scale
state is inherited unless the tool supplies new evidence (scale_to_measure's measured length). Nothing is re-guessed: the frame is the
body frame the input already was in (turn 0), the origin stays where it is."""

import json

from . import normalize as _NZ


def restamp(ob, previous_doc, scale_evidence=None):
    """The object's new canonical document (stamped on it), inheriting ``previous_doc``'s decisions."""
    prev = json.loads(previous_doc) if isinstance(previous_doc, str) else dict(previous_doc)
    generator = (prev.get("raw") or {}).get("generator", {}).get("source", "lampway_tool")
    welded = bool((((prev.get("body") or {}).get("topology") or {}).get("welded")))
    ev = scale_evidence or (prev.get("scale") or {}).get("evidence")
    if "lw_canon" in ob.keys():
        del ob["lw_canon"]
    doc, _ = _NZ.normalize_object(ob, turn_deg=0.0, generator=generator if generator in _NZ.GENERATORS else "lampway_tool",
                                  want_scale="real" if ev else "any", scale_evidence=ev, weld="auto" if welded else "never",
                                  pivot="source_origin", pivot_offset=(0.0, 0.0, 0.0))
    return doc
