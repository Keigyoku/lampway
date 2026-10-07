# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The frame driver: a headless Chromium over the DevTools protocol, one frame at a time (motion_graphics.md section 6).

``Chromium`` is the capture adapter the tool runs (the tests' fake is the other one): it launches the user's headless shell (LAMPWAY_CHROMIUM)
niced, with its own HOME, XDG dirs, TZ=UTC and a fresh profile, opens ONE page at the requested size (DPR 1) with the network blocked, loads the
scene's ``file://`` entry and then, per frame, evaluates ``__frame(t)`` and captures the surface. Frames are asked for in order from frame 0 in
one browser (measured: a frame rendered out of order differs in 4 of 24 cases), and two flags are load-bearing for determinism:
``--disable-partial-raster`` (without it 1 frame of 390 differed between runs) and the network kill (an unresolvable host map and a dead proxy).

The protocol runs over ``--remote-debugging-pipe`` (fd 3 in, fd 4 out, NUL-delimited JSON), not a websocket: the server opens no network door
the egress hook cannot see (tests/test_egress.py) and the browser listens on no port another local process could attach to."""
import base64
import fcntl
import hashlib
import json
import os
import select
import shutil
import subprocess
import time
from pathlib import Path

CHROME_FLAGS = [
    "--headless", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--no-first-run", "--no-default-browser-check",
    "--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-extensions",
    "--disable-default-apps", "--disable-breakpad", "--metrics-recording-only", "--disable-domain-reliability",
    "--font-render-hinting=none", "--disable-lcd-text", "--force-color-profile=srgb", "--force-device-scale-factor=1",
    "--run-all-compositor-stages-before-draw", "--allow-file-access-from-files",
    # determinism: partial raster re-rasters only the invalidated rect, and stroke antialiasing at that clip edge depends on tile/cache state
    # (measured: the first capture of a frame differed from the next 19 by 22 px at the flame glow's rect corner). Full raster every frame removes
    # it. Checker-imaging (deferred image decode) is off for the same reason.
    "--disable-partial-raster", "--disable-checker-imaging",
    # no network: every hostname fails to resolve and every proxied request goes to a closed port
    "--host-resolver-rules=MAP * ~NOTFOUND", "--proxy-server=127.0.0.1:9", "--proxy-bypass-list=<-loopback>",
]
BLOCKED_URLS = ["http://*", "https://*", "ws://*", "wss://*"]
NO_CHROMIUM = "no headless Chromium: set LAMPWAY_CHROMIUM to a chrome-headless-shell binary"


class ChromiumMissing(RuntimeError):
    pass


def chromium_binary(env=None) -> str:
    env = os.environ if env is None else env
    p = env.get("LAMPWAY_CHROMIUM") or ""
    if not (p and os.path.isfile(p) and os.access(p, os.X_OK)):
        raise ChromiumMissing(NO_CHROMIUM)
    return p


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def scene_hash(scene_dir) -> tuple:
    """The code hash: sha256 over the sorted ``relpath\\0sha256`` rows of every file of the scene, and those rows."""
    rows = []
    for dp, dn, fs in os.walk(scene_dir):
        dn.sort()
        for f in sorted(fs):
            p = os.path.join(dp, f)
            rows.append((os.path.relpath(p, scene_dir), sha256_file(p)))
    rows.sort()
    return hashlib.sha256("".join(f"{r}\0{d}\n" for r, d in rows).encode()).hexdigest(), rows


class SceneError(RuntimeError):
    pass


class CDP:
    """A minimal synchronous DevTools client over Chromium's debugging pipe (flattened sessions). Every Network.requestWillBeSent URL is kept."""

    def __init__(self, write_fd: int, read_fd: int, timeout: float = 120.0):
        self.w, self.r = write_fd, read_fd
        self.timeout, self.n, self.events, self.requests = timeout, 0, [], []
        self._chunks, self._tail = [], b""

    def _recv(self, timeout: float) -> dict:
        """One NUL-terminated message (a screenshot is megabytes: read in chunks, joined once)."""
        while True:
            if b"\0" in self._tail:
                msg, _, self._tail = self._tail.partition(b"\0")
                data, self._chunks = b"".join(self._chunks) + msg, []
                return json.loads(data)
            if self._tail:
                self._chunks.append(self._tail)
            ready, _, _ = select.select([self.r], [], [], timeout)
            if not ready:
                raise TimeoutError(f"chromium did not answer within {timeout:g} s")
            self._tail = os.read(self.r, 1 << 20)
            if not self._tail:
                raise RuntimeError("chromium closed its DevTools pipe")

    def _keep(self, msg: dict) -> None:
        if msg.get("method") == "Network.requestWillBeSent":
            self.requests.append(msg["params"]["request"]["url"])
        elif str(msg.get("method", "")).startswith("Page."):
            self.events.append(msg)

    def send(self, method: str, params=None, session=None) -> dict:
        self.n += 1
        msg = {"id": self.n, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        data = json.dumps(msg).encode() + b"\0"
        while data:
            data = data[os.write(self.w, data):]
        while True:
            r = self._recv(self.timeout)
            if r.get("id") == self.n:
                if "error" in r:
                    raise RuntimeError(f"{method}: {r['error']}")
                return r.get("result", {})
            self._keep(r)

    def wait_event(self, name: str, timeout: float = 60.0) -> dict:
        for i, e in enumerate(self.events):
            if e.get("method") == name:
                return self.events.pop(i)
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            e = self._recv(timeout)
            if e.get("method") == name:
                return e
            self._keep(e)
        raise TimeoutError(name)

    def close(self) -> None:
        for fd in (self.w, self.r):
            try:
                os.close(fd)
            except OSError:
                pass


class Chromium:
    """The capture adapter: one headless Chromium, one page, frames in order. ``home`` holds its HOME and XDG dirs; the profile is fresh per run
    and deleted at ``close``."""

    flags = CHROME_FLAGS

    def __init__(self, binary: str, home):
        self.binary, self.home = binary, Path(home)
        self.proc = self.cdp = self.session = None
        self.product = None
        self.profile = self.home / f"profile-{os.getpid()}-{time.monotonic_ns()}"
        self._stderr = self.profile.parent / f"{self.profile.name}.stderr"

    def open(self, entry: Path, width: int, height: int) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.profile.mkdir(parents=True)
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config"), "XDG_CACHE_HOME": str(self.home / ".cache"),
               "XDG_DATA_HOME": str(self.home / ".local" / "share"), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "FONTCONFIG_PATH": "/etc/fonts"}
        r_cmd, w_cmd = os.pipe()                                          # we write commands, the browser reads them on its fd 3
        r_evt, w_evt = os.pipe()                                          # the browser writes answers and events on its fd 4, we read them
        hi = [fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10) for fd in (r_cmd, w_evt)]      # above 4, so the shell's 3<& and 4>& cannot collide
        for fd in (r_cmd, w_evt):
            os.close(fd)
        args = ["sh", "-c", f'exec nice -n 15 "$@" 3<&{hi[0]} 4>&{hi[1]}', "sh", self.binary, *CHROME_FLAGS, f"--user-data-dir={self.profile}",
                "--remote-debugging-pipe", "about:blank"]
        with open(self._stderr, "wb") as err:
            self.proc = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=err, pass_fds=tuple(hi))
        for fd in hi:
            os.close(fd)
        self.cdp = CDP(w_cmd, r_evt)
        try:
            self.product = self.cdp.send("Browser.getVersion").get("product")
        except (RuntimeError, TimeoutError) as exc:
            raise RuntimeError(f"chromium did not start ({exc}): " + self._stderr.read_text(errors="replace")[-800:]) from None
        tgt = self.cdp.send("Target.createTarget", {"url": "about:blank", "width": width, "height": height})
        s = self.session = self.cdp.send("Target.attachToTarget", {"targetId": tgt["targetId"], "flatten": True})["sessionId"]
        self.cdp.send("Page.enable", session=s)
        self.cdp.send("Network.enable", session=s)
        self.cdp.send("Network.setBlockedURLs", {"urls": BLOCKED_URLS}, s)
        self.cdp.send("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False}, s)
        self.cdp.send("Emulation.setTimezoneOverride", {"timezoneId": "UTC"}, s)
        self.cdp.send("Page.navigate", {"url": Path(entry).resolve().as_uri()}, s)
        self.cdp.wait_event("Page.loadEventFired")

    def evaluate(self, expr: str, await_promise: bool = False):
        r = self.cdp.send("Runtime.evaluate", {"expression": expr, "awaitPromise": await_promise, "returnByValue": True}, self.session)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise SceneError(f"the scene threw: {(d.get('exception') or {}).get('description') or d.get('text')}")
        return r["result"].get("value")

    def has_frame(self) -> bool:
        return bool(self.evaluate("typeof window.__frame === 'function'"))

    def setup(self) -> dict:
        return self.evaluate("window.__setup()", await_promise=True) or {}

    def scene(self) -> dict:
        return self.evaluate("window.__scene") or {}

    def animations(self) -> int:
        return int(self.evaluate("document.getAnimations().length") or 0)

    def frame(self, t: float) -> bytes:
        self.evaluate(f"window.__frame({t!r})")
        return base64.b64decode(self.cdp.send("Page.captureScreenshot", {"format": "png", "fromSurface": True, "captureBeyondViewport": False}, self.session)["data"])

    def audit(self) -> dict:
        return self.evaluate("typeof window.__audit === 'function' ? window.__audit() : null") or {}

    def requests(self) -> list:
        return list(self.cdp.requests) if self.cdp else []

    def close(self) -> None:
        try:
            if self.cdp is not None:
                try:
                    self.cdp.send("Browser.close")
                except Exception:  # noqa: BLE001 - the process is killed below
                    pass
                self.cdp.close()
        finally:
            if self.proc is not None:
                try:
                    self.proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait()
            shutil.rmtree(self.profile, ignore_errors=True)
            self._stderr.unlink(missing_ok=True)
