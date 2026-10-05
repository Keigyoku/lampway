/* SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup GHOST
 *
 * X11 Mixar_Window* size, visibility and opacity.
 */

#ifdef WITH_GHOST_X11

#  include <X11/Xatom.h>
#  include <X11/Xlib.h>
#  include <X11/Xutil.h>

#  include <algorithm>
#  include <vector>

#  include "GHOST_MixarX11.hh"

/* Last size Mixar_WindowForceSize asked for, per window. The window manager
 * applies resizes asynchronously, so code that runs right after a resize must
 * not trust the measured geometry. */
struct MixarX11Size {
  Window window;
  int width, height;
};
static std::vector<MixarX11Size> s_x11_requested_sizes;

void mixar_x11_requested_size_set(Window window, int width, int height)
{
  for (MixarX11Size &size : s_x11_requested_sizes) {
    if (size.window == window) {
      size.width = width;
      size.height = height;
      return;
    }
  }
  s_x11_requested_sizes.push_back({window, width, height});
}

bool mixar_x11_requested_size(Window window, int *r_width, int *r_height)
{
  for (const MixarX11Size &size : s_x11_requested_sizes) {
    if (size.window == window) {
      *r_width = size.width;
      *r_height = size.height;
      return true;
    }
  }
  return false;
}

/* Windows currently unmapped by Mixar_WindowSetAlpha(0) - see there. */
static std::vector<Window> s_x11_alpha_hidden;

bool mixar_x11_alpha_hidden_set(Window window, bool hidden)
{
  auto it = std::find(s_x11_alpha_hidden.begin(), s_x11_alpha_hidden.end(), window);
  const bool was_hidden = (it != s_x11_alpha_hidden.end());
  if (hidden && !was_hidden) {
    s_x11_alpha_hidden.push_back(window);
  }
  else if (!hidden && was_hidden) {
    s_x11_alpha_hidden.erase(it);
  }
  return was_hidden;
}

extern "C" void Mixar_WindowForceSize(void *window_handle, int width, int height)
{
  Display *display;
  Window window;
  if (!mixar_x11_resolve_chrome(window_handle, &display, &window) || width <= 0 || height <= 0) {
    return;
  }
  const int phys_w = std::max(1, mixar_x11_to_phys(window_handle, width));
  const int phys_h = std::max(1, mixar_x11_to_phys(window_handle, height));
  /* Resize only. XMoveResizeWindow on a live GL window under this NVIDIA +
   * Xvfb stack destroys the context; the next present segfaults. Anchor
   * updates stay on the tracking timer / Snap* helpers, matching the
   * X11 backend that already ran here. */
  XResizeWindow(display, window, unsigned(phys_w), unsigned(phys_h));
  XFlush(display);
  mixar_x11_requested_size_set(window, phys_w, phys_h);
  mixar_x11_shape_on_resize(window_handle, phys_w, phys_h);
}

static void mixar_x11_set_size_hint(void *window_handle, bool is_min, int width, int height)
{
  Display *display;
  Window window;
  if (!mixar_x11_resolve_chrome(window_handle, &display, &window)) {
    return;
  }
  const int phys_w = mixar_x11_to_phys(window_handle, width);
  const int phys_h = mixar_x11_to_phys(window_handle, height);
  XSizeHints hints = {};
  long supplied = 0;
  if (!XGetWMNormalHints(display, window, &hints, &supplied)) {
    hints.flags = 0;
  }
  if (is_min) {
    hints.flags |= PMinSize;
    hints.min_width = phys_w;
    hints.min_height = phys_h;
  }
  else {
    hints.flags |= PMaxSize;
    hints.max_width = (width > 0) ? phys_w : 32767;
    hints.max_height = (height > 0) ? phys_h : 32767;
  }
  XSetWMNormalHints(display, window, &hints);
  XFlush(display);
}

extern "C" void Mixar_WindowSetMinContentSize(void *window_handle, int width, int height)
{
  mixar_x11_set_size_hint(window_handle, true, width, height);
}

extern "C" void Mixar_WindowSetMaxContentSize(void *window_handle, int width, int height)
{
  mixar_x11_set_size_hint(window_handle, false, width, height);
}

extern "C" void Mixar_WindowGetContentPixelSize(void *window_handle, int *r_width, int *r_height)
{
  if (r_width) {
    *r_width = 0;
  }
  if (r_height) {
    *r_height = 0;
  }
  Display *display;
  Window window;
  if (!mixar_x11_resolve_any(window_handle, &display, &window)) {
    return;
  }
  int x, y, width, height;
  if (!mixar_x11_frame(display, window, &x, &y, &width, &height)) {
    return;
  }
  if (r_width) {
    *r_width = width;
  }
  if (r_height) {
    *r_height = height;
  }
}

extern "C" bool Mixar_WindowGetContentSize(void *window_handle, int *r_width, int *r_height)
{
  if (r_width == nullptr || r_height == nullptr) {
    return false;
  }
  int pixel_w = 0, pixel_h = 0;
  Mixar_WindowGetContentPixelSize(window_handle, &pixel_w, &pixel_h);
  if (pixel_w <= 0 || pixel_h <= 0) {
    return false;
  }
  *r_width = mixar_x11_to_logical(window_handle, pixel_w);
  *r_height = mixar_x11_to_logical(window_handle, pixel_h);
  return true;
}

extern "C" int Mixar_WindowGetMaxHeightToScreenTop(void *window_handle, int reserve_top)
{
  Display *display;
  Window window;
  if (!mixar_x11_resolve_any(window_handle, &display, &window)) {
    return 0;
  }
  int x, y, width, height;
  if (!mixar_x11_frame(display, window, &x, &y, &width, &height)) {
    return 0;
  }
  const int phys = std::max(0, (y + height) - mixar_x11_to_phys(window_handle, reserve_top));
  return mixar_x11_to_logical(window_handle, phys);
}

extern "C" bool Mixar_WindowIsVisible(void *window_handle)
{
  if (window_handle == nullptr) {
    return false;
  }
  /* Wayland (or any non-X11 GHOST backend): never skip wm_draw. False
   * here drops SwapBuffers for every window and the NVIDIA driver then
   * presents into a stale context. */
  if (mixar_x11_system() == nullptr) {
    return true;
  }
  Display *display;
  Window window;
  if (!mixar_x11_resolve_any(window_handle, &display, &window)) {
    return true;
  }
  XWindowAttributes attr;
  if (!XGetWindowAttributes(display, window, &attr)) {
    return true;
  }
  return attr.map_state == IsViewable;
}

extern "C" void Mixar_WindowSetAlpha(void *window_handle, float alpha)
{
  Display *display;
  Window window;
  if (!mixar_x11_resolve_chrome(window_handle, &display, &window)) {
    return;
  }
  const float clamped = std::min(1.0f, std::max(0.0f, alpha));

  /* Callers use alpha 0 to HIDE a window — that is how the pill is put away
   * while the island is expanded (space_agent_bubble.cc). _NET_WM_WINDOW_OPACITY
   * only does that under a compositing manager, and there is none under Xvfb +
   * openbox, so an opacity-only implementation left the pill fully visible on
   * top of the chat. Map state is what X11 always honours, so drive that and
   * set the opacity too for the compositors that do read it.
   *
   * Map/unmap is the pair minimise/restore already uses. Mixar_WindowIsVisible
   * reports map state, so a hidden window correctly stops being drawn.
   *
   * Alpha must not override an explicit hide, though: on Cocoa and Win32 alpha
   * and visibility are independent, and minimise relies on that - it orders
   * the island out, then resets its alpha to 1 for next time. So only a window
   * that THIS function hid is mapped again when its alpha comes back. */
  if (clamped <= 0.0f) {
    if (mixar_x11_is_viewable(display, window)) {
      XUnmapWindow(display, window);
      XFlush(display);
      mixar_x11_alpha_hidden_set(window, true);
    }
    return;
  }
  if (mixar_x11_alpha_hidden_set(window, false)) {
    XMapWindow(display, window);
    XRaiseWindow(display, window);
  }

  Atom opacity = XInternAtom(display, "_NET_WM_WINDOW_OPACITY", False);
  if (opacity == None) {
    XFlush(display);
    return;
  }
  if (clamped >= 1.0f) {
    XDeleteProperty(display, window, opacity);
  }
  else {
    const unsigned long value = (unsigned long)(clamped * 0xffffffffu);
    XChangeProperty(display,
                    window,
                    opacity,
                    XA_CARDINAL,
                    32,
                    PropModeReplace,
                    reinterpret_cast<const unsigned char *>(&value),
                    1);
  }
  XFlush(display);
}

extern "C" void Mixar_WindowAnimateAlphaTo(void *window_handle,
                                           float target_alpha,
                                           float /*duration*/)
{
  Mixar_WindowSetAlpha(window_handle, target_alpha);
}

#endif /* WITH_GHOST_X11 */
