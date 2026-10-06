"""The title policy: a session opened by an agent needs a descriptive title; placeholders are refused with the fix."""
import re

AGENTS = r"(?:claude|codex|opencode|shell|agent|kimi)"
_PLACEHOLDER = re.compile(rf"^(?:(?:untitled|new)\s*(?:conversation|chat|session|task|{AGENTS})?|(?:conversation|chat|session|task)|{AGENTS})\s*#?\s*\d*$", re.I)
FIX = "choose a descriptive title: 2 to 5 words naming the task"


class TitleError(ValueError):
    pass


def check_title(title) -> str:
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    if not t or not re.search(r"[A-Za-z]", t) or _PLACEHOLDER.match(t):
        raise TitleError(f"{t!r} is not a usable title: {FIX}")
    return t
