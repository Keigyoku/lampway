# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What a price chip says (DESIGN.md 8, facelift contracts 04 and 13). No bpy. Each kind of number has its own words and
its own shape, so an estimate can never be read as a quote:

    estimate   ≈ $0.10 est., openrouter.ai              dashed outline
    quote      13.5 credits, read back from Tripo 14:32  solid outline, mono
    spent      $0.05 billed                              filled, the receipt glyph
    local      local, no cost                            the lamp glyph (only money is a chip: the words are its hover)
"""

GLYPH = {"estimate": "", "quote": "", "spent": "LAMPWAY_RECEIPT", "local": "LAMPWAY_LAMP"}


def money(amount, unit) -> str:
    amount = float(amount or 0.0)
    if (unit or "USD").upper() == "USD":
        return f"${amount:.2f}"
    return f"{amount:g} {unit}"


def _clock(at) -> str:
    """'14:32' from an ISO time; empty when there is none."""
    text = str(at or "")
    return text[11:16] if len(text) >= 16 and text[10] in "T " else ""


def chip(step: dict, hosts: dict = None):
    """The chip of a plan step ({price: {kind, amount, unit, source, at}, runs_where}), or None when it has nothing to say.
    ``hosts`` maps a route id to the host the step's data would go to."""
    price = step.get("price") or {}
    kind = price.get("kind") or ""
    where = step.get("runs_where") or ""
    host = (hosts or {}).get(where, "")
    if kind == "estimate":
        text = "≈ " + money(price.get("amount"), price.get("unit")) + " est." + (f", {host}" if host else "")
        tip = "An estimate Lampway computed; the provider's own quote comes before any spend"
    elif kind == "quote":
        source = price.get("source") or host or "the provider"
        text = f"{money(price.get('amount'), price.get('unit'))}, read back from {source}" + (f" {_clock(price.get('at'))}" if _clock(price.get("at")) else "")
        tip = "The price the provider quoted"
    elif kind == "spent":
        text = money(price.get("amount"), price.get("unit")) + " billed"
        tip = "On the ledger"
    elif where == "local":
        kind, text, tip = "local", "local, no cost", "Runs on this machine; nothing is spent"
    else:
        return None
    return {"kind": kind, "text": text, "tooltip": tip, "glyph": GLYPH[kind]}
