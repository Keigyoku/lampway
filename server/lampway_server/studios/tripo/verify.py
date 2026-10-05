# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The "verify everything, right before Generate" checks of tripo_image.py and tripo_mesh.py (shelf, 2026-10-04), lifted out of the
# browser code unchanged in meaning so they can be tested against the owner's own recorded dry runs. Each returns a list of
# problems; an empty list means the page shows exactly what was asked for. The owner's hard rules they encode: a reload resets
# settings, so EVERY setting is read back; maximum value per generation (4 images at 4K, 4 meshes at the topology's top
# polycount); a price that is not the expected one refuses.

import re


def image_count_refusal(count):
    return None if str(count) == "4" else "the captain: never fewer than 4 per generation"


def image_problems(st, *, model, aspect, count, no_4k, prompt, n_refs, n_ref_thumbs):
    bad = []
    if model not in (st["model"] or ""): bad.append(f"model reads {st['model']!r}")
    if st["aspects"].get(aspect) != "on" or sum(v == "on" for v in st["aspects"].values()) != 1: bad.append(f"aspect state {st['aspects']}")
    if st["counts"].get(count) != "on" or sum(v == "on" for v in st["counts"].values()) != 1: bad.append(f"count state {st['counts']}")
    if st["fourk"] != ("false" if no_4k else "true"): bad.append(f"4K switch reads {st['fourk']}")
    if st["prompt"].strip() != prompt: bad.append("prompt text differs")
    if n_refs and n_ref_thumbs < n_refs: bad.append(f"{n_refs} reference(s) uploaded, {n_ref_thumbs} thumbnail(s) seen")
    live = [x for x in st["price"] if not x["struck"]]
    if not live or any(x["v"] != 0 for x in live): bad.append(f"price is not free: {st['price']}")
    return bad


def mesh_problems(rec, *, polycount, topology, expect_price, smart_mesh_on):
    """``rec`` is the run record the driver builds while it sets the page up (the fields tripo_mesh.py writes to run.json)."""
    bad = []
    topo, st, panel = rec["topology_buttons"], rec["generations_state"], rec["panel_text"]
    if not smart_mesh_on and "Topology" not in panel: bad.append("Smart Mesh mode not confirmed")
    if sorted(rec["slot_map"]) != ["Back", "Front", "Left", "Right"]: bad.append("Multi-View slots not mapped")
    if rec["thumbnails_seen"] < 4: bad.append(f"{rec['thumbnails_seen']} of 4 view thumbnails present")
    if polycount != rec["polycount_max_shown"]:
        bad.append(f"polycount {polycount} is not the maximum {rec['polycount_max_shown']} for {topology} (the captain: maximum value per generation)")
    if rec["polycount_read_back"].replace(",", "") != polycount or (rec["polycount_slider"] or "/").split("/")[0] != polycount:
        bad.append(f"polycount reads {rec['polycount_read_back']} / slider {rec['polycount_slider']}")
    if not [t for t in topo if topology in t["t"] and _selected(t)]:
        bad.append(f"{topology} not shown selected: {topo}")
    if st.get("4") != "on" or sum(v == "on" for v in st.values()) != 1: bad.append(f"generations state {st}")
    if "P2.0" not in panel: bad.append("AI model P2.0 not shown")
    price = re.findall(r"(\d+)", rec["generate_button"])
    if price != [expect_price]: bad.append(f"price reads {rec['generate_button']!r}, expected {expect_price}")
    return bad


def _selected(button):
    """A topology button is selected when its state says so, or it carries the selected styling itself. Measured on the
    recorded dry run: an UNselected button's class string still contains 'purple' (the Tailwind variant text
    'data-[state=on]:border-purple-1'), which the shelf's plain substring test took for selected - so only classes that are
    not a data-/hover-/enabled- variant count."""
    if button["st"] in ("on", "true"):
        return True
    return any("purple" in c and not c.startswith(("data-", "hover:", "enabled:", "disabled:")) for c in (button["cls"] or "").split())


def region_refusal(approved):
    return None if approved else "exact-region substitution needs the captain's approval flag"


# ---- the Texture + PBR driver (tripo_texture.py), tested against the owner's recorded texture dry run

def texture_problems(st, *, res, remove_lighting, expect_price):
    """``st`` is the Texture panel as PANEL_JS reads it back: {remove_lighting: 'true'|'false'|None, res: [{t, on|state}],
    button: 'Generate Texture <price>', disabled}. Every requested setting must read back, and the price must be the expected one."""
    bad = []
    want = "true" if remove_lighting else "false"
    if (st.get("remove_lighting") or "") != want:
        bad.append(f"Remove Lighting reads {st.get('remove_lighting')!r}, wanted {want}")
    rows = st.get("res") or []
    on = [r["t"] for r in rows if r.get("on") is True or r.get("state") == "on"]
    if on != [res]:
        bad.append(f"resolution {res} not the one selected (selected: {on or 'none'})")
    bad += _button_problems(st, expect_price, "Texture")
    return bad


def pbr_problems(st, *, expect_price):
    return _button_problems(st, expect_price, "PBR")


def _button_problems(st, expect_price, kind):
    bad = []
    button = st.get("button") or ""
    if not button:
        bad.append(f"no Generate {kind} button read back")
    else:
        digits = re.findall(r"(\d+)\s*$", button)
        if not digits or int(digits[0]) != int(expect_price):
            bad.append(f"price reads {button!r}, expected {expect_price}")
    if st.get("disabled"):
        bad.append("the Generate button is disabled")
    return bad


def texturing_last_refusal(history):
    """Texturing comes LAST: the selected model's History must hold a Smart UV step (the texture fills its islands; any
    geometry or UV step after a texture discards it). ``history`` rows: {stamp, icon}."""
    if any(str(h.get("icon") or "").endswith(":uv") or "uv" in str(h.get("icon") or "").split(":")[-1] for h in history or []):
        return None
    return "texturing-last guard: no Smart UV step in this model's History"
