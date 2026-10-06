#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Facelift contract 16's live checks (tests 6, 7, 9 and 11), run INSIDE the build box on a virtual display, all in one
isolated scratch directory: Lampway's own herdr server (its sockets under the scratch Lampway home), Lampway's own WezTerm
(its class, its socket, every directory it uses under the home). The caller gives the process a scratch HOME and scratch XDG
dirs too, so nothing here reads or writes the person's HOME, XDG dirs or runtime dir; the fleet's herdr is only OBSERVED,
through /proc (its server processes and their start times), never connected to.

    xvfb-run -a python3 scripts/lampway/live_terminal_check.py <server dir> <lampway home> <project dir> <out.json>

The WezTerm binary is the one the add-on installed under <lampway home> (W.get, through the github route).
Writes {checks: {name: {ok, ...facts}}, started: [pids]}; every process it starts is stopped by its own pid at the end."""

import base64
import ctypes
import json
import os
import signal
import struct
import subprocess
import sys
import time
import types
import zlib
from pathlib import Path

SERVER, HOME, PROJECT, OUT = sys.argv[1:5]
for k in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "XDG_CACHE_HOME"):
    if not os.environ.get(k, "").startswith(str(Path(HOME).parent)):
        sys.exit(f"refused: {k} must be a scratch directory beside the Lampway home, not {os.environ.get(k)!r}")
sys.path.insert(0, SERVER)
try:
    import httpx  # noqa: F401
except ImportError:                                   # the box's python has no httpx; nothing here downloads
    stub = types.ModuleType("httpx")
    stub.Client = stub.AsyncClient = type("C", (), {"send": None})
    stub.Request = object
    sys.modules["httpx"] = stub
from lampway_server.addons import wezterm as W  # noqa: E402
from lampway_server.herdr import launcher as L  # noqa: E402
from lampway_server.herdr.host import Cockpit  # noqa: E402

HERDR_ROOT = Path(HOME) / "herdr"
STARTED = []
checks = {}


def alive(pid) -> bool:
    """Running, and not a zombie (a child this run started and has not reaped is dead, not alive)."""
    try:
        os.kill(int(pid), 0)
        return Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, ValueError, TypeError, IndexError):
        return False


def proc_start(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def herdr_servers():
    """Every herdr server process that is not this run's: pid -> [argv, start time], from /proc cmdline and stat only (the box
    cannot read another process's environ, and nothing here connects to a server). This run's own server is excluded by pid."""
    out = {}
    for p in Path("/proc").iterdir():
        if not p.name.isdigit() or int(p.name) in STARTED:
            continue
        try:
            cmd = (p / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if cmd and cmd[0].endswith(b"herdr") and b"server" in cmd:
            out[p.name] = [b" ".join(c for c in cmd if c).decode(errors="replace"), proc_start(p.name)]
    return out


def pane_pids(cock, rec):
    info = json.loads(L.run(cock.root, ["pane", "process-info", "--pane", rec["pane_id"]]))["result"]["process_info"]
    return sorted(int(p["pid"]) for p in info.get("foreground_processes", []) if p.get("pid"))


def solid_png(path: Path, rgb=(255, 0, 255), size=64) -> None:
    row = b"\0" + bytes(rgb) * size
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)  # noqa: E731
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(row * size)) + chunk(b"IEND", b""))


def magenta_box(save=None):
    """The bounding box of the pure-magenta pixels on the root window, or None."""
    x = ctypes.CDLL("libX11.so.6")
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XDefaultRootWindow.restype = ctypes.c_ulong
    x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x.XGetImage.restype = ctypes.c_void_p
    x.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    x.XDisplayWidth.argtypes = x.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
    d = x.XOpenDisplay(None)
    w, h = x.XDisplayWidth(d, 0), x.XDisplayHeight(d, 0)
    img = x.XGetImage(d, x.XDefaultRootWindow(d), 0, 0, w, h, 0xFFFFFFFF, 2)
    data = ctypes.c_void_p.from_address(img + 16).value
    bpl = ctypes.c_int.from_address(img + 44).value
    raw = memoryview(ctypes.string_at(data, bpl * h)).cast("I")
    xs, ys = [], []
    for y in range(h):
        row = raw[y * (bpl // 4):y * (bpl // 4) + w]
        hits = [i for i, v in enumerate(row) if v & 0xFFFFFF == 0xFF00FF]
        if hits:
            xs += [hits[0], hits[-1]]
            ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def magenta_on_screen(save=None) -> int:
    """Count the root window's pure-magenta pixels (XGetImage through Xlib; the box has no screenshot tool); `save` writes the
    screen as a PNG for the report."""
    x = ctypes.CDLL("libX11.so.6")
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XDefaultRootWindow.restype = ctypes.c_ulong
    x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x.XGetImage.restype = ctypes.c_void_p
    x.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    x.XDisplayWidth.argtypes = x.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
    d = x.XOpenDisplay(None)
    if not d:
        return -1
    w, h = x.XDisplayWidth(d, 0), x.XDisplayHeight(d, 0)
    img = x.XGetImage(d, x.XDefaultRootWindow(d), 0, 0, w, h, 0xFFFFFFFF, 2)
    if not img:
        return -2
    data = ctypes.c_void_p.from_address(img + 16).value
    bpl, bpp = ctypes.c_int.from_address(img + 44).value, ctypes.c_int.from_address(img + 48).value
    if bpp != 32:
        return -3
    buf = ctypes.string_at(data, bpl * h)
    if save:
        rows = b"".join(b"\0" + bytes(c for i in range(w) for c in (buf[y * bpl + 4 * i + 2], buf[y * bpl + 4 * i + 1], buf[y * bpl + 4 * i]))
                        for y in range(h))
        chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)  # noqa: E731
        Path(save).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                               + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))
    raw = memoryview(buf).cast("I")
    return sum(1 for v in raw if v & 0xFFFFFF == 0xFF00FF)


fleet_before = herdr_servers()
exe = str(W.binary(HOME))
W.write_config(HOME)
Path(PROJECT).mkdir(parents=True, exist_ok=True)
png = Path(PROJECT) / "magenta.png"
solid_png(png)
# The image is sent as an agent would: the iTerm2 inline-image escape (OSC 1337), which WezTerm draws. (`wezterm imgcat` inside
# a herdr pane refuses with "no size information available": the pane's pty reports no pixel size, so the raw escape is used,
# in both the herdr run and the control.)
show = Path(PROJECT) / "show_iterm2.sh"
show.write_text("#!/bin/sh\nprintf '\\033]1337;File=inline=1;width=16;height=8;preserveAspectRatio=0:%s\\007\\n' "
                f"\"$(base64 -w0 '{png}')\"\n")
link = Path(PROJECT) / "show_link.sh"          # the path as text, on a truecolor magenta bed so the run can find it on screen
link.write_text("#!/bin/sh\nclear\nprintf '\\033[48;2;255;0;255m%s\\033[0m\\n' " f"'{png}'\n")
kitty = Path(PROJECT) / "show_kitty.sh"
kitty.write_text("#!/bin/sh\nprintf '\\033_Ga=T,f=100,c=16,r=8;%s\\033\\\\\\n' " f"\"$(base64 -w0 '{png}')\"\n")
cock = Cockpit(HERDR_ROOT, project_root=PROJECT)
L.start_server(HERDR_ROOT, method="setsid")        # never a systemd --user unit: this run's server is a child it can stop
STARTED.append(L.server_info(HERDR_ROOT).get("pid"))
rec = cock.create_session("command", "live probe sleeper", PROJECT, command="sleep 900")
agent_pids = pane_pids(cock, rec)

# ---- test 6: SIGKILL the "Blender" that launched the window (and its whole process group): the window and the agents live on
blender = subprocess.Popen([sys.executable, "-c", f"""
import sys, types; sys.path.insert(0, {SERVER!r})
try:
    import httpx
except ImportError:
    s = types.ModuleType('httpx'); s.Client = s.AsyncClient = type('C', (), {{'send': None}}); s.Request = object; sys.modules['httpx'] = s
from lampway_server.addons import wezterm as W
inst = W.launch({HOME!r}, {exe!r}, herdr_root={str(HERDR_ROOT)!r}, detached=True, bootstrap=[{L.bin_path()!r}])
print(inst['gui_pid'], flush=True)
import time; time.sleep(600)
"""], stdout=subprocess.PIPE, text=True, start_new_session=True)
gui_pid = int(blender.stdout.readline().strip())
STARTED.append(gui_pid)
for _ in range(60):
    if W.gui_socket(HOME):
        break
    time.sleep(1)
time.sleep(3)
os.killpg(blender.pid, signal.SIGKILL)
blender.wait()
time.sleep(2)
checks["blender_sigkill_leaves_window_and_panes"] = {
    "ok": bool(agent_pids) and alive(gui_pid) and all(alive(p) for p in agent_pids),
    "stand_in_pid": blender.pid, "gui_pid": gui_pid, "gui_alive": alive(gui_pid), "gui_socket": str(W.gui_socket(HOME)),
    "agent_pids": agent_pids, "agents_alive": [alive(p) for p in agent_pids]}

try:
    listed = json.loads(W.cli(HOME, exe, ["list", "--format", "json"]) or "[]")
    checks["window_answers_on_its_own_socket"] = {"ok": bool(listed), "panes": [p.get("pane_id") for p in listed],
                                                  "titles": [p.get("title") for p in listed]}
except Exception as exc:  # noqa: BLE001
    listed = []
    checks["window_answers_on_its_own_socket"] = {"ok": False, "error": str(exc)[:300]}
inst = W.load_instance(HOME)
inst["panes"] = {str(p["pane_id"]): {"herdr_agent_id": rec["id"]} for p in listed}
W.save_instance(HOME, inst)

# ---- test 9: an image inline, drawn by an agent pane INSIDE herdr, shown by the herdr client in Lampway's window; both protocols
for proto, script in (("iterm2", show), ("kitty", kitty)):
    img = cock.create_session("command", f"live probe image {proto}", PROJECT, command=f"sh {script}")
    try:
        L.run(HERDR_ROOT, ["workspace", "focus", img["workspace_id"]])
        L.run(HERDR_ROOT, ["tab", "focus", img["tab_id"]])
    except L.HerdrError as exc:
        checks[f"focus_error_{proto}"] = {"ok": False, "error": str(exc)[:300]}
    time.sleep(8)
    try:
        shown = L.run(HERDR_ROOT, ["pane", "read", img["pane_id"]])[-400:]
    except L.HerdrError as exc:
        shown = f"(pane read refused: {exc})"
    magenta = magenta_on_screen(Path(HOME).parent / f"screen-herdr-{proto}.png")
    checks[f"inline_image_through_herdr_{proto}"] = {"ok": magenta > 100, "magenta_pixels": magenta, "pane_text_tail": shown}
    try:
        cock.close_session(img["id"], confirmed=True)
    except Exception:  # noqa: BLE001
        pass
# ---- the fallback (contract 16, 6.7): the image's path, printed by an agent pane inside herdr, is a link; a click on it queues
# the image for Blender (the Blender half is tests/lampway_visual/test_terminal_image.py)
queue = Path(HOME) / "wezterm" / "show_in_blender.jsonl"
subprocess.run(["xdotool", "search", "--class", W.CLASS, "windowsize", "%@", "1600", "1000"], capture_output=True, timeout=20)
time.sleep(2)
lnk = cock.create_session("command", "live probe link", PROJECT, command=f"sh {link}")
L.run(HERDR_ROOT, ["workspace", "focus", lnk["workspace_id"]])
L.run(HERDR_ROOT, ["tab", "focus", lnk["tab_id"]])
time.sleep(6)
box = magenta_box()
tried = []
for mods in ([], ["ctrl"]):
    if box is None or queue.exists():
        break
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    for wid in subprocess.run(["xdotool", "search", "--class", W.CLASS], capture_output=True, text=True, timeout=20).stdout.split()[:1]:
        subprocess.run(["xdotool", "windowfocus", "--sync", wid], capture_output=True, timeout=20)   # no window manager: give it focus
    cmd = ["xdotool", "mousemove", str(cx), str(cy), "sleep", "0.5"] + [a for m in mods for a in ("keydown", m)]
    cmd += ["mousedown", "1", "sleep", "0.2", "mouseup", "1"] + [a for m in mods for a in ("keyup", m)]
    subprocess.run(cmd, capture_output=True, timeout=20)
    tried.append("+".join(mods) or "plain")
    time.sleep(3)
magenta_on_screen(Path(HOME).parent / "screen-herdr-link.png")
queued = queue.read_text().splitlines() if queue.exists() else []
checks["image_path_link_queues_for_blender"] = {
    "ok": any(json.loads(q).get("path") == str(png) for q in queued), "text_box": box, "clicks": tried, "queued": queued}
try:
    cock.close_session(lnk["id"], confirmed=True)
except Exception:  # noqa: BLE001
    pass

# the control: the same escape sequence straight into a WezTerm pane, no herdr in between
if listed:
    for proto, script in (("iterm2", show), ("kitty", kitty)):
        ctl = W.launch(HOME, exe, detached=True, bootstrap=["sh", "-c", f"sh {script}; sleep 60"])
        STARTED.append(ctl["gui_pid"])
        time.sleep(8)
        m = magenta_on_screen(Path(HOME).parent / f"screen-control-{proto}.png")
        checks[f"inline_image_without_herdr_control_{proto}"] = {"ok": m > 100, "magenta_pixels": m}
        W._signal(ctl["gui_pid"])
        time.sleep(2)
    inst = W.load_instance(HOME)
    inst["gui_pid"] = gui_pid
    W.save_instance(HOME, inst)

# ---- test 7: persistence is herdr's: close the window, the agents live; reopen, the tab re-attaches, no new agent
W._signal(gui_pid)
for _ in range(20):
    if not alive(gui_pid):
        break
    time.sleep(0.5)
after_close = [alive(p) for p in agent_pids]
inst2 = W.launch(HOME, exe, herdr_root=HERDR_ROOT, detached=True, bootstrap=[L.bin_path()])
STARTED.append(inst2["gui_pid"])
time.sleep(8)
agent_pids2 = pane_pids(cock, rec)
recon = W.reconcile(HOME, exe)
checks["persistence_is_herdr_only"] = {
    "ok": not alive(gui_pid) and all(after_close) and agent_pids2 == agent_pids and recon["window"] == "re-adopted",
    "window_closed": not alive(gui_pid), "agents_alive_after_close": after_close, "agent_pids_after_reopen": agent_pids2,
    "reconcile": recon}

# ---- cleanup: only what this run started
if alive(inst2["gui_pid"]):
    W._signal(inst2["gui_pid"])
for s in (rec,):
    try:
        cock.close_session(s["id"], confirmed=True)
    except Exception:  # noqa: BLE001
        pass
try:
    L.stop_server(HERDR_ROOT, True)                   # this run's own server, addressed by its own socket environment
except Exception:  # noqa: BLE001
    pass
time.sleep(2)
srv = L.server_info(HERDR_ROOT).get("pid")
try:
    if srv and alive(srv) and str(HOME).encode() in Path(f"/proc/{srv}/environ").read_bytes():
        os.kill(int(srv), signal.SIGTERM)
except OSError:
    pass
# ---- test 11: the fleet's herdr servers are the same processes, started at the same times, after all of the above
fleet_after = herdr_servers()
checks["fleet_herdr_untouched"] = {"ok": bool(fleet_before) and fleet_before == fleet_after, "before": fleet_before, "after": fleet_after}
leftover = [p for p in STARTED if p and alive(p)]
Path(OUT).write_text(json.dumps({"checks": checks, "started": STARTED, "left_alive": leftover}, indent=1))
print(json.dumps({k: v["ok"] for k, v in checks.items()}), "left_alive", leftover)
