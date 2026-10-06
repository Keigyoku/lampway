# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Asset Vault editor in the ``MIXAR_ASSETS`` space (specs/asset_library/asset_ui_editor.md section 5; the look: client_facelift 09 and DESIGN v2 sections 13-14).

Header: the space switcher, the title, search, kind segments, sort, view, tile size and the counts. Body: facets with counts | results | detail, three columns from 900 px, two
from 600, one below. ``draw`` only reads the session's view-model and lays out; every network call is an operator's, run off the main thread."""

import json
import os

from bpy.types import Header, Panel

from mixar.modules.asset_library import constants as K
from mixar.modules.asset_library.core import present as PR
from mixar.modules.asset_library.core import views as VW

KIND_ICON = {"mesh": "MESH_DATA", "image": "IMAGE_DATA", "material": "MATERIAL", "texture_set": "TEXTURE", "map": "TEXTURE", "hdri": "WORLD", "video": "FILE_MOVIE",
             "animation": "ACTION", "rig": "ARMATURE_DATA", "uv_layout": "UV", "prompt": "TEXT", "receipt": "FILE_TEXT", "collection": "ASSET_MANAGER"}
GLYPH_ICON = {"lamp": "LIGHT", "wire": "URL"}


def _ses():
    from mixar.modules.asset_library.core import session
    return session


def _boards(col, vm) -> None:
    head = col.row(align=True)
    head.label(text="Boards")
    head.operator("mixar.asset_library_boards", text="", icon="FILE_REFRESH", emboss=False)
    for b in vm.boards:
        col.operator("mixar.asset_library_board", text=b["name"], icon="IMAGE_REFERENCE").board_id = b["id"]


def _facets(col, vm) -> None:
    for facet in K.FACETS:
        rows = vm.facets.get(facet) or []
        if not rows:
            continue
        col.label(text=facet.replace("_", " ").title())
        chosen = vm.terms.get(facet, []) if facet != "kind" else ([vm.kind] if vm.kind else [])
        for r in rows:
            value = str(r["value"])
            row = col.row(align=True)
            op = row.operator("mixar.asset_library_toggle_facet", text="", icon="CHECKBOX_HLT" if value in chosen else "CHECKBOX_DEHLT", emboss=False)
            op.facet, op.value = facet, value
            row.label(text=f"{value}  {r['count']}")


def _results(col, vm, props, width) -> None:
    if vm.banner:
        col.label(text=vm.banner, icon="ZOOM_ALL")
    if not vm.items:
        col.label(text=vm.empty_text() or "Searching", icon="INFO")
        return
    tile = props.tile_size if props is not None else K.TILE_DEFAULT
    if props is None or props.view == "GRID":
        grid = col.grid_flow(columns=max(1, int(width // (tile + 16))), even_columns=True, even_rows=True, align=False)
        for it in vm.items:
            cell = grid.column(align=True)
            icon = _ses().thumb_icon(it)
            if icon:
                cell.template_icon(icon_value=icon, scale=tile / 20.0)
            else:
                cell.label(text="", icon=KIND_ICON.get(it.get("kind"), "QUESTION"))
            op = cell.operator("mixar.asset_library_select", text=it["name"], depress=it["id"] in vm.selected)
            op.asset_id = it["id"]
    else:
        for it in vm.items:
            row = col.row(align=True)
            op = row.operator("mixar.asset_library_select", text=it["name"], icon=KIND_ICON.get(it.get("kind"), "QUESTION"), depress=it["id"] in vm.selected)
            op.asset_id = it["id"]
            row.label(text=f"{it.get('kind')}  {'*' * int(it.get('rating') or 0)}")
    nav = col.row(align=True)
    sub = nav.row(align=True)
    sub.enabled = vm.can_prev
    sub.operator("mixar.asset_library_page", text="", icon="TRIA_LEFT").direction = "PREV"
    nav.label(text=f"{vm.total} assets, {len(vm.items)} shown")
    sub = nav.row(align=True)
    sub.enabled = vm.can_next
    sub.operator("mixar.asset_library_page", text="", icon="TRIA_RIGHT").direction = "NEXT"


MODE_LABELS = (("preview", "Turntable"), ("uv", "UV"), ("maps", "Maps"), ("lineage", "Lineage"), ("compare", "Compare"), ("video", "Video"))


def _frame(col, vm, icon_scale=10.0) -> None:
    fb = vm.flipbook
    icon = _ses().file_icon(fb.path())
    if icon:
        col.template_icon(icon_value=icon, scale=icon_scale)
    else:                                                        # no preview icons without a window (a headless run): the frame is named instead
        col.label(text=os.path.basename(fb.path() or ""), icon="IMAGE_DATA")
    row = col.row(align=True)
    row.operator("mixar.asset_library_play_toggle", text="", icon="PAUSE" if fb.playing else "PLAY")
    row.label(text=f"frame {fb.frame + 1} of {len(fb.frames)}, {fb.fps} fps")


def _clip_pair(col, vm) -> None:
    """Two clips on one scrub bar: the alignment modes, then frame A | frame B of the shared flipbook."""
    modes = col.row(align=True)
    for mode, label in (("START", "Start"), ("TIME", "Time"), ("MOTION", "Motion")):
        modes.operator("mixar.asset_library_align", text=label, depress=bool(vm.align and vm.align["mode"] == mode.lower())).mode = mode
    if not vm.align:
        col.label(text="Choose how to line the two clips up", icon="INFO")
        return
    pair = vm.flipbook.path() or ("", "")
    row = col.row()
    for path in pair:
        icon = _ses().file_icon(path)
        row.template_icon(icon_value=icon, scale=8.0) if icon else None
    col.label(text=f"{os.path.basename(pair[0])} | {os.path.basename(pair[1])}")
    ctl = col.row(align=True)
    ctl.operator("mixar.asset_library_play_toggle", text="", icon="PAUSE" if vm.flipbook.playing else "PLAY")
    off = vm.align.get("offset") or {}
    ctl.label(text=f"frame {vm.flipbook.frame + 1} of {len(vm.flipbook.frames)}, offset A {off.get('a', 0)} B {off.get('b', 0)}")


def _preview(col, vm, rec) -> None:
    modes = col.row(align=True)
    for mode, label in MODE_LABELS:
        op = modes.operator("mixar.asset_library_set_view", text=label, depress=vm.view_mode == mode)
        op.mode = mode
    p = vm.products or {}
    mode = vm.view_mode
    if mode == "compare":
        kinds = {it["id"]: it.get("kind") for it in vm.items}
        ids = ([rec["id"]] if rec["id"] not in vm.compare else []) + list(vm.compare)       # the selected asset is A; Compare on another makes B
        records = [{"id": i, "kind": kinds.get(i) or (rec["kind"] if i == rec["id"] else "?")} for i in ids]
        refusal = VW.compare_refusal(records)
        if refusal:
            col.label(text=refusal, icon="INFO")
        elif all(r["kind"] == "video" for r in records[-2:]):
            _clip_pair(col, vm)
        else:
            pair = col.row()
            for i in ids[-2:]:
                cell = pair.column()
                item = next((it for it in vm.items if it["id"] == i), {"id": i, "kind": kinds.get(i), "thumb": None})
                icon = _ses().thumb_icon(item)
                cell.template_icon(icon_value=icon, scale=8.0) if icon else cell.label(text="", icon=KIND_ICON.get(item.get("kind"), "QUESTION"))
                cell.label(text=item.get("name") or i)
        return
    if mode == "lineage":
        lin = vm.lineage if getattr(vm, "lineage", None) and vm.lineage.get("root") == rec["id"] else None
        if lin is None:
            col.operator("mixar.asset_library_lineage", text="Show the lineage", icon="NODETREE").asset_id = rec["id"]
            return
        icon = _ses().file_icon(lin.get("png"))
        if icon:
            col.template_icon(icon_value=icon, scale=12.0)
        op = col.operator("mixar.asset_library_canvas", text="Open on the canvas", icon="FULLSCREEN_ENTER")
        op.action, op.path, op.lineage = "OPEN", lin.get("png") or "", json.dumps({k: lin[k] for k in ("root", "nodes", "width", "height") if k in lin})
        for n in lin["nodes"]:
            op = col.operator("mixar.asset_library_select", text=f"{n['name']} ({n['kind']})", depress=n["id"] == rec["id"])
            op.asset_id = n["id"]
        if lin.get("collapsed"):
            col.label(text=f"{lin['collapsed']} more beyond the limit", icon="THREE_DOTS")
        return
    if mode == "maps":
        stamp = VW.normal_stamp(rec)
        if stamp:
            col.label(text=stamp, icon="NORMALS_FACE")
    if mode == "video":
        chip = VW.dup_chip(rec.get("stats") or {})
        if chip:
            col.label(text=chip["text"], icon="ERROR")
        col.label(text=VW.fps_badge(rec.get("stats") or {}), icon="TIME")
    status = VW.view_status(mode, rec, p)
    if status:
        col.label(text=status, icon="INFO")
    elif mode in ("preview", "video"):
        _frame(col, vm)
    else:
        path = p.get({"uv": "overlay", "maps": "sheet"}[mode])
        icon = _ses().file_icon(path)
        if icon:
            col.template_icon(icon_value=icon, scale=10.0)
        if path:
            op = col.operator("mixar.asset_library_canvas", text="Open on the canvas", icon="FULLSCREEN_ENTER")
            op.action, op.path = "OPEN", path


def _detail(col, vm, scene_ok: bool) -> None:
    rec = vm.detail
    if not rec or rec.get("id") != vm.active:
        col.label(text="Select an asset" if vm.active is None else "Reading the asset", icon="INFO")
        return
    col.label(text=rec.get("name") or rec["id"], icon=KIND_ICON.get(rec.get("kind"), "QUESTION"))
    _preview(col, vm, rec)
    stars = col.row(align=True)
    for n in range(1, 6):
        op = stars.operator("mixar.asset_library_rate", text="", icon="SOLO_ON" if n <= int(rec.get("rating") or 0) else "SOLO_OFF", emboss=False)
        op.asset_id, op.stars = rec["id"], n
    if rec.get("license_id") or rec.get("attribution"):
        col.label(text=str(rec.get("attribution") or rec.get("license_id")), icon="COPY_ID")
    for label, value in PR.stats_rows(rec):
        col.label(text=f"{label}  {value}")
    head, body = col.panel("MIXAR_ASSETS_vault_provenance", default_closed=True)
    head.label(text=f"Where it came from: {PR.provenance_glance(rec)}")
    if body is not None:
        for line in PR.provenance_lines(rec):
            body.label(text=line)
    chip = PR.similar_chip(_ses().BACKEND)
    sim = col.row(align=True)
    op = sim.operator("mixar.asset_library_find_similar", text="Find like this", icon="ZOOM_ALL")
    op.asset_id, op.name = rec["id"], rec.get("name") or ""
    sim.label(text=chip["text"], icon=GLYPH_ICON[chip["glyph"]])
    act = col.row(align=True)
    act.enabled = scene_ok
    act.scale_y = 1.4
    act.operator("mixar.asset_library_place", text="Place in scene", icon="IMPORT").asset_id = rec["id"]
    if rec.get("kind") == "animation":
        act.operator("mixar.asset_library_to_timeline", text="To timeline", icon="NLA").asset_id = rec["id"]
    more = col.row(align=True)
    more.operator("mixar.asset_library_compare_add", text="Compare", icon="SPLIT_HORIZONTAL").asset_id = rec["id"]
    path = next((loc["path"] for f in rec.get("files") or [] if f.get("role") == "main" for loc in f.get("locations") or [] if not loc.get("missing")), None)
    if path:
        more.operator("mixar.asset_library_open_folder", text="Show in folder", icon="FILE_FOLDER").path = path
    more.operator("mixar.asset_library_copy", text="Copy id", icon="COPYDOWN").text = rec["id"]


def _canvas_bar(layout) -> None:
    row = layout.row(align=True)
    row.operator("mixar.asset_library_canvas", text="Fit", icon="ZOOM_ALL").action = "FIT"
    row.operator("mixar.asset_library_canvas", text="Close canvas", icon="X").action = "CLOSE"
    row.label(text="The wheel zooms, the middle button drags, a click on a node selects it, Esc closes")


def draw_body(layout, context) -> None:
    from mixar.modules.asset_library.core import canvas_view as CV
    if CV.STATE["open"]:
        _canvas_bar(layout)                                       # the picture is drawn by the canvas handler below this bar: nothing else is laid out under it
        return
    vm = _ses().VM
    props = getattr(context.window_manager, "mixar_lib", None)
    width = getattr(getattr(context, "region", None), "width", 1200) or 1200
    scene_ok = context.scene is not None
    if vm.status == "offline":
        layout.label(text=vm.empty_text(), icon="ERROR")
    if width >= 900:
        split = layout.split(factor=0.2)
        left = split.column()
        _facets(left, vm)
        _boards(left, vm)
        rest = split.split(factor=0.625)
        _results(rest.column(), vm, props, width * 0.5)
        _detail(rest.column(), vm, scene_ok)
    elif width >= 600:
        split = layout.split(factor=0.62)
        _results(split.column(), vm, props, width * 0.62)
        _detail(split.column(), vm, scene_ok)
    else:
        _results(layout.column(), vm, props, width)
        _detail(layout.column(), vm, scene_ok)
        _facets(layout.column(), vm)


def _import_row(layout, vm) -> None:
    st = vm.importing["state"]
    if st == "preview":
        layout.label(text=vm.import_summary(), icon="IMPORT")
        layout.operator("mixar.asset_library_import_confirm", text="Import", icon="CHECKMARK")
        layout.operator("mixar.asset_library_import_confirm", text="", icon="X").cancel = True
        return
    if st in ("scanning", "importing", "done", "failed"):
        layout.label(text=vm.import_summary(), icon="ERROR" if st == "failed" else "INFO")
    layout.operator("mixar.asset_library_initial_import", text="Initial import", icon="FILE_FOLDER")


class MIXAR_ASSETS_HT_vault(Header):
    """The Asset Vault's header: keeps the stock Editor Type dropdown (every editor stays swappable) and leads with the search."""
    bl_space_type = K.SPACE

    def draw(self, context):
        layout = self.layout
        layout.template_header()
        layout.label(text="Asset Vault")
        props = context.window_manager.mixar_lib
        layout.prop(props, "query", text="", icon="VIEWZOOM")
        layout.prop(props, "kind", text="")
        layout.prop(props, "sort", text="")
        layout.prop(props, "view", text="", expand=True)
        layout.prop(props, "tile_size", text="")
        vm = _ses().VM
        layout.label(text=f"{vm.total} assets" if vm.status != "offline" else "offline", icon="ERROR" if vm.status == "offline" else "NONE")
        _import_row(layout, vm)
        layout.operator("mixar.asset_library_save_search", text="", icon="BOOKMARKS")
        layout.operator("mixar.asset_library_open_window", text="", icon="WINDOW")


class MIXAR_ASSETS_PT_vault(Panel):
    bl_label = ""
    bl_idname = "MIXAR_ASSETS_PT_vault"
    bl_space_type = K.SPACE
    bl_region_type = "WINDOW"
    bl_options = {"HIDE_HEADER"}

    def draw(self, context):
        _ses().ensure_running()
        draw_body(self.layout, context)


classes = (MIXAR_ASSETS_HT_vault, MIXAR_ASSETS_PT_vault)
