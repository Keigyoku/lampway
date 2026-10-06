"""Handwriting into composer text (specs/mixar_docs/voice_handwriting.md): POST /api/v1/handwriting/recognize, the route the Client's handwriting_service calls
(multipart ``image``, optional ``hint`` = the composer's tail; reply data {text, confidence 0..1}; empty text is a normal answer).

Proven code first: the image is binarised and an image without ink is answered with empty text and NO model call; otherwise it is cropped to its strokes
(with a margin) before the reader sees it. The reader is a slot behind ``await read(png, hint) -> (text, confidence)``; the default is an OpenRouter vision
model on the shared spend ledger (label "handwriting"), chosen in Providers (``LAMPWAY_HANDWRITING_MODEL``, else the speech-to-text model's family). The
image is never stored and goes only to that provider."""

import base64
import io

import httpx

MAX_BYTES = 8 * 1024 * 1024
HINT_MAX = 500
INK_LEVEL = 128            # a pixel darker than this (0..255 luminance) is ink
INK_MIN_PIXELS = 20
PROMPT = ("Transcribe the handwriting in this image exactly. Reply with only the written words, no commentary. If nothing legible is written, reply "
          "with nothing.")


class NotAnImage(ValueError):
    pass


def ink(data: bytes):
    """(has ink, the image cropped to its strokes as PNG)."""
    from PIL import Image, UnidentifiedImageError
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise NotAnImage(f"not an image: {exc}") from None
    if im.mode in ("RGBA", "LA"):
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im.convert("RGBA"))
        im = bg
    g = im.convert("L")
    w, h = g.size
    px = g.load()
    xs, ys, n = [], [], 0
    step = max(1, max(w, h) // 1024)
    for y in range(0, h, step):
        for x in range(0, w, step):
            if px[x, y] < INK_LEVEL:
                xs.append(x); ys.append(y); n += 1
    if n * step * step < INK_MIN_PIXELS:
        return False, b""
    m = max(8, (max(xs) - min(xs)) // 20)
    box = (max(0, min(xs) - m), max(0, min(ys) - m), min(w, max(xs) + m + 1), min(h, max(ys) + m + 1))
    out = io.BytesIO()
    g.crop(box).save(out, "PNG")
    return True, out.getvalue()


async def recognize(data: bytes, hint: str, reader) -> dict:
    has, crop = ink(data)
    if not has:
        return {"text": "", "confidence": 0.0}
    text, conf = await reader.read(crop, (hint or "")[-HINT_MAX:])
    return {"text": (text or "").strip(), "confidence": round(float(conf), 3) if text else 0.0}


class OpenRouterReader:
    def __init__(self, api_key: str, model: str, ledger, *, transport=None):
        self._key, self.model, self.ledger, self._transport = api_key, model, ledger, transport

    def __repr__(self) -> str:
        return f"OpenRouterReader(model={self.model!r})"

    async def read(self, image_png: bytes, hint: str):
        from .agent.providers.openrouter import BASE_URL, REFERER, TITLE, redact
        self.ledger.check()
        content = [{"type": "text", "text": PROMPT + (f" The text before it reads: {hint!r}" if hint else "")},
                   {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image_png).decode()}}]
        body = {"model": self.model, "max_tokens": 512, "usage": {"include": True}, "messages": [{"role": "user", "content": content}]}
        async with httpx.AsyncClient(transport=self._transport, timeout=60.0) as client:
            resp = await client.post(f"{BASE_URL}/chat/completions", json=body, headers={"Authorization": f"Bearer {self._key}", "HTTP-Referer": REFERER, "X-Title": TITLE})
        if resp.status_code >= 400:
            raise RuntimeError(redact(f"the handwriting reader answered HTTP {resp.status_code}: {resp.text[:300]}", self._key))
        data = resp.json()
        cost = (data.get("usage") or {}).get("cost")
        if isinstance(cost, (int, float)):
            self.ledger.add(cost, "handwriting")
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            text = ""
        return text, (0.8 if text else 0.0)                 # the model reports no confidence: a fixed value for a non-empty reading [UNVERIFIED]


def default_reader(settings):
    import os
    from .agent.providers import spend_ledger
    from .agent.providers.openrouter import KeyMissing, resolve_api_key
    try:
        key = resolve_api_key()
    except KeyMissing:
        return None
    return OpenRouterReader(key, os.environ.get("LAMPWAY_HANDWRITING_MODEL") or settings.openrouter_stt_model, spend_ledger(settings))
