"""OpenRouter as a model provider: OpenAI-compatible chat completions with tool calling and streaming, plus a hard
spend cap and a key that never leaves the Authorization header.

Budget (the hard cap): every request carries ``max_tokens``; every response's reported ``usage.cost`` is added to a
``SpendLedger`` shared by the main agent and the swarm; once the ledger is at or past its ceiling the next call is refused
BEFORE anything is sent. The key is read from ``OPENROUTER_API_KEY`` or from the file ``LAMPWAY_OPENROUTER_KEY_FILE``
names (a dotenv file or the bare key); it is held only here and redacted from errors and logs.
"""

import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import httpx

from .openai_compat import OpenAICompatProvider

BASE_URL = "https://openrouter.ai/api/v1"
REFERER = "https://github.com/Keigyoku/lampway"
TITLE = "Lampway"
_KEY_SHAPE = re.compile(r"sk-or-v1-[A-Za-z0-9_\-]+")
REDACTED = "[redacted]"


class KeyMissing(RuntimeError):
    pass


class SpendCeilingReached(RuntimeError):
    pass


def redact(text, *secrets) -> str:
    """``text`` with every given secret and anything shaped like an OpenRouter key replaced."""
    out = str(text)
    for secret in secrets:
        if secret:
            out = out.replace(secret, REDACTED)
    return _KEY_SHAPE.sub(REDACTED, out)


def resolve_api_key(env=None) -> str:
    """The key from the environment, else from the file LAMPWAY_OPENROUTER_KEY_FILE names. The error names variables, never values."""
    env = os.environ if env is None else env
    if env.get("OPENROUTER_API_KEY"):
        return env["OPENROUTER_API_KEY"].strip()
    ref = env.get("LAMPWAY_OPENROUTER_KEY_FILE")
    if ref:
        try:
            text = Path(ref).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise KeyMissing(f"LAMPWAY_OPENROUTER_KEY_FILE does not name a readable file ({type(exc).__name__}); "
                             "set OPENROUTER_API_KEY or point it at a file holding OPENROUTER_API_KEY=...") from None
        for line in text.splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "OPENROUTER_API_KEY":
                return value.strip().strip("\"'")
        bare = text.strip()
        if bare and "\n" not in bare and "=" not in bare:
            return bare
    raise KeyMissing("no OpenRouter key: set OPENROUTER_API_KEY, or LAMPWAY_OPENROUTER_KEY_FILE to a file holding "
                     "OPENROUTER_API_KEY=... (the key is never read from settings.json)")


class _RedactingFilter(logging.Filter):
    def __init__(self, secret: str):
        super().__init__()
        self._secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage(), self._secret)
        record.args = ()
        return True


_installed: set = set()


def install_log_redaction(secret: str) -> None:
    """Redact the key (and key-shaped strings) from every log record that passes through any handler."""
    if secret in _installed:
        return
    _installed.add(secret)
    flt = _RedactingFilter(secret)
    logging.getLogger().addFilter(flt)
    for handler in logging.getLogger().handlers:
        handler.addFilter(flt)
    logging.setLogRecordFactory(_factory_with(flt, logging.getLogRecordFactory()))


def _factory_with(flt, previous):
    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        flt.filter(record)
        return record
    return factory


class SpendLedger:
    """What this server session has spent on OpenRouter, in USD as OpenRouter reports it; thread-safe."""

    def __init__(self, ceiling_usd: float, log_path=None):
        self.ceiling_usd = float(ceiling_usd)
        self.log_path = Path(log_path) if log_path else None
        self.spent = 0.0
        self.by_label: dict = {}
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            if self.spent >= self.ceiling_usd:
                raise SpendCeilingReached(
                    f"OpenRouter session spend ceiling reached (${self.spent:.2f} of ${self.ceiling_usd:.2f}); "
                    "nothing was sent. Raise LAMPWAY_OPENROUTER_BUDGET_USD to continue.")

    def add(self, cost: float, label: str) -> None:
        with self._lock:
            self.spent += float(cost)
            self.by_label[label] = self.by_label.get(label, 0.0) + float(cost)
            if self.log_path is not None:                       # one line per paid call: when, who, how much
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"t": time.time(), "label": label, "cost_usd": float(cost)}) + "\n")

    def __repr__(self) -> str:
        return f"SpendLedger(spent={self.spent:.4f}, ceiling={self.ceiling_usd:.2f})"


class OpenRouterProvider(OpenAICompatProvider):
    name = "openrouter"

    def __init__(self, model: str, api_key: str, ledger: SpendLedger, *, max_tokens: int = 4096, label: str = "main",
                 base_url: str = BASE_URL, transport=None, **kw):
        super().__init__(base_url, model, api_key, transport=transport, **kw)
        self.ledger = ledger
        self.max_tokens = int(max_tokens)
        self.label = label
        install_log_redaction(api_key)

    def __repr__(self) -> str:
        return f"OpenRouterProvider(model={self.model!r}, label={self.label!r})"

    def _extra_body(self) -> dict:
        return {"max_tokens": self.max_tokens, "usage": {"include": True}}

    def _extra_headers(self) -> dict:
        return {"HTTP-Referer": REFERER, "X-Title": TITLE}

    def _before_request(self) -> None:
        self.ledger.check()

    def _on_chunk(self, chunk: dict) -> None:
        usage = chunk.get("usage")
        if isinstance(usage, dict) and isinstance(usage.get("cost"), (int, float)):
            self.ledger.add(usage["cost"], self.label)

    def _http_error(self, status: int, detail: str) -> str:
        return redact(f"OpenRouter answered HTTP {status}: {detail}", self._api_key)
