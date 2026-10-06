"""The quick router: routine requests answered without a model call. A message is routed only when it matches a rule COMPLETELY and resolves to an existing item; compound, ambiguous and
unknown requests return None and go to the agent unchanged. English only. The subject resolves exact, then by a UNIQUE partial match (every word a prefix of a word of the name); a name shared
by a card and a session, or by several items, returns None (the surface is the user's to say)."""
import datetime
import os
import re

UNIQUE_ONLY = True
_POLITE = re.compile(r"^(?:please|kindly|hey|can you|could you|would you|will you|i want you to|go ahead and)\s+", re.I)
_COMPOUND = re.compile(r"(?:;|\n)|\b(?:and|then|also|after that|followed by)\s+(?:open|show|archive|unarchive|restore|pin|unpin|close|mark|read|summari[sz]e|list|create|research|what)\b", re.I)
_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_STATUS = {"done": "done", "complete": "done", "completed": "done", "finished": "done", "active": "active"}


def request_date(text: str, now=None):
    now = now or datetime.date.today()
    t = text.lower()

    def valid(y, m, d):
        try:
            return datetime.date(y, m, d).isoformat()
        except ValueError:
            return None
    if "day before yesterday" in t:
        return (now - datetime.timedelta(days=2)).isoformat()
    if "yesterday" in t:
        return (now - datetime.timedelta(days=1)).isoformat()
    if re.search(r"\btoday\b", t):
        return now.isoformat()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        return valid(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b", t)
    if m:
        return valid(int(m[3] or now.year), int(m[2]), int(m[1]))
    m = re.search(r"\b(\d{1,2})\s+([a-z]{3,9})\s*(\d{4})?\b", t)
    if m and m[2] in _MONTHS:
        return valid(int(m[3] or now.year), _MONTHS[m[2]], int(m[1]))
    m = re.search(r"\b([a-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})?\b", t)
    if m and m[1] in _MONTHS:
        return valid(int(m[3] or now.year), _MONTHS[m[1]], int(m[2]))
    return None


def _norm(text: str) -> str:
    t = re.sub(r"\s+", " ", text.strip())
    while True:
        n = _POLITE.sub("", t)
        if n == t:
            break
        t = n
    return re.sub(r"[\s?.!]+$", "", re.sub(r"\s+please$", "", t, flags=re.I))


def _words(s):
    return re.findall(r"[a-z0-9]+", s.lower())


def _matches(subject, names):
    sw = _words(subject)
    if not sw:
        return False
    nw = _words(names)
    return all(any(w.startswith(s) for w in nw) for s in sw)


def _resolve(subject, hint, state, allowed):
    """(surface, id) or None."""
    s = re.sub(r"^(?:the|my|that)\s+", "", subject.strip(), flags=re.I)
    m = re.search(r"\s+(card|session|chat)$", s, re.I)
    if m:
        hint = "card" if m[1].lower() == "card" else "session"
        s = s[:m.start()]
    if s.lower() in ("this", "current", "it", "this one"):
        sel = state.get("selected")
        if not sel or (hint and sel["kind"] != hint) or sel["kind"] not in allowed:
            return None
        return sel["kind"], sel["id"]
    if hint and hint not in allowed:
        return None
    cands = []
    for kind in ([hint] if hint else allowed):
        for item in state.get("cards" if kind == "card" else "sessions", []):
            name = item.get("title") if kind == "card" else item.get("name")
            cands.append((kind, item["id"], name or ""))
    exact = [c for c in cands if c[2].lower() == s.lower() or c[1].lower() == s.lower()]
    if exact:
        return (exact[0][0], exact[0][1]) if len(exact) == 1 else None
    part = [c for c in cands if _matches(s, c[2])]
    if len(part) == 1 or (part and not UNIQUE_ONLY):
        return part[0][0], part[0][1]
    return None


RULES = [
    (re.compile(r"^archive\s+(?P<s>.+)$", re.I), "archive", ("card",), None),
    (re.compile(r"^(?:unarchive|restore)\s+(?P<s>.+?)(?:\s+from\s+(?:the\s+)?archive)?$", re.I), "unarchive", ("card",), None),
    (re.compile(r"^mark\s+(?P<s>.+?)\s+(?:as\s+)?(?P<st>done|complete|completed|finished|active)$", re.I), "set_status", ("card",), None),
    (re.compile(r"^unpin\s+(?P<s>.+)$", re.I), "unpin", ("card",), None),
    (re.compile(r"^pin\s+(?P<s>.+)$", re.I), "pin", ("card",), None),
    (re.compile(r"^close\s+(?P<s>.+)$", re.I), "close", ("session",), None),
    (re.compile(r"^(?:open|show|switch to|go to)\s+(?P<s>.+)$", re.I), "open", ("card", "session"), None),
    (re.compile(r"^(?:read|summari[sz]e)\s+(?P<s>.+)$", re.I), "read", ("card", "session"), None),
]


def plan(text: str, state: dict, now=None):
    if os.environ.get("LAMPWAY_QUICK_ACTIONS") == "0":
        return None
    t = _norm(str(text))
    if not t or _COMPOUND.search(t):
        return None
    if re.match(r"^(?:what did we do|what happened|what have we done)\b", t, re.I):
        d = request_date(t, now)
        return {"action": "history", "date": d} if d else None
    m = re.match(r"^list\s+(?:my\s+|all\s+|the\s+)?(sessions|chats|cards)$", t, re.I)
    if m:
        return {"action": "list", "surface": "cards" if m[1].lower() == "cards" else "sessions"}
    for rx, action, allowed, _ in RULES:
        m = rx.match(t)
        if not m:
            continue
        hit = _resolve(m["s"], None, state, allowed)
        if hit is None:
            return None
        out = {"action": action, "surface": hit[0], "id": hit[1]}
        if action == "set_status":
            out["status"] = _STATUS[m["st"].lower()]
        return out
    return None
