# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The status bar (facelift contract 03, DESIGN.md 9 and 13): a decision that waits for you, today's spend against its cap, and whether data is
leaving this machine, always in the bottom right of the window.

draw() reads ``statusbar_state`` and never the network; one timer refreshes it (0.5 s while any route is on, 5 s otherwise). The only thing that
moves is the sending wire: a second timer swaps its two frames while the server says data is leaving, ends itself within a tick after, and is never
started under reduced motion."""

import bpy
from bpy.types import Operator

from mixar.modules.lampway_tools import statusbar_state as S
from mixar.modules.lampway_tools import status_client, studio_client

CLIENT_FACTORY = lambda: status_client.StatusClient()  # noqa: E731  (tests swap it)
REDUCE_MOTION = {"on": False}
FRAME = {"b": False}
FRAME_S = 0.4


def preview(name):
    """The colour-baked glyph (an icon_value) of a cue; contract 14's previews."""
    from mixar.modules.common.lampway_icons import icon_id
    return icon_id(name)


def _timers():
    return bpy.app.timers


def _redraw_statusbar():
    """The bar is a global area (``Window.global_areas``); ``screen.areas`` never holds it."""
    wm = getattr(bpy.context, "window_manager", None)
    for window in getattr(wm, "windows", []) or []:
        for area in getattr(window, "global_areas", []) or []:
            if area.type == 'STATUSBAR':
                area.tag_redraw()


def _wire_frame():
    """Swap the sending wire's two frames; end with the sending."""
    if not S.sending() or REDUCE_MOTION["on"]:
        FRAME["b"] = False
        _redraw_statusbar()
        return None
    FRAME["b"] = not FRAME["b"]
    _redraw_statusbar()
    return FRAME_S


def sync_animation():
    timers = _timers()
    if S.sending() and not REDUCE_MOTION["on"]:
        if not timers.is_registered(_wire_frame):
            timers.register(_wire_frame, first_interval=FRAME_S)
    elif timers.is_registered(_wire_frame):
        timers.unregister(_wire_frame)


def refresh():
    try:
        client = CLIENT_FACTORY()
        S.update(egress=client.egress(), spend=client.spend(), studio=client.studio(),
                 provider=((client.provider_settings() or {}).get("values") or {}).get("provider") or "")
    except studio_client.StudioError as exc:
        S.fail(str(exc), signed_out=isinstance(exc, studio_client.SignedOut))
    sync_animation()
    _sync_route_line()
    _open_awaited_card()
    _show_terminal_images()
    _redraw_statusbar()


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".exr", ".webp", ".tga", ".tif", ".tiff", ".bmp")


def _show_terminal_images() -> dict:
    """Contract 16's image fallback: inline images do not cross herdr, so an image path clicked in the Lampway terminal is
    appended to ``<Lampway home>/wezterm/show_in_blender.jsonl``. Drain it once (renamed first, so a click landing meanwhile
    waits for the next refresh), load each existing image file and show the last in an Image Editor: the main window's
    existing one, else a new window. Anything else is skipped and named."""
    import json
    import os
    from mixar.modules.lampway_tools import canon_io, settings
    out = {"loaded": [], "skipped": [], "shown_in": None}
    q = settings.lampway_home() / "wezterm" / "show_in_blender.jsonl"
    if not q.exists():
        return out
    taken = q.with_suffix(".draining")
    try:
        os.replace(q, taken)
        lines = taken.read_text(encoding="utf-8").splitlines()
    finally:
        taken.unlink(missing_ok=True)
    for line in filter(None, (x.strip() for x in lines)):
        try:
            path = str(json.loads(line)["path"])
        except (ValueError, KeyError, TypeError):
            out["skipped"].append(line[:200])
            continue
        if not path.lower().endswith(IMAGE_SUFFIXES) or not os.path.isfile(path):
            out["skipped"].append(path)
            continue
        if path in out["loaded"]:
            continue
        canon_io.load_image(path, check_existing=True)       # the canon door: every image load goes through canon_io
        out["loaded"].append(path)
    if out["loaded"] and not bpy.app.background:
        out["shown_in"] = _image_editor_show(canon_io.load_image(out["loaded"][-1], check_existing=True))
    return out


def _image_editor_show(image):
    """Show ``image`` in the main window's Image Editor; with none there, in a new window (the user's areas are never retyped)."""
    wm = bpy.context.window_manager
    main = next((w for w in wm.windows if w.parent is None), None)
    if main is None:
        return None
    for window in [main, *[w for w in wm.windows if w is not main]]:
        for area in window.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.spaces.active.image = image
                area.tag_redraw()
                return "existing"
    before = set(wm.windows[:])
    area = max(main.screen.areas, key=lambda a: a.width * a.height)
    with bpy.context.temp_override(window=main, area=area):
        bpy.ops.wm.window_new()
    new = next((w for w in wm.windows if w not in before), None)
    if new is None:
        return None
    target = max(new.screen.areas, key=lambda a: a.width * a.height)
    target.type = 'IMAGE_EDITOR'
    target.spaces.active.image = image
    return "new window"


def _open_awaited_card():
    """A Spend pressed in the island's Image / Video tab opens the spend card of the approval it caused (contracts 08 and 13)."""
    from mixar.modules.lampway_tools import generate_face
    ap = generate_face.next_card((S.STATE.get("studio") or {}).get("approvals"))
    if ap is None or bpy.app.background:
        return
    unit = (ap.get("settings") or {}).get("unit") or "credits"
    wm = bpy.context.window_manager
    win = next((w for w in wm.windows if w.parent is None), None)
    if win is None:
        return
    area = max(win.screen.areas, key=lambda a: a.width * a.height)
    try:
        with bpy.context.temp_override(window=win, area=area):   # a timer has no window of its own: the card opens on the main one
            bpy.ops.lampway.studio_confirm('INVOKE_DEFAULT', approval_id=ap["id"], price=float(ap.get("price") or 0.0),
                                           label=ap.get("label") or "", unit=unit)
    except RuntimeError:
        pass


def _sync_route_line():
    """Where the next chat message goes, for the island's Send (facelift contract 04)."""
    from mixar.modules.lampway_tools import chat_route
    wm = getattr(bpy.context, "window_manager", None)
    scene = getattr(bpy.context, "scene", None)
    if wm is not None and hasattr(wm, "lampway_chat_send_ok"):
        chat_route.sync(wm, scene)


def _tick():
    refresh()
    return S.poll_interval()


def draw(self, context):
    layout = self.layout
    row = layout.row(align=True)
    if not S.STATE["ok"]:
        row.label(text=S.down_line(), icon='LAMPWAY_COIN')
        row.label(text="egress unknown", icon='LAMPWAY_WIRE')
        _plug(row)
        return   # the version is the status bar's own (Blender draws it at the far right)
    count = S.waiting()
    if count:
        row.operator("lampway.status_waiting", text=f"{count} waiting for you", icon='LAMPWAY_HAND', depress=True)
    text, step, _tip = S.spend_line()
    if step is None:
        row.operator("lampway.status_spend", text=text, icon='LAMPWAY_COIN', emboss=False)
    else:
        row.operator("lampway.status_spend", text=text, icon_value=preview(f"meter_{step}"), emboss=False)
    chip, glyph, _tip = S.wire_chip()
    if glyph == "wire_dot":
        glyph = "wire_dot_b" if FRAME["b"] else "wire_dot_a"
    row.operator("lampway.status_wire", text=chip, icon_value=preview(glyph), emboss=False)
    _plug(row)


def _plug(row):
    """Connections, beside the wire chip (specs/connections/connections_face.md 3): which accounts work, and which may send."""
    row.operator("lampway.connections_open", text="", icon_value=preview("plug"), emboss=False)


class LAMPWAY_OT_status_waiting(Operator):
    """Open the first decision that waits for your click"""
    bl_idname = "lampway.status_waiting"
    bl_label = "Waiting for you"

    def execute(self, context):
        pending = [a for a in (S.STATE["studio"] or {}).get("approvals") or [] if a.get("state") == "pending"]
        if not pending:
            self.report({'INFO'}, "Nothing waits for you")
            return {'CANCELLED'}
        first = pending[0]
        if (first.get("settings") or {}).get("unit") == "answer":
            self.report({'INFO'}, f"{first.get('label') or 'A question'} waits for your answer in the Studios panel")
            return {'FINISHED'}
        return bpy.ops.lampway.studio_confirm('INVOKE_DEFAULT', approval_id=first["id"], price=float(first.get("price") or 0.0),
                                              label=first.get("label") or "")


class LAMPWAY_OT_status_spend(Operator):
    """What has been spent, against which cap"""
    bl_idname = "lampway.status_spend"
    bl_label = "Spend"

    @classmethod
    def description(cls, context, properties):
        return S.spend_line()[2]

    def execute(self, context):
        self.report({'INFO'}, S.spend_line()[2])
        return {'FINISHED'}


class LAMPWAY_OT_status_wire(Operator):
    """Whether data is leaving this machine"""
    bl_idname = "lampway.status_wire"
    bl_label = "Egress"

    @classmethod
    def description(cls, context, properties):
        return S.wire_chip()[2]

    def execute(self, context):
        """Opens "What leaves this machine" (facelift contract 12)."""
        return bpy.ops.lampway.privacy_open()


classes = (LAMPWAY_OT_status_waiting, LAMPWAY_OT_status_spend, LAMPWAY_OT_status_wire)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.STATUSBAR_HT_header.append(draw)
    if not bpy.app.background and not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=1.0, persistent=True)


def unregister():
    for fn in (_tick, _wire_frame):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    bpy.types.STATUSBAR_HT_header.remove(draw)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
