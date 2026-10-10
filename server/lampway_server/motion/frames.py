# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The frame driver: a headless Chromium over the DevTools protocol, one frame at a time (motion_graphics.md section 6).

``Chromium`` is the capture adapter the tool runs (the tests' fake is the other one): it launches the user's headless shell (LAMPWAY_CHROMIUM)
niced, with its own HOME, XDG dirs, TZ=UTC and a fresh profile, opens ONE page at the requested size (DPR 1) with the network blocked, loads the
scene's ``file://`` entry and then, per frame, evaluates ``__frame(t)`` and captures the surface. Frames are asked for in order from frame 0 in
one browser (measured: a frame rendered out of order differs in 4 of 24 cases), and two flags are load-bearing for determinism:
``--disable-partial-raster`` (without it 1 frame of 390 differed between runs) and the network kill (an unresolvable host map and a dead proxy).

The protocol runs over ``--remote-debugging-pipe`` (fd 3 in, fd 4 out, NUL-delimited JSON), not a websocket: the server opens no network door
the egress hook cannot see (tests/test_egress.py) and the browser listens on no port another local process could attach to.

File requests in pages and subframes are paused before loading: only decoded, scene-contained regular files are supplied as checked bytes.
New pages are attached while paused, including popups. Workers remain paused and are refused: their CDP targets do not offer Fetch interception,
so the scene must use the main-page frame driver. No target may resume with an unguarded file loader."""
import base64
import fcntl
import hashlib
import json
import mimetypes
import os
import select
import shutil
import stat
import subprocess
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .cancellation import checkpoint, kill_owned, own_process

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
NO_CHROMIUM = ("no headless Chromium: set LAMPWAY_CHROMIUM to a chrome-headless-shell binary (Chrome for Testing's chrome-headless-shell, "
               "tested 155.0.8059.39; BUILD-LAMPWAY.md, 'The motion-graphics browser')")
WRONG_BROWSER = ("LAMPWAY_CHROMIUM must be chrome-headless-shell: this browser started its own component extension ({kind} {url}), "
                 "which the scene-file containment cannot guard; a full Google Chrome or Chromium does this even with --disable-extensions. "
                 "Install Chrome for Testing's chrome-headless-shell (BUILD-LAMPWAY.md, 'The motion-graphics browser')")


class ChromiumMissing(RuntimeError):
    pass


def chromium_binary(env=None) -> str:
    env = os.environ if env is None else env
    p = env.get("LAMPWAY_CHROMIUM") or ""
    if not (p and os.path.isfile(p) and os.access(p, os.X_OK)):
        raise ChromiumMissing(NO_CHROMIUM)
    return p


def sha256_file(p, cancel=None) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            checkpoint(cancel)
            h.update(b)
    return h.hexdigest()


def scene_hash(scene_dir, cancel=None) -> tuple:
    """The code hash: sha256 over the sorted ``relpath\\0sha256`` rows of every file of the scene, and those rows."""
    root = Path(scene_dir).resolve()
    rows = []
    for dp, dn, fs in os.walk(root):
        checkpoint(cancel)
        for name in dn + fs:
            if not (Path(dp) / name).resolve().is_relative_to(root):
                raise SceneError("file outside the scene folder: remove escaping symlinks")
        dn.sort()
        for f in sorted(fs):
            p = os.path.join(dp, f)
            with _open_scene_file(Path(p), root) as source:
                h = hashlib.sha256()
                for block in iter(lambda: source.read(1 << 20), b""):
                    checkpoint(cancel)
                    h.update(block)
            rows.append((os.path.relpath(p, root), h.hexdigest()))
    rows.sort()
    return hashlib.sha256("".join(f"{r}\0{d}\n" for r, d in rows).encode()).hexdigest(), rows


class SceneError(RuntimeError):
    pass


def allowed_file_url(url: str, scene_dir) -> bool:
    """Decode a file URI once, including authority; contain its real filesystem target."""
    try:
        u = urlsplit(url)
        return (u.scheme == "file" and u.netloc in ("", "localhost") and
                Path(unquote(u.path, errors="strict")).resolve().is_relative_to(Path(scene_dir).resolve()))
    except (ValueError, OSError, UnicodeError):
        return False


def _open_scene_file(path: Path, root: Path):
    """Return a checked regular file; never read an escaping symlink or block on a FIFO."""
    if not path.resolve().is_relative_to(root):
        raise SceneError("file outside the scene folder: use only scene-local assets")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        actual = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if not actual.is_relative_to(root):
            raise SceneError("file outside the scene folder: use only scene-local assets")
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise SceneError("scene assets must be regular files")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


class CDP:
    """A minimal synchronous DevTools client over Chromium's debugging pipe (flattened sessions). Every Network.requestWillBeSent URL is kept."""

    def __init__(self, write_fd: int, read_fd: int, timeout: float = 120.0, cancel=None):
        self.cancel = cancel
        self.w, self.r = write_fd, read_fd
        self.timeout, self.n, self.events, self.requests = timeout, 0, [], []
        self._chunks, self._tail = [], b""
        self.responses, self.handler = {}, None
        self._request_ids = set()

    def _recv(self, timeout: float) -> dict:
        """One NUL-terminated message (a screenshot is megabytes: read in chunks, joined once)."""
        while True:
            checkpoint(self.cancel)
            if b"\0" in self._tail:
                msg, _, self._tail = self._tail.partition(b"\0")
                data, self._chunks = b"".join(self._chunks) + msg, []
                return json.loads(data)
            if self._tail:
                self._chunks.append(self._tail)
            ready, _, _ = select.select([self.r], [], [], timeout)
            checkpoint(self.cancel)
            if not ready:
                raise TimeoutError(f"chromium did not answer within {timeout:g} s")
            self._tail = os.read(self.r, 1 << 20)
            checkpoint(self.cancel)
            if not self._tail:
                raise RuntimeError("chromium closed its DevTools pipe")

    def _keep(self, msg: dict) -> None:
        if "id" in msg:
            self.responses[msg["id"]] = msg
            return
        if self.handler is not None:
            self.handler(msg)
        if msg.get("method") == "Network.requestWillBeSent":
            self.keep_request(msg["params"]["request"]["url"], msg["params"].get("requestId"), msg.get("sessionId"))
        elif str(msg.get("method", "")).startswith("Page."):
            self.events.append(msg)

    def keep_request(self, url, request_id, session):
        key = (session, request_id, url)
        if request_id is None or key not in self._request_ids:
            self.requests.append(url)
            self._request_ids.add(key)

    def send(self, method: str, params=None, session=None) -> dict:
        checkpoint(self.cancel)
        self.n += 1
        request_id = self.n
        msg = {"id": request_id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        data = json.dumps(msg).encode() + b"\0"
        while data:
            checkpoint(self.cancel)
            try:
                data = data[os.write(self.w, data):]
            except OSError:
                checkpoint(self.cancel)
                raise
        while True:
            r = self.responses.pop(request_id, None)
            if r is None:
                r = self._recv(self.timeout)
            if r.get("id") == request_id:
                if "error" in r:
                    raise RuntimeError(f"{method}: {r['error']}")
                return r.get("result", {})
            self._keep(r)

    def wait_event(self, name: str, timeout: float = 60.0, session=None) -> dict:
        for i, e in enumerate(self.events):
            if e.get("method") == name and (session is None or e.get("sessionId") == session):
                return self.events.pop(i)
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            e = self._recv(timeout)
            if e.get("method") == name and (session is None or e.get("sessionId") == session):
                return e
            self._keep(e)
        raise TimeoutError(name)

    def close(self) -> None:
        owned_fds = (self.w, self.r)
        self.w = self.r = None
        for fd in owned_fds:
            if fd is None:
                continue
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
        self.scene_root, self.violation = None, None
        self._target_sessions = {}
        self.cancel, self._unregister = None, None
        self.profile = self.home / f"profile-{os.getpid()}-{time.monotonic_ns()}"
        self._stderr = self.profile.parent / f"{self.profile.name}.stderr"

    def _configure_target(self, session):
        self.cdp.send("Network.enable", session=session)
        self.cdp.send("Network.setBlockedURLs", {"urls": BLOCKED_URLS}, session)
        self.cdp.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]}, session)
        self.cdp.send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True}, session)

    def _event(self, event):
        method, params = event.get("method"), event.get("params", {})
        if method == "Target.attachedToTarget":
            child = params["sessionId"]
            self._target_sessions[params["targetInfo"]["targetId"]] = child
            if params["targetInfo"]["type"] == "browser_ui":
                # Browser-owned chrome UI is not a scene loader. Resume without granting scene access.
                self.cdp.send("Runtime.runIfWaitingForDebugger", session=child)
                return
            if params["targetInfo"]["type"] not in ("page", "iframe"):
                # Worker targets do not expose Fetch. Keep them paused and close rather than allow an unguarded loader.
                url = str(params["targetInfo"].get("url") or "")
                if url.startswith("chrome-extension://"):
                    # Not the scene's: a full Chrome starts its component extensions even with --disable-extensions. Same refusal, named.
                    self.violation = WRONG_BROWSER.format(kind=params["targetInfo"]["type"], url=url)
                else:
                    self.violation = "worker may read files outside the scene folder: use the main-page scene driver"
                self.cdp.send("Target.closeTarget", {"targetId": params["targetInfo"]["targetId"]})
                raise SceneError(self.violation)
            self._configure_target(child)
            self.cdp.send("Runtime.runIfWaitingForDebugger", session=child)
        elif method == "Fetch.requestPaused":
            url, request_id = params["request"]["url"], params["requestId"]
            session = event.get("sessionId")
            self.cdp.keep_request(url, params.get("networkId") or request_id, session)
            scheme = urlsplit(url).scheme
            if scheme == "file":
                if not allowed_file_url(url, self.scene_root):
                    self.violation = "file outside the scene folder: use only scene-local assets"
                    self.cdp.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "AccessDenied"}, session)
                    return
                try:
                    path = Path(unquote(urlsplit(url).path, errors="strict"))
                    # Fulfill the checked bytes, never let Chromium reopen the pathname. Verify the opened inode as well
                    # so a path/symlink swap between resolve and open cannot return an outside file.
                    with _open_scene_file(path, self.scene_root) as source:
                        chunks = []
                        for chunk in iter(lambda: source.read(1 << 20), b""):
                            checkpoint(self.cancel)
                            chunks.append(chunk)
                        body = b"".join(chunks)
                except SceneError as exc:
                    self.violation = str(exc)
                    self.cdp.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "AccessDenied"}, session)
                    return
                except OSError:
                    self.cdp.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "AccessDenied"}, session)
                    return
                mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                self.cdp.send("Fetch.fulfillRequest", {"requestId": request_id, "responseCode": 200,
                              "responseHeaders": [{"name": "Content-Type", "value": mime}],
                              "body": base64.b64encode(body).decode()}, session)
            elif scheme in ("data", "blob", "about"):
                self.cdp.send("Fetch.continueRequest", {"requestId": request_id}, session)
            else:
                self.cdp.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "AccessDenied"}, session)

    def _check_containment(self):
        checkpoint(self.cancel)
        if self.violation:
            raise SceneError(self.violation)

    def open(self, entry: Path, width: int, height: int) -> None:
        checkpoint(self.cancel)
        self.scene_root = Path(self.scene_root or Path(entry).parent).resolve()
        if not allowed_file_url(Path(entry).absolute().as_uri(), self.scene_root):
            raise SceneError("entry outside the scene folder")
        self.home.mkdir(parents=True, exist_ok=True)
        self.profile.mkdir(parents=True)
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config"), "XDG_CACHE_HOME": str(self.home / ".cache"),
               "XDG_DATA_HOME": str(self.home / ".local" / "share"), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "FONTCONFIG_PATH": "/etc/fonts"}
        r_cmd, w_cmd = os.pipe()                                          # we write commands, the browser reads them on its fd 3
        r_evt, w_evt = os.pipe()                                          # the browser writes answers and events on its fd 4, we read them
        hi = [fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10) for fd in (r_cmd, w_evt)]      # above 4, so the shell's 3<& and 4>& cannot collide
        for fd in (r_cmd, w_evt):
            os.close(fd)
        args = ["bash", "-c", f'exec nice -n 15 "$@" 3<&{hi[0]} 4>&{hi[1]}', "sh", self.binary, *CHROME_FLAGS, f"--user-data-dir={self.profile}",
                "--remote-debugging-pipe", "about:blank"]
        with open(self._stderr, "wb") as err:
            self.proc = own_process(subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=err, pass_fds=tuple(hi), start_new_session=True))
        for fd in hi:
            os.close(fd)
        self._unregister = self.cancel.on_cancel(lambda: kill_owned(self.proc)) if self.cancel is not None else None
        self.cdp = CDP(w_cmd, r_evt, cancel=self.cancel)
        try:
            self.product = self.cdp.send("Browser.getVersion").get("product")
        except (RuntimeError, TimeoutError) as exc:
            raise RuntimeError(f"chromium did not start ({exc}): " + self._stderr.read_text(errors="replace")[-800:]) from None
        self.cdp.handler = self._event
        # Browser-level attachment also catches popup pages before their first document executes.
        self.cdp.send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True})
        tgt = self.cdp.send("Target.createTarget", {"url": "about:blank"})
        self.cdp.send("Target.getTargets")
        s = self.session = self._target_sessions[tgt["targetId"]]
        self.cdp.send("Page.enable", session=s)
        self.cdp.send("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False}, s)
        self.cdp.send("Emulation.setTimezoneOverride", {"timezoneId": "UTC"}, s)
        # Discard the initial about:blank load before waiting for this navigation.
        self.cdp.send("Runtime.evaluate", {"expression": "document.readyState"}, s)
        self.cdp.events.clear()
        navigation = self.cdp.send("Page.navigate", {"url": Path(entry).resolve().as_uri()}, s)
        if navigation.get("errorText"):
            self._check_containment()
            raise SceneError("scene entry could not load: " + navigation["errorText"])
        self.cdp.wait_event("Page.loadEventFired", session=s)
        self._check_containment()

    def evaluate(self, expr: str, await_promise: bool = False):
        self._check_containment()
        r = self.cdp.send("Runtime.evaluate", {"expression": expr, "awaitPromise": await_promise, "returnByValue": True}, self.session)
        self._check_containment()
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise SceneError(f"the scene threw: {(d.get('exception') or {}).get('description') or d.get('text')}")
        return r["result"].get("value")

    def has_frame(self) -> bool:
        return bool(self.evaluate("typeof window.__frame === 'function'"))

    def has_audit(self) -> bool:
        return bool(self.evaluate("typeof window.__audit === 'function'"))

    def setup(self) -> dict:
        return self.evaluate("window.__setup()", await_promise=True)

    def scene(self) -> dict:
        return self.evaluate("window.__scene") or {}

    def animations(self) -> int:
        return int(self.evaluate("document.getAnimations().length") or 0)

    def frame(self, t: float) -> bytes:
        self.evaluate(f"window.__frame({t!r})")
        result = self.cdp.send("Page.captureScreenshot", {"format": "png", "fromSurface": True, "captureBeyondViewport": False}, self.session)
        self._check_containment()
        return base64.b64decode(result["data"])

    def audit(self) -> dict:
        result = self.evaluate("typeof window.__audit === 'function' ? window.__audit() : null")
        if not isinstance(result, dict) or not isinstance(result.get("text"), list) or not isinstance(result.get("marks"), list):
            raise SceneError("the scene must define window.__audit() returning text and marks arrays")
        from .check import validate_audit
        try:
            validate_audit(result)
        except ValueError as exc:
            raise SceneError(str(exc)) from None
        return result

    def requests(self) -> list:
        return list(self.cdp.requests) if self.cdp else []

    def close(self) -> None:
        try:
            if self.cdp is not None:
                try:
                    self.cdp.send("Browser.close")
                except Exception:  # noqa: BLE001 - the owned process is stopped below
                    pass
                self.cdp.close()
        finally:
            if self.proc is not None:
                try:
                    self.proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    kill_owned(self.proc)
                    self.proc.wait()
            if self._unregister is not None:
                self._unregister()
                self._unregister = None
            shutil.rmtree(self.profile, ignore_errors=True)
            self._stderr.unlink(missing_ok=True)
