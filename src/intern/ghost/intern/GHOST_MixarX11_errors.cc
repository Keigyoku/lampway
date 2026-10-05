/* SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup GHOST
 *
 * Xlib error guard for the X11 Mixar_Window* helpers.
 */

#ifdef WITH_GHOST_X11

#  include <X11/Xlib.h>
#  include <X11/Xproto.h>

#  include "GHOST_MixarX11.hh"

/* Upstream leaves Xlib's default error handler installed (GHOST_SystemX11.cc
 * keeps USE_X11_ERROR_HANDLERS off), and that handler exits the process on any
 * error. These helpers act on windows the window manager may be mapping,
 * unmapping or destroying at the same moment - XSetInputFocus on a window that
 * is not viewable yet is a BadMatch, a geometry query on a just-closed window a
 * BadWindow. Ignore exactly those window-lifetime errors on core window
 * requests and hand everything else to the previous handler, so genuine
 * failures (GLX, extensions, resource exhaustion) stay fatal as upstream. */
static XErrorHandler s_x11_prev_error_handler = nullptr;

static bool mixar_x11_is_window_race(const XErrorEvent *event)
{
  switch (event->error_code) {
    case BadWindow:
    case BadMatch:
    case BadDrawable:
      break;
    default:
      return false;
  }
  switch (event->request_code) {
    case X_GetWindowAttributes:
    case X_MapWindow:
    case X_UnmapWindow:
    case X_ConfigureWindow:
    case X_GetGeometry:
    case X_QueryTree:
    case X_ChangeProperty:
    case X_DeleteProperty:
    case X_GetProperty:
    case X_SendEvent:
    case X_QueryPointer:
    case X_TranslateCoords:
    case X_SetInputFocus:
      return true;
    default:
      return false;
  }
}

static int mixar_x11_error_handler(Display *display, XErrorEvent *event)
{
  if (mixar_x11_is_window_race(event)) {
    return 0;
  }
  return s_x11_prev_error_handler ? s_x11_prev_error_handler(display, event) : 0;
}

void mixar_x11_install_error_guard()
{
  static bool installed = false;
  if (installed) {
    return;
  }
  installed = true;
  s_x11_prev_error_handler = XSetErrorHandler(mixar_x11_error_handler);
}

#endif /* WITH_GHOST_X11 */
