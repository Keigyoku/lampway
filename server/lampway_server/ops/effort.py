"""The effort policy: efforts are medium | high | xhigh | max; max only when the latest request asks for it and the phrase is not negated just before it; a preferred max is capped to xhigh
otherwise; research or architecture wording gives xhigh, implementation or debugging high, default medium. English only (a port of the vendored function, with an English negation guard)."""
import re

EFFORTS = ("medium", "high", "xhigh", "max")
NEGATION_WINDOW = 45
_REQUEST = re.compile(r"\bmax(?:imum)?[\s-]+(?:effort|reasoning)\b|\b(?:effort|reasoning)\s*(?:[:=]|to)?\s*max\b|\buse\s+max\b", re.I)
_NEGATED = re.compile(r"\b(?:not|never|without|no)\b[^.!?;]{0,40}$", re.I)


def explicit_max(text: str = "") -> bool:
    value = str(text)
    for m in _REQUEST.finditer(value):
        before = value[max(0, m.start() - NEGATION_WINDOW): m.start()]
        if not _NEGATED.search(before):
            return True
    return False


def task_effort(request: str = "", preferred=None) -> str:
    if explicit_max(request):
        return "max"
    if preferred == "max":
        return "xhigh"
    if preferred in ("medium", "high", "xhigh"):
        return preferred
    if re.search(r"research|architecture|complex|in-depth|deep dive", request, re.I):
        return "xhigh"
    if re.search(r"implement|integration|develop|debug|refactor", request, re.I):
        return "high"
    return "medium"
