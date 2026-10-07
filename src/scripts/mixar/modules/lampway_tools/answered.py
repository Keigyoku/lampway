# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 04's calm pass: an answered question collapses to one line, "Which glass? Clear, you answered 14:30", and the
choices not taken sit behind one expander row ("2 other choices"). The expander is an action row whose value starts with
``PREFIX``: the island's action operator handles it here and never sends it to the agent. No bpy: the bubble is any object
with ``content``, ``text``, ``action_items`` and ``lampway_answered``."""

import json

PREFIX = "lampway_answered:"


def _question(bubble) -> str:
    text = (getattr(bubble, "content", "") or getattr(bubble, "text", "") or "").strip()
    first = text.splitlines()[0].strip() if text else ""
    return first if len(first) <= 160 else first[:157].rstrip() + "..."


def _set_text(bubble, value: str) -> None:
    if getattr(bubble, "content", ""):
        bubble.content = value
    else:
        bubble.text = value


def _expander(bubble, record: dict) -> None:
    bubble.action_items.clear()
    others = record["others"]
    if not others:
        return
    item = bubble.action_items.add()
    item.value = PREFIX + (getattr(bubble, "bubble_id", "") or "")
    item.label = "Hide other choices" if record["open"] else f"{len(others)} other choice{'' if len(others) == 1 else 's'}"
    if hasattr(item, "style"):
        item.style = "DEFAULT"         # a plain row: the primary flame belongs to a decision still waiting


def _draw(bubble, record: dict) -> None:
    line = f"{record['question']} {record['answer']}, you answered {record['at']}".strip()
    if record["open"]:
        line += "\nOther choices: " + ", ".join(record["others"])
    _set_text(bubble, line)
    _expander(bubble, record)


def collapse(bubble, chosen_value: str, clock: str) -> dict:
    """Record the answer on the bubble and draw it as one line (its choices replaced by the expander). Returns the record."""
    labels = [(a.value, a.label) for a in bubble.action_items]
    answer = next((label for value, label in labels if value == chosen_value), chosen_value)
    record = {"question": _question(bubble), "answer": answer, "at": clock,
              "others": [label for value, label in labels if value != chosen_value], "open": False}
    bubble.lampway_answered = json.dumps(record)
    _draw(bubble, record)
    return record


def toggle(bubble) -> bool:
    """Open or close the other choices of an answered bubble; False when the bubble is not one."""
    try:
        record = json.loads(getattr(bubble, "lampway_answered", "") or "")
    except ValueError:
        return False
    record["open"] = not record["open"]
    bubble.lampway_answered = json.dumps(record)
    _draw(bubble, record)
    return True
