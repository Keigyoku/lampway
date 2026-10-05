/* SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup GHOST
 *
 * X11 Mixar_WindowSetCornerRadius: clips the window to a rounded rectangle with
 * the X Shape extension.
 *
 * X11 GL windows are opaque, so without a shape the pill's capsule and the
 * island's card sit on visible square corners. A shape mask is binary (no
 * anti-aliasing) but needs no compositor and no ARGB visual. The mask has a
 * fixed size, so it is rebuilt whenever Mixar_WindowForceSize resizes the
 * window - otherwise a window that grows would be clipped to its old size.
 */

#ifdef WITH_GHOST_X11

#  include <X11/Xlib.h>

#  ifdef WITH_MIXAR_X11_SHAPE
#    include <X11/extensions/shape.h>
#  endif

#  include <algorithm>
#  include <vector>

#  include "GHOST_MixarX11.hh"

#  ifdef WITH_MIXAR_X11_SHAPE

struct MixarX11Shape {
  Window window;
  float radius; /* Logical units, as passed to Mixar_WindowSetCornerRadius. */
};

static std::vector<MixarX11Shape> s_x11_shapes;

static bool mixar_x11_shape_supported(Display *display)
{
  static int supported = -1;
  if (supported < 0) {
    int event_base = 0, error_base = 0;
    supported = XShapeQueryExtension(display, &event_base, &error_base) ? 1 : 0;
  }
  return supported == 1;
}

static void mixar_x11_shape_apply(
    void *window_handle, Display *display, Window window, float radius, int width, int height)
{
  if (radius <= 0.0f || width <= 0 || height <= 0) {
    XShapeCombineMask(display, window, ShapeBounding, 0, 0, None, ShapeSet);
    XFlush(display);
    return;
  }
  const int r = std::min({mixar_x11_to_phys(window_handle, int(radius + 0.5f)),
                          width / 2,
                          height / 2});
  Pixmap mask = XCreatePixmap(display, window, unsigned(width), unsigned(height), 1);
  GC gc = XCreateGC(display, mask, 0, nullptr);
  XSetForeground(display, gc, 0);
  XFillRectangle(display, mask, gc, 0, 0, unsigned(width), unsigned(height));
  XSetForeground(display, gc, 1);
  if (r <= 0) {
    XFillRectangle(display, mask, gc, 0, 0, unsigned(width), unsigned(height));
  }
  else {
    const unsigned d = unsigned(2 * r);
    XFillRectangle(display, mask, gc, r, 0, unsigned(width - 2 * r), unsigned(height));
    XFillRectangle(display, mask, gc, 0, r, unsigned(width), unsigned(height - 2 * r));
    XFillArc(display, mask, gc, 0, 0, d, d, 0, 360 * 64);
    XFillArc(display, mask, gc, width - int(d), 0, d, d, 0, 360 * 64);
    XFillArc(display, mask, gc, 0, height - int(d), d, d, 0, 360 * 64);
    XFillArc(display, mask, gc, width - int(d), height - int(d), d, d, 0, 360 * 64);
  }
  XShapeCombineMask(display, window, ShapeBounding, 0, 0, mask, ShapeSet);
  XFreeGC(display, gc);
  XFreePixmap(display, mask);
  XFlush(display);
}

static MixarX11Shape *mixar_x11_shape_find(Window window)
{
  for (MixarX11Shape &shape : s_x11_shapes) {
    if (shape.window == window) {
      return &shape;
    }
  }
  return nullptr;
}

void mixar_x11_shape_on_resize(void *window_handle, int phys_width, int phys_height)
{
  Display *display;
  Window window;
  if (!mixar_x11_resolve_chrome(window_handle, &display, &window) ||
      !mixar_x11_shape_supported(display))
  {
    return;
  }
  if (const MixarX11Shape *shape = mixar_x11_shape_find(window)) {
    mixar_x11_shape_apply(window_handle, display, window, shape->radius, phys_width, phys_height);
  }
}

extern "C" void Mixar_WindowSetCornerRadius(void *window_handle, float radius)
{
  Display *display;
  Window window;
  if (!mixar_x11_resolve_chrome(window_handle, &display, &window) ||
      !mixar_x11_shape_supported(display))
  {
    return;
  }
  if (MixarX11Shape *shape = mixar_x11_shape_find(window)) {
    shape->radius = radius;
  }
  else {
    s_x11_shapes.push_back({window, radius});
  }
  /* Callers usually resize first (Mixar_WindowForceSize), and the window
   * manager applies that asynchronously; use the size we last asked for. */
  int width = 0, height = 0;
  if (!mixar_x11_requested_size(window, &width, &height)) {
    int x, y;
    if (!mixar_x11_frame(display, window, &x, &y, &width, &height)) {
      return;
    }
  }
  mixar_x11_shape_apply(window_handle, display, window, radius, width, height);
}

#  else /* !WITH_MIXAR_X11_SHAPE */

/* Built without libXext's Shape extension: corners stay square. */
void mixar_x11_shape_on_resize(void * /*window_handle*/, int /*phys_width*/, int /*phys_height*/)
{
}

extern "C" void Mixar_WindowSetCornerRadius(void * /*window_handle*/, float /*radius*/) {}

#  endif /* WITH_MIXAR_X11_SHAPE */

#endif /* WITH_GHOST_X11 */
