# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The prompt library as a list (facelift contract 08): one row per template with its version and mean price; runs and
rating are the row's hover (the calm pass). No bpy: ``rows`` turns the server's /app/prompts and /app/prompts/stats
answers into what the list draws."""


def _price(mean_cost) -> str:
    if mean_cost is None:
        return "no runs yet"
    amount = float(mean_cost)
    if amount < 0.1:
        text = f"{amount:.3f}".rstrip("0")
        text = text + "0" if len(text.split(".")[1]) < 2 else text
        return f"≈ ${text}"
    return f"≈ ${amount:.2f}"


def rows(templates: list, stats: list) -> list:
    """[{id, title, version, media, runs, rating, price, hover}] in the library's order; stats are per ``id@version``."""
    by = {s.get("template"): s for s in stats or []}
    out = []
    for t in templates or []:
        s = by.get(f"{t['id']}@{t['version']}") or {}
        runs, rating, cost = int(s.get("runs") or 0), s.get("mean_rating"), s.get("mean_cost")
        if runs:
            rated = f"rated {rating:g} ({s.get('rated') or 0} rating{'s' if (s.get('rated') or 0) != 1 else ''})" if rating is not None else "not rated yet"
            billed = f", mean billed ${float(cost):.3f}" if cost is not None else ", no billed cost recorded"
            hover = f"{runs} run{'s' if runs != 1 else ''}, {rated}{billed}"
        else:
            hover = "No runs yet: its price shows after the first billed run"
        out.append({"id": t["id"], "title": t.get("title") or t["id"], "version": t["version"], "media": t.get("media") or "image",
                    "runs": runs, "rating": rating, "price": _price(cost if runs else None), "hover": hover})
    return out
