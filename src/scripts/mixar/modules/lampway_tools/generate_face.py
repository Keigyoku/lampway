# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the island's Image and Video tabs say before Generate (facelift contract 08). No bpy, no arithmetic of price or
policy: the server's /app/generate/estimate answer says the price, whether it needs a click and whether a cap refuses
it; this turns that answer and the last /app/egress answer into words. The pump (ui/generate_pump.py) writes them into
the WindowManager, where the native media pane reads them (agent_ui_tabmedia.cc).

    estimate   ≈ $0.067 est.           dashed chip; "price unknown" when there is none (in the stop colour)
    cap_job    ≈ $0.07 of cap $1.00 per job            amber from 80 percent of the cap, red over it
    cap_session  session: $0.31 + 0.07 of $3.00
    route      openrouter.ai           the host the job goes to
    content    prompt only, no asset
    button     Generate, ≈ $0.07  |  Spend $0.40  |  Spend, price unknown  |  Generate (disabled, with the refusal)
    policy     the sentence of the user's click rule, the button's hover
"""

from .price_chips import money

HIGGSFIELD_PREFIX = "higgsfield/"
OFF = "{route} is off: switch it on in Privacy to let data leave"
WARN_AT = 0.8


def route_of(model: str) -> str:
    return "higgsfield" if str(model or "").startswith(HIGGSFIELD_PREFIX) else "openrouter"


def _route_row(route: str, egress):
    return next((r for r in (egress or {}).get("routes") or [] if r.get("id") == route), None)


def route_off(route: str, egress) -> bool:
    row = _route_row(route, egress)
    return row is not None and not row.get("enabled")


def ask(client, service: str, model: str, params: dict, references: int, egress):
    """The server's estimate for this request, or None. A route that is off asks nothing: the tab refuses on its own."""
    if route_off(route_of(model), egress):
        return None
    return client.generate_estimate(service, model, params, references)


def _fine(amount, unit) -> str:
    """$0.067 for an amount under ten cents (three places, no trailing zero), $0.40 above; credits as they are."""
    if (unit or "USD").upper() != "USD":
        return money(amount, unit)
    amount = float(amount)
    if amount < 0.1:
        text = f"{amount:.3f}".rstrip("0")
        return "$" + (text + "0" if len(text.split(".")[1]) < 2 else text)
    return f"${amount:.2f}"


def _cents(amount, unit) -> str:
    return money(amount, unit)


def _level(fill) -> str:
    return "over" if fill > 1.0 else "warn" if fill >= WARN_AT else "ok"


def _content(references: int) -> str:
    n = int(references or 0)
    return "prompt only, no asset" if n == 0 else f"prompt and {n} reference image{'s' if n != 1 else ''}"


def _policy_sentence(provider: str, policy: dict, amount, unit, needs_click: bool) -> str:
    click = (policy or {}).get("click") or "always"
    if click == "off":
        return f"Your policy: no click for {provider}; the caps still apply"
    if click == "always":
        return f"Your policy: every {provider} job waits for your click"
    line = _cents((policy or {}).get("above") or 0.0, unit)
    if amount is None:
        return f"Your policy: a click above {line}. An unknown price is never waved through: Spend asks you first"
    if needs_click:
        return f"Your policy: a click above {line}. This one is over it: Spend asks you first"
    return f"Your policy: a click above {line}. This one is under it: Generate sends it"


def face(model: str, answer, egress, references: int = 0) -> dict:
    route = (answer or {}).get("route") or route_of(model)
    row = _route_row(route, egress)
    out = {"route": (row.get("hosts") or [row.get("label") or route])[0] if row else "",
           "route_ok": not route_off(route, egress), "content": _content(references), "refusal": "",
           "last_run": (answer or {}).get("last_run") or ""}      # the results row's line (section 5), from the run log
    price = (answer or {}).get("price")
    amount = None if not price else float(price.get("amount"))
    unit = (price or {}).get("unit") or "USD"
    if price and price.get("kind") == "estimate":
        out.update(estimate=f"≈ {_fine(amount, unit)} est.", estimate_kind="estimate",
                   estimate_tip=f"An estimate ({price.get('source') or 'listed price'}), not read back: {price.get('basis') or ''}".rstrip(": "))
    elif price:
        out.update(estimate=f"{_fine(amount, unit)}, read back", estimate_kind="quote", estimate_tip="The price the provider quoted")
    else:
        why = (answer or {}).get("basis") or (f"Not asked while {route} is off" if not out["route_ok"] else "Lampway's server is not answering")
        out.update(estimate="price unknown", estimate_kind="unknown", estimate_tip=why + ": an unknown price is never waved through")
    policy = (answer or {}).get("policy") or {}
    job_cap, session_cap, spent = policy.get("job_cap"), policy.get("session_cap"), float(policy.get("spent") or 0.0)
    approx = "≈ " if out["estimate_kind"] == "estimate" else ""
    if answer is None:
        out.update(cap_job=f"caps not asked: {route} is off" if not out["route_ok"] else "caps unknown: the server is not answering",
                   cap_job_fill=0.0, cap_job_level="ok", cap_session="", cap_session_fill=0.0)
    else:
        if job_cap:
            fill = (amount or 0.0) / float(job_cap)
            said = f"{approx}{_cents(amount, unit)}" if amount is not None else "price unknown"
            out.update(cap_job=f"{said} of cap {_cents(job_cap, unit)} per job", cap_job_fill=fill, cap_job_level=_level(fill))
        else:
            out.update(cap_job="no per-job cap", cap_job_fill=0.0, cap_job_level="ok")
        add = f" + {float(amount):.2f}" if amount is not None and unit.upper() == "USD" else f" + {amount:g}" if amount is not None else ""
        if session_cap:
            fill = (spent + (amount or 0.0)) / float(session_cap)
            out.update(cap_session=f"session: {_cents(spent, unit)}{add} of {_cents(session_cap, unit)}", cap_session_fill=fill)
        else:
            out.update(cap_session=f"session: {_cents(spent, unit)} spent, no cap", cap_session_fill=0.0)
    needs_click = True if answer is None else bool(answer.get("needs_click"))
    out["policy"] = _policy_sentence(route, policy, amount, unit, needs_click) if answer is not None else \
        "An unknown price is never waved through: Spend asks you first"
    refused = (answer or {}).get("refused")
    if not out["route_ok"]:
        out.update(button="Generate", button_kind="refused", refusal=OFF.format(route=route))
    elif refused:
        out.update(button="Generate", button_kind="refused", refusal=refused, cap_job_level="over")
    elif needs_click:
        out.update(button=f"Spend {_cents(amount, unit)}" if amount is not None else "Spend, price unknown", button_kind="spend")
    else:
        number = f"{approx}{_cents(amount, unit)}" if amount is not None else "price unknown"
        out.update(button=f"Generate, {number}", button_kind="generate")
    return out


OWNERS = {"image_gen": "MixieMoodboardTabImageGenProps", "video_gen": "MixieMoodboardTabVideoGenProps"}


def refusal(context, owner_type: str):
    """The sentence Generate refuses with when the face computed for THIS tab (``owner_type``, the tab PropertyGroup's RNA
    identifier) says it is refused (route off, over a cap), else None. Another tab's Generate is never judged by it."""
    wm = getattr(context, "window_manager", None)
    if owner_type and getattr(wm, "lampway_gen_owner", "") == owner_type and getattr(wm, "lampway_gen_button_kind", "") == "refused":
        return getattr(wm, "lampway_gen_refusal", "") or "This generation is refused"
    return None


_AWAIT = {"known": None}


def await_card(approvals) -> None:
    """Spend was pressed: remember the approvals already waiting; the next new spend approval is the one it caused."""
    _AWAIT["known"] = {a.get("id") for a in approvals or []}


def next_card(approvals):
    """The new spend approval Spend caused (once), or None."""
    known = _AWAIT["known"]
    if known is None:
        return None
    for a in approvals or []:
        if a.get("id") not in known and a.get("state") == "pending" and (a.get("settings") or {}).get("unit") != "answer":
            _AWAIT["known"] = None
            return a
    return None
