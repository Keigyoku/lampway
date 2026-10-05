"""Keep OAuth and API secrets out of every log line.

Uvicorn's access logger writes the whole request line, and the ChatGPT sign-in callback's query carries the authorization
``code``, ``state`` and ``client_id``. The redaction runs when the log RECORD is made (a record factory), so it holds
whatever handlers or logging configuration uvicorn installs later. Sensitive query values and token-shaped strings
(a JWT, an ``sk-`` key) are replaced; the rest of the line is kept.
"""

import logging
import re

REDACTED = "[redacted]"
SENSITIVE = ("code", "state", "client_id", "id_token", "access_token", "refresh_token", "code_verifier", "token",
             "api_key", "key", "client_secret", "password")
_QUERY = re.compile(r"(?i)([?&](?:" + "|".join(SENSITIVE) + r")=)[^&\s\"'#]*")
_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
_SK = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")
_installed = False


def redact_text(text) -> str:
    out = _QUERY.sub(lambda m: m.group(1) + REDACTED, str(text))
    return _SK.sub(REDACTED, _JWT.sub(REDACTED, out))


def _clean(value):
    return redact_text(value) if isinstance(value, str) else value


def install() -> None:
    """Wrap the log record factory once: every record's message and arguments are redacted as it is created."""
    global _installed
    if _installed:
        return
    _installed = True
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        try:
            record.msg = _clean(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(_clean(a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: _clean(v) for k, v in record.args.items()}
        except Exception:  # noqa: BLE001 - a malformed record is not ours to judge
            pass
        return record

    logging.setLogRecordFactory(factory)
