"""Asset Vault previews (specs/asset_library/asset_render.md): thumbnails, turntables, material balls, UV overlays, map and contact sheets.

Off the user's live Blender, always. The software rasteriser and the image products run in this process; Workbench / EEVEE jobs run a separate, niced, batch-mode Blender
with factory settings, a throw-away user config and the bridge port forced to 0 (never Cycles). Jobs are keyed (version, product, recipe hash): the same recipe is a
cache hit, a recipe change re-renders lazily. A Blender job waits while the box is busy (load > 0.6 x cores, or a windowed Blender above 25 % CPU), backing off
30 s, 2 min, 10 min. The software path never waits: it cannot contend with the user's GPU work."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from . import derived as D
from . import ingest as I
from .previews import LABEL_H, contact_sheet, image_thumb, map_sheet, uv_loops, uv_overlay, video_thumb  # noqa: F401
from .raster import RECIPE, encode_jpeg, frame_views, glb_mesh, render_mesh  # noqa: F401
from .store import AssetLibrary, LibraryError

PRODUCTS = ("thumb", "turntable", "ball", "uv_overlay", "map_sheet", "contact_sheet")
FOR_KINDS = {"thumb": ("mesh", "image", "video", "hdri", "map", "material", "uv_layout"), "turntable": ("mesh",), "ball": ("material", "texture_set"),
             "uv_overlay": ("mesh",), "map_sheet": ("texture_set", "material"), "contact_sheet": ("mesh",)}
WRONG_KIND = {"turntable": "turntable is for meshes: use ball for materials", "ball": "ball is for materials and texture sets: use turntable for meshes",
              "uv_overlay": "uv_overlay is for meshes with a UV set", "map_sheet": "map_sheet is for texture sets and materials with maps",
              "contact_sheet": "contact_sheet is for meshes (from the turntable): a video's strip is asset_video's"}
DEFAULT_SIZE, DEFAULT_FRAMES = {"thumb": 256, "turntable": 256, "ball": 256, "uv_overlay": 1024, "map_sheet": 256, "contact_sheet": 256}, 36
ENGINES = ("auto", "software", "workbench", "eevee")
SOFT_MAX_TRIS = 2_000_000          # above: the software path refuses and Workbench renders a decimated copy
SOFT_TURNTABLE_MAX_TRIS = 50_000   # above: turntables go to Workbench
DECIMATE_TO = 300_000              # the preview-only decimation target (never saved)
BACKOFF = (30, 120, 600)
NICE = 15
WORKER = Path(__file__).with_name("render_worker.py")
BLENDER_NAMES = {"blender", "mixar"}
BACKFILL_KINDS = ("mesh", "image", "video", "hdri", "map")


def recipe_hash(product: str, size: Optional[int] = None, frames: Optional[int] = None) -> str:
    key = {"recipe": RECIPE, "product": product, "size": int(size or DEFAULT_SIZE[product]), "frames": int(frames or DEFAULT_FRAMES) if product in ("turntable", "contact_sheet") else None}
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def blender_command(blender, job_path, scratch, script=None) -> tuple:
    """argv and environment of one headless render job: niced, batch mode, factory settings, a private user config, the bridge disabled."""
    scratch = Path(scratch)
    env = {k: v for k, v in os.environ.items() if k not in ("BLENDER_MCP_PORT",)}
    env.update(BLENDER_USER_CONFIG=str(scratch / "config"), BLENDER_USER_SCRIPTS=str(scratch / "scripts"), LAMPWAY_BRIDGE_PORT="0", LAMPWAY_BACKEND_URL="http://127.0.0.1:9")
    argv = ["nice", "-n", str(NICE), str(blender), "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script or WORKER), "--", str(job_path)]
    return argv, env


# ---- the live-window meter --------------------------------------------------------------------------------------------------------
def blender_cpu_sample(proc="/proc", now: Optional[float] = None) -> dict:
    """CPU ticks (utime + stime) of every Blender with a window (argv[0] named blender/mixar, no -b / --background), at time ``now``."""
    ticks, root = {}, Path(proc)
    for d in root.iterdir() if root.is_dir() else ():
        if not d.name.isdigit():
            continue
        try:
            argv = (d / "cmdline").read_bytes().split(b"\0")
            if Path(argv[0].decode(errors="replace")).name not in BLENDER_NAMES or b"-b" in argv or b"--background" in argv:
                continue
            fields = (d / "stat").read_text().rsplit(")", 1)[1].split()
            ticks[d.name] = int(fields[11]) + int(fields[12])
        except (OSError, IndexError, ValueError):
            continue                                               # a process that ended mid-read
    return {"t": time.monotonic() if now is None else now, "ticks": ticks}


def cpu_percent(a: dict, b: dict, hz: int = 100) -> float:
    dt = b["t"] - a["t"]
    if dt <= 0:
        return 0.0
    return max([(b["ticks"][p] - a["ticks"][p]) / hz / dt * 100.0 for p in b["ticks"] if p in a["ticks"]] or [0.0])


class LiveWindowMeter:
    """The busiest windowed Blender's CPU % since the previous call (the first call samples twice, half a second apart)."""

    def __init__(self, proc="/proc", sleep: Callable[[float], None] = time.sleep):
        self.proc, self.sleep, self.last = proc, sleep, None
        self.hz = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100

    def __call__(self) -> float:
        if self.last is None:
            self.last = blender_cpu_sample(self.proc)
            self.sleep(0.5)
        cur = blender_cpu_sample(self.proc)
        pct, self.last = cpu_percent(self.last, cur, self.hz), cur
        return pct


# ---- the queue ------------------------------------------------------------------------------------------------------------------
class Renderer:
    def __init__(self, lib: AssetLibrary, blender=None, runner: Callable = subprocess.run, loadavg: Callable = os.getloadavg, cpus: Optional[int] = None,
                 live_window_cpu: Optional[Callable[[], float]] = None, now: Callable[[], float] = time.monotonic):
        self.lib, self.blender, self.runner, self.loadavg = lib, blender, runner, loadavg
        self.cpus = cpus or os.cpu_count() or 1
        self.live_window_cpu = live_window_cpu or LiveWindowMeter()
        self.now = now
        self.jobs: dict = {}                                       # (asset_id, product key) -> job
        self._lock = threading.RLock()

    # -- interface --------------------------------------------------------------------------------------------------------------
    def enqueue(self, asset_id: str, products, size: Optional[int] = None, frames: Optional[int] = None, engine: str = "auto", priority: str = "normal", force: bool = False) -> dict:
        a = self.lib.get(asset_id)
        self._check(a, products, size, frames, engine)
        queued, cached = [], []
        vid = self.lib.version_of(asset_id)
        for prod in products:
            pkey = self._key(prod, size)
            h = recipe_hash(prod, size, frames)
            have = (a["attrs"].get("render_recipe") or {}).get(pkey) == h and any(f["role"] == self._role(prod, size) for f in a["files"])
            if have and not force:
                cached.append(pkey)
                continue
            with self._lock:
                self.jobs[(asset_id, pkey)] = {"asset_id": asset_id, "version_id": vid, "product": prod, "key": pkey, "size": int(size or DEFAULT_SIZE[prod]),
                                               "frames": int(frames or DEFAULT_FRAMES), "engine": engine, "hash": h, "priority": priority, "state": "queued",
                                               "attempts": 0, "backoff": -1, "next_at": None}
            queued.append(pkey)
        return {"ok": True, "queued": len(queued), "jobs": queued, "cached": cached}

    def handle(self, req: dict) -> dict:
        """The tool surface (``lampway_asset_render``): ``{action: enqueue|status|cancel|regenerate, asset_id, products, size, frames, engine, priority}`` ->
        ``{ok, ...}``; a refusal is ``{ok: false, error, help}``, never an exception."""
        action, aid = req.get("action") or "status", req.get("asset_id")
        kw = {k: req[k] for k in ("size", "frames", "engine", "priority") if req.get(k) is not None}
        try:
            if not aid:
                raise LibraryError("asset_id is required")
            if action in ("enqueue", "regenerate"):
                return {"ok": True, **getattr(self, action)(aid, list(req.get("products") or ["thumb"]), **kw)}
            if action == "cancel":
                return {"ok": True, **self.cancel(aid, list(req.get("products") or PRODUCTS))}
            if action == "status":
                self.lib.get(aid)
                return {"ok": True, **self.status(aid)}
            raise LibraryError(f"unknown action {action!r}: enqueue|status|cancel|regenerate")
        except LibraryError as e:
            return {"ok": False, "error": str(e), "help": [f"products: {list(PRODUCTS)}; size 128..1024; frames 8..72; engine auto|software|workbench|eevee",
                                                           "status {asset_id} shows what is queued, deferred, done or failed"]}

    def backfill(self, limit: int = 50) -> int:
        """Queue a low-priority thumbnail for every active asset that has none and no job yet: every asset in the grid gets one without anyone asking."""
        kinds = ",".join("?" * len(BACKFILL_KINDS))
        rows = self.lib._reader().execute(
            f"SELECT a.id FROM asset a JOIN version v ON v.asset_id=a.id AND v.n=a.current_version WHERE a.status='active' AND a.kind IN ({kinds}) "
            "AND NOT EXISTS(SELECT 1 FROM version_file f WHERE f.version_id=v.id AND f.role='thumb') ORDER BY a.created_at, a.id", BACKFILL_KINDS).fetchall()
        n = 0
        with self._lock:
            for (aid,) in rows:
                if n >= limit:
                    break
                if (aid, "thumb") in self.jobs:
                    continue
                self.enqueue(aid, ["thumb"], priority="low")
                n += 1
        return n

    def start(self, stop: threading.Event, idle_s: float = 2.0) -> threading.Thread:
        """The single worker thread: drain what is due, else backfill, else wait ``idle_s`` (until ``stop`` is set)."""
        def loop():
            while not stop.is_set():
                try:
                    ran = self.drain() or self.backfill()
                except Exception:  # noqa: BLE001 - one bad asset never stops the previews of the rest
                    ran = 0
                if not ran:
                    stop.wait(idle_s)
        t = threading.Thread(target=loop, name="vault-render", daemon=True)
        t.start()
        return t

    def regenerate(self, asset_id: str, products, **kw) -> dict:
        return self.enqueue(asset_id, products, force=True, **kw)

    def cancel(self, asset_id: str, products) -> dict:
        done = []
        with self._lock:
            for (aid, pkey), job in self.jobs.items():
                if aid == asset_id and (pkey in products or job["product"] in products) and job["state"] in ("queued", "deferred"):
                    job["state"] = "cancelled"
                    done.append(pkey)
        return {"cancelled": done}

    def status(self, asset_id: str) -> dict:
        out = {}
        with self._lock:
            jobs = list(self.jobs.items())
        for (aid, pkey), job in jobs:
            if aid == asset_id:
                out[pkey] = {k: job[k] for k in ("state", "engine") if k in job}
                for k in ("error", "ms", "paths"):
                    if job.get(k) is not None:
                        out[pkey][k] = job[k]
                if job.get("paths"):
                    out[pkey]["path"] = job["paths"][0]
                if job["state"] == "deferred":
                    out[pkey]["retry_in_s"] = BACKOFF[job["backoff"]]
        return {"asset_id": asset_id, "products": out}

    def drain(self) -> int:
        """Run every job that is due, visible-in-UI (``priority: high``) first. Returns how many ran."""
        ran = 0
        with self._lock:
            due = [j for j in self.jobs.values() if j["state"] == "queued" or (j["state"] == "deferred" and self.now() >= j["next_at"])]
            for j in due:
                j["state"] = "running"
        rank = {"high": 0, "normal": 1, "low": 2}
        due.sort(key=lambda j: (rank.get(j["priority"], 1), j["product"] == "contact_sheet"))     # visible first; a contact sheet reads the turntable's frames: last
        for job in due:
            self._run(job)
            ran += 1
        return ran

    # -- internals --------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _key(prod, size):
        return f"thumb:{size}" if prod == "thumb" and size and int(size) != DEFAULT_SIZE["thumb"] else prod

    @staticmethod
    def _role(prod, size=None):
        return {"thumb": f"thumb:{size}" if size and int(size) != 256 else "thumb", "turntable": "turntable", "ball": "ball", "uv_overlay": "overlay",
                "map_sheet": "sheet:maps", "contact_sheet": "sheet"}[prod]

    @staticmethod
    def _check(a, products, size, frames, engine):
        for p in products:
            if p not in PRODUCTS:
                raise LibraryError(f"unknown product {p!r}; products: {list(PRODUCTS)} (video strips are asset_video's)")
            if a["kind"] not in FOR_KINDS[p]:
                raise LibraryError(WRONG_KIND.get(p, f"{p} does not apply to a {a['kind']}"))
        if size is not None and int(size) > 1024:
            raise LibraryError("size max 1024: previews, not renders")
        if size is not None and int(size) < 128:
            raise LibraryError("size min 128")
        if frames is not None and not 8 <= int(frames) <= 72:
            raise LibraryError("frames 8..72 (36 is a turntable)")
        if engine == "cycles":
            raise LibraryError("Cycles is not a preview engine here (never Cycles): use workbench or eevee")
        if engine not in ENGINES:
            raise LibraryError(f"engine: {'|'.join(ENGINES)}")

    def _main(self, a):
        for role in ("main", "blend", "script"):
            for f in a["files"]:
                if f["role"] == role and f["locations"]:
                    return Path(f["locations"][0]["path"])
        raise LibraryError("no primary file on this asset")

    def _tris(self, a, path) -> Optional[int]:
        if a["stats"].get("tris") is not None:
            return int(a["stats"]["tris"])
        try:
            with open(path, "rb") as fh:
                return int(I.extract_glb(fh)["stats"]["tris"])
        except (OSError, ValueError, KeyError):
            return None                                            # not a GLB: Blender imports it

    def _engine(self, job, a, path) -> tuple:
        """(engine, decimate_to) for this job."""
        prod, want = job["product"], job["engine"]
        if prod == "ball" or (a["kind"] == "material" and prod == "thumb"):          # a material's thumbnail IS its ball
            return ("eevee" if want == "auto" else want), None
        if a["kind"] != "mesh" or prod in ("uv_overlay", "contact_sheet"):
            return "software", None
        tris = self._tris(a, path)
        decimate = DECIMATE_TO if tris is not None and tris > SOFT_MAX_TRIS else None
        if want != "auto":
            if want == "software" and (tris is None or decimate):
                raise LibraryError(f"the software path reads GLB meshes up to {SOFT_MAX_TRIS} triangles: use workbench (it decimates a preview copy)")
            return want, (decimate if want != "software" else None)
        limit = SOFT_TURNTABLE_MAX_TRIS if prod == "turntable" else SOFT_MAX_TRIS
        if tris is None or tris > limit:
            return "workbench", decimate
        return "software", None

    def _busy(self) -> bool:
        return self.loadavg()[0] > 0.6 * self.cpus or self.live_window_cpu() > 25.0

    def _run(self, job):
        a = self.lib.get(job["asset_id"])
        t0 = time.perf_counter()
        try:
            path = self._main(a)
            if not path.exists():
                self.lib.mark_missing(path)
                raise LibraryError(f"file missing: {path}; the thumbnail stays the last good one")
            engine, decimate = self._engine(job, a, path)
            job["engine"] = engine
            if engine in ("workbench", "eevee"):
                if self._busy():
                    job["backoff"] = min(job["backoff"] + 1, len(BACKOFF) - 1)
                    job["state"], job["next_at"] = "deferred", self.now() + BACKOFF[job["backoff"]]
                    return
                items = self._blender(job, a, path, engine, decimate)
            else:
                items = self._software(job, a, path)
            job["paths"] = D.replace(self.lib, job["version_id"], self._role(job["product"], job["size"]), items)
            D.set_attr(self.lib, job["version_id"], "render_recipe", job["key"], job["hash"])
            job.update(state="done", error=None, ms=round((time.perf_counter() - t0) * 1000, 1))
        except LibraryError as e:
            if "empty mesh" in str(e):
                D.add_tag(self.lib, job["asset_id"], "defect:empty")
            job.update(state="failed", error=str(e))

    def _software(self, job, a, path) -> list:
        prod, size = job["product"], job["size"]
        if prod == "thumb":
            name = f"thumb_{size}.jpg"
            if a["kind"] == "mesh":
                img, _ = render_mesh(glb_mesh(path), size)
                return [(name, encode_jpeg(img))]
            if a["kind"] == "video":
                return [(name, video_thumb(path, size, NICE))]
            return [(name, image_thumb(path, size))]
        if prod == "turntable":
            mesh = glb_mesh(path)
            n = job["frames"]
            yaws = [2 * math.pi * i / n for i in range(n)]
            fr = frame_views(mesh["tris"], yaws) if len(mesh["tris"]) else None
            return [(f"turn_{i:03d}.jpg", encode_jpeg(render_mesh(mesh, size, yaw, fr)[0])) for i, yaw in enumerate(yaws)]
        if prod == "contact_sheet":
            frames = [f["locations"][0]["path"] for f in sorted(a["files"], key=lambda f: f["ord"]) if f["role"] == "turntable" and f["locations"]]
            return [("contact.jpg", contact_sheet(frames, size))]
        if prod == "uv_overlay":
            return [("uv_overlay.png", uv_overlay(glb_mesh(path), size))]
        raise LibraryError(f"{prod} has no software path")

    def _blender(self, job, a, path, engine, decimate) -> list:
        if not self.blender:
            raise LibraryError("no Blender binary configured for headless previews: set the server's blender path (LAMPWAY_BIN)")
        work = Path(tempfile.mkdtemp(prefix="render-", dir=self.lib.root))
        out = work / "out"
        out.mkdir()
        role = next((f["role"] for f in a["files"] if any(l["path"] == str(path) for l in f["locations"])), "main")
        spec = {"product": job["product"], "input": str(path), "input_role": role, "kind": a["kind"], "frames": job["frames"], "size": job["size"], "engine": engine,
                "decimate_to": decimate, "recipe": RECIPE, "out_dir": str(out)}
        (work / "job.json").write_text(json.dumps(spec, sort_keys=True))
        argv, env = blender_command(self.blender, work / "job.json", work / "scratch")
        err = ""
        for attempt in range(2):                                   # a crash restarts the job once
            job["attempts"] += 1
            p = self.runner(argv, env=env, capture_output=True, text=True, timeout=1800)
            if p.returncode == 0:
                break
            err = (p.stderr or p.stdout or "")[-400:]
        else:
            raise LibraryError(f"the headless render failed twice: {err.strip()}")
        frames = sorted(out.glob("*.png"))
        if not frames:
            raise LibraryError(f"the worker wrote no frames: {(p.stderr or '')[-300:].strip()}")
        from PIL import Image
        names = {"thumb": f"thumb_{job['size']}.jpg", "ball": f"ball_{job['size']}.jpg"}
        items = []
        for i, f in enumerate(frames):
            with Image.open(f) as im:
                b = io.BytesIO()
                im.convert("RGB").save(b, "JPEG", quality=RECIPE["jpeg_quality"], subsampling=0)
            items.append((names.get(job["product"], f"turn_{i:03d}.jpg"), b.getvalue()))
        shutil.rmtree(work, ignore_errors=True)                    # a failed job's directory stays for inspection; a good one goes
        return items
