# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The model-compare window (facelift contract 11 over specs/mrmak/05-model-compare.md, section 6.4's local-view path):
one new window on the scratch scene, its 3D view split into one area per model, each area in local view of its own
model; a POST_PIXEL overlay per area draws the alias large and "name hidden" while blind; the Compare panel (the
sidebar of every compare area) carries the mode bar, Sync / Spin / Blind, each view's strip, the pair table and the blind
pick. Cameras follow one another on a 100 ms timer while Sync is on.

Modes built here: Wire, Clay, Normals (Solid with the normal matcap), Textured (Material Preview). The data modes (Base
colour, Normal map, ORM) need the replacement materials of section 6.5 and are drawn disabled with that said."""

import json
from pathlib import Path

import bpy
from bpy.props import IntProperty, StringProperty
from bpy.types import Operator, Panel

from mixar.modules.lampway_tools import compare_face

STATE = {"manifest": None, "stats": [], "numbers": {}, "labels": {}, "revealed": False, "picked": None, "areas": {}, "mode": "1",
         "sync": True, "spin": False, "window": None, "last": None, "root": "", "set_dir": ""}
DATA_MODES = {"5", "6", "7"}
_HANDLE = []


def _root():
    from mixar.modules.lampway_tools import settings
    return str(settings.load().project_root)


def load_set(set_id: str, piece: str, root: str) -> None:
    """Read compare.json (and numbers.json when the numbers ran); stats come from the files themselves, read without Blender."""
    from mixar.modules.lampway_tools.features import model_compare as MC
    man, d = MC._load({"id": set_id, "piece": piece}, root)
    files = [m for m in man["models"] if m.get("file")]
    stats = MC.stats([{"file": m["file"]} for m in files], root) if len(files) == len(man["models"]) else [{} for _ in man["models"]]
    numbers = json.loads((d / "numbers.json").read_text()) if (d / "numbers.json").exists() else {}
    STATE.update(manifest=man, stats=stats, numbers=numbers, revealed=not man["blind"], picked=None, root=root, set_dir=str(d),
                 labels={m["index"]: m.get("label") or m["alias"] or m["object"] for m in man["models"]})


def overlay_for(area_ptr) -> list:
    """The overlay text of a compare area, or [] for any other area."""
    i = STATE["areas"].get(area_ptr)
    man = STATE["manifest"]
    if i is None or man is None:
        return []
    m = man["models"][i]
    view = {"alias": m.get("alias") or "ABCD"[i], "label": STATE["labels"].get(i) if STATE["revealed"] else None}
    return compare_face.overlay_texts(view, blind=bool(man["blind"]), revealed=STATE["revealed"])


def _draw_overlay():
    import blf
    area = bpy.context.area
    texts = overlay_for(area.as_pointer() if area else 0)
    if not texts:
        return
    font = 0
    blf.size(font, 40)
    blf.color(font, 0.93, 0.73, 0.27, 1.0)
    blf.position(font, 24, area.height - 120, 0)
    blf.draw(font, texts[0])
    blf.size(font, 14)
    blf.color(font, 0.66, 0.65, 0.62, 1.0)
    blf.position(font, 24, area.height - 144, 0)
    blf.draw(font, texts[1])


def _compare_areas():
    out = []
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.as_pointer() in STATE["areas"]:
                out.append((window, area))
    return out


def _sync():
    if not STATE["sync"] or not STATE["areas"]:
        return 0.1 if STATE["areas"] else None
    views = []
    for _w, area in _compare_areas():
        r3d = area.spaces.active.region_3d
        views.append((area, r3d))
    current = [(tuple(map(tuple, r.view_matrix)), round(r.view_distance, 6)) for _a, r in views]
    if STATE["last"] is not None and len(current) == len(STATE["last"]):
        moved = next((k for k, (cur, old) in enumerate(zip(current, STATE["last"])) if cur != old), None)
        if moved is not None:
            src = views[moved][1]
            for k, (_a, r) in enumerate(views):
                if k != moved:
                    r.view_rotation = src.view_rotation.copy()
                    r.view_location = src.view_location.copy()
                    r.view_distance = src.view_distance
            current = [(tuple(map(tuple, r.view_matrix)), round(r.view_distance, 6)) for _a, r in views]
    STATE["last"] = current
    return 0.1


def apply_mode(mode: str) -> None:
    STATE["mode"] = mode
    for _w, area in _compare_areas():
        shading = area.spaces.active.shading
        overlay = area.spaces.active.overlay
        overlay.show_wireframes = mode == "1"
        if mode == "1":
            shading.type, shading.light, shading.color_type = 'SOLID', 'STUDIO', 'SINGLE'
            shading.single_color = (0.04, 0.045, 0.06)
            overlay.wireframe_opacity = 1.0
        elif mode == "2":
            shading.type, shading.light, shading.color_type = 'SOLID', 'STUDIO', 'SINGLE'
            shading.single_color = (0.76, 0.76, 0.76)
        elif mode == "3":
            shading.type, shading.light = 'SOLID', 'MATCAP'
            shading.studio_light = "check_normal+y.exr"
        elif mode == "4":
            shading.type = 'MATERIAL'
        area.tag_redraw()


def open_window(context) -> int:
    """A new window on the scratch scene, one 3D area per model in local view of that model. Returns the area count."""
    from mixar.modules.lampway_tools.features import model_compare as MC
    man = STATE["manifest"]
    scene = bpy.data.scenes.get(MC.SCRATCH_SCENE)
    if man is None or scene is None:
        raise RuntimeError("build the compare set first (model_compare build)")
    before = set(context.window_manager.windows[:])
    bpy.ops.wm.window_new()
    window = next(w for w in context.window_manager.windows if w not in before)
    window.scene = scene
    screen = window.screen
    view = max((a for a in screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height, default=None)
    if view is None:
        view = max(screen.areas, key=lambda a: a.width * a.height)
        view.type = 'VIEW_3D'
    for other in [a for a in screen.areas if a != view]:   # one canvas: the views share the window
        with context.temp_override(window=window, area=other):
            try:
                bpy.ops.screen.area_close()
            except RuntimeError:
                pass
    n = len(man["models"])
    target = view
    for k in range(n - 1):
        # The split leaves the left part as one view and the rest to split again: 1/n of the window each.
        with context.temp_override(window=window, area=target, screen=screen):
            bpy.ops.screen.area_split(direction='VERTICAL', factor=1.0 / (n - k))
        target = max((a for a in screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.x)
    areas = sorted([a for a in screen.areas if a.type == 'VIEW_3D'], key=lambda a: a.x)[:n]
    STATE["areas"] = {}
    for i, area in enumerate(areas):
        STATE["areas"][area.as_pointer()] = i
        ob = scene.objects.get(man["models"][i]["object"])
        region = next(r for r in area.regions if r.type == 'WINDOW')
        if ob is not None:
            with context.temp_override(window=window, area=area, region=region, scene=scene):
                for o in scene.objects:
                    o.select_set(o == ob)
                bpy.context.view_layer.objects.active = ob
                bpy.ops.view3d.localview(frame_selected=True)
    STATE["window"] = window.as_pointer()
    STATE["last"] = None
    if not _HANDLE:
        _HANDLE.append(bpy.types.SpaceView3D.draw_handler_add(_draw_overlay, (), 'WINDOW', 'POST_PIXEL'))
    if not bpy.app.timers.is_registered(_sync):
        bpy.app.timers.register(_sync, first_interval=0.1)
    apply_mode(STATE["mode"])
    return len(areas)


class LAMPWAY_OT_compare_open(Operator):
    """Open a compare set in its own window: one view per model, one camera"""
    bl_idname = "lampway.compare_open"
    bl_label = "Compare"
    set_id: StringProperty(options={"SKIP_SAVE"})
    piece: StringProperty(default="compare", options={"SKIP_SAVE"})

    def execute(self, context):
        try:
            load_set(self.set_id, self.piece, _root())
            n = open_window(context)
        except Exception as exc:  # noqa: BLE001  (a missing set or a refused split is said, never a crash)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"{n} views")
        return {"FINISHED"}


class LAMPWAY_OT_compare_mode(Operator):
    """Change every view at once"""
    bl_idname = "lampway.compare_mode"
    bl_label = "Mode"
    bl_options = {"INTERNAL"}
    mode: StringProperty(default="1", options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        if properties.mode in DATA_MODES:
            return "Not built yet: the data modes need the replacement materials of the compare spec (section 6.5)"
        return dict(compare_face.MODES).get(properties.mode, "Mode")

    def execute(self, context):
        if self.mode in DATA_MODES:
            self.report({"WARNING"}, "not built yet: the data modes need their replacement materials")
            return {"CANCELLED"}
        apply_mode(self.mode)
        return {"FINISHED"}


class LAMPWAY_OT_compare_toggle(Operator):
    """Sync the cameras, spin, or keep the names blind"""
    bl_idname = "lampway.compare_toggle"
    bl_label = "Toggle"
    bl_options = {"INTERNAL"}
    what: StringProperty(options={"SKIP_SAVE"})

    def execute(self, context):
        if self.what in ("sync", "spin"):
            STATE[self.what] = not STATE[self.what]
        return {"FINISHED"}


class LAMPWAY_OT_compare_pick(Operator):
    """Your pick: one decision row in the ledger, by you; while blind the names show only after it"""
    bl_idname = "lampway.compare_pick"
    bl_label = "Pick"
    model: IntProperty(default=-1, options={"SKIP_SAVE"})
    reveal_only: StringProperty(default="", options={"SKIP_SAVE"})

    def execute(self, context):
        from mixar.modules.lampway_tools import human_gate
        from mixar.modules.lampway_tools.features import model_compare as MC
        man = STATE["manifest"]
        if man is None:
            return {"CANCELLED"}
        if human_gate.script_running():
            self.report({"ERROR"}, "only the user picks: a script cannot press it")
            return {"CANCELLED"}
        if not self.reveal_only:
            MC.record_pick(man["id"], man["piece"], self.model, "blind" if man["blind"] and not STATE["revealed"] else "named", "", "user", STATE["root"])
            STATE["picked"] = self.model
        if man["blind"]:
            shown = MC.reveal({"id": man["id"], "piece": man["piece"]}, False, STATE["root"])
            STATE["labels"] = {m["index"]: m["label"] for m in shown["models"]}
            STATE["revealed"] = True
        for _w, area in _compare_areas():
            area.tag_redraw()
        return {"FINISHED"}


def draw_compare(layout, context):
    man = STATE["manifest"]
    if man is None:
        layout.label(text="No compare set is open")
        return
    layout.label(text=f"{man['piece']}, {len(man['models'])} variants, normalised to a 2-unit box", icon='LAMPWAY_COMPARE')
    modes = layout.row(align=True)
    for key, word in compare_face.MODES:
        col = modes.row(align=True)
        col.enabled = key not in DATA_MODES
        op = col.operator("lampway.compare_mode", text=f"{key} {word}", depress=STATE["mode"] == key)
        op.mode = key
    toggles = layout.row(align=True)
    for what, word in (("sync", "Sync"), ("spin", "Spin")):
        toggles.operator("lampway.compare_toggle", text=word, depress=STATE[what]).what = what
    toggles.label(text="Blind" if man["blind"] and not STATE["revealed"] else "Names shown")
    for i, m in enumerate(man["models"]):
        box = layout.box()
        head = box.row()
        alias = m.get("alias") or "ABCD"[i]
        head.label(text=f"{alias}: {'name hidden' if man['blind'] and not STATE['revealed'] else STATE['labels'].get(i)}")
        pick = head.operator("lampway.compare_pick", text=f"Pick {alias}", depress=STATE["picked"] == i)
        pick.model = i
        st = STATE["stats"][i] if i < len(STATE["stats"]) else {}
        if st:
            s = compare_face.strip(st)
            row = box.row()
            row.label(text=s["tris"])
            row.label(text=s["hover"])
            chans = box.row()
            for c in s["channels"]:
                cell = chans.row()
                cell.alert = c["tone"] == "stop"
                cell.label(text=c["text"], icon="X" if c["glyph"] == "cross" else "NONE")
    rows = compare_face.pair_rows(STATE["numbers"], "".join((m.get("alias") or "ABCD"[i]) for i, m in enumerate(man["models"])))
    if rows:
        layout.label(text="pair, outline IoU (worst view), interior difference")
        for r in rows:
            line = layout.row()
            line.label(text=r["pair"])
            line.label(text=r["iou"])
            cell = line.row()
            cell.alert = r["interior_tone"] == "accent"
            cell.label(text=r["interior"])
    if man["blind"] and not STATE["revealed"]:
        box = layout.box()
        box.label(text="Blind pick: a decision row in the ledger, by you, blind")
        box.operator("lampway.compare_pick", text="Reveal without picking").reveal_only = "yes"


class LAMPWAY_PT_compare(Panel):
    bl_idname = "LAMPWAY_PT_compare"
    bl_label = "Compare"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Compare"

    @classmethod
    def poll(cls, context):
        return STATE["manifest"] is not None

    def draw(self, context):
        draw_compare(self.layout, context)


classes = [LAMPWAY_OT_compare_open, LAMPWAY_OT_compare_mode, LAMPWAY_OT_compare_toggle, LAMPWAY_OT_compare_pick, LAMPWAY_PT_compare]
