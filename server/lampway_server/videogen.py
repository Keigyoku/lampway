"""Video generation and upscaling on OpenRouter's asynchronous videos API.

  GET  /api/v1/videos/models      the catalogue (29 models at the time of writing): supported_resolutions / aspect_ratios / durations /
                                  frame_images, generate_audio, upscale_factor / creativity, pricing_skus
  POST /api/v1/videos             submit -> {id, polling_url, status: pending}
  GET  polling_url                pending | in_progress | completed (unsigned_urls, usage.cost) | failed (error)
  GET  unsigned_urls[0]           the content; NOT presigned, the key rides in the Authorization header

Everything is checked BEFORE anything is sent: the request is validated against the model's own lists, priced from ``pricing_skus``
(an unknown price family refuses), and held to the spend ledger and a per-job cap. The ACTUAL billed cost (``usage.cost``) goes on the
ledger and is returned next to the estimate, so the estimate formulas are checked against what is billed. A job is never re-submitted
(a second submit is a second charge); one that does not finish raises and says so.

Seedance bills in video tokens: tokens ~ W x H x fps x seconds / 1024 at 24 fps; the rate is the SKU for the audio / video-input case.
"""

import base64
import hashlib
import io
import re
import time
from typing import Optional

import httpx

ORIGIN = "https://openrouter.ai"
API = ORIGIN + "/api/v1"
FPS = 24
MAX_REFERENCE_IMAGES = 9
MAX_INLINE_IMAGE_BYTES = 3_500_000      # the API refuses ~5 MB inline; base64 adds a third, so the raw cap stays under it
FALLBACK_EDGE = 2048


class VideoError(ValueError):
    pass


# ----------------------------------------------------------------------------------------------------- pricing
def _usd(skus: dict, key):
    try:
        return float(skus[key])
    except (KeyError, TypeError, ValueError):
        return None


def _short_edge(resolution: str):
    m = re.match(r"^(\d{3,4})p$", resolution or "")
    return int(m.group(1)) if m else None


def pixels(row: dict, resolution: str, aspect_ratio: str):
    """(width, height) for a resolution and aspect ratio: the model's own ``supported_sizes`` when it lists the shape, else computed
    from the short edge."""
    edge = _short_edge(resolution) or ({"1K": 1024, "2K": 2048, "4K": 2160}.get(resolution))
    if edge is None:
        return None
    try:
        a, b = (float(x) for x in (aspect_ratio or "16:9").split(":"))
    except ValueError:
        a, b = 16.0, 9.0
    for size in row.get("supported_sizes") or []:
        w, h = (int(x) for x in size.split("x"))
        if min(w, h) == edge and abs(w / h - a / b) < 0.02:
            return w, h
    if a >= b:
        return int(round(edge * a / b / 2) * 2), edge
    return edge, int(round(edge * b / a / 2) * 2)


def estimate(row: dict, p: dict) -> dict:
    """The cost of one job in USD from the model's pricing_skus. ``p``: resolution, duration, aspect_ratio, generate_audio, references
    (count of reference images), reference_video (bool), frames (count), and for an upscale: source_width, source_height,
    upscale_factor, creativity. ``known`` False (usd None) when no SKU family fits: nothing is guessed."""
    skus = row.get("pricing_skus") or {}
    dur = float(p.get("duration") or 0)
    res = p.get("resolution") or ""
    resk = res.lower()
    audio = p.get("generate_audio")
    if audio is None or not audio_controllable(row):
        audio = bool(row.get("generate_audio"))

    def done(usd, basis, **extra):
        floor = _usd(skus, "minimum_cents_per_generation")
        if floor is not None and usd is not None:
            usd = max(usd, floor / 100)
        return {"usd": usd, "basis": basis, "known": usd is not None, **extra}

    # an upscale: per megapixel-second of the OUTPUT
    if "cents_per_megapixel_second_precise" in skus:
        w, h, f = p.get("source_width"), p.get("source_height"), float(p.get("upscale_factor") or 0)
        if not (w and h and f and dur):
            return {"usd": None, "basis": "an upscale needs the source width, height, duration and the factor", "known": False}
        kind = "creative" if p.get("creativity") else "precise"
        mp = (w * f) * (h * f) / 1e6
        return done(mp * dur * _usd(skus, f"cents_per_megapixel_second_{kind}") / 100, f"cents_per_megapixel_second_{kind} x {mp:.2f} MP x {dur:g} s")
    # video tokens (Seedance)
    if any(k.startswith("video_tokens") for k in skus):
        wh = pixels(row, res, p.get("aspect_ratio") or "16:9")
        if wh is None or not dur:
            return {"usd": None, "basis": "tokens need a resolution and a duration", "known": False}
        tokens = wh[0] * wh[1] * FPS * dur / 1024
        order = []
        if p.get("reference_video"):
            order.append("video_tokens_with_video_input")
        order += [] if audio else ["video_tokens_without_audio"]
        order += [f"video_tokens_{resk}", "video_tokens"]
        key = next((k for k in order if k in skus), None)
        return done(tokens * _usd(skus, key), f"{key} x {tokens:,.0f} tokens ({wh[0]}x{wh[1]} x {FPS} fps x {dur:g} s / 1024)", tokens=tokens)
    # dollars per second
    aud = "with_audio" if audio else "without_audio"
    order = []
    if p.get("references"):
        order += [f"reference_duration_seconds_{resk}", "reference_duration_seconds"]
    order += [f"duration_seconds_{aud}_{resk}", f"duration_seconds_{resk}_{aud}", f"duration_seconds_{aud}", f"duration_seconds_{resk}",
              "duration_seconds"]
    if not p.get("frames") and not p.get("references"):
        order += [f"text_to_video_duration_seconds_{resk}", "text_to_video_duration_seconds"]
    key = next((k for k in order if k in skus), None)
    if key and dur:
        return done(_usd(skus, key) * dur, f"{key} x {dur:g} s")
    # cents per second
    for key in (f"cents_per_second_output_{resk}", "cents_per_second_output", f"cents_per_video_output_second_{resk}", "cents_per_video_output_second"):
        if key in skus and dur:
            extra = (_usd(skus, "cents_per_image_input") or 0) * (p.get("frames", 0) + p.get("references", 0))
            return done((_usd(skus, key) * dur + extra) / 100, f"{key} x {dur:g} s" + (" + image inputs" if extra else ""))
    return {"usd": None, "basis": f"no pricing family fits {sorted(skus)}", "known": False}


# -------------------------------------------------------------------------------------------------- validation
def audio_controllable(row: dict) -> bool:
    return row.get("generate_audio") is True


def audio_state(row: dict, params: dict) -> str:
    if not audio_controllable(row):
        return "always on (not controllable)"
    flag = params.get("generate_audio")
    return "model default" if flag is None else ("on" if flag else "off")


def takes_video_input(row: dict) -> bool:
    skus = row.get("pricing_skus") or {}
    return any("video_input" in k for k in skus) or any(t in row.get("id", "") for t in ("flux-video-edit", "flux-video-upscale", "aleph"))


def is_upscaler(row: dict) -> bool:
    return bool(row.get("upscale_factor"))


def validate(row: dict, p: dict) -> dict:
    """The request's parameters, checked against the model's own lists; a value it does not list is refused with what it lists."""
    out = {}
    mid = row.get("id", "the model")

    def listed(key, field, label):
        if p.get(key) is None:
            return
        allowed = row.get(field)
        if allowed and p[key] not in allowed:
            raise VideoError(f"{mid} does not take {label} {p[key]!r}; it takes {allowed}")
        out[key] = p[key]
    listed("resolution", "supported_resolutions", "resolution")
    listed("duration", "supported_durations", "duration")
    listed("aspect_ratio", "supported_aspect_ratios", "aspect ratio")
    if p.get("generate_audio") is not None and audio_controllable(row):
        out["generate_audio"] = bool(p["generate_audio"])
    # a model whose catalogue says generate_audio false/None has NO control: it renders whatever audio it renders and the API refuses an explicit
    # flag (HeyGen: "always renders an audio track; generate_audio cannot be set to false"), so the field is omitted entirely, never refused
    if p.get("seed") is not None:
        out["seed"] = int(p["seed"])
    frames = p.get("frame_images") or []
    if frames:
        takes = row.get("supported_frame_images") or []
        for f in frames:
            if f.get("frame_type") not in takes:
                raise VideoError(f"{mid} does not take a {f.get('frame_type')} (it takes {takes or 'no frame images'})")
        out["frame_images"] = frames
    videos = p.get("reference_videos") or []
    if videos and not takes_video_input(row):
        raise VideoError(f"{mid} does not take a source or reference video (Seedance 2.x, FLUX Video Edit, Runway Aleph and the upscaler do)")
    if videos:
        out["reference_videos"] = videos
    if is_upscaler(row):
        span = row["upscale_factor"]
        factor = p.get("upscale_factor")
        if not (isinstance(span, dict) and factor and span["min"] <= float(factor) <= span["max"]):
            raise VideoError(f"upscale_factor must be between {span['min']} and {span['max']}, not {factor!r}")
        if len(videos) != 1:
            raise VideoError(f"{mid} needs exactly one source video")
        out["upscale_factor"] = float(factor)
        creativity = p.get("creativity", 0)
        if creativity not in (0, 1):
            raise VideoError("creativity is 0 (precise) or 1 (creative)")
        out["creativity"] = int(creativity)
    return out


# ------------------------------------------------------------------------------------------------------- client
def _data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def _image_mime(data: bytes) -> str:
    from .imagegen import _sniff_mime
    return _sniff_mime(data)


def _video_mime(data: bytes) -> str:
    return "video/webm" if data[:4] == b"\x1aE\xdf\xa3" else "video/quicktime" if data[4:12] == b"ftypqt  " else "video/mp4"


def _facts(data: bytes, width: int, height: int, fmt: str) -> dict:
    return {"width": width, "height": height, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "format": fmt}


def fit_image(data: bytes, max_edge: Optional[int], max_bytes: int = MAX_INLINE_IMAGE_BYTES) -> tuple:
    """An image fitted to a model's limits: shrunk (never enlarged) so its LONG edge is at most ``max_edge`` (there is no gain in sending 3840 px to a
    768p model), the aspect ratio kept, and re-encoded as JPEG q92 when it is over the byte cap (quality then edge are stepped down, bounded).
    Returns ``(bytes, info)``: the original's and the sent file's dimensions, bytes and sha256, and whether anything changed."""
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise VideoError(f"an image input could not be read ({type(exc).__name__}): send a PNG or JPEG") from None
    fmt = img.format or "PNG"
    original = _facts(data, img.width, img.height, fmt)
    edge = max_edge or (FALLBACK_EDGE if len(data) > max_bytes else max(img.size))
    scale = min(1.0, edge / max(img.size))
    if scale >= 1.0 and len(data) <= max_bytes:
        return data, {"original": original, "sent": dict(original), "changed": False}
    work = img
    if scale < 1.0:
        work = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    rgb = work
    if work.mode in ("RGBA", "LA", "P"):
        rgba = work.convert("RGBA")
        rgb = Image.new("RGB", rgba.size, (255, 255, 255))
        rgb.paste(rgba, mask=rgba.split()[3])
    elif work.mode != "RGB":
        rgb = work.convert("RGB")
    out = data
    if scale < 1.0 and fmt in ("JPEG",) and len(data) <= max_bytes:
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=92)
        out = buf.getvalue()
    elif scale < 1.0 or len(data) > max_bytes:
        out = None
        for quality, shrink in ((92, 1.0), (85, 1.0), (78, 0.9), (70, 0.8), (60, 0.7), (50, 0.6)):
            cand = rgb if shrink == 1.0 else rgb.resize((max(1, round(rgb.width * shrink)), max(1, round(rgb.height * shrink))), Image.LANCZOS)
            buf = io.BytesIO()
            cand.save(buf, "JPEG", quality=quality)
            out, size = buf.getvalue(), cand.size
            if len(out) <= max_bytes:
                break
        if len(out) > max_bytes:
            raise VideoError(f"an image input is still {len(out) / 1e6:.1f} MB after fitting; the limit is {max_bytes / 1e6:.1f} MB")
        work = cand
    sent = Image.open(io.BytesIO(out))
    return out, {"original": original, "sent": _facts(out, sent.width, sent.height, sent.format or "JPEG"), "changed": True}


class VideoClient:
    def __init__(self, *, ledger, transport=None, key: Optional[str] = None, poll_s: float = 10.0, timeout_s: float = 1800.0,
                 max_job_usd: float = 2.0, base: str = API):
        self.ledger = ledger
        self._transport = transport
        self._key = key
        self.poll_s, self.timeout_s, self.max_job_usd, self.base = poll_s, timeout_s, max_job_usd, base.rstrip("/")
        self._models = None

    # -------------------------------------------------------------------- plumbing
    def _headers(self) -> dict:
        from .agent.providers.openrouter import REFERER, TITLE, resolve_api_key
        return {"Authorization": f"Bearer {self._key or resolve_api_key()}", "HTTP-Referer": REFERER, "X-Title": TITLE}

    def _http(self):
        return httpx.Client(transport=self._transport, timeout=120.0)

    def _redact(self, text: str) -> str:
        from .agent.providers.openrouter import redact
        return redact(text, self._key)

    # -------------------------------------------------------------------- catalogue
    def models(self) -> list:
        if self._models is None:
            with self._http() as client:
                resp = client.get(f"{self.base}/videos/models", headers=self._headers())
            if resp.status_code >= 400:
                raise VideoError(self._redact(f"the video catalogue answered HTTP {resp.status_code}: {resp.text[:300]}"))
            self._models = resp.json().get("data") or []
        return self._models

    def model(self, model_id: str) -> dict:
        row = next((m for m in self.models() if m["id"] == model_id), None)
        if row is None:
            raise VideoError(f"no video model {model_id!r}; the models are: {', '.join(sorted(m['id'] for m in self.models())[:40])}")
        return row

    # ------------------------------------------------------------------------ plan
    def _fit_inputs(self, row, clean, frames, ref_images):
        """Every image input fitted to the model: long edge <= the output resolution's, bytes <= the inline cap. Returns the fitted lists and the record."""
        wh = pixels(row, clean.get("resolution") or "", clean.get("aspect_ratio") or "16:9") if clean.get("resolution") else None
        edge = max(wh) if wh else None
        record, fframes, frefs = [], [], []
        for t, data in frames or []:
            fitted, info = fit_image(data, edge)
            fframes.append((t, fitted))
            record.append({"role": t, **info})
        for i, data in enumerate(ref_images or []):
            fitted, info = fit_image(data, edge)
            frefs.append(fitted)
            record.append({"role": f"reference_{i + 1}", **info})
        return fframes, frefs, record

    def _prepare(self, model_id, params, frames, ref_images, ref_videos, source: Optional[dict] = None):
        row = self.model(model_id)
        raw = dict(params or {})
        raw["frame_images"] = [{"frame_type": t} for t, _ in (frames or [])]
        raw["reference_videos"] = list(ref_videos or [])
        clean = validate(row, raw)
        price_in = dict(clean, frames=len(frames or []), references=len(ref_images or []), reference_video=bool(ref_videos))
        if source:
            price_in.update(source)
        est = estimate(row, price_in)
        return row, clean, est

    def _budget(self, est: dict, accept_unknown: bool) -> dict:
        remaining = max(0.0, self.ledger.ceiling_usd - self.ledger.spent)
        usd = est["usd"]
        return {"known": est["known"], "remaining_usd": round(remaining, 4), "per_job_cap_usd": self.max_job_usd,
                "within_budget": bool(est["known"] and usd <= self.max_job_usd and usd <= remaining)}

    def plan(self, model_id, prompt, params=None, frame_images=None, reference_images=None, reference_videos=None, source=None) -> dict:
        """A dry run: the validated parameters and the price, nothing sent."""
        try:
            row, clean, est = self._prepare(model_id, params, frame_images, reference_images, reference_videos, source)
        except VideoError as exc:
            return {"ok": False, "dry_run": True, "error": str(exc)}
        out = {"ok": True, "dry_run": True, "model": model_id, "params": {k: v for k, v in clean.items() if k not in ("frame_images", "reference_videos")},
               "audio": audio_state(row, clean), "inputs": self._fit_inputs(row, clean, frame_images, reference_images)[2],
               "estimate_usd": None if est["usd"] is None else round(est["usd"], 4), "basis": est["basis"], **self._budget(est, False)}
        if not est["known"]:
            out["warning"] = "the price cannot be estimated from this model's pricing_skus: a live run is refused"
        return out

    # -------------------------------------------------------------------- generate
    def generate(self, model_id, prompt, params=None, *, frame_images=None, reference_images=None, reference_videos=None, source=None,
                 label="video", accept_unknown_price=False) -> dict:
        row, clean, est = self._prepare(model_id, params, frame_images, reference_images, reference_videos, source)
        frame_images, reference_images, inputs = self._fit_inputs(row, clean, frame_images, reference_images)
        if not str(prompt or "").strip() and not is_upscaler(row):
            raise VideoError("a video needs a prompt")
        if not est["known"] and not accept_unknown_price:
            raise VideoError(f"the price of this job is unknown ({est['basis']}): refused; pass accept_unknown_price to run it anyway")
        self.ledger.check()
        if est["known"]:
            if est["usd"] > self.max_job_usd:
                raise VideoError(f"estimated ${est['usd']:.2f} is over the per-job cap of ${self.max_job_usd:.2f} ({est['basis']})")
            remaining = self.ledger.ceiling_usd - self.ledger.spent
            if est["usd"] > remaining:
                raise VideoError(f"estimated ${est['usd']:.2f} is more than the ${remaining:.2f} remaining of the session spend ceiling")
        body = {"model": model_id, "prompt": prompt}
        for key in ("duration", "resolution", "aspect_ratio", "generate_audio", "seed", "upscale_factor", "creativity"):
            if key in clean:
                body[key] = clean[key]
        if frame_images:
            body["frame_images"] = [{"type": "image_url", "image_url": {"url": _data_url(data, _image_mime(data))}, "frame_type": t}
                                    for t, data in frame_images]
        refs = [{"type": "image_url", "image_url": {"url": _data_url(d, _image_mime(d))}} for d in (reference_images or [])[:MAX_REFERENCE_IMAGES]]
        refs += [{"type": "video_url", "video_url": {"url": _data_url(v, _video_mime(v))}} for v in (reference_videos or [])]
        if refs and not frame_images:               # frame_images takes precedence and makes the request image-to-video
            body["input_references"] = refs
        elif refs:
            body["input_references"] = refs
        with self._http() as client:
            job = self._submit(client, body)
            final = self._wait(client, job)
            video, mime = self._download(client, final)
        cost = (final.get("usage") or {}).get("cost")
        actual = float(cost) if isinstance(cost, (int, float)) else None
        if actual is not None:
            self.ledger.add(actual, label)
        return {"video": video, "media_type": mime, "job_id": job["id"], "generation_id": final.get("generation_id") or job.get("generation_id"), "inputs": inputs, "model": model_id, "estimate_usd": est["usd"], "basis": est["basis"],
                "actual_usd": actual, "delta_usd": None if actual is None or est["usd"] is None else round(actual - est["usd"], 6),
                "tokens": est.get("tokens")}

    def _submit(self, client, body) -> dict:
        resp = client.post(f"{self.base}/videos", json=body, headers=self._headers())
        if resp.status_code >= 400:
            raise VideoError(self._redact(f"OpenRouter refused the video request (HTTP {resp.status_code}): {resp.text[:500]}"))
        job = resp.json()
        if not job.get("id") or not job.get("polling_url"):
            raise VideoError("OpenRouter accepted the request but returned no job id")
        return job

    def _url(self, url: str) -> str:
        return ORIGIN + url if url.startswith("/") else url

    def _wait(self, client, job) -> dict:
        deadline = time.monotonic() + self.timeout_s
        url = self._url(job["polling_url"])
        while True:
            resp = client.get(url, headers=self._headers())
            if resp.status_code >= 400:
                raise VideoError(self._redact(f"polling job {job['id']} answered HTTP {resp.status_code}: {resp.text[:300]}"))
            data = resp.json()
            status = data.get("status")
            if status == "completed":
                return data
            if status in ("failed", "cancelled", "expired"):
                raise VideoError(self._redact(f"the video job {status}: {data.get('error') or 'no reason given'}"))
            if time.monotonic() >= deadline:
                raise VideoError(f"job {job['id']} did not finish within {self.timeout_s:.0f} s (status {status}); it is NOT re-submitted: "
                                 "check it on OpenRouter before trying again")
            time.sleep(self.poll_s)

    def _download(self, client, final) -> tuple:
        urls = final.get("unsigned_urls") or []
        if not urls:
            raise VideoError("the job completed with no content URL")
        resp = client.get(self._url(urls[0]), headers=self._headers(), follow_redirects=True)
        if resp.status_code >= 400 or not resp.content:
            raise VideoError(self._redact(f"downloading the video answered HTTP {resp.status_code}"))
        return resp.content, resp.headers.get("content-type", "video/mp4").split(";")[0] or "video/mp4"
