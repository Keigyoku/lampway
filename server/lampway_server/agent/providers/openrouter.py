"""OpenRouter as a model provider: OpenAI-compatible chat completions with tool calling and streaming, plus a hard
spend cap and a key that never leaves the Authorization header.

Budget (the hard cap): every request carries ``max_tokens``; every response's reported ``usage.cost`` is added to a
``SpendLedger`` shared by the main agent and the swarm; once the ledger is at or past its ceiling the next call is refused
BEFORE anything is sent. The key is read from ``OPENROUTER_API_KEY`` or from the file ``LAMPWAY_OPENROUTER_KEY_FILE``
names (a dotenv file or the bare key); it is held only here and redacted from errors and logs.
"""

import json
import logging
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
    """The key Connections resolves for ``openrouter`` (the environment, else the file LAMPWAY_OPENROUTER_KEY_FILE names - owner-only, C8 -
    else a key saved in Connections). The error names variables and the fix, never values. ``env`` is for tests and one-off callers."""
    from ... import connections as C
    hub = C.active() if env is None else C.Hub(C.active().state_dir, secrets_dir=C.active().secrets_dir, env=env)
    try:
        return C.secret_of(hub.credential("openrouter"))
    except C.Refused as exc:
        raise KeyMissing(f"no OpenRouter key ({exc}): set OPENROUTER_API_KEY, or LAMPWAY_OPENROUTER_KEY_FILE to an owner-only file holding "
                         "OPENROUTER_API_KEY=..., or connect it in Connections (the key is never read from settings.json)") from None


class _RedactingFilter(logging.Filter):
    def __init__(self, secret: str):
        super().__init__()
        self._secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            text = record.getMessage()
        except Exception:  # noqa: BLE001 - a malformed record is not ours to judge
            return True
        if self._secret in text or _KEY_SHAPE.search(text):       # untouched otherwise: formatters read record.args
            record.msg = redact(text, self._secret)
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
    """What this session has spent on OpenRouter, in USD as OpenRouter reports it; thread-safe. With a ``log_path`` the log file IS
    the ledger (one JSON line per paid call), so a child process pointed at the same file (LAMPWAY_SPEND_LOG) counts toward the same
    ceiling; a session lasts until the file is rotated (the launcher starts a fresh one)."""

    def __init__(self, ceiling_usd: float, log_path=None):
        self.ceiling_usd = float(ceiling_usd)
        self.log_path = Path(log_path) if log_path else None
        self._spent = 0.0
        self._by_label: dict = {}
        self._lock = threading.Lock()

    def _totals(self):
        if self.log_path is None:
            return self._spent, dict(self._by_label)
        spent, by_label = 0.0, {}
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0.0, {}
        for line in lines:
            try:
                row = json.loads(line)
                spent += float(row["cost_usd"])
                by_label[row["label"]] = by_label.get(row["label"], 0.0) + float(row["cost_usd"])
            except (ValueError, KeyError, TypeError):
                continue
        return spent, by_label

    @property
    def spent(self) -> float:
        with self._lock:
            return self._totals()[0]

    @property
    def by_label(self) -> dict:
        with self._lock:
            return self._totals()[1]

    def check(self) -> None:
        spent = self.spent
        if spent >= self.ceiling_usd:
            raise SpendCeilingReached(
                f"OpenRouter session spend ceiling reached (${spent:.2f} of ${self.ceiling_usd:.2f}); "
                "nothing was sent. Raise LAMPWAY_OPENROUTER_BUDGET_USD to continue.")

    def add(self, cost: float, label: str) -> None:
        with self._lock:
            if self.log_path is None:
                self._spent += float(cost)
                self._by_label[label] = self._by_label.get(label, 0.0) + float(cost)
                return
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:        # one line per paid call: when, who, how much
                fh.write(json.dumps({"t": time.time(), "label": label, "cost_usd": float(cost)}) + "\n")

    def __repr__(self) -> str:
        return f"SpendLedger(spent={self.spent:.4f}, ceiling={self.ceiling_usd:.2f})"


class OpenRouterProvider(OpenAICompatProvider):
    name = "openrouter"
    connection = "openrouter"

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
        error = chunk.get("error")
        if error:                                                  # a failure reported inside a 200 stream
            detail = error if isinstance(error, str) else f"{error.get('code', '')} {error.get('message', '')}".strip()
            raise RuntimeError(redact(f"OpenRouter reported an error in the stream: {detail}", self._api_key))
        usage = chunk.get("usage")
        if isinstance(usage, dict) and isinstance(usage.get("cost"), (int, float)):
            self.ledger.add(usage["cost"], self.label)

    def _http_error(self, status: int, detail: str) -> str:
        return redact(f"OpenRouter answered HTTP {status}: {detail}", self._api_key)
