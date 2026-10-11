# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Live Mode 1 support (docs/reports/agent-modes-spec.md A1-A3): herdr played, but its ``pane run`` REALLY runs the command in a pty,
the way a herdr pane would, so the real pane wrapper starts the real pinned ``hermes serve`` and Hermes's real TUI. Every process a
test starts is ended by its recorded process group at teardown (never a pattern kill), serve included (its pid is in the pane's
home)."""

import fcntl
import json
import os
import pty
import re
import signal
import struct
import termios
import threading
import time
from pathlib import Path

from lampway_server.herdr import launcher as L

from .herdr_support import PaneHerdr

ANSI = re.compile(rb"\x1b\[[0-9;?<>=]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b[()][A-Z0-9]|\x1b[=>78]")


class PtyProcess:
    def __init__(self, argv, env, cwd, cols=120, rows=40):
        self.argv = argv
        self.cols, self.rows = cols, rows
        self.buf = bytearray()
        self.pid, self.fd = pty.fork()
        if self.pid == 0:                                           # the child: the pane's foreground program
            try:
                os.chdir(cwd)
                os.execve(argv[0], argv, env)
            finally:
                os._exit(127)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while True:
            try:
                data = os.read(self.fd, 65536)
            except OSError:
                return
            if not data:
                return
            with self.lock:
                self.buf += data

    def text(self) -> str:
        with self.lock:
            raw = bytes(self.buf)
        return ANSI.sub(b"", raw).decode("utf-8", "replace")

    def screen_text(self) -> str:
        """The current visible terminal, with cursor movement and erasure applied.

        Ink writes differential redraws: stripping ANSI and concatenating those bytes loses words and retains erased text.
        Keep ``text`` as the legacy output log for tests that mark/slice its length; use this method for displayed evidence.
        """
        import pyte
        with self.lock:
            raw = bytes(self.buf)
        screen = pyte.Screen(self.cols, self.rows)
        pyte.ByteStream(screen).feed(raw)
        return "\n".join(screen.display)

    def write(self, s: str) -> None:
        os.write(self.fd, s.encode())

    def alive(self) -> bool:
        try:
            pid, _ = os.waitpid(self.pid, os.WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False

    def cmdline(self) -> str:
        try:
            return Path(f"/proc/{self.pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        except OSError:
            return ""

    def end(self, timeout=15.0) -> None:
        """SIGHUP, as a closing pane sends: the wrapper ends its serve. Then SIGKILL its group if anything is left."""
        if self.alive():
            try:
                os.kill(self.pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
            end = time.monotonic() + timeout
            while self.alive() and time.monotonic() < end:
                time.sleep(0.1)
        if self.alive():
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                os.waitpid(self.pid, 0)
            except ChildProcessError:
                pass
        try:
            os.close(self.fd)
        except OSError:
            pass


class RunningHerdr(PaneHerdr):
    """``PaneHerdr`` whose ``pane run`` starts the command for real in a pty, with herdr's scrubbed base plus the pane's own
    ``--env`` values; ``process-info`` reports the live process; ``send-text``/``send-keys`` type into it; ``pane close`` ends it."""

    def __init__(self, egress=None):
        super().__init__(egress)
        self.procs: dict = {}

    def __call__(self, root, args, timeout=30, input=None):
        args = [str(a) for a in args]
        if args[:2] == ["pane", "run"]:
            out = super().__call__(root, args, timeout, input)
            pane_id = args[2]
            env = {**L.scrubbed_base(), **self.env_of(pane_id)}
            made = self.made()[int(pane_id[1:]) - 1]["args"]
            cwd = made[made.index("--cwd") + 1] if "--cwd" in made else env.get("HOME", "/")
            # like herdr 0.9.3: its arguments joined by spaces, typed into the pane's shell (here: run by /bin/sh, exec'd)
            self.procs[pane_id] = PtyProcess(["/bin/sh", "-c", "exec " + " ".join(args[3:])], env, cwd)
            return out
        if args[:2] == ["pane", "process-info"]:
            pane_id = args[args.index("--pane") + 1]
            proc = self.procs.get(pane_id)
            if proc is not None and pane_id in self.panes:
                cmd = proc.cmdline() if proc.alive() else "-bash"
                return json.dumps({"result": {"process_info": {"foreground_processes": [{"cmdline": cmd}]}}})
        if args[:2] == ["pane", "send-text"]:
            self.procs[args[2]].write(args[3])
            return ""
        if args[:2] == ["pane", "send-keys"]:
            self.procs[args[2]].write({"enter": "\r", "ctrl-c": "\x03"}.get(args[3], ""))
            return ""
        if args[:2] == ["pane", "close"] and args[2] in self.procs:
            self.procs.pop(args[2]).end()
        return super().__call__(root, args, timeout, input)

    def proc_for(self, record) -> PtyProcess:
        return self.procs[record["pane_id"]]

    def end_all(self, homes=()) -> list:
        """Every pane this test opened, then any serve still alive by the pid its wrapper recorded. Returns what was still alive."""
        for proc in list(self.procs.values()):
            proc.end()
        self.procs.clear()
        left = []
        for home in homes:
            pid_file = Path(home) / "serve.pid"
            if pid_file.is_file():
                pid = int(pid_file.read_text())
                if _alive(pid):
                    left.append(pid)
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
        return left


def _alive(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.split(")")[-1].split()[0] != "Z"


def wait_for(cond, timeout=60.0, step=0.1):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return cond()
