# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The read side of the Scribble marks (specs/mixar_docs/scribble_marks.md): the Client already keeps every mark as a scene record and re-reads it with
scribble_mark/core/marks.get_marks (the sandbox entry point) and restates it with payload.summarize; this answers them for an external driver. Read-only;
include_image writes the mark's frozen frame (the annotated one when it exists, else the clean still) inside the project root."""

import os

import bpy

from . import common as C


def _ndc(anchor):
    if not anchor:
        return None
    return [round(2.0 * float(anchor[0]) - 1.0, 4), round(2.0 * float(anchor[1]) - 1.0, 4)]


def _mark(m):
    res = m.get("resolved") or {}
    objects = [o.get("name") for o in res.get("objects") or [] if o.get("name")] if res.get("hit") else []
    region = m.get("region") or {}
    bbox = region.get("bbox")
    anchor = region.get("anchor") or ([(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0] if bbox else None)
    return {"id": m.get("id"), "kind": m.get("gesture"), "object": objects[0] if objects else None, "region": bbox, "ndc": _ndc(anchor),
            "state": m.get("state")}


def _frame_for(marks):
    from mixar.modules.scribble_mark.core import freeze, preview
    newest = marks[-1]
    same_view = [m for m in marks if m.get("view") == newest.get("view")]
    for name in (freeze.annotated_name(same_view[-1]["id"]), preview.frame_for_view(newest.get("view"))):
        img = freeze.get_image(name)
        if img is not None:
            return img
    return None


def read(root, include_image=False, include_sent=True, out_dir="scribble"):
    from mixar.modules.scribble_mark.core import marks as M, payload as P
    ctx = M.get_marks(include_sent=include_sent)
    marks = ctx.get("marks") or []
    out = {"mode": ctx.get("intent") if marks else None, "marks": [_mark(m) for m in marks], "summary": P.summarize(ctx) if marks else ""}
    if include_image:
        img = _frame_for(marks) if marks else None
        if img is None:
            raise C.FeatureError("no frozen frame for these marks in this file: the frame is made when the user freezes the viewport to draw; "
                                 "call without include_image to read the marks alone")
        os.makedirs(os.path.join(root, out_dir), exist_ok=True)
        path = os.path.join(root, out_dir, img.name + ".png")
        copy = img.copy()                                       # save a copy: the Client's own frame datablock keeps its filepath and packing
        try:
            copy.filepath_raw = path
            copy.file_format = "PNG"
            copy.save()
        finally:
            bpy.data.images.remove(copy)
        out["image_path"] = path
    return out
