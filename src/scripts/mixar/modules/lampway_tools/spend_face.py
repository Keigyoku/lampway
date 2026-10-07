# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the spend card says (facelift contract 13). No bpy. One card for every spend that waits for a click: the Studios
panel and the status bar's waiting chip open it, and a generation or a chat plan that needs a click reaches it as a
server approval that waits there. The card is ``lampway.studio_confirm``'s popup; its Spend button is the only confirm.

    card(approval, spend_view)   the waiting card: price, its kind and source, who planned it, the caps as meters
                                 (the pending amount apart from what is used), the button carrying the number
    classify(message)            which state a refused confirm ended in
    state_row(state, approval, message)  one row per state: title, detail, the numbers, the fixes
"""

import re
import time

OPERATOR = "lampway.studio_confirm"
SOURCES = ("statusbar.py", "lampway_panels.py")     # the waiting chip, the Studios panel
GATE_NOTE = "Only your click spends. Enter does nothing here."
AGENT_ORIGIN = "planned by the agent, only your click spends"
PROVIDER_OF = {"openrouter": "openrouter", "higgsfield": "higgsfield", "hyper3d": "hyper3d"}


def _num(x) -> str:
    return f"{float(x):g}"


def _usd(approval) -> bool:
    return str((approval.get("settings") or {}).get("unit") or "credits").lower() == "usd"


def price_text(amount, usd: bool) -> str:
    return f"${float(amount):.2f}" if usd else f"{_num(amount)} credits"


def _row(spend_view, studio):
    provider = PROVIDER_OF.get(str(studio or ""), "studios")
    return next((r for r in (spend_view or {}).get("providers") or [] if r.get("provider") == provider), {})


def _meters(approval, spend_view, usd):
    row = _row(spend_view, approval.get("studio"))
    price = float(approval.get("price") or 0.0)
    spent = float(row.get("spent") or 0.0)
    fmt = (lambda v: f"${float(v):.2f}") if usd else _num
    job_cap, day_cap = row.get("job_cap"), row.get("day_cap")
    if job_cap:
        job = {"text": f"this job {fmt(price)} of {fmt(job_cap)}", "used": 0.0, "pending": price / float(job_cap), "used_tone": "muted"}
    else:
        job = {"text": "no per-job cap", "used": 0.0, "pending": 0.0, "used_tone": "muted"}
    if day_cap:
        used = spent / float(day_cap)
        session = {"text": f"spent today {fmt(spent)} + {fmt(price)} of {fmt(day_cap)}", "used": used,
                   "pending": price / float(day_cap), "used_tone": "stop" if used > 0.9 else "muted"}
    else:
        session = {"text": f"spent today {fmt(spent)}, no daily cap", "used": 0.0, "pending": 0.0, "used_tone": "muted"}
    return [job, session]


def card(approval: dict, spend_view, now=None) -> dict:
    usd = _usd(approval)
    price = float(approval.get("price") or 0.0)
    studio = str(approval.get("studio") or "Studio")
    if usd and price == 0.0:
        kind, shown, source = "unknown", "price set by the model", "The model sets the price; the bill reads it back afterwards"
        button = "Spend, price set by the model"
    elif usd:
        kind, shown, source = "estimate", price_text(price, True), "Estimated from the model listing, not read back"
        button = f"Spend {shown}"
    else:
        kind, shown, source = "quoted", price_text(price, False), f"Read back from {studio.capitalize()}"
        button = f"Spend {shown}"
    who = str(approval.get("requested_by") or "")
    origin = "planned by you" if who in ("user", "captain", "") else AGENT_ORIGIN
    settings = approval.get("settings") or {}
    uploads = settings.get("uploads")
    expired = approval.get("state") == "expired" or (now or time.time()) >= float(approval.get("expires") or 2e18)
    return {"title": approval.get("label") or "A spend", "origin": origin, "price": shown, "kind": kind, "source": source,
            "meters": _meters(approval, spend_view, usd),
            "uploads": f"uploads: {uploads}" if uploads else "uploads: not reported by the server",
            "button": button, "gate": GATE_NOTE, "expired": expired}


def classify(message: str) -> str:
    m = str(message or "")
    if "per-job cap" in m:
        return "over_job_cap"
    if "today's cap" in m or "day cap" in m or "session cap" in m:          # the server's ruling-5 refusal: "would pass today's cap"
        return "past_cap"
    if m.startswith("the price shown was"):
        return "price_changed"
    if "script cannot confirm" in m or "only the user can confirm" in m:
        return "agent_tried"
    if "expired" in m:
        return "expired"
    return "unknown"


def state_row(state: str, approval: dict, message: str) -> dict:
    usd = _usd(approval)
    if state == "over_job_cap":
        return {"state": state, "glyph": "LAMPWAY_GATE", "title": "Refused before sending: over the per-job cap", "detail": message,
                "fixes": ["Raise the per-job cap in Choices", "Plan a smaller job"], "button": ""}
    if state == "past_cap":
        return {"state": state, "glyph": "LAMPWAY_METER_OVER", "title": "Past today's cap",
                "detail": message + " (the day total is saved and resets at local midnight)",
                "fixes": ["Raise the day cap in Choices", "Wait for tomorrow: the total resets at local midnight"], "button": ""}
    if state == "price_changed":
        m = re.match(r"the price shown was ([0-9.]+)", message)
        new = float(m.group(1)) if m else None
        return {"state": state, "glyph": "LAMPWAY_COIN", "title": "The price changed: the old approval is void",
                "detail": message, "fixes": ["Spend at the new price", "Not now"],
                "button": f"Spend {price_text(new, usd)}" if new is not None else "", "price": new}
    if state == "agent_tried":
        return {"state": state, "glyph": "LAMPWAY_HAND", "title": "Agents can plan, never confirm", "detail": message,
                "fixes": ["Show the plan"], "button": ""}
    if state == "expired":
        return {"state": state, "glyph": "LAMPWAY_GATE", "title": "This quote expired", "detail": message,
                "fixes": ["Ask for the plan again so the price is read back fresh"], "button": ""}
    if state == "spent":
        return {"state": state, "glyph": "LAMPWAY_RECEIPT", "title": f"Spent: job {approval.get('job_id') or '?'}",
                "detail": "Its receipt was written before the request left; it is never resubmitted", "fixes": ["Show the job"], "button": ""}
    return {"state": "unknown", "glyph": "LAMPWAY_GATE", "title": f"This spend cannot go ahead: {message or 'no reason given'}",
            "detail": message or "no reason given", "fixes": ["Not now"], "button": ""}


RULE = {"over_job_cap": "REFUSED", "past_cap": "REFUSED", "expired": "REFUSED", "unknown": "REFUSED", "agent_tried": "AGENT",
        "spent": "SPENT"}


def rule(state: str) -> str:
    """The card's left rule for a state: accent while it waits (a changed price waits too), stop refused, agent, go spent."""
    return RULE.get(state, "WAITING")


def drawn_rows(card: dict) -> list:
    """[(element, text)] for the drawn card (layout.mixar_spend, interface_mixar_spend_card.cc): a price packs its kind and
    a meter its used part, pending part and whether the used part is hot, after \\x1f."""
    rows = [("TITLE", card["title"]), ("LINE", card["origin"]), ("PRICE", f"{card['price']}\x1f{card['kind']}"),
            ("LINE", card["source"])]
    for m in card["meters"]:
        rows.append(("METER", f"{m['text']}\x1f{m['used']:.4f}\x1f{m['pending']:.4f}\x1f{1 if m['used_tone'] == 'stop' else 0}"))
    rows.append(("LINE", card["uploads"]))
    return rows
