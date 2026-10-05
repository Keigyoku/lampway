/* SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup GHOST
 *
 * Shared internals for the X11 Mixar_Window* backend. The public helpers
 * live in GHOST_MixarX11.cc / _parent.cc / _move.cc so each file stays
 * under the overlay's 500-line limit.
 */

#pragma once

#ifdef WITH_GHOST_X11

#  include <cstdlib>

#  include <X11/Xlib.h>

#  include "GHOST_ISystem.hh"
#  include "GHOST_IWindow.hh"
#  include "GHOST_SystemX11.hh"
#  include "GHOST_WindowX11.hh"

enum MixarX11TrackMode {
  MIXAR_X11_TRACK_ABOVE_TOP_LEFT,
  MIXAR_X11_TRACK_CENTRE_BOTTOM,
  MIXAR_X11_TRACK_FOLLOW_MOVE,
  MIXAR_X11_TRACK_RELATIVE_OFFSET,
};

/* Gap between the pill's bottom and the bubble's top — mirrors
 * AGENT_BUBBLE_PILL_GAP in space_agent_bubble.cc (Win32 hardcodes 6). */
static constexpr int MIXAR_X11_PILL_GAP = 6;

/* Light mutations: chat-island move (``_NET_WM_MOVERESIZE`` ClientMessage)
 * and minimise/restore (map / unmap). These are what Linux users need. */
static constexpr bool MIXAR_X11_ALLOW_MOVE_MINIMISE = true;

/* Chrome writes: _MOTIF_WM_HINTS decorations, XResizeWindow, and the
 * WM size hints that make the WM honour that size. The pill window needs
 * both — without them it keeps the WM title bar and never shrinks out of
 * the chat island's way, which is what a Linux user actually sees.
 *
 * Separated from the heavy gate below deliberately. What segfaulted after
 * READY on NVIDIA L4 + Xvfb were the reparenting paths (WM_TRANSIENT_FOR)
 * and XMoveResizeWindow, which moves a live GL drawable; a property write
 * and a pure XResizeWindow are neither. MIXAR_X11_CHROME=0 in the
 * environment turns these back off without a rebuild, so a stack that does
 * regress can be bisected in place rather than recompiled. */
inline bool mixar_x11_chrome_enabled()
{
  static const bool enabled = []() {
    const char *env = getenv("LAMPWAY_X11_CHROME") ? getenv("LAMPWAY_X11_CHROME") : getenv("MIXAR_X11_CHROME");
    return (env == nullptr) || (env[0] != '0');
  }();
  return enabled;
}

/* Heavy mutations: transient-for parenting, the host-tracking timer, stacking
 * (_NET_WM_STATE_ABOVE) and anchoring moves. These segfaulted Mixar after READY
 * on an NVIDIA L4 + Xvfb + openbox sandbox, so that branch shipped them
 * compiled off - which leaves the pill wherever the window manager first put
 * it and the island unanchored. On a real desktop (KWin) they are what the
 * placement needs, so they default ON; MIXAR_X11_HEAVY=0 in the environment
 * turns them off without a rebuild if a stack regresses. Wayland no-ops via
 * ``dynamic_cast`` below. */
inline bool mixar_x11_heavy_enabled()
{
  static const bool enabled = []() {
    const char *env = getenv("LAMPWAY_X11_HEAVY") ? getenv("LAMPWAY_X11_HEAVY") : getenv("MIXAR_X11_HEAVY");
    return (env == nullptr) || (env[0] != '0');
  }();
  return enabled;
}

inline GHOST_SystemX11 *mixar_x11_system()
{
  /* dynamic_cast, not static_cast: a Wayland session returns
   * GHOST_SystemWayland and every helper here must no-op. */
  return dynamic_cast<GHOST_SystemX11 *>(GHOST_ISystem::getSystem());
}

inline GHOST_WindowX11 *mixar_x11_window(void *window_handle)
{
  if (window_handle == nullptr) {
    return nullptr;
  }
  /* Same resolve as the X11 backend that already ran on this sandbox:
   * dynamic_cast only. validWindow() is not required for a live handle,
   * and a failed lookup used to make Mixar_WindowIsVisible report every
   * window as hidden, which skipped SwapBuffers and crashed NVIDIA. */
  return dynamic_cast<GHOST_WindowX11 *>(static_cast<GHOST_IWindow *>(window_handle));
}

/* Installs (once) an Xlib error handler that survives window-lifetime races.
 * Defined in GHOST_MixarX11.cc. */
void mixar_x11_install_error_guard();

inline bool mixar_x11_resolve_any(void *window_handle, Display **r_display, Window *r_window)
{
  GHOST_SystemX11 *system = mixar_x11_system();
  GHOST_WindowX11 *window = mixar_x11_window(window_handle);
  if (system == nullptr || window == nullptr) {
    return false;
  }
  Display *display = system->getXDisplay();
  Window xwindow = window->getXWindow();
  if (display == nullptr || xwindow == None) {
    return false;
  }
  mixar_x11_install_error_guard();
  *r_display = display;
  *r_window = xwindow;
  return true;
}

inline bool mixar_x11_resolve(void *window_handle, Display **r_display, Window *r_window)
{
  if (!mixar_x11_heavy_enabled()) {
    return false;
  }
  return mixar_x11_resolve_any(window_handle, r_display, r_window);
}

inline bool mixar_x11_resolve_chrome(void *window_handle, Display **r_display, Window *r_window)
{
  if (!mixar_x11_chrome_enabled()) {
    return false;
  }
  return mixar_x11_resolve_any(window_handle, r_display, r_window);
}

inline bool mixar_x11_resolve_move_minimise(void *window_handle,
                                            Display **r_display,
                                            Window *r_window)
{
  if (!MIXAR_X11_ALLOW_MOVE_MINIMISE) {
    return false;
  }
  return mixar_x11_resolve_any(window_handle, r_display, r_window);
}

/* Root-relative geometry. XGetGeometry is parent-relative; reparenting
 * WMs make that the frame, not the screen. */
inline bool mixar_x11_frame(
    Display *display, Window window, int *r_x, int *r_y, int *r_width, int *r_height)
{
  Window root;
  int x, y;
  unsigned int width, height, border, depth;
  if (!XGetGeometry(display, window, &root, &x, &y, &width, &height, &border, &depth)) {
    return false;
  }
  Window child;
  int root_x = x, root_y = y;
  XTranslateCoordinates(display, window, root, 0, 0, &root_x, &root_y, &child);
  *r_x = root_x;
  *r_y = root_y;
  *r_width = int(width);
  *r_height = int(height);
  return true;
}

inline float mixar_x11_dpi_scale(void *window_handle)
{
  GHOST_WindowX11 *window = mixar_x11_window(window_handle);
  if (window == nullptr) {
    return 1.0f;
  }
  const uint16_t dpi = window->getDPIHint();
  return (dpi > 0) ? (float(dpi) / 96.0f) : 1.0f;
}

inline int mixar_x11_to_phys(void *window_handle, int logical)
{
  return int(float(logical) * mixar_x11_dpi_scale(window_handle));
}

inline int mixar_x11_to_logical(void *window_handle, int phys)
{
  const float scale = mixar_x11_dpi_scale(window_handle);
  if (scale <= 0.0f) {
    return phys;
  }
  return int(float(phys) / scale);
}

inline bool mixar_x11_is_viewable(Display *display, Window window)
{
  XWindowAttributes attr;
  if (!XGetWindowAttributes(display, window, &attr)) {
    return false;
  }
  return attr.map_state == IsViewable;
}

void mixar_x11_centre_bottom_of(void *child_handle, void *parent_handle, int margin_bottom);
void mixar_x11_track_add(void *child_handle,
                         void *parent_handle,
                         int mode,
                         int offset_x,
                         int offset_y,
                         int margin_bottom);
bool mixar_x11_track_remove(void *child_handle);

/* Size most recently requested by Mixar_WindowForceSize (physical pixels). */
void mixar_x11_requested_size_set(Window window, int width, int height);
bool mixar_x11_requested_size(Window window, int *r_width, int *r_height);

/* Re-applies a window's corner-radius shape after a resize
 * (GHOST_MixarX11_shape.cc). */
void mixar_x11_shape_on_resize(void *window_handle, int phys_width, int phys_height);

/* Marks `window` as hidden (or not) by Mixar_WindowSetAlpha; returns whether
 * it was marked before. Explicit show/hide calls clear the mark. */
bool mixar_x11_alpha_hidden_set(Window window, bool hidden);

void mixar_x11_dock_register(void *window_handle, Window window);
void mixar_x11_dock_forget(const void *window_handle);
bool mixar_x11_dock_suppress_if_needed(void *window_handle);

#endif /* WITH_GHOST_X11 */
