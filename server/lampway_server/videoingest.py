"""Bring ONE reference clip in from a link the user supplied (specs/mrmak/13): the link is checked, the metadata is read and the caps applied BEFORE any download, the download is video-only
by default and lands through a temp name and an atomic rename, and the clip keeps its provenance. The downloader is ``yt-dlp`` as an argv subprocess (never a shell) in a clean environment.

A URL an agent proposes, or any call without the user's confirm, returns the confirm CARD and runs nothing at all: not even the metadata fetch (that would be a request to a host the user
has not approved). Registration with asset_video happens when that library exists (Wave 5b); until then the asset id is ``video-<sha256[:16]>`` and the folder holds provenance.json."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Optional

SCHEMES = ("http", "https")
REDACT_PARAMS = {"token", "sig", "signature", "key", "auth"}
DEFAULT_BYTES = 500 * 1024 ** 2
MAX_BYTES = 2 * 1024 ** 3
META_TIMEOUT_S = 120
DOWNLOAD_TIMEOUT_S = 3600


class IngestError(ValueError):
    pass


def validate_url(url) -> urllib.parse.ParseResult:
    if not isinstance(url, str) or not url or url.startswith("-") or any(c.isspace() or ord(c) < 32 for c in url) or len(url) > 2048:
        raise IngestError("only an http or https link, typed or pasted by you")
    p = urllib.parse.urlsplit(url)
    if p.scheme.lower() not in SCHEMES or not p.hostname or p.username is not None or p.password is not None or "@" in p.netloc:
        raise IngestError("only an http or https link, typed or pasted by you (no userinfo, no other scheme)")
    return p


def redact(url: str) -> str:
    """No userinfo, and the query parameters that carry a credential removed."""
    p = urllib.parse.urlsplit(url)
    host = p.hostname or ""
    netloc = host + (f":{p.port}" if p.port else "")
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if k.lower() not in REDACT_PARAMS]
    return urllib.parse.urlunsplit((p.scheme, netloc, p.path, urllib.parse.urlencode(q), ""))


def _selector(audio: bool, h: int) -> str:
    if audio:
        return f"bestvideo[height<={h}][vcodec^=avc1]+bestaudio/best[height<={h}]"
    return f"bestvideo[height<={h}][ext=mp4][vcodec^=avc1]/bestvideo[height<={h}][vcodec^=avc1]/best[height<={h}][ext=mp4]/best[height<={h}]"


def _env(home: Path) -> dict:
    return {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "LANG": "C.UTF-8"}                        # no Lampway secret reaches the downloader


def _run(argv: list, env: dict, timeout: int) -> subprocess.CompletedProcess:
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except BaseException:
        try:
            os.killpg(p.pid, 9)
        except OSError:
            pass
        p.wait()
        raise
    return subprocess.CompletedProcess(argv, p.returncode, out, err)


def probe(path: Path) -> dict:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
        data = json.loads(out.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        raise IngestError("ffprobe could not read the downloaded file")
    streams = data.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if v is None:
        raise IngestError("the downloaded file has no video stream")
    num, _, den = str(v.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {"duration_s": float((data.get("format") or {}).get("duration") or 0), "width": int(v.get("width") or 0), "height": int(v.get("height") or 0), "container_fps": fps,
            "has_audio": any(s.get("codec_type") == "audio" for s in streams)}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _bounds(max_height, max_seconds, max_bytes):
    if not 144 <= int(max_height) <= 1080:
        raise IngestError("max_height is 144..1080")
    if not 1 <= int(max_seconds) <= 3600:
        raise IngestError("max_seconds is 1..3600")
    if not 1 <= int(max_bytes) <= MAX_BYTES:
        raise IngestError("max_bytes is 1..2 GB (2147483648)")


def ingest(root, url, origin: str = "user", confirmed: bool = False, audio: bool = False, max_height: int = 720, max_seconds: int = 600, max_bytes: int = DEFAULT_BYTES,
           name: Optional[str] = None, range: Optional[dict] = None, ytdlp: Optional[str] = None, ledger=None, blocklist=()) -> dict:  # noqa: A002
    p = validate_url(url)
    _bounds(max_height, max_seconds, max_bytes)
    host = p.hostname.lower()
    if any(host == b or host.endswith("." + b) for b in (b.lower().lstrip(".") for b in blocklist)):
        raise IngestError(f"{host} is on this project's blocklist")
    sect = None
    if range and (range.get("start_s") is not None or range.get("end_s") is not None):
        s0, s1 = range.get("start_s"), range.get("end_s")
        if (s0 is not None and float(s0) < 0) or (s1 is not None and float(s1) <= float(s0 or 0)):
            raise IngestError("range needs 0 <= start_s < end_s")
        sect = f"*{float(s0 or 0):g}-{'inf' if s1 is None else format(float(s1), 'g')}"
    if origin != "user" or not confirmed:
        return {"state": "needs_approval", "card": {"host": host, "max_height": int(max_height), "audio": bool(audio), "max_seconds": int(max_seconds), "max_bytes": int(max_bytes), "url_redacted": redact(url)},
                "message": "An agent can propose a link; you confirm the download. Nothing was fetched: the size and length are read from the host only after you confirm."}
    exe = ytdlp or shutil.which("yt-dlp")
    if not exe:
        raise IngestError("install yt-dlp on the server: the downloader is not bundled")
    base = Path(root) / "video" / "ingest"
    base.mkdir(parents=True, exist_ok=True)
    index_path = base / "urls.json"
    try:
        index = json.loads(index_path.read_text())
    except (OSError, ValueError):
        index = {}
    ukey = hashlib.sha256(f"{url}|audio={bool(audio)}|h={int(max_height)}|{sect}".encode()).hexdigest()
    folder = base / index[ukey] if ukey in index else None
    if folder is not None and (folder / "provenance.json").exists() and next(folder.glob("source.*"), None):
        rec = json.loads((folder / "provenance.json").read_text())
        _ledger(ledger, rec, origin, True)
        return dict(rec, reused=True)
    if shutil.disk_usage(base).free < int(max_bytes):
        raise IngestError("the project folder has less free space than max_bytes")
    work = base / f".part-{uuid.uuid4().hex[:12]}"
    work.mkdir()
    try:
        env = _env(work)
        meta = _run([exe, "--no-playlist", "--dump-single-json", "--no-warnings", "--", url], env, META_TIMEOUT_S)
        if meta.returncode != 0:
            raise IngestError("the downloader could not read that link: " + (meta.stderr.strip().splitlines() or ["no message"])[-1][:200])
        try:
            info = json.loads(meta.stdout)
        except ValueError:
            raise IngestError("the downloader answered with something that is not JSON")
        if info.get("_type") == "playlist" or info.get("entries"):
            raise IngestError("that link is a playlist: one clip per call, pass the video's own link")
        dur = info.get("duration")
        if dur is not None and float(dur) > int(max_seconds):
            raise IngestError(f"the clip is {float(dur):g} s: over the {int(max_seconds)} s cap; raise max_seconds or pass a range")
        size = info.get("filesize") or info.get("filesize_approx")
        if size is not None and int(size) > int(max_bytes):
            raise IngestError(f"the clip is about {int(size)} bytes: over the {int(max_bytes)} byte cap")
        argv = [exe, "--no-playlist", "--no-warnings", "--max-filesize", str(int(max_bytes)), "-f", _selector(audio, int(max_height)), "-o", str(work / "source.%(ext)s")]
        if audio:
            argv += ["--merge-output-format", "mp4"]
        if sect:
            argv += ["--download-sections", sect]
        done = _run(argv + ["--", url], env, DOWNLOAD_TIMEOUT_S)
        got = next((f for f in sorted(work.glob("source.*")) if not f.name.endswith((".part", ".ytdl"))), None)
        if done.returncode != 0 or got is None:
            raise IngestError("the download failed: " + (done.stderr.strip().splitlines() or ["no file was written"])[-1][:200])
        sha, facts = _sha(got), probe(got)
        final_dir = base / sha[:16]
        final_dir.mkdir(exist_ok=True)
        final = final_dir / f"source{got.suffix}"
        if not final.exists():
            os.replace(got, final)                                          # the rename is the only moment a file appears under its final name
        ver = (info.get("_version") or {}).get("version") or _run([exe, "--version"], env, 30).stdout.strip() or "unknown"
        rec = {"asset_id": f"video-{sha[:16]}", "path": str(final), "sha256": sha, "bytes": final.stat().st_size, **facts,
               "provenance": {"url_redacted": redact(url), "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "extractor": info.get("extractor_key") or info.get("extractor"),
                              "title": info.get("title"), "uploader": info.get("uploader"), "license_note": info.get("license"), "tool": f"yt-dlp@{ver}"}}
        if name:
            rec["name"] = str(name)[:80]
        (final_dir / "provenance.json").write_text(json.dumps(rec, indent=1, sort_keys=True))
        index[ukey] = sha[:16]
        index_path.write_text(json.dumps(index))
        _ledger(ledger, rec, origin, False)
        return dict(rec, reused=False)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _ledger(ledger, rec: dict, origin: str, reused: bool) -> None:
    if ledger is None:
        return
    ledger.record({"piece": "video-ingest", "stage": "other", "studio": "local", "by": "captain" if origin == "user" else "agent", "output_hashes": [rec["sha256"]],
                   "reason": "reference clip ingested from " + rec["provenance"]["url_redacted"], "settings": {"reused": reused, "extractor": rec["provenance"]["extractor"], "tool": rec["provenance"]["tool"]}})
