# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault's canvas in Blender: one picture (a lineage graph, a UV overlay, a maps sheet, a frame) drawn with ``gpu`` in a POST_PIXEL handler over the Vault's region,
panned and zoomed by ``mixar.asset_library_canvas`` (a modal operator), clicked to select a lineage node. The mapping is ``canvas.Canvas``; while the canvas is open the
panel draws only its bar, so nothing is drawn under the picture."""

import bpy

from .. import constants as K
from .canvas import Canvas

BAR_PX = 44
STATE = {"open": False, "path": None, "layout": None, "canvas": None, "image": None, "area": None, "board": None}
_handle = None


def open_canvas(path: str, layout=None) -> None:
    img = bpy.data.images.load(path, check_existing=True)
    STATE.update(open=True, path=path, layout=layout, image=img.name, canvas=Canvas(image=tuple(img.size)), area=None, board=None)


def close() -> None:
    STATE.update(open=False, path=None, layout=None, canvas=None, image=None, area=None, board=None)


def view_rect(region) -> tuple:
    return (8.0, 8.0, region.width - 8.0, region.height - BAR_PX)


def ensure_fitted(region) -> Canvas:
    c = STATE["canvas"]
    v = view_rect(region)
    if c.view != v:
        first = c.view == (0.0, 0.0, 1.0, 1.0)
        c.set_view(v)
        if first:
            c.fit()
    return c


def click(sx: float, sy: float):
    """The lineage node under a click, or None; selects it in the editor."""
    c, lay = STATE["canvas"], STATE["layout"]
    if c is None or lay is None or not c.inside(sx, sy):
        return None
    ix, iy = c.to_image(sx, sy)
    for n in lay.get("nodes") or []:
        if n["x"] <= ix < n["x"] + n["w"] and n["y"] <= iy < n["y"] + n["h"]:
            from . import session
            session.VM.select(n["id"])
            return n["id"]
    return None


def _draw():
    if not STATE["open"]:
        return
    region = bpy.context.region
    if region is None:
        return
    if STATE.get("board"):
        _draw_board(ensure_fitted(region))
        return
    if STATE["image"] is None:
        return
    img = bpy.data.images.get(STATE["image"])
    if img is None:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    c = ensure_fitted(region)
    x0, y0, x1, y1 = c.quad()
    vx0, vy0, vx1, vy1 = c.view
    tex = gpu.texture.from_image(img)
    shader = gpu.shader.from_builtin("IMAGE")
    batch = batch_for_shader(shader, "TRI_FAN", {"pos": ((x0, y0), (x1, y0), (x1, y1), (x0, y1)), "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1))})
    gpu.state.scissor_test_set(True)
    gpu.state.scissor_set(int(vx0), int(vy0), int(vx1 - vx0), int(vy1 - vy0))
    shader.bind()
    shader.uniform_sampler("image", tex)
    batch.draw(shader)
    gpu.state.scissor_test_set(False)


def install() -> None:
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceMixarAssets.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL")


def uninstall() -> None:
    global _handle
    if _handle is not None:
        bpy.types.SpaceMixarAssets.draw_handler_remove(_handle, "WINDOW")
        _handle = None


def redraw() -> None:
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == K.SPACE:
                area.tag_redraw()


# ---- a board on the canvas: tiles in board pixels, dragged to a new place

TILE, GAP = 128.0, 16.0


def open_board(board_id: str, items: list) -> None:
    from . import board as B
    placed = B.place(items, tile=TILE, gap=GAP)
    STATE.update(open=True, path=None, layout=None, image=None, area=None, board={"id": board_id, "items": placed, "drag": None},
                 canvas=Canvas(image=B.extent(placed, tile=TILE, gap=GAP)))


def board_press(sx: float, sy: float):
    from . import board as B
    bd, c = STATE.get("board"), STATE["canvas"]
    if not bd or c is None or not c.inside(sx, sy):
        return None
    ix, iy = c.to_image(sx, sy)
    aid = B.hit(bd["items"], ix, iy, tile=TILE)
    if aid:
        bd["drag"] = B.Drag(bd["items"], aid, ix, iy)
    return aid


def board_drag(sx: float, sy: float) -> bool:
    bd, c = STATE.get("board"), STATE["canvas"]
    if not bd or not bd.get("drag"):
        return False
    bd["drag"].move(*c.to_image(sx, sy))
    return True


def board_release():
    """The dragged tile's new place, saved on the server off the main thread."""
    bd = STATE.get("board")
    if not bd or not bd.get("drag"):
        return None
    aid, x, y = bd["drag"].end()
    bd["drag"] = None
    from mixar.modules.lampway_tools import library_client as LC
    from . import session
    board = bd["id"]
    session.PUMP.later(lambda: LC.board_move(board, aid, x, y), lambda ok, v: None if ok else session.VM.__setattr__("message", str(v)))
    return aid, x, y


def _draw_board(c) -> None:
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
    from . import session
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    shader.bind()
    h = c.image[1]
    for it in STATE["board"]["items"]:
        x0, y1 = c.ox + it["x"] * c.zoom, c.oy + (h - it["y"]) * c.zoom
        x1, y0 = x0 + TILE * c.zoom, y1 - TILE * c.zoom
        selected = it["id"] == session.VM.active
        shader.uniform_float("color", (0.35, 0.28, 0.13, 1.0) if selected else (0.12, 0.13, 0.17, 1.0))
        batch_for_shader(shader, "TRI_FAN", {"pos": ((x0, y0), (x1, y0), (x1, y1), (x0, y1))}).draw(shader)
        img = bpy.data.images.load(it["thumb"], check_existing=True) if it.get("thumb") else None
        if img is not None:
            ishader = gpu.shader.from_builtin("IMAGE")
            pad = 6 * c.zoom
            ishader.bind()
            ishader.uniform_sampler("image", gpu.texture.from_image(img))
            batch_for_shader(ishader, "TRI_FAN", {"pos": ((x0 + pad, y0 + 22 * c.zoom), (x1 - pad, y0 + 22 * c.zoom), (x1 - pad, y1 - pad), (x0 + pad, y1 - pad)),
                                                  "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1))}).draw(ishader)
            shader.bind()
        blf.size(0, max(8.0, 11.0 * c.zoom))
        blf.position(0, x0 + 6 * c.zoom, y0 + 7 * c.zoom, 0)
        blf.color(0, 0.93, 0.91, 0.87, 1.0)
        blf.draw(0, str(it.get("name") or it["id"]))
