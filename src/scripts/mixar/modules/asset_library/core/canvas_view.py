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
STATE = {"open": False, "path": None, "layout": None, "canvas": None, "image": None, "area": None}
_handle = None


def open_canvas(path: str, layout=None) -> None:
    img = bpy.data.images.load(path, check_existing=True)
    STATE.update(open=True, path=path, layout=layout, image=img.name, canvas=Canvas(image=tuple(img.size)), area=None)


def close() -> None:
    STATE.update(open=False, path=None, layout=None, canvas=None, image=None, area=None)


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
    if region is None or STATE["image"] is None:
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
