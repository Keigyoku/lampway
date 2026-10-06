"""Scribble marks in the model context (specs/mixar_docs/scribble_marks.md). The Client sends ``mark_context`` beside the message: the dict
scribble_mark/core/payload.build_payload makes (marks resolved against the live scene before they left the client). Models act on sentences more reliably
than on JSON, so it is restated here as prose: object names and world-space points, deterministic, no model. The wording follows the Client's own
payload.summarize so the two never tell the agent different things."""

VERBS = {"circle": "circled", "arrow": "drew an arrow at", "point": "tapped", "strike": "struck through", "stroke": "marked"}


def _xyz(p):
    return ", ".join(f"{float(c):g}" for c in p)


def _mark(mark, numbered):
    prefix = f"Mark {mark.get('id')}: " if numbered else ""
    verb = VERBS.get(mark.get("gesture"), "marked")
    res = mark.get("resolved") or {}
    if not res:
        return f"{prefix}the user {verb} a region of the frozen view."
    point = res.get("point")
    if not res.get("hit"):
        if res.get("plane") and point:
            return f"{prefix}the user {verb} an empty spot on the ground plane at world ({_xyz(point)}) - a placement target."
        return f"{prefix}the user {verb} empty space ({res.get('empty_reason') or 'nothing under it'}) - no object is under this mark."
    objects = [o for o in res.get("objects") or [] if isinstance(o, dict) and o.get("name")]
    if not objects:
        return f"{prefix}the user {verb} a region, but no object resolved."
    first = objects[0]
    if not first.get("partial"):
        part = ", covering essentially all of it"
    elif first.get("object_fraction") is not None:
        part = f", covering about {int(round(float(first['object_fraction']) * 100))}% of it"
    else:
        part = ", covering part of it"
    s = f"{prefix}the user {verb} `{first['name']}`{part}."
    if first.get("vertex_group"):
        s += f" The marked faces are in the vertex group `{first['vertex_group']}` on `{first['name']}`: select that rather than re-deriving the region."
    if len(objects) > 1:
        s += " Also partly covered: " + ", ".join(f"`{o['name']}`" for o in objects[1:]) + "."
    if point:
        s += f" Surface point at world ({_xyz(point)})."
    direction = (mark.get("region") or {}).get("direction")
    if direction and mark.get("gesture") == "arrow":
        s += f" The arrow points ({float(direction[0]):g}, {float(direction[1]):g}) in the frame, right/up positive."
    return s


def _sketch(ctx):
    sk = ctx.get("sketch") or {}
    n = int(sk.get("stroke_count") or 0)
    chosen = "a reading they chose" if ctx.get("intent_source") == "user" else "read from the ink"
    lines = [f"The user DREW A SKETCH over the frozen view ({n} stroke{'' if n == 1 else 's'}, {chosen}): build what it depicts, laid out where it was "
             "drawn, not one object per mark."]
    ext = sk.get("world_bbox")
    if isinstance(ext, dict):
        size, c = ext.get("size") or [0, 0, 0], ext.get("center") or [0, 0, 0]
        lines.append(f"It spans about {float(size[0]):.1f} m by {float(size[1]):.1f} m of the ground around world ({_xyz(c[:3])}).")
    crossed = []
    for m in ctx.get("marks") or []:
        res = (m.get("resolved") if isinstance(m, dict) else None) or {}
        if not res.get("hit"):
            continue
        for o in res.get("objects") or []:
            if isinstance(o, dict) and o.get("name") and o["name"] not in crossed:
                crossed.append(o["name"])
    if crossed:
        lines.append("The ink also crosses existing objects: " + ", ".join(f"`{n}`" for n in crossed) + ".")
    return "\n".join(lines)


def describe(ctx) -> str:
    """The marks as prose, or "" when there are none (or the field is not a mark payload)."""
    if not isinstance(ctx, dict):
        return ""
    marks = [m for m in ctx.get("marks") or [] if isinstance(m, dict)]
    if not marks:
        return ""
    if ctx.get("intent") == "sketch" and ctx.get("sketch"):
        body = _sketch(ctx)
    else:
        body = "\n".join(_mark(m, len(marks) > 1) for m in marks)
    return "[Scribble marks on the frozen viewport, resolved against the scene]\n" + body
