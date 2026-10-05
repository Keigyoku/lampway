# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The live bridge, ported from the shelf's live/bridge.py (the one the main session drives the captain's
Blender through).

Two doors, both polled from the app's own timer so every command runs on the main thread, in a window context:

* a loopback socket the Blender MCP connects to. Request: ``{"type": "execute", "code": ..., "strict_json": bool}``
  + NUL. Reply: ``{"status": "ok"|"error", "result" | "message", "stdout", "stderr"}`` + NUL. A bare connect
  (a port probe) carries no request and is ignored.
* an inbox directory of numbered ``.py`` files: each runs once, is consumed, and leaves ``<name>.json`` in the
  outbox (and a screenshot of the window in the frames directory when there is a window).

The port: ``LAMPWAY_BRIDGE_PORT``, else the MCP's own ``BLENDER_MCP_PORT``, else 9876. ``0`` disables the
bridge. A port already in use is reported (``Bridge.error``), never raised, and never taken over: a second
Lampway (or a stock Blender on the same port) keeps its listener and this one runs without a bridge.
"""

import contextlib
import io
import json
import os
import socket
import traceback
from pathlib import Path
from typing import Callable, Optional

import bpy

DEFAULT_PORT = 9876


def port_from_env(environ=None) -> int:
    env = os.environ if environ is None else environ
    for name in ("LAMPWAY_BRIDGE_PORT", "BLENDER_MCP_PORT"):
        raw = env.get(name)
        if raw is None or raw.strip() == "":
            continue
        try:
            return int(raw)
        except ValueError:
            return DEFAULT_PORT                              # a malformed explicit setting is not read as another one
    return DEFAULT_PORT


def explicitly_configured(environ=None) -> bool:
    env = os.environ if environ is None else environ
    return any((env.get(n) or "").strip() for n in ("LAMPWAY_BRIDGE_PORT", "BLENDER_MCP_PORT"))


def exec_code(code: str, g: dict) -> None:
    """Run ``code`` in namespace ``g`` (no window context: the plain runner, used by tests and headless)."""
    exec(compile(code, "<mcp>", "exec"), g)


def _window():
    wm = getattr(bpy.context, "window_manager", None)
    windows = list(getattr(wm, "windows", []) or [])
    return windows[0] if windows else None


def window_exec(code: str, g: dict) -> None:
    """Run ``code`` inside the first window's context: a timer has no window of its own."""
    win = _window()
    if win is None:
        return exec_code(code, g)
    with bpy.context.temp_override(window=win, screen=win.screen):
        exec_code(code, g)


class Bridge:
    def __init__(self, port: int, run_code: Callable[[str, dict], None] = window_exec,
                 inbox: Optional[Path] = None, outbox: Optional[Path] = None, frames: Optional[Path] = None):
        self.port = port
        self.run_code = run_code
        self.inbox = Path(inbox) if inbox else None
        self.outbox = Path(outbox) if outbox else None
        self.frames = Path(frames) if frames else None
        self.error = ""
        self.handled = 0
        self._srv: Optional[socket.socket] = None
        self._frame = 0

    # -- lifecycle
    @property
    def enabled(self) -> bool:
        return self._srv is not None

    @property
    def address(self):
        return self._srv.getsockname() if self._srv else None

    def start(self) -> bool:
        if self.port == 0:
            self.error = "disabled (port 0)"
            return False
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("127.0.0.1", self.port))
        except OSError as exc:
            srv.close()
            self.error = f"port {self.port} in use or not bindable: {exc}"
            return False
        srv.listen(4)
        srv.setblocking(False)
        self._srv = srv
        self.error = ""
        return True

    def stop(self) -> None:
        if self._srv is not None:
            self._srv.close()
            self._srv = None

    # -- the socket door
    def pump(self) -> int:
        """Serve every pending connection; returns the cumulative number handled."""
        while self._srv is not None:
            try:
                conn, _ = self._srv.accept()
            except BlockingIOError:
                break
            with conn:
                try:
                    self._serve_one(conn)
                except Exception:
                    traceback.print_exc()
                self.handled += 1
        return self.handled

    def _serve_one(self, conn: socket.socket) -> None:
        conn.settimeout(10.0)
        buf = bytearray()
        while b"\0" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
        raw = bytes(buf).partition(b"\0")[0]
        if not raw.strip():                                  # a bare connect (a port probe) carries no request
            return
        req = json.loads(raw.decode("utf-8"))
        out, err = io.StringIO(), io.StringIO()
        reply = {"status": "ok"}
        g = {"bpy": bpy, "__name__": "__mcp__"}
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.run_code(req.get("code", ""), g)
            reply["result"] = g.get("result")
        except Exception:
            reply = {"status": "error", "message": traceback.format_exc()}
        reply["stdout"], reply["stderr"] = out.getvalue(), err.getvalue()
        try:
            data = json.dumps(reply, default=None if req.get("strict_json") else repr)
        except TypeError as exc:
            data = json.dumps({"status": "error", "message": f"result is not JSON-serialisable: {exc}",
                               "stdout": reply["stdout"], "stderr": reply["stderr"]})
        conn.sendall(data.encode("utf-8") + b"\0")
        self._after_command("mcp")

    # -- the file door
    def poll_inbox(self) -> int:
        if self.inbox is None or not self.inbox.is_dir():
            return 0
        done = 0
        for f in sorted(self.inbox.glob("*.py")):
            name = f.stem
            out = {"cmd": name}
            try:
                code = f.read_text(encoding="utf-8")
                f.unlink()
                g = {"bpy": bpy, "__name__": "__bridge__", "shot": self.shot, "view3d": view3d}
                self.run_code(code, g)
                out["ok"] = True
                frame = self.shot(name)
                if frame:
                    out["frame"] = frame
            except Exception:
                out["ok"] = False
                out["error"] = traceback.format_exc()
            if self.outbox is not None:
                self.outbox.mkdir(parents=True, exist_ok=True)
                (self.outbox / f"{name}.json").write_text(json.dumps(out), encoding="utf-8")
            done += 1
        return done

    def shot(self, tag: str) -> Optional[str]:
        """A screenshot of the window into the frames directory; None without a frames directory or a window."""
        win = _window()
        if self.frames is None or win is None:
            return None
        self.frames.mkdir(parents=True, exist_ok=True)
        path = str(self.frames / f"{self._frame:05d}_{tag}.png")
        self._frame += 1
        with bpy.context.temp_override(window=win, area=win.screen.areas[0]):
            bpy.ops.screen.screenshot(filepath=path)
        return path

    def _after_command(self, tag: str) -> None:
        try:
            win = _window()
            if win is not None:
                with bpy.context.temp_override(window=win, screen=win.screen):
                    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                self.shot(tag)
        except Exception:
            pass


def view3d() -> dict:
    """A context override for the 3D viewport: ``with bpy.context.temp_override(**view3d()): ...``"""
    win = _window()
    area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    return {"window": win, "screen": win.screen, "area": area,
            "region": next(r for r in area.regions if r.type == "WINDOW")}
