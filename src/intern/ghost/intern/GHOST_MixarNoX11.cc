/* SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/** \file
 * \ingroup GHOST
 *
 * Inert Mixar_Window* helpers for a Linux build WITHOUT the X11 GHOST backend
 * (-DWITH_GHOST_X11=OFF, Wayland-only). The Agent Bubble references these under
 * __linux__ regardless of the backend, so they must link. Every helper reports
 * "unsupported" (false / 0) or does nothing; the run-time backend check in
 * space_agent_bubble.cc keeps the window controls hidden so none is reached in
 * practice. The set is pinned equal to the X11 backend's by
 * tests/test_ghost_no_x11_stub_parity.py.
 */

#if defined(__linux__) && !defined(WITH_GHOST_X11)

extern "C" void Mixar_WindowSetChromeless(void *, bool)
{
}

extern "C" void Mixar_WindowSetBorderless(void *)
{
}

extern "C" void Mixar_WindowSetFloatingLevel(void *)
{
}

extern "C" void Mixar_WindowMarkAsFloatingDock(void *)
{
}

extern "C" void Mixar_WindowSetDockWindowType(void *, bool)
{
}

extern "C" void Mixar_FloatingDocksSuppressForModal()
{
}

extern "C" void Mixar_FloatingDocksRestoreAfterModal()
{
}

extern "C" void Mixar_WindowSetHidesOnDeactivate(void *, bool)
{
}

extern "C" void Mixar_WindowBindToParentSpace(void *)
{
}

extern "C" void Mixar_WindowSetBlurBehind(void *, bool)
{
}

extern "C" bool Mixar_WindowHasAlphaChannel(void *)
{
  return false;
}

extern "C" void Mixar_WindowSetPerPixelAlpha(void *, bool)
{
}

extern "C" void Mixar_WindowOrderFront(void *)
{
}

extern "C" void Mixar_WindowOrderFrontNoActivate(void *)
{
}

extern "C" void Mixar_WindowOrderOut(void *)
{
}

extern "C" void Mixar_WindowMakeKey(void *)
{
}

extern "C" void Mixar_WindowPositionAboveParent(void *, void *, int, int)
{
}

extern "C" void Mixar_WindowSnapToCentreBottomOfWindow(void *, void *, int)
{
}

extern "C" void Mixar_WindowSnapToCentreBottom(void *, int)
{
}

extern "C" void Mixar_WindowAnimateFrameToCentreBottomOfWindow(void *, void *, int, int, int, float)
{
}

extern "C" void Mixar_WindowFloatIn(void *, int, float)
{
}

extern "C" void Mixar_WindowFloatOut(void *, int, float)
{
}

extern "C" bool Mixar_WindowContainsScreenCursor(void *, int)
{
  return false;
}

extern "C" void Mixar_WindowBeginDrag(void *)
{
}

extern "C" void Mixar_WindowUpdateDrag(void *)
{
}

extern "C" void Mixar_WindowEndDrag(void *)
{
}

extern "C" void Mixar_WindowSetParent(void *, void *)
{
}

extern "C" void Mixar_WindowSetParentPlain(void *, void *)
{
}

extern "C" void Mixar_WindowSetParentTracked(void *, void *)
{
}

extern "C" void Mixar_WindowDetachFromParent(void *, void *)
{
}

extern "C" void Mixar_WindowForgetTracking(const void *)
{
}

extern "C" bool Mixar_WindowHasChildWindow(void *)
{
  return false;
}

extern "C" void Mixar_WindowAnchorAtParentCentreBottom(void *, void *, int)
{
}

extern "C" void Mixar_WindowAnchorAtParentOffset(void *, void *, int, int)
{
}

extern "C" bool Mixar_WindowGetParentOffset(void *, void *, int *, int *)
{
  return false;
}

extern "C" void Mixar_WindowPlaceInParent(void *, void *, int, int)
{
}

extern "C" void Mixar_WindowSetCornerRadius(void *, float)
{
}

extern "C" void Mixar_WindowForceSize(void *, int, int)
{
}

extern "C" void Mixar_WindowSetMinContentSize(void *, int, int)
{
}

extern "C" void Mixar_WindowSetMaxContentSize(void *, int, int)
{
}

extern "C" void Mixar_WindowGetContentPixelSize(void *, int *, int *)
{
}

extern "C" bool Mixar_WindowGetContentSize(void *, int *, int *)
{
  return false;
}

extern "C" int Mixar_WindowGetMaxHeightToScreenTop(void *, int)
{
  return 0;
}

extern "C" bool Mixar_WindowIsVisible(void *)
{
  return false;
}

extern "C" void Mixar_WindowSetAlpha(void *, float)
{
}

extern "C" void Mixar_WindowAnimateAlphaTo(void *, float, float)
{
}

extern "C" void Mixar_DispatchMainAfter(float /*delay_seconds*/,
                                        void (*callback)(void *),
                                        void *user_data)
{
  if (callback) {
    callback(user_data);
  }
}

#endif
